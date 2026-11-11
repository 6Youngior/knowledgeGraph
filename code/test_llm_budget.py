"""Budget accounting uses synthetic usage and never calls a model."""
import tempfile
import unittest
from pathlib import Path

from llm_budget import TokenBudget


class TokenBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "usage.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def test_pending_reservations_count_across_instances(self):
        first = TokenBudget(self.path, limit=4000)
        second = TokenBudget(self.path, limit=4000)
        first.reserve("test", "synthetic", 1000, 1000)
        with self.assertRaisesRegex(RuntimeError, "预算不足"):
            second.reserve("test", "synthetic", 0, 0)
        self.assertEqual(second.snapshot()["reserved_tokens"], 3024)

    def test_reported_usage_replaces_reservation_once(self):
        budget = TokenBudget(self.path, limit=4000)
        request_id = budget.reserve("test", "synthetic", 10, 10)
        budget.complete(request_id, {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})
        budget.complete(request_id, {"total_tokens": 1})
        self.assertEqual(budget.snapshot()["reported_tokens"], 120)
        self.assertEqual(budget.snapshot()["reserved_tokens"], 0)

    def test_missing_usage_is_not_free(self):
        budget = TokenBudget(self.path, limit=4000)
        request_id = budget.reserve("test", "synthetic", 10, 10)
        budget.complete(request_id, {})
        self.assertEqual(budget.snapshot()["reserved_tokens"], 1044)
        self.assertEqual(budget.snapshot()["reported_tokens"], 0)
