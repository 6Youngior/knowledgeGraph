"""Evidence-backed research views, temporal audits and portable research notes.

The text below describes graph queries. It does not ask a model to invent
financial conclusions, assign influence scores or predict prices.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from graph_store import read_json


ROLE_LABELS = {"direct": "直接研发", "adaptation": "硬件适配", "distribution": "云服务接入"}
SOURCE_LABELS = {"official_news": "官方公告", "official_blog": "官方发布", "official_docs": "产品文档",
                 "exchange": "交易所资料", "exchange_filing": "交易所文件", "news": "媒体报道",
                 "code_repository": "官方代码仓库", "company_profile": "公司资料"}


def validate_cutoff(value):
    if value:
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("研究截止日期必须是有效的 YYYY-MM-DD 日期") from exc
    return value


def all_paths(stock):
    return stock.get("paths", [stock["path"]])


class ResearchService:
    def __init__(self, store, market=None):
        self.store = store
        self.market = market

    def _excluded(self, event, visible, current, as_of):
        visible_ids = {s["id"] for s in visible}
        current_ids = {s["id"] for s in current}
        excluded = []
        if as_of:
            for stock in current:
                if stock["id"] not in visible_ids:
                    dates = [p.get("available_from") for p in all_paths(stock)]
                    available = min((d for d in dates if d), default=None)
                    blocking = [e for p in all_paths(stock) for e in p["edges"]
                                if self.store.edge_view(e, as_of) is None]
                    uncertain = any(not any(self.store.sources.get(sid, {}).get("published_at")
                                            for sid in edge.get("source_ids", [])) for edge in blocking)
                    reason = ("关联路径的部分来源未核实发布日期。" if uncertain else
                              f"已有资料最早在 {available} 形成完整路径，晚于所选日期。" if available else
                              "关联路径的部分来源缺少日期记录。")
                    excluded.append({"id": stock["id"], "label": stock["company_name"], "symbol": stock["symbol"],
                                     "reason_code": "not_yet_disclosed",
                                     "time_basis": "unverified_publication" if uncertain else "publication",
                                     "available_from": available,
                                     "reason": reason})
        # Industry memberships support a negative example, never a stock path.
        model_id = self.store.research_focus(event)
        reference_companies = {e["target"] for e in self.store._out(model_id, "DEVELOPED_BY", as_of)}
        industries = {e["target"] for e in self.store._out(model_id, "BELONGS_TO", as_of)}
        for company_id in reference_companies:
            industries.update(e["target"] for e in self.store._out(company_id, "BELONGS_TO", as_of))
        for company in sorted(self.store.nodes.values(), key=lambda n: n["id"]):
            if company["type"] != "Company" or company["id"] in reference_companies:
                continue
            membership = self.store._out(company["id"], "BELONGS_TO", as_of)
            shared = [e for e in membership if e["target"] in industries]
            if not shared:
                continue
            for listing in self.store._out(company["id"], "LISTED_AS", as_of):
                stock = self.store.nodes[listing["target"]]
                if stock["id"] in current_ids:
                    continue
                excluded.append({"id": stock["id"], "label": company["label"],
                                 "symbol": stock.get("properties", {}).get("symbol", stock["label"]),
                                 "reason_code": "industry_only",
                                 "source_ids": sorted({s for e in shared for s in e.get("source_ids", [])}),
                                 "reason": "同属一个行业，当前未收集到具体的研发、适配或云接入关系。"})
        return excluded

    def detail(self, event_id, as_of=None):
        validate_cutoff(as_of)
        event = self.store.event(event_id)
        model = self.store.nodes[self.store.research_focus(event)]
        current = self.store.related_stocks(event_id)
        stocks = self.store.related_stocks(event_id, as_of)
        paths = [p for s in stocks for p in all_paths(s)]
        source_ids = sorted({sid for p in paths for e in p["edges"] for sid in e.get("source_ids", [])})
        roles = []
        for group, label in ROLE_LABELS.items():
            members = [s for s in stocks if group in s.get("relation_groups", [s["relation_group"]])]
            roles.append({"group": group, "label": label, "count": len(members), "symbols": [s["symbol"] for s in members]})
        active_roles = [r for r in roles if r["count"]]
        excluded = self._excluded(event, stocks, current, as_of)
        max_hops = max((len(p["edges"]) for p in paths), default=0)
        findings = []
        if stocks:
            examples = "；".join(r["label"] + "：" + "、".join(s["company_name"] for s in stocks
                                  if r["group"] in s.get("relation_groups", [s["relation_group"]])) for r in active_roles)
            findings.append({"id": "roles", "kind": "derived", "title": f"{len(stocks)} 只关联证券",
                             "text": f"{examples}。",
                             "source_ids": source_ids})
            findings.append({"id": "fusion", "kind": "derived", "title": "引用来源",
                             "text": f"{len(source_ids)} 条来源支持当前 {len(paths)} 条路径；点击关系可查看原句和出处。",
                             "source_ids": source_ids})
        else:
            findings.append({"id": "empty", "kind": "boundary", "title": "暂无关联证券",
                             "text": "截至所选日期，已收集资料尚未形成完整的证券路径。", "source_ids": []})
        developer_edges = self.store._out(model["id"], "DEVELOPED_BY", as_of)
        developer_symbols = [s for s in stocks if "direct" in s.get("relation_groups", [s["relation_group"]])]
        if developer_edges and not developer_symbols:
            developers = "、".join(self.store.nodes[e["target"]]["label"] for e in developer_edges)
            findings.append({"id": "developer", "kind": "boundary", "title": "研发方暂无证券映射",
                             "text": f"研发方{developers}在当前资料中没有对应的上市证券。",
                             "source_ids": sorted({s for e in developer_edges for s in e.get("source_ids", [])})})
        later_listings = [s for s in stocks if s.get("listed_at_event") is False]
        if later_listings:
            names = "、".join(s["company_name"] for s in later_listings)
            findings.append({"id": "listing", "kind": "boundary", "title": "事件发生时尚未上市",
                             "text": f"{names}的上市日期晚于事件日期，没有该时点的股票行情。",
                             "source_ids": sorted({sid for s in later_listings for sid in s["source_ids"]})})
        if any(e["reason_code"] == "industry_only" for e in excluded):
            findings.append({"id": "industry", "kind": "boundary", "title": "只有行业分类的候选",
                             "text": "这些公司与研究对象同属一个行业，当前尚无具体研发、适配或云接入资料。",
                             "source_ids": sorted({s for e in excluded if e["reason_code"] == "industry_only" for s in e.get("source_ids", [])})})
        later = [e for e in excluded if e["reason_code"] == "not_yet_disclosed"]
        if as_of:
            findings.append({"id": "time", "kind": "boundary", "title": f"截至 {as_of}：{len(stocks)} 只关联证券",
                             "text": f"另有 {len(later)} 只证券的关联资料在该日期之后公开，或尚未核实发布日期。",
                             "source_ids": []})
        milestones = defaultdict(list)
        for stock in current:
            dates = [p.get("available_from") for p in all_paths(stock)]
            first = min((d for d in dates if d), default=None)
            if first:
                milestones[first].append(stock["symbol"])
        temporal = {"cutoff": as_of, "current_count": len(current), "visible_count": len(stocks),
                    "excluded_count": len(later),
                    "milestones": [{"date": day, "title": f"新增 {len(symbols)} 只证券的资料记录", "symbols": sorted(symbols)}
                                   for day, symbols in sorted(milestones.items())]}
        samples = read_json(self.store.data_dir / "extraction_samples.json", [])
        if isinstance(samples, dict):
            samples = samples.get("samples", [])
        updates = []
        for sample in samples:
            relations = sample.get("extraction", {}).get("relations", [])
            if any(model["id"] in (r.get("source"), r.get("target")) for r in relations):
                updates.append({key: sample.get(key, "") for key in ("id", "title", "document_id")})
        coverage = {"path_count": len(paths), "source_count": len(source_ids), "max_hops": max_hops,
                    "source_types": sorted({self.store.sources[s].get("source_type", "other") for s in source_ids if s in self.store.sources})}
        return {"question": "涉及哪些上市公司，依据是什么，相关资料在当时是否已公开？",
                "event_id": event_id, "as_of": as_of,
                "headline": f"{model['label']} · {len(stocks)} 只关联证券 · {len(active_roles)} 类产业角色",
                "findings": findings, "roles": roles, "excluded": excluded, "temporal": temporal,
                "coverage": coverage, "updates": updates}

    def overview(self):
        events = []
        for event in self.store.events.values():
            detail = self.detail(event["id"])
            historical_count = len(self.store.related_stocks(event["id"], event["date"]))
            events.append({"id": event["id"], "title": event["title"], "date": event.get("event_at", event["date"]),
                           "model": self.store.nodes[self.store.research_focus(event)]["label"],
                           "stock_count": detail["temporal"]["current_count"],
                           "role_counts": {r["group"]: r["count"] for r in detail["roles"]},
                           "source_count": detail["coverage"]["source_count"], "max_hops": detail["coverage"]["max_hops"],
                           "summary": detail["findings"][0]["text"],
                           "historical_stock_count": historical_count,
                           "temporal_summary": f"事件日：{historical_count} 只；全部已收集资料：{detail['temporal']['current_count']} 只。"})
        source_types = Counter(s.get("source_type", "other") for s in self.store.sources.values())
        dates = sorted(e["date"][:10] for e in events if e.get("date"))
        return {"events": events, "stats": self.store.stats(),
                "coverage": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None,
                             "source_types": [{"type": t, "label": SOURCE_LABELS.get(t, t), "count": c}
                                              for t, c in source_types.items()],
                             "models": len({self.store.research_focus(e) for e in self.store.events.values()}),
                             "markets": sorted({n.get("properties", {}).get("market", "") for n in self.store.nodes.values()
                                                if n["type"] == "Stock"} - {""})}}

    def brief(self, event_id, as_of=None):
        detail = self.detail(event_id, as_of)
        event = self.store.event(event_id)
        stocks = self.store.related_stocks(event_id, as_of)
        title = f"{event['title']} · 研究简报"
        lines = [f"# {title}", "", f"研究问题：{detail['question']}", "",
                 f"研究范围：截至 {as_of} 的已公开资料。" if as_of else "研究范围：全部已收集资料，含事件后补充的材料。", "",
                 "## 关联概况", ""]
        for finding in detail["findings"]:
            lines.extend([f"- **{finding['title']}**：{finding['text']}"])
        lines.extend(["", "## 关系路径与来源", ""])
        references = set()
        for stock in stocks:
            lines.extend([f"### {stock['company_name']} · {stock['symbol']}", ""])
            for path in all_paths(stock):
                lines.extend([f"角色：{ROLE_LABELS.get(path.get('relation_group'), stock['relation_group'])}", ""])
                for edge in path["edges"]:
                    source = self.store.nodes[edge["source"]]["label"]
                    target = self.store.nodes[edge["target"]]["label"]
                    lines.append(f"- {source} → **{edge.get('label', edge['type'])}** → {target}")
                    lines.append(f"  关系最早证据记录：{edge.get('disclosed_at') or '未注明'}。")
                    records = edge.get("evidence_records") or [{"evidence": edge.get("evidence", ""),
                                "source_ids": edge.get("source_ids", []), "disclosed_at": edge.get("disclosed_at")}]
                    for record in records:
                        lines.append(f"  原句：{record.get('evidence', '')}；本条证据记录：{record.get('disclosed_at') or '未注明'}。")
                        for sid in record.get("source_ids", []):
                            references.add(sid)
                            doc = self.store.sources.get(sid, {})
                            date_note = (f"发布日期 {doc['published_at'][:10]}" if doc.get("published_at") else
                                         f"采集记录 {doc['retrieved_at'][:10]}（发布日期未核实）" if doc.get("retrieved_at") else
                                         "来源日期未核实")
                            lines.append(f"  来源：[{doc.get('publisher', '')} · {doc.get('title', sid)}]({doc.get('url', '')})；{date_note}。")
                lines.append("")
            if self.market:
                try:
                    observation = self.market.event_window(stock["symbol"], event, as_of=as_of)
                    values = []
                    for h in ("1", "3", "5"):
                        value = observation["returns"][h]
                        excess = observation.get("excess_returns", {}).get(h)
                        values.append(f"{h}日 {'不可用' if value is None else f'{value:+.2%}'}" +
                                      (f"（相对基准 {excess * 100:+.2f} 个百分点）" if excess is not None else ""))
                    lines.extend([f"市场观察：T0={observation['anchor_date']}，" + "；".join(values) + "。", ""])
                except (KeyError, ValueError, FileNotFoundError):
                    lines.extend(["市场观察：在本次研究范围内，没有足够的真实行情形成该证券的事件窗口。", ""])
        if detail["excluded"]:
            lines.extend(["## 其他候选", ""])
            lines.extend(f"- {e['label']}（{e['symbol']}）：{e['reason']}" for e in detail["excluded"])
        lines.extend(["", "## 说明", "", "关联结果按研发、适配和云服务等关系查询，不评价商业收益。",
                      "行情使用股票与基准的同窗口累计收益，简单收益差不识别事件的因果影响。", ""])
        return {"title": title, "markdown": "\n".join(lines), "filename": event_id.replace(":", "-") + "-research.md",
                "stats": {"stocks": len(stocks), "paths": detail["coverage"]["path_count"], "sources": len(references)}}
