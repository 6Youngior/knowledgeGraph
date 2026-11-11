"""Explicit, provenance-aware financial knowledge graph and constrained queries.

The graph is a NetworkX MultiDiGraph. Prices are kept separately from facts.
Stock discovery uses typed relation patterns, never generic industry proximity.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

NODE_TYPES = {"Company", "Stock", "Model", "Product", "Industry", "Event"}
RELATION_SCHEMA = {
    "DEVELOPED_BY": ({"Model"}, {"Company"}),
    "LISTED_AS": ({"Company"}, {"Stock"}),
    "PRODUCES": ({"Company"}, {"Product"}),
    "SUPPORTS_MODEL": ({"Product"}, {"Model"}),
    "HOSTS_MODEL": ({"Product"}, {"Model"}),
    "RELEASED_MODEL": ({"Event"}, {"Model"}),
    "CONCERNS": ({"Event"}, NODE_TYPES - {"Industry"}),
    "BELONGS_TO": ({"Company", "Product", "Model"}, {"Industry"}),
    "UPSTREAM_OF": ({"Product"}, {"Product"}),
    "COOPERATES_WITH": ({"Company"}, {"Company"}),
    "INVESTS_IN": ({"Company"}, {"Company"}),
    "DEPLOYS": ({"Company"}, {"Model"}),
}
RELATION_LABELS = {
    "DEVELOPED_BY": "研发主体", "LISTED_AS": "上市证券", "PRODUCES": "提供产品",
    "SUPPORTS_MODEL": "技术适配", "HOSTS_MODEL": "推理服务接入", "RELEASED_MODEL": "发布模型", "CONCERNS": "事件涉及",
    "BELONGS_TO": "所属产业", "UPSTREAM_OF": "产品上游", "COOPERATES_WITH": "商业合作",
    "INVESTS_IN": "投资关系", "DEPLOYS": "模型接入",
}


def read_json(path: Path, default=None):
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def normalized(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value).casefold())


def evidence_key(value: str) -> str:
    """Ignore layout whitespace while preserving signs and decimal points."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)))


def fact_id(source, predicate, target):
    digest = hashlib.sha256(f"{source}|{predicate}|{target}".encode()).hexdigest()[:16]
    return f"rel:{digest}"


