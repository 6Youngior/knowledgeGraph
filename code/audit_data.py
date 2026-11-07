"""Audit the delivered factual dataset and held-out update, without mutating it."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from graph_store import GraphStore, NODE_TYPES, RELATION_SCHEMA, normalized, read_json, write_json
from market import MarketData

ROOT = Path(__file__).resolve().parents[1]


def audit():
    data_dir = ROOT / "data"
    issues, checks = [], []
    required = ["knowledge_graph.json", "sources.json", "extraction_samples.json", "market/manifest.json"]
    missing = [name for name in required if not (data_dir / name).is_file()]
    if missing:
        return {"passed": False, "issues": [f"Missing data/{name}" for name in missing], "checks": []}
    graph = read_json(data_dir / "knowledge_graph.json")
    sources = read_json(data_dir / "sources.json")
    store = GraphStore(data_dir, persist=False)
    source_ids = [s["id"] for s in sources]
    node_ids = [n["id"] for n in graph["nodes"]]
    edge_ids = [e["id"] for e in graph["edges"]]
    for name, values in (("source", source_ids), ("node", node_ids), ("edge", edge_ids)):
        if len(values) != len(set(values)):
            issues.append(f"Duplicate {name} IDs")
    fact_keys = [(e["source"], e["type"], e["target"]) for e in graph["edges"]]
    if len(fact_keys) != len(set(fact_keys)):
        issues.append("Duplicate natural facts (source, type, target)")
    checks.append("stable unique IDs and fact deduplication")
    for source in sources:
        if urlparse(source.get("url", "")).scheme not in {"http", "https"}:
            issues.append(f"Source URL invalid: {source['id']}")
        if not isinstance(source.get("text"), str) or not source["text"].strip():
            issues.append(f"Empty source text: {source['id']}")
        day = source.get("published_at")
        if day:
            try:
                datetime.strptime(day[:10], "%Y-%m-%d")
            except ValueError:
                issues.append(f"Invalid publication date: {source['id']}")
    for node in store.nodes.values():
        if node["type"] not in NODE_TYPES:
            issues.append(f"Unknown node type: {node['id']}")
        if not node.get("source_ids") or not set(node.get("source_ids", [])) <= set(source_ids):
            issues.append(f"Entity provenance missing: {node['id']}")
    for edge in graph["edges"]:
        eid = edge["id"]
        a, b = store.nodes.get(edge["source"]), store.nodes.get(edge["target"])
        rule = RELATION_SCHEMA.get(edge["type"])
        if a is None or b is None or rule is None or a["type"] not in rule[0] or b["type"] not in rule[1]:
            issues.append(f"Invalid schema/endpoints: {eid}")
        cited = edge.get("source_ids", [])
        if not cited or not set(cited) <= set(source_ids):
            issues.append(f"Unknown evidence source: {eid}")
            continue
        quote = normalized(edge.get("evidence", ""))
        if not quote or not any(quote in normalized(store.sources[s].get("text", "")) for s in cited):
            issues.append(f"Evidence not locatable in cited excerpts: {eid}")
        published = [store.sources[s].get("published_at", "")[:10] for s in cited if store.sources[s].get("published_at")]
        disclosed = edge.get("disclosed_at")
        if published and disclosed and disclosed[:10] < min(published):
            issues.append(f"Fact dated before every cited publication: {eid}")
        captures = [store.sources[s].get("retrieved_at", "")[:10] for s in cited if store.sources[s].get("retrieved_at")]
        if edge["type"] in {"HOSTS_MODEL", "SUPPORTS_MODEL", "DEPLOYS"} and not published and captures and disclosed and disclosed[:10] < min(captures):
            issues.append(f"Dynamic fact backdated from undated-only sources: {eid}")
    checks.extend(["typed schema and valid endpoints", "source IDs and verbatim evidence location", "publication/disclosure consistency"])
    event_ids = [e["id"] for e in graph["events"]]
    if len(event_ids) != len(set(event_ids)):
        issues.append("Duplicate event IDs")
    for event in store.events.values():
        if event["entity_id"] not in store.nodes:
            issues.append(f"Event focus does not exist: {event['id']}")
        if not set(event.get("source_ids", [])) <= set(source_ids):
            issues.append(f"Event source does not exist: {event['id']}")
    checks.append("event focus and provenance")
    market = MarketData(data_dir)
    market_summary = []
    for symbol, spec in market.manifest().items():
        try:
            rows, _ = market.rows(symbol)
            if len(rows) < 10:
                issues.append(f"Too few daily observations: {symbol}")
            for row in rows:
                if all(k in row for k in ("open", "high", "low")):
                    if not (0 < row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]):
                        issues.append(f"OHLC inconsistency: {symbol} {row['date']}")
                if row["volume"] < 0:
                    issues.append(f"Negative volume: {symbol} {row['date']}")
            if "test" in spec.get("provider", "").lower() or "synthetic" in spec.get("provider", "").lower():
                issues.append(f"Synthetic provider in actual delivery: {symbol}")
            market_summary.append({"symbol": symbol, "rows": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"],
                                   "provider": spec.get("provider"), "adjusted": spec.get("adjusted")})
        except (KeyError, ValueError, OSError) as exc:
            issues.append(f"Market cache {symbol}: {exc}")
    checks.append("real cached series, trading dates and OHLC")
    windows = []
    for event in store.events.values():
        for stock in store.related_stocks(event["id"]):
            try:
                window = market.event_window(stock["symbol"], event)
                windows.append({"event_id": event["id"], "symbol": stock["symbol"], "anchor_date": window["anchor_date"],
                                "returns": window["returns"], "points": len(window["prices"])})
            except (KeyError, ValueError, OSError) as exc:
                listing_date = market.manifest().get(stock["symbol"], {}).get("listing_date")
                if listing_date and listing_date > (event.get("disclosed_at") or event["date"])[:10]:
                    windows.append({"event_id": event["id"], "symbol": stock["symbol"], "available": False,
                                    "reason": "not_listed_at_event", "listing_date": listing_date})
                else:
                    issues.append(f"Event window {event['id']} / {stock['symbol']}: {exc}")
    checks.append("event-to-stock window coverage")
    samples = read_json(data_dir / "extraction_samples.json")
    update_results = []
    found_new_stock = False
    for sample in samples:
        fresh = GraphStore(data_dir, persist=False)
        document = {**fresh.sources.get(sample["document_id"], {}), "id": sample["document_id"],
                    "text": sample["text"], "title": sample["title"], "url": sample.get("url", "")}
        try:
            before = {eid: {s["symbol"] for s in fresh.related_stocks(eid)} for eid in fresh.events}
            aligned = fresh.align_extraction(sample["extraction"], document)
            change = fresh.ingest({**aligned, "document": document})
            gains = {eid: sorted({s["symbol"] for s in fresh.related_stocks(eid)} - before.get(eid, set())) for eid in before}
            found_new_stock |= any(gains.values())
            repeated = fresh.ingest({**aligned, "document": document})
            if any(repeated[key] for key in ("added_nodes", "added_edges", "updated_nodes", "updated_edges")):
                issues.append(f"Update is not idempotent: {sample['id']}")
            update_results.append({"sample_id": sample["id"], "added_nodes": change["added_nodes"],
                                   "added_edges": change["added_edges"], "new_stocks": gains})
        except (KeyError, ValueError) as exc:
            issues.append(f"Extraction sample {sample['id']}: {exc}")
    if not found_new_stock:
        issues.append("No held-out sample adds a new explainable stock path")
    checks.append("held-out update, new stock discovery and idempotence")
    return {"passed": not issues, "created_at": datetime.now(timezone.utc).isoformat(), "issues": issues,
            "checks": checks, "stats": store.stats(), "market": market_summary, "windows": windows, "updates": update_results}


if __name__ == "__main__":
    result = audit()
    write_json(ROOT / "docs" / "results" / "data_audit.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
