"""Read-only access to the curated finance sample.

The public package is under ``data/finance``. Financial records are current
aggregate-provider snapshots: ``available_at`` is the snapshot date, not the
reporting-period end or the exchange notice date. An ``as_of`` before the
snapshot therefore returns no records even when the report period is older.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "finance"
COMPANIES_FILE = "companies.json"
FINANCIALS_FILE = "financials.jsonl"
DEFINITIONS_FILE = "metric_definitions.json"


def _parse_date(value: str | date | datetime, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty YYYY-MM-DD date")
    text = value.strip()
    if len(text) != 10:
        raise ValueError(f"{field} must be exactly YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def normalize_symbol(symbol: str) -> str:
    """Normalize the exact exchange-qualified code used by the package."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    return symbol.strip().upper()


class FinanceStore:
    """A finance package reader bound to an explicit data directory."""

    def __init__(self, data_dir: str | Path = DATA_DIR) -> None:
        self.data_dir = Path(data_dir)
        self._cache: dict[str, Any] = {}

    def _read_json(self, name: str) -> Any:
        with (self.data_dir / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    def _read_jsonl(self, name: str) -> list[dict[str, Any]]:
        with (self.data_dir / name).open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def _cached(self, name: str, loader) -> Any:
        if name not in self._cache:
            self._cache[name] = loader()
        return self._cache[name]

    def list_companies(self) -> list[dict[str, Any]]:
        """Return the package's company records, ordered by symbol."""
        rows = [dict(row) for row in self._cached("companies", lambda: self._read_json(COMPANIES_FILE))]
        return sorted(rows, key=lambda row: row["symbol"])

    def metric_definitions(self) -> dict[str, Any]:
        """Return the package metric, period and availability definitions."""
        raw = self._cached("definitions", lambda: self._read_json(DEFINITIONS_FILE))
        return json.loads(json.dumps(raw, ensure_ascii=False))

    def company_financials(
        self, symbol: str, as_of: str | date | datetime, limit: int = 4
    ) -> list[dict[str, Any]]:
        """Return financial records visible at ``as_of``.

        Records are loaded from the package and then filtered by the snapshot
        ``available_at`` date. No record after the cutoff is returned and no
        record is backfilled from ``notice_date``. The newest report periods
        are returned first, up to ``limit``.
        """
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be a non-negative integer")
        if limit < 0:
            raise ValueError("limit must be a non-negative integer")
        cutoff = _parse_date(as_of, "as_of")
        wanted = normalize_symbol(symbol)
        companies = {row["symbol"]: row for row in self.list_companies()}
        if wanted not in companies:
            return []
        records = [
            row for row in self._cached("financials", lambda: self._read_jsonl(FINANCIALS_FILE))
            if row["symbol"] == wanted
            and _parse_date(row["available_at"], "available_at") <= cutoff
        ]
        records.sort(key=lambda row: (row["report_period"], row["report_type"]), reverse=True)
        definitions = self.metric_definitions()
        result = []
        for row in records[:limit]:
            item = json.loads(json.dumps(row, ensure_ascii=False))
            item["metric_definitions"] = definitions["metrics"]
            result.append(item)
        return result

    def clear_cache(self) -> None:
        """Clear this store's process-local cache after a deliberate rebuild."""
        self._cache.clear()


_DEFAULT_STORE = FinanceStore(DATA_DIR)


def list_companies() -> list[dict[str, Any]]:
    return _DEFAULT_STORE.list_companies()


def metric_definitions() -> dict[str, Any]:
    return _DEFAULT_STORE.metric_definitions()


def company_financials(
    symbol: str, as_of: str | date | datetime, limit: int = 4
) -> list[dict[str, Any]]:
    return _DEFAULT_STORE.company_financials(symbol, as_of, limit=limit)


def clear_cache() -> None:
    _DEFAULT_STORE.clear_cache()


__all__ = [
    "DATA_DIR",
    "FinanceStore",
    "clear_cache",
    "company_financials",
    "list_companies",
    "metric_definitions",
    "normalize_symbol",
]
