"""Run a small real-model pilot on source-checked, explicitly scoped relations.

This is not a broad extraction benchmark: the model receives the entity registry
and the task evaluates only the focal model and relation types stated per case.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import time

from extraction import ExtractionService
from graph_store import GraphStore, normalized, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def run_case(case):
    store = GraphStore(ROOT / "data", persist=False)
    service = ExtractionService(store, ROOT)
    document = {**store.sources[case["document_id"]], "text": case["text"], "title": case["title"]}
    references = case.get("reference", [])
    for ref in references:
        if ref["source"] not in store.nodes or ref["target"] not in store.nodes:
            raise ValueError(f"Reference endpoint not in registry: {case['id']} {ref}")
        if normalized(ref.get("evidence", "")) not in normalized(case["text"]):
            raise ValueError(f"Reference evidence not in case text: {case['id']}")
    scope = case.get("relation_types") or sorted({r["type"] for r in references})
    focal = case.get("focus_entity_id")
    if not focal and references:
        model_endpoints = {r[k] for r in references for k in ("source", "target")
                           if store.nodes[r[k]]["type"] == "Model"}
        focal = next(iter(model_endpoints)) if len(model_endpoints) == 1 else None
    expected = {(r["source"], r["type"], r["target"]) for r in references}
    started = time.perf_counter()
    output = None
    try:
        raw, model = service._generate(service._prompt(document))
        parsed = service.parse_output(raw)
        output = store.align_extraction(parsed, document)
        all_predicted = {(r["source"], r["type"], r["target"]) for r in output["relations"]}
        predicted = {r for r in all_predicted if (not scope or r[1] in scope) and (not focal or focal in (r[0], r[2]))}
        error = None
    except Exception as exc:
        raw, model = locals().get("raw", ""), locals().get("model", "DeepSeek V4.1 Flash")
        predicted, all_predicted = set(), set()
        error = str(exc)
    tp, fp, fn = len(expected & predicted), len(predicted - expected), len(expected - predicted)
    return {"id": case["id"], "title": case["title"], "document_id": document["id"], "url": document["url"],
            "mode": "live", "model": model, "negative": case.get("negative", False),
            "scope": {"focus_entity_id": focal, "relation_types": scope or "all_schema_relations"},
            "expected": sorted(expected), "predicted": sorted(predicted), "all_predicted": sorted(all_predicted),
            "tp": tp, "fp": fp, "fn": fn, "error": error,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "raw_output": raw, "validation": output.get("validation") if output else None}


def evaluate(limit=6, workers=2):
    fixture = read_json(ROOT / "data" / "extraction_eval.json")
    cases = fixture["cases"][:limit]
    pending = [case["id"] for case in cases if case.get("reference_status") == "needs_review"]
    if pending:
        raise ValueError("参考关系尚未完成复核，未发起模型调用：" + ", ".join(pending))
    # Fail before calling the model if a source-checked reference is malformed.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_case, cases))
    tp, fp, fn = (sum(r[key] for r in results) for key in ("tp", "fp", "fn"))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else 0
    negatives = [r for r in results if r["negative"]]
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "live_model_called": True,
              "task": "指定模型与关系类型的定向关系抽取预实验", "case_count": len(results),
              "model": results[0]["model"] if results else None,
              "valid_outputs": sum(r["error"] is None for r in results),
              "counts": {"tp": tp, "fp": fp, "fn": fn},
              "micro_precision": precision, "micro_recall": recall, "micro_f1": f1,
              "negative_cases": len(negatives), "negative_false_positive_cases": sum(bool(r["predicted"]) for r in negatives),
              "limitations": ["规模小，仅用于期中预实验，不代表总体抽取性能。", "抽取器已获得实体目录；未评估开放域实体发现。",
                              "按逐例记录的目标模型和关系类型核对，不将范围外的正确关系计为误报。",
                              "参考三元组由项目构建者依据来源核对，尚未进行独立多人标注一致性研究。"],
              "results": results}
    write_json(ROOT / "docs" / "results" / "extraction_pilot.json", report)
    print({key: value for key, value in report.items() if key != "results"}, flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    evaluate(args.limit, args.workers)
