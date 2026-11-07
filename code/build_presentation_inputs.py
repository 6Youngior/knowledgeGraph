"""Generate Beamer numbers from the actual graph, market cache and saved checks."""
from datetime import datetime, timezone
import json
from pathlib import Path

from graph_store import GraphStore, read_json, write_json
from market import MarketData
from research import ResearchService
from extraction import ExtractionService

ROOT = Path(__file__).resolve().parents[1]


def generate():
    store = GraphStore(ROOT / "data", persist=False)
    market = MarketData(ROOT / "data")
    stats = store.stats()
    validation = read_json(ROOT / "docs" / "results" / "api_validation.json", {})
    live = read_json(ROOT / "docs" / "results" / "live_extraction.json", {})
    unit = read_json(ROOT / "docs" / "results" / "unit_tests.json", {})
    event = store.events["event:glm5-release"]
    window = market.event_window("02513.HK", event)
    research = ResearchService(store, market)
    overview = research.overview()
    case = research.detail(event["id"])
    historic = research.detail(event["id"], event["date"])
    series = market.manifest()
    macros = {"GraphNodeCount": stats["entities"], "GraphEdgeCount": stats["relations"],
              "SourceCount": stats["documents"], "EventCount": stats["events"], "StockCount": stats["stocks"],
              "ValidationCount": unit.get("tests_run", 0), "ApiCheckCount": validation.get("check_count", 0),
              "LiveModelName": live.get("model", "DeepSeek V4.1 Flash"),
              "LiveElapsedSeconds": f"{live.get('elapsed_ms', 0) / 1000:.1f}",
              "GLMAnchorDate": window["anchor_date"],
              "CoverageStart": overview["coverage"]["start"], "CoverageEnd": overview["coverage"]["end"],
              "ModelCount": overview["coverage"]["models"], "MarketCount": len(overview["coverage"]["markets"]),
              "MarketSeriesCount": len(series), "MarketRowCount": sum(len(market.rows(s)[0]) for s in series),
              "GLMCurrentStockCount": case["temporal"]["current_count"],
              "GLMHistoricalStockCount": historic["temporal"]["visible_count"],
              "GLMPathCount": case["coverage"]["path_count"],
              "GLMBenchmarkFive": f"{window['benchmark_returns']['5'] * 100:+.2f}\\%" if window['benchmark_returns']['5'] is not None else "--",
              "GLMExcessFive": f"{window['excess_returns']['5'] * 100:+.2f}" if window['excess_returns']['5'] is not None else "--"}
    updated = GraphStore(ROOT / "data", persist=False)
    extraction = ExtractionService(updated, ROOT)
    sample = next((s for s in extraction.samples() if s["id"] == "sample:mtt-glm5-adapt"), None)
    update = None
    if sample:
        result = extraction.extract(sample_id=sample["id"], mode="replay")
        update = extraction.ingest(result["extraction_id"])
        macros.update({"GLMPostUpdateStockCount": len(updated.related_stocks(event["id"])),
                       "UpdateNodeCount": update["added_nodes"], "UpdateEdgeCount": update["added_edges"]})
    for horizon, name in (("1", "GLMReturnOne"), ("3", "GLMReturnThree"), ("5", "GLMReturnFive")):
        macros[name] = f"{window['returns'][horizon] * 100:+.2f}\\%"
    output = ROOT / "docs" / "presentation" / "generated"
    output.mkdir(parents=True, exist_ok=True)
    lines = ["% Generated from actual delivered data; do not hand-edit."]
    lines += [f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in macros.items()]
    (output / "metrics.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(output / "metrics.json", {"created_at": datetime.now(timezone.utc).isoformat(), "stats": stats,
                                         "market": window, "macros": macros})
    write_json(output / "research_results.json", {"overview": overview, "glm_current": case, "glm_historical": historic,
               "glm_after_update": ResearchService(updated, market).detail(event["id"]) if update else None,
               "market": window, "update": {k: v for k, v in update.items() if k != "graph"} if update else None})
    write_json(ROOT / "docs" / "results" / "research_results.json", {"overview": overview, "glm_current": case,
               "glm_historical": historic, "market": window,
               "update": {k: v for k, v in update.items() if k != "graph"} if update else None})
    (ROOT / "docs" / "results" / "GLM5-研究简报.md").write_text(research.brief(event["id"])["markdown"], encoding="utf-8")
    if update:
        (ROOT / "docs" / "results" / "GLM5-更新后研究简报.md").write_text(
            ResearchService(updated, market).brief(event["id"])["markdown"], encoding="utf-8")
    print(json.dumps(macros, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    generate()
