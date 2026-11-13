"""Plan bounded corpus extraction, save model proposals, and ingest reviewed facts.

Reuses the document preparer, ExtractionService and GraphStore. Planning is
offline; running a plan calls the configured model. Nothing is auto-ingested.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from extraction import ExtractionService
from graph_store import GraphStore, read_json
from prepare_documents import read_records

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def local_path(directory, name):
    directory = Path(directory).resolve()
    path = (directory / name).resolve()
    if not path.is_relative_to(directory):
        raise ValueError("prepared file must remain inside its batch directory")
    return path


def relevance(text):
    """Select passages for review, without claiming the keywords are facts."""
    compact = re.sub(r"\s+", "", text)
    # Financial tables often refer back to the business section by its exact
    # heading. That reference is not itself a description of the business.
    compact = re.sub(r"参见[^。]{0,120}相关内容", "", compact)
    headings = ["主营业务", "主要业务", "主要产品", "核心产品", "公司产品", "公司主要"]
    if len(text) < 300 or not any(word in compact for word in headings):
        return 0
    score = 10 * sum(word in compact for word in headings) + sum(
        min(compact.count(word), 3) for word in ["芯片", "CPU", "DCU", "GPU", "服务器", "光模块", "产品", "研发"])
    # A report's risk or financial discussion can repeat more product words
    # than the actual business description. Prefer explicit business sections.
    if re.search(r"报告期内公司从事的主要业务|报告期内公司所属行业及主营业务情况", compact):
        score += 200
    if re.search(r"公司的主要产品|主要产品及[^。]{0,20}用途", compact):
        score += 60
    if re.search(r"公司主要从事|公司主营业务为|公司的主营业务是", compact):
        score += 40
    if re.search(r"公司面临的风险|风险和应对措施|主要风险因素|重大风险提示", compact[:500]):
        score -= 150
    return max(score, 0)


def plan_extraction(inputs, *, limit=8, per_document=2, universe=None):
    if not 1 <= limit <= 200 or not 1 <= per_document <= 4:
        raise ValueError("limit must be 1..200; per_document must be 1..4")
    issuers = {row["symbol"]: row["name"] for row in (universe or {}).get("securities", [])}
    by_hash = {}
    for directory in inputs:
        directory = Path(directory)
        chunks = {}
        for chunk in read_records(directory / "chunks.jsonl"):
            chunks.setdefault(chunk["source_id"], []).append(chunk)
        for doc in read_records(directory / "documents.jsonl"):
            if not doc.get("complete"):
                continue
            body = local_path(directory, doc["text_file"]).read_text(encoding="utf-8")
            if hashlib.sha256(body.encode()).hexdigest() != doc["text_sha256"]:
                raise ValueError("prepared document hash mismatch")
            pages = {p["page"]: p["text"] for p in read_records(local_path(directory, doc["pages_file"]))}
            reconstructed = "\n\n".join(pages[number].strip() for number in sorted(pages)).strip()
            if hashlib.sha256(reconstructed.encode()).hexdigest() != doc["text_sha256"]:
                raise ValueError("prepared pages do not match the document body")
            candidates = []
            for chunk in chunks.get(doc["id"], []):
                score = relevance(chunk["text"])
                if not score:
                    continue
                page = pages[chunk["page"]]
                if page[chunk["char_start"]:chunk["char_end"]] != chunk["text"]:
                    raise ValueError("chunk does not match original page offsets")
                source = {k: v for k, v in doc.items() if k not in {"text_file", "pages_file"}}
                source.update({"id": chunk["id"], "parent_document_id": doc["id"],
                               "title": f"{doc['title']}（第{chunk['page']}页）",
                               "url": doc["url"].split("#", 1)[0] + f"#page={chunk['page']}",
                               "text": chunk["text"], "page": chunk["page"],
                               "char_start": chunk["char_start"], "char_end": chunk["char_end"],
                               "issuer_name": issuers.get(doc["symbol"], "")})
                candidates.append((score, chunk["page"], chunk["char_start"], source))
            candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
            # Don't select overlapping passages of the same page twice.
            chosen = []
            for _, _, _, source in candidates:
                if any(old["page"] == source["page"] and
                       max(old["char_start"], source["char_start"]) < min(old["char_end"], source["char_end"])
                       for old in chosen):
                    continue
                chosen.append(source)
                if len(chosen) == per_document:
                    break
            key = doc["text_sha256"]
            old = by_hash.get(key)
            trusted = doc.get("version_status") in {"original_filing", "archived_version"}
            if old is None or (trusted and not old[0]):
                by_hash[key] = (trusted, doc, chosen)
    companies = {}
    for _, doc, chosen in sorted(by_hash.values(), key=lambda item: (
            item[1].get("published_at") or "", item[1]["id"]), reverse=True):
        companies.setdefault(doc["symbol"], []).extend(chosen)
    selected = []
    while len(selected) < limit and any(companies.values()):
        for symbol in sorted(companies):
            if companies[symbol] and len(selected) < limit:
                selected.append(companies[symbol].pop(0))
    return {"schema_version": "corpus-extraction-plan-v1", "passages": selected,
            "documents": len({s["parent_document_id"] for s in selected}),
            "companies": len({s["symbol"] for s in selected})}


def require_current_source(parsed, document):
    for row in [*parsed["entities"], *parsed["relations"]]:
        if row.get("source_ids", [document["id"]]) != [document["id"]]:
            raise ValueError("batch facts must cite only the current passage")
    if parsed.get("events"):
        raise ValueError("this batch extracts business relations; events require separate review")


def run_plan(plan, output, service, *, continue_invalid=False):
    """Serial calls; resume only byte-identical documents and model IDs."""
    output = Path(output)
    completed = []
    for document in plan["passages"]:
        key = digest({"document": document, "model": service.model,
                      "prompt": service._prompt(document)})
        path = output / "results" / (key + ".json")
        if path.exists():
            prior = read_json(path)
            if prior.get("request_digest") != key or prior.get("document") != document:
                raise ValueError("cached extraction identity mismatch")
            completed.append({"file": path.name, "status": prior["status"], "resumed": True})
            if prior["status"] == "failed" and not (
                    continue_invalid and prior.get("error_type") in {"ValueError", "JSONDecodeError"}):
                break
            continue
        result = {"request_digest": key, "document": document, "model": service.model,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            raw, model = service._generate(service._prompt(document))
            result.update({"raw_output": raw, "model": model})
            parsed = service.parse_output(raw)
            require_current_source(parsed, document)
            result["parsed"] = copy.deepcopy(parsed)
            result["aligned"] = service.store.align_extraction(parsed, document)
            result["status"] = "needs_review"
        except Exception as error:
            # Don't save HTTP request headers or provider response bodies.
            result.update({"status": "failed", "error_type": type(error).__name__, "error": str(error)})
        write(path, result)
        completed.append({"file": path.name, "status": result["status"], "resumed": False})
        print(json.dumps({"source": document["id"], "status": result["status"]}), flush=True)
        if result["status"] == "failed" and not (
                continue_invalid and result.get("error_type") in {"ValueError", "JSONDecodeError"}):
            break
    manifest = {"planned": len(plan["passages"]), "results": completed,
                "automatically_ingested": 0}
    write(output / "run.json", manifest)
    return manifest


def ingest_reviewed(results_dir, review, store):
    """Require an exact file hash and selected relations for every approval."""
    accepted, seen = [], set()
    for item in review["reviews"]:
        if item["decision"] != "accept":
            continue
        path = local_path(results_dir, item["file"])
        if path in seen:
            raise ValueError("duplicate reviewed extraction")
        seen.add(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("reviewed extraction has changed")
        record = read_json(path)
        if record["status"] != "needs_review" or not item.get("reviewer") or not item.get("note"):
            raise ValueError("approval needs a successful extraction, reviewer and note")
        selected = set(item.get("relation_ids", []))
        original = record["aligned"]["relations"]
        if not selected or not selected <= {r["id"] for r in original}:
            raise ValueError("approval must select existing relations explicitly")
        payload = copy.deepcopy(record["aligned"])
        payload["relations"] = [r for r in original if r["id"] in selected]
        connected = {r[k] for r in payload["relations"] for k in ("source", "target")}
        payload["entities"] = [n for n in payload["entities"] if n["id"] in connected]
        # Revalidate against the current graph, not just cached model output.
        payload = store.align_extraction(payload, record["document"])
        payload["document"] = record["document"]
        accepted.append(payload)
    changes = [store.ingest(payload) for payload in accepted]
    return {"accepted_extractions": len(changes), "stats": store.stats()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="offline passage selection")
    plan.add_argument("--inputs", nargs="+", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--limit", type=int, default=8)
    plan.add_argument("--per-document", type=int, default=2)
    plan.add_argument("--universe", type=Path, default=ROOT / "data/universe.json")
    run = commands.add_parser("run", help="calls the configured model; does not ingest")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--data-dir", type=Path, default=ROOT / "data")
    run.add_argument("--continue-invalid", action="store_true", help="skip invalid proposals; provider errors still stop the batch")
    ingest = commands.add_parser("ingest", help="ingest only explicitly reviewed relations")
    ingest.add_argument("--results", type=Path, required=True)
    ingest.add_argument("--review", type=Path, required=True)
    ingest.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    if args.command == "plan":
        value = plan_extraction(args.inputs, limit=args.limit, per_document=args.per_document,
                                universe=read_json(args.universe, {}))
        write(args.output, value)
        print(json.dumps({k: v for k, v in value.items() if k != "passages"}, ensure_ascii=False))
    elif args.command == "run":
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        service = ExtractionService(GraphStore(args.data_dir, persist=False, read_runtime=True), ROOT)
        if not (service.base_url and service.api_key):
            parser.error("batch extraction requires the configured API and shared token budget")
        print(json.dumps(run_plan(read_json(args.plan), args.output, service,
                                  continue_invalid=args.continue_invalid), ensure_ascii=False))
    else:
        print(json.dumps(ingest_reviewed(args.results, read_json(args.review),
                                        GraphStore(args.data_dir)), ensure_ascii=False))


if __name__ == "__main__":
    main()
