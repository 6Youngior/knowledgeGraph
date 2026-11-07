"""Exercise actual delivered data through the API, keeping the base data intact."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app
from graph_store import write_json

ROOT = Path(__file__).resolve().parents[1]


def validate(live=False):
    checks = []
    app = create_app(persist=False)
    store = app.state.store
    if not store.nodes:
        raise AssertionError("Actual dataset is missing; synthetic tests cannot prove demo completeness")
    def record(name, detail):
        checks.append({"name": name, "passed": True, "detail": detail})
    with TestClient(app) as client:
        overview = client.get("/api/overview")
        assert overview.status_code == 200
        assert overview.json()["stats"]["entities"] == len(store.nodes)
        record("overview statistics match actual graph", overview.json()["stats"])
        sources = client.get("/api/sources").json()["sources"]
        assert sources and len(sources) == len(store.sources)
        for source in sources:
            assert client.get(f"/api/sources/{source['id']}").status_code == 200
        record("all provenance endpoints resolve", len(sources))
        events = client.get("/api/events").json()["events"]
        assert events
        for event in events:
            response = client.get(f"/api/events/{event['id']}")
            assert response.status_code == 200, response.text
            detail = response.json()
            node_ids = {n["id"] for n in detail["graph"]["nodes"]}
            assert all(e["source"] in node_ids and e["target"] in node_ids for e in detail["graph"]["edges"])
            windows = []
            for stock in detail["stocks"]:
                market = client.get(f"/api/market/{stock['symbol']}", params={"event_id": event["id"]})
                if market.status_code == 422 and "尚未上市" in market.json().get("detail", ""):
                    windows.append({"symbol": stock["symbol"], "available": False, "reason": "not_listed_at_event"})
                    continue
                assert market.status_code == 200, market.text
                value = market.json()
                assert value["prices"] and value["returns"]["1"] is not None
                windows.append({"symbol": stock["symbol"], "anchor_date": value["anchor_date"], "returns": value["returns"]})
            record(f"event detail and cached windows: {event['id']}", windows)
        sample_items = client.get("/api/extraction/samples").json()["samples"]
        assert sample_items
        live_record = None
        for sample in sample_items:
            mode = "live" if live and live_record is None else "replay"
            extract = client.post("/api/extract", json={"sample_id": sample["id"], "mode": mode})
            assert extract.status_code == 200, extract.text
            value = extract.json()
            assert value["mode"] == mode and value["validation"]["valid"], value
            if mode == "live":
                live_record = value
                write_json(ROOT / "docs" / "results" / "live_extraction.json", value)
            before_stocks = {eid: {s["symbol"] for s in store.related_stocks(eid)} for eid in store.events}
            ingest = client.post("/api/ingest", json={"extraction_id": value["extraction_id"]})
            assert ingest.status_code == 200, ingest.text
            changes = ingest.json()
            again = client.post("/api/ingest", json={"extraction_id": value["extraction_id"]}).json()
            assert all(again[k] == 0 for k in ("added_nodes", "added_edges", "updated_nodes", "updated_edges")), again
            new_stocks = {eid: sorted({s["symbol"] for s in store.related_stocks(eid)} - before_stocks[eid]) for eid in before_stocks}
            if sample["id"] == "sample:mtt-glm5-adapt":
                assert "688795.SH" in new_stocks.get("event:glm5-release", []), "The held-out update did not produce its stock explanation path"
            record(f"{mode} extraction, validated ingestion and idempotence: {sample['id']}",
                   {"model": value["model"], "elapsed_ms": value["elapsed_ms"], "new_stocks": new_stocks,
                    "added_nodes": changes["added_nodes"], "added_edges": changes["added_edges"]})
            reset = client.post("/api/reset")
            assert reset.status_code == 200
            assert reset.json()["stats"] == overview.json()["stats"]
        record("reset restores base graph and statistics", store.stats())
        matrix = client.get("/api/research").json()
        assert len(matrix["events"]) == len(store.events)
        for event in events:
            detail = client.get(f"/api/research/{event['id']}").json()
            assert detail["coverage"]["path_count"] >= detail["temporal"]["visible_count"]
            assert detail["findings"]
            historical = client.get(f"/api/research/{event['id']}", params={"as_of": event["date"]}).json()
            assert historical["temporal"]["visible_count"] <= historical["temporal"]["current_count"]
            brief = client.post(f"/api/research/{event['id']}/brief", json={})
            assert brief.status_code == 200 and "关系路径与来源" in brief.json()["markdown"]
            assert "https://" in brief.json()["markdown"]
        record("research findings, historical review and downloadable briefs", len(matrix["events"]))
        missing = client.get("/api/events/does-not-exist")
        assert missing.status_code == 404 and "detail" in missing.json()
        bad = client.post("/api/extract", json={"mode": "replay", "text": "custom"})
        assert bad.status_code == 422
        record("invalid inputs return actionable JSON errors", [404, 422])
        page = client.get("/")
        assert page.status_code == 200 and 'id="root"' in page.text, "Production frontend has not been built"
        import re
        scripts = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page.text)
        assert scripts and all(client.get(path).status_code == 200 for path in scripts)
        record("production HTML and bundled assets served", scripts)
    return {"passed": True, "created_at": datetime.now(timezone.utc).isoformat(), "live_model_called": live,
            "checks": checks, "check_count": len(checks)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Actually call the configured model on the first real sample")
    args = parser.parse_args()
    try:
        result = validate(args.live)
    except Exception as exc:
        result = {"passed": False, "error": str(exc), "created_at": datetime.now(timezone.utc).isoformat()}
        write_json(ROOT / "docs" / "results" / "api_validation.json", result)
        raise
    write_json(ROOT / "docs" / "results" / "api_validation.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
