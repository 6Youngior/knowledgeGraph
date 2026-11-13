import json
import tempfile
import unittest
from pathlib import Path

from quant_tools import QuantResearch
from fastapi.testclient import TestClient
from app import create_app


class QuantResearchTests(unittest.TestCase):
    def test_early_date_hides_result_and_current_ranking_keeps_ties(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            data = {"schema_version": "quant-baseline-v1", "available_at": "2024-02-02",
                    "feature_as_of": "2024-02-01", "model": "fixture", "engine": "Qlib",
                    "horizon_trading_days": 5, "capture": {"stocks": [{}, {}]}, "segments": {},
                    "latest_ranking": [{"rank": 1, "symbol": "A", "score": 0.3},
                                       {"rank": 1, "symbol": "B", "score": 0.3}]}
            path.write_text(json.dumps(data), encoding="utf-8")
            early = QuantResearch(path, "2024-02-01").analyze()
            missing = QuantResearch(path.parent / "absent", "2024-02-01").analyze()
            self.assertEqual(early, missing)
            now = QuantResearch(path, "2024-02-02").analyze(limit=2)
            self.assertEqual([row["rank"] for row in now["ranking"]], [1, 1])
            self.assertEqual(now["feature_as_of"], "2024-02-01")
            (path.parent / "quant").mkdir()
            (path.parent / "quant/baseline.json").write_bytes(path.read_bytes())
            (path.parent / "knowledge_graph.json").write_text('{"nodes":[],"edges":[],"events":[]}', encoding="utf-8")
            (path.parent / "sources.json").write_text('[]', encoding="utf-8")
            with TestClient(create_app(path.parent, persist=False)) as client:
                hidden = client.get("/api/quant?view=ranking&as_of=2024-02-01")
                self.assertEqual(hidden.status_code, 200)
                self.assertFalse(hidden.json()["found"])
                current = client.get("/api/quant?view=ranking&limit=50&as_of=2024-02-02")
                self.assertEqual(current.status_code, 200)
                self.assertEqual(current.json()["ranking"], now["ranking"])
                self.assertEqual(client.get("/api/quant?view=unknown").status_code, 422)
                self.assertEqual(client.get("/api/quant?as_of=2024-02-31").status_code, 422)

    def test_invalid_or_nonfinite_results_are_not_served(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            path.write_text('{"schema_version":"quant-baseline-v1","score":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-finite"):
                QuantResearch(path, "2024-02-02").analyze()
            with self.assertRaises(ValueError):
                QuantResearch(path, "2024-02-30")


if __name__ == "__main__":
    unittest.main()