class GraphStore:
    def __init__(self, data_dir: Path, persist: bool = True, read_runtime: bool | None = None):
        """Open a graph.

        ``persist`` controls writes, as before. ``read_runtime`` controls
        whether a matching runtime snapshot may be read; ``None`` preserves
        the historical default (read iff ``persist`` is true). A read-only
        research session can therefore use ``read_runtime=True`` without
        gaining permission to write an overlay.
        """
        self.data_dir = Path(data_dir)
        self.persist = persist
        self.read_runtime = read_runtime
        self.lock = threading.RLock()
        self.runtime_path = self.data_dir / "runtime" / "graph_state.json"
        self.meta = {}
        self.nodes = {}
        self.edges = {}
        self.events = {}
        self.sources = {}
        self.graph = nx.MultiDiGraph()
        self.updated_at = ""
        self.load()

    def load(self, use_runtime=True):
        with self.lock:
            base = read_json(self.data_dir / "knowledge_graph.json", {"nodes": [], "edges": [], "events": []})
            sources = read_json(self.data_dir / "sources.json", [])
            if isinstance(sources, dict):
                sources = sources.get("sources", [])
            self.meta = base.get("meta", {})
            self.sources = {s["id"]: s for s in sources}
            allow_runtime = self.persist if self.read_runtime is None else self.read_runtime
            if use_runtime and allow_runtime and self.runtime_path.exists():
                saved = read_json(self.runtime_path, {})
                if saved.get("base_digest") == self.base_digest():
                    base = saved["graph"]
                    self.sources.update({s["id"]: s for s in saved.get("sources", [])})
            self.nodes = {n["id"]: copy.deepcopy(n) for n in base.get("nodes", [])}
            self.edges = {e["id"]: copy.deepcopy(e) for e in base.get("edges", [])}
            self.events = {e["id"]: copy.deepcopy(e) for e in base.get("events", [])}
            self.updated_at = datetime.now(timezone.utc).isoformat()
            self._reindex()

    def base_digest(self):
        path = self.data_dir / "knowledge_graph.json"
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "empty"

    def _reindex(self):
        self.graph = nx.MultiDiGraph()
        self.alias_index = {}
        self.fact_index = {}
        for node in self.nodes.values():
            self.graph.add_node(node["id"], **node)
            aliases = [node["id"], node.get("label", ""), *node.get("aliases", [])]
            if node["type"] == "Stock":
                aliases.append(node.get("properties", {}).get("symbol", ""))
            for alias in aliases:
                key = (node["type"], normalized(alias))
                if key[1]:
                    self.alias_index[key] = node["id"]
        for edge in self.edges.values():
            if edge["source"] in self.nodes and edge["target"] in self.nodes:
                self.graph.add_edge(edge["source"], edge["target"], key=edge["id"], **edge)
                self.fact_index[(edge["source"], edge["type"], edge["target"])] = edge["id"]

    def snapshot(self):
        return {"meta": copy.deepcopy(self.meta), "nodes": list(copy.deepcopy(self.nodes).values()),
                "edges": list(copy.deepcopy(self.edges).values()), "events": list(copy.deepcopy(self.events).values())}

    def save(self):
        if self.persist:
            write_json(self.runtime_path, {"base_digest": self.base_digest(), "graph": self.snapshot(),
                                          "sources": list(self.sources.values()), "updated_at": self.updated_at})

    def reset(self):
        with self.lock:
            if self.persist and self.runtime_path.exists():
                self.runtime_path.unlink()
            self.load(use_runtime=False)
            return {"status": "reset", "stats": self.stats()}

    def stats(self):
        return {"entities": len(self.nodes), "relations": len(self.edges), "documents": len(self.sources),
                "events": len(self.events), "stocks": sum(n["type"] == "Stock" for n in self.nodes.values())}

    def overview(self):
        types = Counter(n["type"] for n in self.nodes.values())
        relations = Counter(e["type"] for e in self.edges.values())
        return {"title": self.meta.get("title", "FinGraph"), "description": self.meta.get("description", "多源市场信息融合与事件研究"),
                "as_of": self.meta.get("as_of", "2026-11-06"), "stats": self.stats(),
                "entity_types": [{"type": t, "count": c} for t, c in types.items()],
                "relation_types": [{"type": t, "label": RELATION_LABELS.get(t, t), "count": c} for t, c in relations.items()],
                "updated_at": self.updated_at}

    def event(self, event_id=None):
        if not self.events:
            raise KeyError("尚未准备事件数据")
        if event_id is None:
            return next(iter(self.events.values()))
        if event_id not in self.events:
            raise KeyError(f"未找到事件：{event_id}")
        return self.events[event_id]

    def _visible(self, edge, as_of=None):
        if not as_of:
            return True
        # Undated facts belong to the current research snapshot; they cannot be
        # assumed to have been public at an arbitrary historical cutoff.
        disclosed = edge.get("disclosed_at")
        return bool(disclosed and disclosed[:10] <= as_of[:10])

    def edge_view(self, edge, as_of=None):
        """Return only evidence available at the chosen cutoff, including merged facts."""
        if not self._visible(edge, as_of):
            return None
        result = copy.deepcopy(edge)
        if as_of:
            records = edge.get("evidence_records") or [{"source_ids": edge.get("source_ids", []),
                       "evidence": edge.get("evidence", ""), "disclosed_at": edge.get("disclosed_at", "")}]
            records = [r for r in records if r.get("disclosed_at") and r["disclosed_at"][:10] <= as_of[:10]]
            visible_records = []
            for record in records:
                for sid in record.get("source_ids", []):
                    doc = self.sources.get(sid, {})
                    published = doc.get("published_at", "")[:10]
                    captured = doc.get("retrieved_at", "")[:10]
                    # A listing or product mapping also needs evidence available
                    # at the cutoff. Its valid-from date cannot backdate the
                    # observation of an undated document.
                    available = published or captured
                    if not available or available > as_of[:10]:
                        continue
                    quote = record.get("evidence", "")
                    if not evidence_key(quote) or evidence_key(quote) not in evidence_key(doc.get("text", "")):
                        continue
                    visible_records.append({"source_ids": [sid], "evidence": quote,
                                            "disclosed_at": record["disclosed_at"]})
            records = visible_records
            if not records:
                return None
            result["evidence_records"] = records
            result["evidence"] = records[0]["evidence"]
            result["source_ids"] = sorted({s for r in records for s in r.get("source_ids", [])})
        return result

    def _out(self, node_id, predicate, as_of=None):
        return [view for _, _, _, e in self.graph.out_edges(node_id, keys=True, data=True)
                if e["type"] == predicate and (view := self.edge_view(e, as_of)) is not None] if node_id in self.graph else []

    def _in(self, node_id, predicate, as_of=None):
        return [view for _, _, _, e in self.graph.in_edges(node_id, keys=True, data=True)
                if e["type"] == predicate and (view := self.edge_view(e, as_of)) is not None] if node_id in self.graph else []

    def research_focus(self, event):
        """Resolve a product announcement to its explicitly linked model topic."""
        focus = event["entity_id"]
        if self.nodes[focus]["type"] == "Model":
            return focus
        candidates = {e["target"] for predicate in ("RELEASED_MODEL", "CONCERNS")
                      for e in self._out(event["id"], predicate)
                      if self.nodes[e["target"]]["type"] == "Model"}
        if len(candidates) == 1:
            return next(iter(candidates))
        return focus

    def related_stocks(self, event_id=None, as_of=None):
        event = self.event(event_id)
        if as_of and (event.get("disclosed_at") or event.get("date", ""))[:10] > as_of[:10]:
            return []
        model_id = self.research_focus(event)
        prefix_nodes, prefix_edges = [], []
        if event["id"] in self.nodes:
            prefix_nodes = [self.nodes[event["id"]]]
            prefix_edges = [e for e in self._out(event["id"], "RELEASED_MODEL", as_of) if e["target"] == model_id][:1]
            if not prefix_edges:
                prefix_edges = [e for e in self._out(event["id"], "CONCERNS", as_of) if e["target"] == model_id][:1]
            if not prefix_edges:
                prefix_nodes = []
        candidates = []
        for edge in self._out(model_id, "DEVELOPED_BY", as_of):
            candidates.append((edge["target"], [model_id, edge["target"]], [edge], "direct"))
        for predicate, group in (("SUPPORTS_MODEL", "adaptation"), ("HOSTS_MODEL", "distribution")):
            for support in self._in(model_id, predicate, as_of):
                product_id = support["source"]
                for production in self._in(product_id, "PRODUCES", as_of):
                    company_id = production["source"]
                    candidates.append((company_id, [model_id, product_id, company_id], [support, production], group))
        for deployment in self._in(model_id, "DEPLOYS", as_of):
            company_id = deployment["source"]
            candidates.append((company_id, [model_id, company_id], [deployment], "distribution"))
        results = {}
        for company_id, node_ids, path_edges, group in candidates:
            for listing in self._out(company_id, "LISTED_AS", as_of):
                stock = self.nodes[listing["target"]]
                if stock["type"] != "Stock":
                    continue
                edges = prefix_edges + path_edges + [listing]
                nodes = prefix_nodes + [self.nodes[n] for n in node_ids] + [stock]
                props = stock.get("properties", {})
                listing_date = props.get("listing_date")
                event_date = (event.get("disclosed_at") or event.get("date", ""))[:10]
                item = {"id": stock["id"], "symbol": props.get("symbol", stock.get("symbol", stock["label"])),
                        "label": stock["label"], "company_id": company_id, "company_name": self.nodes[company_id]["label"],
                        "market": props.get("market", ""), "currency": props.get("currency", ""), "relation_group": group,
                        "path": {"nodes": nodes, "edges": edges},
                        "source_ids": sorted({sid for e in edges for sid in e.get("source_ids", [])}),
                        "evidence_dates": sorted({e["disclosed_at"] for e in edges if e.get("disclosed_at")})}
                item["listing_date"] = listing_date
                item["listed_at_event"] = listing_date <= event_date if listing_date else None
                if listing_date and listing_date > event_date:
                    item["market_note"] = f"事后证券映射：事件时尚未上市，上市日期 {listing_date}。"
                dates = [e.get("disclosed_at", "")[:10] for e in edges]
                path = {**item["path"], "relation_group": group,
                        "available_from": max(dates) if dates and all(dates) else None,
                        "source_ids": item["source_ids"]}
                item["path"] = path
                previous = results.get(stock["id"])
                if previous is None:
                    item["paths"] = [path]
                    item["relation_groups"] = [group]
                    item["path_count"] = 1
                    results[stock["id"]] = item
                else:
                    identity = tuple(e["id"] for e in edges)
                    if not any(tuple(e["id"] for e in p["edges"]) == identity for p in previous["paths"]):
                        previous["paths"].append(path)
                    previous["relation_groups"] = sorted({p["relation_group"] for p in previous["paths"]})
                    previous["path_count"] = len(previous["paths"])
                    previous["source_ids"] = sorted(set(previous["source_ids"]) | set(item["source_ids"]))
                    priority = {"direct": 0, "adaptation": 1, "distribution": 2}
                    if (priority.get(group, 9), len(edges)) < (priority.get(previous["relation_group"], 9), len(previous["path"]["edges"])):
                        previous["path"] = path
                        previous["relation_group"] = group
        return sorted(results.values(), key=lambda s: (s["relation_group"] != "direct", s["symbol"]))

    def query_graph(self, event_id=None, q=None, relation_group=None, as_of=None):
        with self.lock:
            visible = [view for e in self.edges.values() if (view := self.edge_view(e, as_of)) is not None]
            focus = None
            keep = set(self.nodes)
            if event_id:
                event = self.event(event_id)
                focus = self.research_focus(event)
                keep = {focus, event["id"]} & set(self.nodes)
                # A research view shows the focal model's evidence network.
                # Generic two-hop expansion via a shared cloud platform would
                # pull in unrelated models, making its meaning hard to read.
                keep.update(e["target"] for e in self._out(focus, "DEVELOPED_BY", as_of))
                keep.update(e["source"] for e in self._in(focus, "DEPLOYS", as_of))
                for predicate in ("SUPPORTS_MODEL", "HOSTS_MODEL"):
                    for support in self._in(focus, predicate, as_of):
                        keep.add(support["source"])
                        keep.update(e["source"] for e in self._in(support["source"], "PRODUCES", as_of))
                for stock in self.related_stocks(event_id, as_of):
                    for path in stock.get("paths", [stock["path"]]):
                        keep.update(n["id"] for n in path["nodes"])
                keep.update(e["target"] for e in visible if e["type"] == "BELONGS_TO" and e["source"] in keep)
            if q:
                needle = normalized(q)
                matches = {n["id"] for n in self.nodes.values()
                           if any(needle in normalized(a) for a in [n["id"], n["label"], *n.get("aliases", []),
                                                                  n.get("properties", {}).get("symbol", "")])}
                if matches:
                    focus = sorted(matches)[0]
                neighborhood = set(matches)
                for e in visible:
                    if e["source"] in matches or e["target"] in matches:
                        neighborhood.update((e["source"], e["target"]))
                keep = neighborhood
            edges = [copy.deepcopy(e) for e in visible if e["source"] in keep and e["target"] in keep
                     and (not relation_group or relation_group == "all" or e.get("relation_group", "direct") == relation_group)]
            if relation_group and relation_group != "all":
                keep &= {i for e in edges for i in (e["source"], e["target"])} | ({focus} if focus else set())
            nodes = [copy.deepcopy(n) for n in self.nodes.values() if n["id"] in keep]
            return {"nodes": nodes, "edges": edges, "focus_id": focus,
                    "stats": {"nodes": len(nodes), "edges": len(edges)}}

    def event_detail(self, event_id=None, as_of=None):
        event = self.event(event_id)
        graph = self.query_graph(event["id"], as_of=as_of)
        source_ids = set(event.get("source_ids", []))
        for edge in graph["edges"]:
            source_ids.update(edge.get("source_ids", []))
        sources = [self.sources[sid] for sid in source_ids if sid in self.sources]
        sources.sort(key=lambda s: (s.get("published_at") or "", s["id"]))
        timeline = [{"date": event.get("event_at", event["date"]), "title": event["title"],
                     "type": "event", "source_ids": event.get("source_ids", [])}]
        timeline.extend({"date": s.get("published_at", ""), "title": s["title"], "type": "source", "source_ids": [s["id"]]}
                        for s in sources if s.get("published_at"))
        timeline.sort(key=lambda t: t["date"])
        return {"event": event, "graph": graph, "stocks": self.related_stocks(event["id"], as_of), "sources": sources,
                "timeline": timeline, "summary": event.get("summary", "")}

    def align_extraction(self, extraction, document):
        """Align exact typed aliases; preserve original evidence and reject unsupported facts."""
        entities = copy.deepcopy(extraction.get("entities", extraction.get("nodes", [])))
        relations = copy.deepcopy(extraction.get("relations", extraction.get("edges", [])))
        events = copy.deepcopy(extraction.get("events", []))
        id_map, matched, warnings = {}, [], []
        all_nodes = copy.deepcopy(self.nodes)
        known_aliases = dict(self.alias_index)
        aligned_nodes = {}
        for node in entities:
            if node.get("type") not in NODE_TYPES or not node.get("label"):
                raise ValueError("抽取实体缺少有效的 type 或 label")
            proposed = node.get("id", f"{node['type'].lower()}:{normalized(node['label'])}")
            names = [node.get("properties", {}).get("symbol", ""), node["label"], *node.get("aliases", [])]
            existing = next((known_aliases[(node["type"], normalized(a))] for a in names
                             if a and (node["type"], normalized(a)) in known_aliases), None)
            canonical = existing or proposed
            if proposed in self.nodes and self.nodes[proposed]["type"] != node["type"]:
                raise ValueError("实体 ID 与现有类型冲突")
            id_map[proposed] = canonical
            id_map[node["label"]] = canonical
            node["id"] = canonical
            node.setdefault("aliases", [])
            node.setdefault("properties", {})
            node.setdefault("source_ids", [document["id"]])
            if existing:
                matched.append({"input": node["label"], "canonical_id": canonical, "label": self.nodes.get(canonical, node)["label"]})
            all_nodes[canonical] = node
            aligned_nodes[canonical] = node
            for name in [node["label"], *node.get("aliases", [])]:
                known_aliases[(node["type"], normalized(name))] = canonical
        available_sources = {**self.sources, document["id"]: document}
        aligned_edges = []
        for edge in relations:
            edge["source"] = id_map.get(edge.get("source"), edge.get("source"))
            edge["target"] = id_map.get(edge.get("target"), edge.get("target"))
            if edge.get("source") not in all_nodes or edge.get("target") not in all_nodes:
                raise ValueError("关系端点缺少有效实体")
            rule = RELATION_SCHEMA.get(edge.get("type"))
            if rule is None:
                raise ValueError(f"未定义的关系类型：{edge.get('type')}")
            if all_nodes[edge["source"]]["type"] not in rule[0] or all_nodes[edge["target"]]["type"] not in rule[1]:
                raise ValueError(f"关系 {edge['type']} 的端点类型不符合 Schema")
            edge.setdefault("source_ids", [document["id"]])
            if not edge["source_ids"] or any(s not in available_sources for s in edge["source_ids"]):
                raise ValueError("关系证据来源缺失")
            evidence = edge.get("evidence", "").strip()
            if not evidence:
                raise ValueError("关系缺少原文证据片段")
            supported = any(evidence_key(evidence) in evidence_key(available_sources[s].get("text", ""))
                            for s in edge["source_ids"])
            if not supported:
                raise ValueError(f"证据片段无法在来源中定位：{evidence[:60]}")
            edge["id"] = fact_id(edge["source"], edge["type"], edge["target"])
            edge.setdefault("disclosed_at", document.get("published_at", "")[:10])
            if document.get("published_at") and document["id"] in edge["source_ids"]:
                documented = document["published_at"][:10]
                if edge.get("disclosed_at") != documented:
                    warnings.append("关系披露日期已按来源发布日期校正，未采用模型推测日期。")
                    edge["disclosed_at"] = documented
            elif document["id"] in edge["source_ids"] and edge.get("disclosed_at"):
                edge["disclosed_at"] = ""
                warnings.append("来源未核实发布日期，该关系不进入历史时点视图。")
            edge["label"] = RELATION_LABELS[edge["type"]]
            canonical_group = ("adaptation" if edge["type"] == "SUPPORTS_MODEL" else
                               "distribution" if edge["type"] in {"HOSTS_MODEL", "DEPLOYS"} else
                               "industry" if edge["type"] in {"BELONGS_TO", "UPSTREAM_OF"} else "direct")
            if edge.get("relation_group", canonical_group) != canonical_group:
                warnings.append("关系分组已按 Schema 校正，区分研发、技术适配和云服务接入。")
            edge["relation_group"] = canonical_group
            aligned_edges.append(edge)
        for event in events:
            event["entity_id"] = id_map.get(event.get("entity_id"), event.get("entity_id"))
            if event.get("entity_id") not in all_nodes:
                raise ValueError("事件关联实体不存在")
            event.setdefault("date", event.get("event_at", document.get("published_at", ""))[:10])
            event.setdefault("event_at", event["date"])
            event.setdefault("source_ids", [document["id"]])
        preview = {"new_nodes": sum(n not in self.nodes for n in aligned_nodes),
                   "new_edges": len({(e["source"], e["type"], e["target"]) for e in aligned_edges} - set(self.fact_index)),
                   "matched_entities": matched}
        if not aligned_edges:
            warnings.append("本次没有抽取出可验证关系；可以修改文本后重试。")
        return {"entities": list(aligned_nodes.values()), "relations": aligned_edges, "events": events,
                "validation": {"valid": bool(aligned_edges), "warnings": warnings}, "preview": preview}

    def ingest(self, result):
        if not result.get("validation", {}).get("valid"):
            raise ValueError("校验未通过，不能入图")
        with self.lock:
            changes = dict(added_nodes=0, added_edges=0, updated_nodes=0, updated_edges=0)
            for node in result["entities"]:
                nid = node["id"]
                if nid in self.nodes:
                    old = self.nodes[nid]
                    merged = copy.deepcopy(old)
                    merged["aliases"] = sorted(set(old.get("aliases", [])) | set(node.get("aliases", [])))
                    merged["source_ids"] = sorted(set(old.get("source_ids", [])) | set(node.get("source_ids", [])))
                    merged["properties"] = {**old.get("properties", {}), **node.get("properties", {})}
                    if merged != old:
                        self.nodes[nid] = merged
                        changes["updated_nodes"] += 1
                else:
                    self.nodes[nid] = copy.deepcopy(node)
                    changes["added_nodes"] += 1
            for edge in result["relations"]:
                key = (edge["source"], edge["type"], edge["target"])
                eid = self.fact_index.get(key)
                if eid:
                    old = self.edges[eid]
                    merged = copy.deepcopy(old)
                    merged["source_ids"] = sorted(set(old.get("source_ids", [])) | set(edge.get("source_ids", [])))
                    records = old.get("evidence_records", [{"source_ids": old.get("source_ids", []),
                                                              "evidence": old.get("evidence", ""), "disclosed_at": old.get("disclosed_at", "")}])
                    record = {"source_ids": edge.get("source_ids", []), "evidence": edge.get("evidence", ""),
                              "disclosed_at": edge.get("disclosed_at", "")}
                    if record not in records:
                        merged["evidence_records"] = records + [record]
                    dates = [d for d in (old.get("disclosed_at"), edge.get("disclosed_at")) if d]
                    if dates:
                        merged["disclosed_at"] = min(dates)
                    if merged != old:
                        self.edges[eid] = merged
                        changes["updated_edges"] += 1
                else:
                    eid = edge["id"]
                    self.edges[eid] = copy.deepcopy(edge)
                    self.fact_index[key] = eid
                    changes["added_edges"] += 1
            for event in result.get("events", []):
                self.events[event["id"]] = copy.deepcopy(event)
            document = result["document"]
            self.sources[document["id"]] = copy.deepcopy(document)
            self.updated_at = datetime.now(timezone.utc).isoformat()
            self._reindex()
            self.save()
            return {**changes, "stats": self.stats(), "graph": self.query_graph()}
