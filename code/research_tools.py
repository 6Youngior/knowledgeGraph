"""Read-only financial research tools over a dated view of the local dataset.

The service deliberately separates three clocks:

* ``published_at`` — when the source says it was made public;
* ``retrieved_at`` — when this local copy of the body was observed;
* ``available_at`` — the earliest date on which the observed body can be
  treated as available to this research view.

A source whose body was observed after the requested cutoff is not available
for that historical view, even if its URL was published earlier.  A source
with no public date but a capture date can be shown as a captured observation
on/after that capture day; its ``published_at`` stays unknown.  A date-only
publication is still represented as such.  This is intentionally conservative:
the service does not claim to reconstruct an unarchived old page body.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from graph_store import GraphStore, normalized, evidence_key
from market import MarketData

CHINA = timezone(timedelta(hours=8))


def day(value):
    """Return an ISO calendar day in China time, or ``None`` if unparseable."""
    if not value:
        return None
    try:
        if len(str(value)) == 10:
            return date.fromisoformat(str(value)).isoformat()
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            return moment.date().isoformat()
        return moment.astimezone(CHINA).date().isoformat()
    except (TypeError, ValueError):
        return None


def _source_info(source, observed_today=None):
    """Classify publication and observed-body clocks without inventing dates."""
    observed_today = observed_today or datetime.now(CHINA).date().isoformat()
    published_raw = str(source.get("published_at") or "").strip()
    published = day(published_raw)
    captured = day(source.get("retrieved_at"))
    modified = day(source.get("modified_at"))
    explicit = day(source.get("available_at"))
    version_status = str(source.get("version_status") or "")
    archived = version_status in {"original_filing", "archived_version"}

    if published:
        date_status = "exact" if len(published_raw) > 10 else "day_only"
        public_at = published
        if archived and explicit:
            body_at = max(explicit, published)
            body_status = "archived_version"
        else:
            # A missing capture/modification date means the observed body
            # version is not the URL's publication version.  Conservatively
            # use the current observation date; never equate body with the
            # publication date without archive evidence.
            candidates = [published]
            candidates.append(captured or observed_today)
            if modified:
                candidates.append(modified)
            body_at = max(x for x in candidates if x)
            body_status = (
                "archived_version" if archived and explicit else
                "observed_current" if not captured else
                "observed_version" if body_at != published else
                "publication"
            )
        return {
            "public_at": public_at,
            "body_at": body_at,
            "date_status": date_status,
            "body_status": body_status,
            "published_at": published_raw,
            "retrieved_at": captured,
            "modified_at": modified,
            "version_status": version_status,
            "archived": archived,
        }

    if explicit and archived:
        # A verified archive can be used even if the current URL was captured
        # later.  The explicit archive date is the version's public date.
        return {
            "public_at": explicit,
            "body_at": explicit,
            "date_status": "archived_version",
            "body_status": "archived_version",
            "published_at": "",
            "retrieved_at": captured,
            "modified_at": modified,
            "version_status": version_status,
            "archived": True,
        }

    if captured or modified:
        # There is a body, but no public date.  It is visible as a captured
        # observation on/after its observation day; publication time remains
        # unknown.  It must not be treated as a historical public source.
        body_at = max(x for x in (captured or observed_today, modified) if x)
        return {
            "public_at": None,
            "body_at": body_at,
            "date_status": "captured_only",
            "body_status": "captured_only",
            "published_at": "",
            "retrieved_at": captured,
            "modified_at": modified,
            "version_status": version_status,
            "archived": False,
        }

    return {
        "public_at": None,
        "body_at": None,
        "date_status": "unknown",
        "body_status": "unknown",
        "published_at": "",
        "retrieved_at": captured,
        "modified_at": modified,
        "version_status": version_status,
        "archived": False,
    }


def source_available_on(source, observed_today=None):
    """Return the observed-body availability date.

    ``observed_today`` is the date used when a publication date exists but the
    body has no capture/modification date.  It is not a publication date.
    ``None`` means the source has neither a public date nor an observable body
    date.
    """
    return _source_info(source, observed_today)["body_at"]


class ResearchTools:
    """Five read-only tools over a cutoff-filtered graph and market cache."""

    def __init__(self, data_dir: Path, as_of=None):
        observed_today = datetime.now(CHINA).date().isoformat()
        self.as_of = as_of or observed_today
        try:
            if day(self.as_of) != self.as_of:
                raise ValueError("研究截止日必须是 YYYY-MM-DD")
        except (TypeError, ValueError) as exc:
            raise ValueError("研究截止日必须是有效的 YYYY-MM-DD 日期") from exc
        if self.as_of > observed_today:
            raise ValueError("研究日期不能晚于今天")

        self.data_dir = Path(data_dir)
        self.market = MarketData(self.data_dir)
        # persist=False means this service never writes.  read_runtime=True is
        # a separate, explicit permission to read a base_digest-matching Web
        # update; graph_store.py only applies it when the digest matches.
        # The old GraphStore(persist=False) default still ignores runtime.
        store = GraphStore(self.data_dir, persist=False, read_runtime=True)

        self.sources = {}
        self.hidden_sources = {}
        for sid, source in store.sources.items():
            info = _source_info(source, observed_today)
            if info["body_at"] is None:
                self.hidden_sources[sid] = {
                    "reason": "date_unverified",
                    "date_status": info["date_status"],
                    "retrieved_at": info["retrieved_at"],
                }
                continue
            if info["body_at"] > self.as_of:
                self.hidden_sources[sid] = {
                    "reason": "body_after_cutoff",
                    "date_status": info["date_status"],
                    "body_status": info["body_status"],
                    "available_at": info["body_at"],
                }
                continue
            self.sources[sid] = {
                **copy.deepcopy(source),
                "available_at": info["body_at"],
                "date_status": info["date_status"],
                "body_status": info["body_status"],
            }

        source_text = {sid: evidence_key(source.get("text", "")) for sid, source in self.sources.items()}
        edges = {}
        for eid, original in store.edges.items():
            edge_day = day(original.get("disclosed_at"))
            if edge_day and edge_day > self.as_of:
                continue
            raw_records = original.get("evidence_records")
            if not raw_records:
                raw_records = [{
                    "source_ids": original.get("source_ids") or [],
                    "evidence": original.get("evidence", ""),
                    "disclosed_at": original.get("disclosed_at", ""),
                }]
            records = []
            for record in raw_records:
                record_day = day(record.get("disclosed_at"))
                if record_day and record_day > self.as_of:
                    continue
                evidence = str(record.get("evidence") or "").strip()
                if not evidence:
                    continue
                # A mixed old/new citation cannot keep a future-only quote
                # after the unavailable source ID has been removed.
                quote = evidence_key(evidence)
                source_ids = [sid for sid in (record.get("source_ids") or [])
                              if sid in self.sources and quote and quote in source_text[sid]]
                if not source_ids:
                    continue
                source_days = [day(self.sources[sid].get("available_at")) for sid in source_ids]
                source_days = [d for d in source_days if d]
                if not source_days:
                    continue
                source_day = max(source_days)
                # An undated edge/record may be used only from the date its
                # supporting body is actually available.  This applies the
                # lower bound required by the review and never backdates the
                # evidence to an earlier URL.
                effective_day = max(x for x in (record_day, source_day) if x)
                if effective_day > self.as_of:
                    continue
                records.append({
                    "source_ids": source_ids,
                    "evidence": evidence,
                    "disclosed_at": effective_day,
                })
            if not records:
                continue
            edge = copy.deepcopy(original)
            edge["evidence_records"] = records
            edge["source_ids"] = sorted({sid for record in records for sid in record["source_ids"]})
            edge["evidence"] = records[0]["evidence"]
            # If the top-level edge had no date, use the earliest visible
            # evidence availability.  It can still be filtered per record.
            edge["disclosed_at"] = edge_day or min(record["disclosed_at"] for record in records)
            edges[eid] = edge

        endpoints = {n for edge in edges.values() for n in (edge["source"], edge["target"])}
        allowed_properties = {"symbol", "market", "exchange", "currency", "company_id", "company_name", "listing_date"}
        self.stock_meta = {}
        for nid, node in store.nodes.items():
            if node.get("type") == "Stock":
                listing = day(node.get("properties", {}).get("listing_date"))
                if listing:
                    self.stock_meta[nid] = {
                        "listing_date": listing,
                        "symbol": node.get("properties", {}).get("symbol", ""),
                    }
        nodes = {}
        for nid, node in store.nodes.items():
            source_ids = [sid for sid in (node.get("source_ids") or []) if sid in self.sources]
            if not source_ids and nid not in endpoints:
                continue
            properties = {}
            for key, value in node.get("properties", {}).items():
                if key not in allowed_properties:
                    continue
                if key == "listing_date" and day(value) and day(value) > self.as_of:
                    continue
                properties[key] = copy.deepcopy(value)
            nodes[nid] = {
                "id": nid,
                "type": node["type"],
                "label": node["label"],
                "source_ids": source_ids,
                "properties": properties,
            }
        store.nodes = nodes
        store.edges = {
            eid: edge for eid, edge in edges.items()
            if edge["source"] in nodes and edge["target"] in nodes
        }

        events = {}
        for eid, event in store.events.items():
            disclosed = day(event.get("disclosed_at") or event.get("date"))
            occurred = day(event.get("event_at") or event.get("date"))
            if not disclosed or not occurred or disclosed > self.as_of or occurred > self.as_of:
                continue
            source_ids = [sid for sid in (event.get("source_ids") or []) if sid in self.sources]
            if not source_ids:
                continue
            events[eid] = {
                key: copy.deepcopy(value) for key, value in event.items()
                if key in {"id", "title", "date", "event_at", "disclosed_at",
                           "entity_id", "model_id", "focus_id", "type"}
            }
            events[eid]["source_ids"] = source_ids

        store.events = events
        store.sources = self.sources
        store._reindex()
        self.store = store

    def overview(self):
        return {
            "as_of": self.as_of,
            "knowledge": self.store.stats(),
            "events": [
                {key: event.get(key) for key in ("id", "title", "date")}
                for event in self.store.events.values()
            ],
            "coverage": "当前为大模型产业的初始案例资料，财务表与更多公司正在扩充。",
            "time_policy": (
                "只使用截止日前有可核实公开/归档日期、且观测正文版本不晚于截止日的来源；"
                "抓取日期不当作发布日期，未归档旧页的新正文不进入历史证据。"
            ),
        }

    def search_entities(self, query, limit=8):
        needle = normalized(query)
        if not needle:
            return {"as_of": self.as_of, "entities": []}
        try:
            count = max(1, min(int(limit), 20))
        except (TypeError, ValueError):
            count = 8
        matches = [
            node for node in self.store.nodes.values()
            if needle in normalized(node["label"])
            or needle in normalized(node["id"])
            or needle in normalized(node.get("properties", {}).get("symbol", ""))
        ]
        return {"as_of": self.as_of, "entities": matches[:count]}

    def related_stocks(self, event_id):
        if event_id not in self.store.events:
            return {"as_of": self.as_of, "found": False, "stocks": []}
        try:
            values = self.store.related_stocks(event_id, self.as_of)
        except (KeyError, TypeError, ValueError):
            # A filtered graph can correctly contain an event whose focal
            # entity is not available in this historical view.
            return {
                "as_of": self.as_of,
                "found": True,
                "event": self.store.events[event_id],
                "stocks": [],
                "reason": "当前截止日没有可核实的实体/路径",
            }

        stocks = []
        for stock in values[:20]:
            listing = (self.stock_meta.get(stock.get("id"), {}) or {}).get("listing_date")
            if listing and listing > self.as_of:
                continue
            paths = []
            for path in stock.get("paths", [stock.get("path", {})]):
                edges = []
                for edge in path.get("edges", []):
                    citations = [
                        self._citation(sid) for sid in (edge.get("source_ids") or [])
                        if sid in self.sources
                    ]
                    if not citations:
                        continue
                    edges.append({
                        "type": edge.get("type", ""),
                        "evidence": edge.get("evidence", ""),
                        "sources": citations,
                    })
                if not edges:
                    continue
                paths.append({
                    "nodes": [
                        {"id": node["id"], "label": node["label"]}
                        for node in path.get("nodes", [])
                        if node.get("id") in self.store.nodes
                    ],
                    "edges": edges,
                })
            if not paths:
                continue
            stocks.append({
                "symbol": stock["symbol"],
                "company": stock["company_name"],
                "roles": stock.get("relation_groups", [stock.get("relation_group", "")]),
                "paths": paths,
            })
        return {
            "as_of": self.as_of,
            "found": True,
            "event": self.store.events[event_id],
            "stocks": stocks,
        }

    def _citation(self, source_id):
        source = self.sources[source_id]
        citation = {
            key: source.get(key, "") for key in
            ("id", "title", "publisher", "url", "published_at", "retrieved_at",
             "available_at", "date_status", "body_status")
        }
        # A future capture date is itself metadata from the present body;
        # omit it from a historical citation even when an archived version is
        # usable.
        if citation.get("retrieved_at") and day(citation["retrieved_at"]) and day(citation["retrieved_at"]) > self.as_of:
            citation["retrieved_at"] = ""
        return citation

    def read_source(self, source_id):
        if source_id not in self.sources:
            # An unknown ID and a future source have identical public results.
            return {"as_of": self.as_of, "found": False}
        source = self.sources[source_id]
        return {
            "as_of": self.as_of,
            "found": True,
            **self._citation(source_id),
            "text": source.get("text", "")[:6000],
        }

    def price_history(self, symbol, days=30):
        matching = [
            node for node in self.store.nodes.values()
            if node.get("properties", {}).get("symbol") == symbol
        ]
        if not matching:
            return {"as_of": self.as_of, "found": False, "prices": []}
        stock_node = matching[0]
        listing = (self.stock_meta.get(stock_node.get("id"), {}) or {}).get("listing_date")
        if listing and listing > self.as_of:
            return {
                "as_of": self.as_of, "found": False, "prices": [],
                "reason": "该证券在研究截止日尚未上市，不能提供该时点价格。",
            }
        try:
            rows, spec = self.market.rows(symbol)
        except (KeyError, ValueError, FileNotFoundError):
            return {"as_of": self.as_of, "found": False, "prices": []}

        spec_listing = day(spec.get("listing_date"))
        if spec_listing and spec_listing > self.as_of:
            return {
                "as_of": self.as_of, "found": False, "prices": [],
                "reason": "该证券在研究截止日尚未上市，不能提供该时点价格。",
            }

        adjusted = str(spec.get("adjusted") or "").lower()
        raw_adjusted = adjusted in {"", "none", "raw", "unadjusted"}
        version_date = day(spec.get("retrieved_at")) or day(spec.get("available_at"))
        if version_date and version_date > self.as_of:
            return {
                "as_of": self.as_of, "found": False, "prices": [],
                "reason": "该行情版本在研究截止日尚未取得，需要相应历史快照。",
            }
        if not version_date and not raw_adjusted:
            return {
                "as_of": self.as_of, "found": False, "prices": [],
                "reason": "复权行情版本日期未核实，不能用于历史研究。",
            }

        visible = []
        for row in rows:
            row_day = day(row.get("date"))
            if not row_day or row_day > self.as_of:
                continue
            if listing and row_day < listing:
                continue
            visible.append(row)
        if not visible:
            return {"as_of": self.as_of, "found": False, "prices": []}

        try:
            count = max(1, min(int(days), 120))
        except (TypeError, ValueError):
            count = 30
        retrieved = spec.get("retrieved_at") or ""
        if retrieved and day(retrieved) and day(retrieved) > self.as_of:
            retrieved = ""
        return {
            "as_of": self.as_of,
            "found": True,
            "symbol": symbol,
            "currency": spec.get("currency"),
            "adjusted": spec.get("adjusted"),
            "source_url": spec.get("url"),
            "retrieved_at": retrieved,
            "version_status": "observed_snapshot" if version_date else "unverified",
            "last_available_date": visible[-1]["date"],
            "prices": visible[-count:],
        }
