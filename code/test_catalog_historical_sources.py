"""Synthetic tests for the public historical-source catalogue."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from catalog_historical_sources import _day, build_catalog


def _record(source_id, event_id, body_name, body, version_time, published_at, status, title):
    return {
        "id": source_id,
        "event_id": event_id,
        "title": title,
        "publisher": "synthetic publisher",
        "url": f"https://example.test/{source_id}",
        "source_type": "synthetic",
        "published_at": published_at,
        "commit_time": version_time,
        "source_version_status": status,
        "cache_file": body_name,
        "text_path": body_name,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        "text_hash": hashlib.sha256(body.encode()).hexdigest(),
        "text_chars": len(body),
    }


class CatalogHistoricalSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / "private"
        self.cache.mkdir()
        self.metadata = self.root / "metadata.jsonl"
        self.output = self.root / "public"

        same = "DeepSeek-R1 synthetic historical README body"
        rows = [
            _record("ds-gh", "event:deepseek-r1-release", "ds-gh.md", same,
                    "2025-01-20T20:19:44+08:00", "2025-01-20T20:19:44+08:00",
                    "historical_commit", "DeepSeek GH"),
            _record("ds-hf", "event:deepseek-r1-release", "ds-hf.md", same,
                    "2025-01-20T12:26:50Z", "2025-01-20T12:26:50Z",
                    "historical_revision", "DeepSeek HF"),
            _record("glm-hf", "event:glm5-release", "glm.md", "GLM-5 synthetic body",
                    "2026-02-11T14:27:15Z", "2026-02-11T14:27:15Z",
                    "historical_revision", "GLM HF"),
            _record("qwen-hf", "event:qwen3-release", "qwen.md", "Qwen3 synthetic body",
                    "2025-04-28T15:41:30Z", "2025-04-28T15:41:30Z",
                    "historical_revision", "Qwen HF"),
            _record("zhipu-prospectus", "listing:zhipu-02513", "prospectus.md", "prospectus synthetic body",
                    "2025-12-30", "2025-12-30", "original_filing", "Prospectus"),
            _record("zhipu-annual", "listing:zhipu-02513", "annual.md", "annual synthetic body",
                    "2026-03-31", "2026-03-31", "retrospective_filing", "Annual"),
        ]
        bodies = {
            "ds-gh.md": same,
            "ds-hf.md": same,
            "glm.md": "GLM-5 synthetic body",
            "qwen.md": "Qwen3 synthetic body",
            "prospectus.md": "prospectus synthetic body",
            "annual.md": "annual synthetic body",
        }
        for row in rows:
            (self.cache / row["cache_file"]).write_text(
                bodies[row["cache_file"]], encoding="utf-8"
            )
        self.metadata.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                                  encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_duplicate_body_is_one_bodily_record_but_two_sources(self):
        manifest = build_catalog(self.metadata, self.cache, self.output)
        self.assertEqual(manifest["sources"], 6)
        self.assertEqual(manifest["independent_bodies"], 5)
        self.assertEqual(manifest["duplicate_sources"], 1)
        self.assertEqual(len(manifest["duplicate_body_groups"]), 1)
        sources = [json.loads(line) for line in (self.output / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
        bodies = [json.loads(line) for line in (self.output / "bodies.jsonl").read_text(encoding="utf-8").splitlines()]
        by_id = {row["source_id"]: row for row in sources}
        self.assertEqual(by_id["ds-gh"]["body_group_id"], by_id["ds-hf"]["body_group_id"])
        group = next(row for row in bodies if row["source_count"] == 2)
        self.assertEqual(group["source_ids"], ["ds-gh", "ds-hf"])
        self.assertEqual(len(group["urls"]), 2)

    def test_available_at_uses_release_date_not_earlier_revision_date(self):
        manifest = build_catalog(self.metadata, self.cache, self.output)
        sources = {row["source_id"]: row for row in
                   (json.loads(line) for line in (self.output / "sources.jsonl").read_text(encoding="utf-8").splitlines())}
        self.assertEqual(sources["glm-hf"]["version_date"], "2026-02-11")
        self.assertEqual(sources["glm-hf"]["available_at"], "2026-02-12")
        self.assertEqual(sources["qwen-hf"]["version_date"], "2025-04-28")
        self.assertEqual(sources["qwen-hf"]["available_at"], "2025-04-29")
        self.assertEqual(sources["ds-gh"]["available_at"], "2025-01-20")
        self.assertEqual(sources["ds-hf"]["available_at"], "2025-01-20")
        self.assertEqual(sources["zhipu-prospectus"]["available_at"], "2025-12-30")
        self.assertEqual(sources["zhipu-annual"]["available_at"], "2026-03-31")
        self.assertEqual(sources["glm-hf"]["availability_status"], "release_date_assumption")
        self.assertFalse(sources["glm-hf"]["eligible_for_strict_replay"])
        self.assertEqual(sources["qwen-hf"]["availability_status"], "release_date_assumption")
        self.assertFalse(sources["qwen-hf"]["eligible_for_strict_replay"])
        self.assertEqual(sources["zhipu-prospectus"]["availability_status"], "original_filing_date")
        self.assertTrue(sources["zhipu-prospectus"]["eligible_for_strict_replay"])
        self.assertEqual(sources["zhipu-annual"]["availability_status"], "original_filing_date")
        self.assertTrue(sources["zhipu-annual"]["eligible_for_strict_replay"])
        self.assertIn("https://z.ai/blog/glm-5", sources["glm-hf"]["date_basis"])
        self.assertEqual(sources["glm-hf"]["official_release_url"], "https://z.ai/blog/glm-5")
        self.assertIn("https://qwenlm.github.io/blog/qwen3/", sources["qwen-hf"]["date_basis"])
        self.assertIn("https://api-docs.deepseek.com/news/news250120/", sources["ds-gh"]["date_basis"])
        self.assertEqual(manifest["strict_replay_eligible_count"], 2)
        self.assertEqual(manifest["release_date_assumption_count"], 4)

    def test_public_catalog_has_no_bodies_or_private_paths(self):
        build_catalog(self.metadata, self.cache, self.output)
        text = (self.output / "sources.jsonl").read_text(encoding="utf-8") + \
               (self.output / "bodies.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(str(self.cache), text)
        self.assertNotIn("synthetic historical README body", text)
        self.assertNotIn("GLM-5 synthetic body", text)
        self.assertNotIn("cache_file", text)
        self.assertNotIn("text_path", text)
        records = [json.loads(line) for line in (self.output / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
        for record in records:
            self.assertFalse(record["intraday_claim"])
            self.assertEqual(len(record["available_at"]), 10)
            self.assertIsNone(record["intraday_available_at"])
            self.assertNotIn("text", record)
            self.assertNotIn("can_prove_historical_publication", record)

    def test_day_validation_and_cross_utc_day(self):
        self.assertEqual(_day("2025-01-20"), "2025-01-20")
        self.assertEqual(_day("2025-01-20T20:19:44+08:00"), "2025-01-20")
        self.assertEqual(_day("2026-02-11T20:00:00Z"), "2026-02-12")
        with self.assertRaises(ValueError):
            _day("2026-02-30")
        with self.assertRaises(ValueError):
            _day("2026-02-11T20:00:00")

    def test_mismatched_private_hash_is_rejected(self):
        rows = [json.loads(line) for line in self.metadata.read_text(encoding="utf-8").splitlines()]
        rows[0]["content_hash"] = "0" * 64
        self.metadata.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        with self.assertRaises(ValueError):
            build_catalog(self.metadata, self.cache, self.output)

    def test_private_path_cannot_escape_cache_dir(self):
        rows = [json.loads(line) for line in self.metadata.read_text(encoding="utf-8").splitlines()]
        rows[0]["cache_file"] = "../outside.md"
        self.metadata.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        with self.assertRaises(ValueError):
            build_catalog(self.metadata, self.cache, self.output)


if __name__ == "__main__":
    unittest.main()
