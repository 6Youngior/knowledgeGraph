"""Independently locate cited factual excerpts on their original web pages.

Network failures and a failed text match are reported separately. A failure to
match HTML is a review flag, not automatic evidence that a fact is false.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
from datetime import datetime, timezone
from html import unescape
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from graph_store import normalized, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def verify(render_fallback=False):
    graph = read_json(ROOT / "data" / "knowledge_graph.json")
    sources = read_json(ROOT / "data" / "sources.json")
    cited = {}
    for edge in graph["edges"]:
        for source_id in edge["source_ids"]:
            cited.setdefault(source_id, []).append(edge)
    def quotes_for(edge, source_id):
        records = [r["evidence"] for r in edge.get("evidence_records", [])
                   if source_id in r.get("source_ids", []) and r.get("evidence")]
        return list(dict.fromkeys(records or [edge["evidence"]]))
    def fetch(source):
        result = {"source_id": source["id"], "url": source["url"], "facts": []}
        if source["id"] not in cited:
            return {**result, "status": "bibliography_only"}
        try:
            request = urllib.request.Request(source["url"], headers={"User-Agent": "Mozilla/5.0 FinGraph-course-research"})
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read(5_000_000)
                result["http_status"] = response.status
            result["sha256"] = hashlib.sha256(raw).hexdigest()
            if raw.startswith(b"%PDF"):
                import fitz
                with fitz.open(stream=raw, filetype="pdf") as pdf:
                    text = "\n".join(p.get_text() for p in pdf)
            else:
                text = raw.decode("utf-8", errors="replace")
                text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
                text = text.replace("\\n", "\n").replace("\\r", "\n")
                text = unescape(re.sub(r"<[^>]*>", " ", text))
            haystack = normalized(text)
            result["status"] = "fetched"
            for edge in cited[source["id"]]:
                quotes = quotes_for(edge, source["id"])
                found = next((q for q in quotes if normalized(q) in haystack), None)
                result["facts"].append({"edge_id": edge["id"], "located": found is not None,
                                        "evidence": found or quotes[0], "candidate_quotes": quotes})
        except Exception as exc:
            result.update(status="fetch_error", error=str(exc))
        return result
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(fetch, sources))
    if render_fallback:
        from playwright.sync_api import sync_playwright
        # These official sites inject the article body after their initial HTML.
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            for result in results:
                if not any(not fact["located"] for fact in result["facts"]):
                    continue
                try:
                    page.goto(result["url"], wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1800)
                    text = page.inner_text("body")
                    result["rendered_text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
                    result["rendered_chars"] = len(text)
                    for fact in result["facts"]:
                        if not fact["located"]:
                            found = next((q for q in fact["candidate_quotes"] if normalized(q) in normalized(text)), None)
                            if found:
                                fact["located"] = True
                                fact["evidence"] = found
                                fact["method"] = "rendered source page"
                except Exception as exc:
                    result["render_error"] = str(exc)
            browser.close()
    facts = [f for row in results for f in row["facts"]]
    by_edge = {e["id"]: any(f["located"] for f in facts if f["edge_id"] == e["id"]) for e in graph["edges"]}
    return {"created_at": datetime.now(timezone.utc).isoformat(), "sources": results,
            "located": sum(f["located"] for f in facts), "checked": len(facts),
            "verified_facts": sum(by_edge.values()), "total_facts": len(by_edge),
            "all_facts_located": all(by_edge.values()),
            "review_flags": [f["edge_id"] for f in facts if not f["located"]],
            "network_errors": [r["source_id"] for r in results if r["status"] == "fetch_error"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Render dynamically loaded official article bodies with Edge")
    result = verify(parser.parse_args().browser)
    write_json(ROOT / "docs" / "results" / "source_verification.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "sources"}, ensure_ascii=False, indent=2))
