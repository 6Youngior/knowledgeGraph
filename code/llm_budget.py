"""Project-local, transactional token accounting shared with the Pi client."""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = Path(__file__).with_name("llm_usage.sql").read_text(encoding="utf-8")


class TokenBudget:
    def __init__(self, path=None, limit=None):
        self.path = Path(path or ROOT / ".fingraph" / "usage.sqlite")
        self.limit = int(limit if limit is not None else os.getenv("FINGRAPH_LLM_TEST_TOKEN_LIMIT", "1000000"))
        if self.limit <= 0:
            raise ValueError("测试 token 上限必须为正数")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.executescript(SCHEMA)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @staticmethod
    def _charged(db):
        return int(db.execute("SELECT COALESCE(SUM(COALESCE(total_tokens, reserved_tokens)), 0) FROM llm_requests").fetchone()[0])

    def reserve(self, model, purpose, input_bytes, max_output_tokens, run_id="python"):
        # UTF-8 byte count plus message overhead is a conservative input bound.
        reserve = max(0, int(input_bytes)) + max(0, int(max_output_tokens)) + 1024
        request_id = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if self._charged(db) + reserve > self.limit:
                    raise RuntimeError("测试 token 预算不足，未发起模型调用；扩大额度前请先确认。")
                db.execute(
                    "INSERT INTO llm_requests(request_id,run_id,model,purpose,started_at,reserved_tokens) VALUES(?,?,?,?,?,?)",
                    (request_id, run_id, model, purpose, datetime.now(timezone.utc).isoformat(), reserve),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return request_id

    def complete(self, request_id, usage):
        total = usage.get("total_tokens")
        if total is None:
            total = int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))
        if not isinstance(total, (int, float)) or total <= 0:
            self.uncertain(request_id)
            return
        with closing(self._connect()) as db:
            db.execute(
                "UPDATE llm_requests SET input_tokens=?,output_tokens=?,total_tokens=?,status='complete',completed_at=? WHERE request_id=? AND total_tokens IS NULL",
                (int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)), int(total),
                 datetime.now(timezone.utc).isoformat(), request_id),
            )

    def uncertain(self, request_id):
        # Keep the reservation when the provider didn't report billable usage.
        with closing(self._connect()) as db:
            db.execute("UPDATE llm_requests SET status='uncertain' WHERE request_id=? AND total_tokens IS NULL", (request_id,))

    def snapshot(self):
        with closing(self._connect()) as db:
            row = db.execute("SELECT COUNT(*) AS requests, COALESCE(SUM(total_tokens),0) AS reported_tokens, COALESCE(SUM(CASE WHEN total_tokens IS NULL THEN reserved_tokens ELSE 0 END),0) AS reserved_tokens FROM llm_requests").fetchone()
            return {**dict(row), "limit": self.limit, "remaining_tokens": self.limit - self._charged(db)}
