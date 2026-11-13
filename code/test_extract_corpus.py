import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from extract_corpus import ingest_reviewed, plan_extraction, relevance, run_plan, write
from extraction import ExtractionService
from graph_store import GraphStore
from llm_budget import TokenBudget


class CorpusExtractionTests(unittest.TestCase):
    def test_business_section_precedes_keyword_dense_risk_discussion(self):
        business = "报告期内公司从事的主要业务。公司主营业务为服务器研发、生产及销售。" + "本期提供计算设备与服务。" * 30
        risk = "公司面临的风险和应对措施。" + "公司主要产品服务器、GPU芯片、CPU芯片的研发和主营业务面临市场风险。" * 15
        self.assertGreater(relevance(business), relevance(risk))
        self.assertEqual(relevance("重大风险提示。" + risk), 0)
        reference = '三、主营业务分析。概述参见“一、报告期内公司从事的主要业务”相关内容。' + "营业收入和毛利率同比变动情况。" * 30
        self.assertGreater(relevance(business), relevance(reference))
        shanghai = "一、报告期内公司所属行业及主营业务情况说明。公司主要从事集成电路设计。" + "本期提供芯片产品。" * 35
        self.assertGreater(relevance(shanghai), relevance(reference))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.store = GraphStore(self.data)
        self.source = {"id": "src:report:p1:0", "parent_document_id": "src:report",
                       "title": "甲公司年报", "text": "甲公司主要产品包括甲芯片。",
                       "published_at": "2025-03-01", "retrieved_at": "2026-11-12T00:00:00Z",
                       "available_at": "2025-03-01", "version_status": "original_filing"}
        self.parsed = {"entities": [
            {"id": "company:a", "label": "甲公司", "type": "Company"},
            {"id": "product:a", "label": "甲芯片", "type": "Product"}],
            "relations": [{"source": "company:a", "target": "product:a", "type": "PRODUCES",
                           "evidence": "甲公司主要产品包括甲芯片。"}], "events": []}

    def test_offline_plan_balances_companies_and_checks_page_offsets(self):
        prepared = self.root / "prepared"
        docs, chunks = [], []
        for symbol in ["000001.SZ", "000002.SZ"]:
            name = symbol[:6]
            body = "公司的主要产品为服务器，产品由公司研发。" * 25
            write(prepared / f"pages/{name}.json", [{"page": 1, "text": body}])
            (prepared / f"{name}.txt").write_text(body, encoding="utf-8")
            docs.append({"id": name, "symbol": symbol, "title": name, "complete": True,
                         "url": "https://example.com/report.pdf", "text_file": f"{name}.txt",
                         "pages_file": f"pages/{name}.json", "published_at": "2025-03-01",
                         "text_sha256": hashlib.sha256(body.encode()).hexdigest()})
            # Two different prepared PDFs with identical text count as one document.
            chunks.append({"id": name + ":p1:0", "source_id": name, "page": 1,
                           "char_start": 0, "char_end": len(body), "text": body})
        # Make the second document distinct to test balancing.
        second = "公司主营业务为GPU芯片设计。" * 25
        (prepared / "000002.txt").write_text(second, encoding="utf-8")
        write(prepared / "pages/000002.json", [{"page": 1, "text": second}])
        docs[1]["text_sha256"] = hashlib.sha256(second.encode()).hexdigest()
        chunks[1].update(text=second, char_end=len(second))
        for name, rows in [("documents", docs), ("chunks", chunks)]:
            (prepared / (name + ".jsonl")).write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        plan = plan_extraction([prepared], limit=2)
        self.assertEqual(plan["companies"], 2)
        self.assertEqual([d["symbol"] for d in plan["passages"]], ["000001.SZ", "000002.SZ"])
        chunks[1]["char_end"] -= 1
        (prepared / "chunks.jsonl").write_text("\n".join(json.dumps(r) for r in chunks), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "offsets"):
            plan_extraction([prepared])

    def test_run_resume_review_tamper_and_idempotent_ingestion(self):
        service = ExtractionService(self.store, self.root)
        out = self.root / "run"
        plan = {"passages": [self.source]}
        with patch.object(service, "_generate", return_value=(json.dumps(self.parsed), service.model)) as generate:
            manifest = run_plan(plan, out, service)
            self.assertEqual(generate.call_count, 1)
            run_plan(plan, out, service)
            self.assertEqual(generate.call_count, 1)
        self.assertFalse(self.store.edges)
        file = manifest["results"][0]["file"]
        path = out / "results" / file
        record = json.loads(path.read_text(encoding="utf-8"))
        review = {"reviews": [{"file": file, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "decision": "accept", "reviewer": "test", "note": "原文明示公司产品",
                  "relation_ids": [record["aligned"]["relations"][0]["id"]]}]}
        ingest_reviewed(path.parent, review, self.store)
        ingest_reviewed(path.parent, review, self.store)
        self.assertEqual(len(self.store.edges), 1)
        from research_tools import ResearchTools
        earlier = ResearchTools(self.data, "2024-12-31")
        self.assertEqual(earlier.overview()["knowledge"]["relations"], 0)
        self.assertEqual(earlier.entity_relations("company:a"), earlier.entity_relations("missing"))
        current = ResearchTools(self.data, "2026-11-01").entity_relations("company:a")
        self.assertEqual(current["relations"][0]["target"]["label"], "甲芯片")
        self.assertEqual(current["relations"][0]["evidence"][0]["quote"], "甲公司主要产品包括甲芯片。")
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            ingest_reviewed(path.parent, review, self.store)

    def test_failed_call_stops_without_ingestion(self):
        service = ExtractionService(self.store, self.root)
        with patch.object(service, "_generate", side_effect=ValueError("bad JSON")) as generate:
            result = run_plan({"passages": [self.source, {**self.source, "id": "other"}]}, self.root, service)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result["results"][0]["status"], "failed")
        self.assertEqual(len(self.store.edges), 0)

    def test_report_pronouns_cannot_merge_unrelated_companies(self):
        first = self.store.align_extraction(self.parsed, self.source)
        first["entities"][0]["aliases"] = ["公司", "本公司"]
        # Incoming data must be validated before ingestion, as the batch does.
        first = self.store.align_extraction(first, self.source)
        first["document"] = self.source
        self.store.ingest(first)
        second = {"entities": [{"id": "company:b", "label": "乙公司", "type": "Company",
                                 "aliases": ["本公司", "公司"]}], "relations": [], "events": []}
        result = self.store.align_extraction(second, self.source)
        self.assertEqual(result["entities"][0]["id"], "company:b")
        self.assertEqual(result["entities"][0]["aliases"], [])


class ExtractionTransportTests(unittest.TestCase):
    def test_go_session_is_stable_and_usage_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "LLM_BASE_URL": "https://opencode.ai/inference/go/openai/v1", "LLM_API_KEY": "test-only",
                "FINGRAPH_LLM_TEST_TOKEN_LIMIT": "100000"}):
            root = Path(directory)
            service = ExtractionService(GraphStore(root / "data", persist=False), root)
            requests = []
            def handler(request):
                requests.append(request)
                return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}],
                                                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
            client = httpx.Client(transport=httpx.MockTransport(handler))
            with patch("extraction.httpx.Client", return_value=client):
                service._generate("first")
            client = httpx.Client(transport=httpx.MockTransport(handler))
            with patch("extraction.httpx.Client", return_value=client):
                service._generate("second")
            self.assertEqual(requests[0].headers["x-opencode-session"], requests[1].headers["x-opencode-session"])
            self.assertEqual(requests[0].headers["user-agent"], "FinGraphAgent/0.2.0")
            self.assertEqual(TokenBudget(root / ".fingraph/usage.sqlite").snapshot()["reported_tokens"], 24)


if __name__ == "__main__":
    unittest.main()
