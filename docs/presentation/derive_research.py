"""Derive presentation macros from the actual graph, market cache and audit results.

Writes docs/presentation/derived/research.tex.  No hand-entered statistics:
counts, symbols, anchors and returns come from data/ and docs/results/.
Run from anywhere: python docs/presentation/derive_research.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))

from graph_store import GraphStore  # noqa: E402
from market import MarketData  # noqa: E402

OUT = Path(__file__).resolve().parent / "derived"
OUT.mkdir(parents=True, exist_ok=True)


def pct(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value * 100:+.2f}\\%"


def syms(stocks: list[dict]) -> str:
    return "、".join(s["symbol"] for s in stocks)


def count_group(stocks: list[dict], group: str) -> int:
    return sum(1 for s in stocks if s.get("relation_group") == group)


def main() -> None:
    store = GraphStore(ROOT / "data", persist=False)
    market = MarketData(ROOT / "data")
    events = store.events

    glm = events["event:glm5-release"]
    mini = events["event:minimax-m25-release"]
    adapt = events["event:mtt-minimax-adapt"]
    ds = events["event:deepseek-r1-release"]
    qwen = events["event:qwen3-release"]

    glm_now = store.related_stocks(glm["id"])
    glm_then = store.related_stocks(glm["id"], as_of=glm["date"])
    mini_now = store.related_stocks(mini["id"])
    mini_then = store.related_stocks(mini["id"], as_of=mini["date"])
    adapt_now = store.related_stocks(adapt["id"])
    adapt_then = store.related_stocks(adapt["id"], as_of=adapt["date"])
    ds_now = store.related_stocks(ds["id"])
    ds_start = store.related_stocks(ds["id"], as_of=ds["date"])
    ds_feb3 = store.related_stocks(ds["id"], as_of="2025-02-03")
    ds_feb5 = store.related_stocks(ds["id"], as_of="2025-02-05")
    qwen_now = store.related_stocks(qwen["id"])
    qwen_then = store.related_stocks(qwen["id"], as_of=qwen["date"])

    audit = json.loads((ROOT / "docs" / "results" / "data_audit.json").read_text(encoding="utf-8"))
    update = (audit.get("updates") or [{}])[0]
    new_nodes = update.get("added_nodes", 0)
    new_edges = update.get("added_edges", 0)
    new_glm = (update.get("new_stocks") or {}).get(glm["id"], [])
    glm_after = glm_now + [{"symbol": s} for s in new_glm if s not in {x["symbol"] for x in glm_now}]
    roles = lambda xs: len({x.get("relation_group") for x in xs})

    def window(symbol: str, event: dict) -> dict:
        try:
            return market.event_window(symbol, event)
        except Exception:
            return {}

    glm_w = window("02513.HK", glm)
    ali_w = window("09988.HK", glm)
    mini_w = window("00100.HK", mini)
    adapt_w = window("688795.SH", adapt)

    paths = {
        "GLM": glm_now,
        "MiniMax": mini_now,
        "Adapt": adapt_now,
    }
    total_paths = sum(len(v) for v in paths.values())
    max_hops = max(
        (len(s.get("path", {}).get("nodes", [])) - 1 for v in paths.values() for s in v),
        default=0,
    )

    macros: dict[str, str] = {
        "EntityTypeCount": str(len({n["type"] for n in store.nodes.values()})),
        "RelationTypeCount": str(len({e["type"] for e in store.edges.values()})),
        "TotalPathCount": str(total_paths),
        "MaxHops": str(max_hops),
        "GLMCurrentStocks": str(len(glm_now)),
        "GLMHistoricalStocks": str(len(glm_then)),
        "LiveNodeCount": str(len(store.nodes)),
        "LiveEdgeCount": str(len(store.edges)),
        "LiveSourceCount": str(len(store.sources)),
        "LiveEventCount": str(len(store.events)),
        "LiveStockCount": str(sum(1 for n in store.nodes.values() if n["type"]=="Stock")),
        "LiveModelCount": str(sum(1 for n in store.nodes.values() if n["type"]=="Model")),
        "GLMCurrentPaths": str(len(glm_now)),
        "DeepSeekStartStocks": str(len(ds_start)),
        "DeepSeekFebThreeStocks": str(len(ds_feb3)),
        "DeepSeekFebFiveStocks": str(len(ds_feb5)),
        "DeepSeekCurrentStocks": str(len(ds_now)),
        "DeepSeekFebThreeSymbols": syms(ds_feb3),
        "DeepSeekFebFiveSymbols": syms(ds_feb5),
        "DeepSeekCurrentSymbols": syms(ds_now),
        "QwenEventStocks": str(len(qwen_then)),
        "QwenCurrentStocks": str(len(qwen_now)),
        "QwenEventSymbols": syms(qwen_then),
        "QwenCurrentSymbols": syms(qwen_now),
        "GLMHistoricalPaths": str(len(glm_then)),
        "GLMCurrentRoles": str(roles(glm_now)),
        "GLMHistoricalRoles": str(roles(glm_then)),
        "GLMAfterUpdatePaths": str(len(glm_after)),
        "MiniMaxCurrentPaths": str(len(mini_now)),
        "MiniMaxHistoricalPaths": str(len(mini_then)),
        "MiniMaxExcludedCount": str(len(mini_now)-len(mini_then)),
        "AdaptCurrentPaths": str(len(adapt_now)),
        "AdaptHistoricalPaths": str(len(adapt_then)),
        "GLMAfterUpdateStocks": str(len(glm_after)),
        "GLMCurrentSymbols": syms(glm_now),
        "GLMHistoricalSymbols": syms(glm_then),
        "GLMAfterUpdateSymbols": syms(glm_after),
        "GLMDirectCount": str(count_group(glm_now, "direct")),
        "GLMDistributionCount": str(count_group(glm_now, "distribution")),
        "MiniMaxCurrentStocks": str(len(mini_now)),
        "MiniMaxHistoricalStocks": str(len(mini_then)),
        "MiniMaxCurrentSymbols": syms(mini_now),
        "MiniMaxHistoricalSymbols": syms(mini_then),
        "AdaptCurrentStocks": str(len(adapt_now)),
        "AdaptHistoricalStocks": str(len(adapt_then)),
        "AdaptCurrentSymbols": syms(adapt_now),
        "AdaptHistoricalSymbols": syms(adapt_then),
        "UpdateNewNodes": str(new_nodes),
        "UpdateNewEdges": str(new_edges),
        "UpdateNewStocks": str(len(new_glm)),
        "UpdateNewStockSymbols": "、".join(new_glm),
        "GLMReleaseDate": glm["date"],
        "MiniMaxReleaseDate": mini["date"],
        "AdaptReleaseDate": adapt["date"],
        "GLMAnchorDateDerived": glm_w.get("anchor_date", "--"),
        "MiniMaxAnchorDate": mini_w.get("anchor_date", "--"),
        "AdaptAnchorDate": adapt_w.get("anchor_date", "--"),
        "GLMReturnOneD": pct(glm_w.get("returns", {}).get("1")),
        "GLMReturnThreeD": pct(glm_w.get("returns", {}).get("3")),
        "GLMReturnFiveD": pct(glm_w.get("returns", {}).get("5")),
        "AliReturnOneD": pct(ali_w.get("returns", {}).get("1")),
        "AliReturnThreeD": pct(ali_w.get("returns", {}).get("3")),
        "AliReturnFiveD": pct(ali_w.get("returns", {}).get("5")),
        "GLMExcessOneD": pct(glm_w.get("excess_returns", {}).get("1")),
        "GLMExcessThreeD": pct(glm_w.get("excess_returns", {}).get("3")),
        "GLMExcessFiveD": pct(glm_w.get("excess_returns", {}).get("5")),
        "AliExcessOneD": pct(ali_w.get("excess_returns", {}).get("1")),
        "AliExcessThreeD": pct(ali_w.get("excess_returns", {}).get("3")),
        "AliExcessFiveD": pct(ali_w.get("excess_returns", {}).get("5")),
        "HSIReturnOneD": pct(glm_w.get("benchmark_returns", {}).get("1")),
        "HSIReturnThreeD": pct(glm_w.get("benchmark_returns", {}).get("3")),
        "HSIReturnFiveD": pct(glm_w.get("benchmark_returns", {}).get("5")),
        "MiniMaxReturnOneD": pct(mini_w.get("returns", {}).get("1")),
        "MiniMaxReturnThreeD": pct(mini_w.get("returns", {}).get("3")),
        "MiniMaxReturnFiveD": pct(mini_w.get("returns", {}).get("5")),
        "AdaptReturnOneD": pct(adapt_w.get("returns", {}).get("1")),
        "AdaptReturnThreeD": pct(adapt_w.get("returns", {}).get("3")),
        "AdaptReturnFiveD": pct(adapt_w.get("returns", {}).get("5")),
    }

    lines = [
        "% Derived from the actual graph, market cache and audit output; do not hand-edit.",
        "% Regenerate with: python docs/presentation/derive_research.py",
    ]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    (OUT / "research.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT / 'research.tex'} ({len(macros)} macros)")


if __name__ == "__main__":
    main()




