#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bounded Eastmoney daily-price collector for the AI A-share universe.

The endpoint and field order follow the current AKShare source for
``stock_zh_a_hist`` / ``stock_zh_index_daily_em``. This script deliberately
keeps one HTTP request per symbol/adjustment and uses a persistent ledger so a
resume cannot reset the batch budget.

Output layout (default .fingraph/market/ai-a-share):
  manifest.json
  requests.jsonl
  failures.jsonl
  raw/<symbol>_<adjustment>.json
  <symbol>_<adjustment>.csv
  index_000300_none.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIVERSE = ROOT / "data" / "universe.json"
DEFAULT_OUTPUT = ROOT / ".fingraph" / "market" / "ai-a-share"
DEFAULT_BASE = "https://push2his.eastmoney.com"
DEFAULT_REQUESTS = 80
DEFAULT_BYTES = 40_000_000
ENDPOINT = "/api/qt/stock/kline/get"
FIELDS1 = "f1,f2,f3,f4,f5,f6"
FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116"
ADJUSTMENTS = {"none": "0", "qfq": "1"}


class BudgetError(RuntimeError):
    pass


def parse_date(value: str, field: str) -> date:
    if not isinstance(value, str) or len(value.strip()) != 10:
        raise ValueError(f"{field} must be exactly YYYY-MM-DD")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value: float, field: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field}: non-finite number")
    return value


def safe_relative_path(base: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("relative path is empty or absolute")
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("relative path escapes output directory")
    return path


def validate_security(sec: dict[str, Any]) -> None:
    symbol = sec.get("symbol")
    code = sec.get("code")
    if not isinstance(symbol, str) or not re.fullmatch(r"\d{6}\.(SH|SZ)", symbol):
        raise ValueError(f"unsafe or invalid symbol: {symbol!r}")
    if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
        raise ValueError(f"invalid code: {code!r}")
    if symbol.split(".")[0] != code:
        raise ValueError(f"symbol/code mismatch: {symbol}/{code}")
    expected_exchange = "SSE" if symbol.endswith(".SH") else "SZSE"
    if sec.get("exchange") != expected_exchange:
        raise ValueError(f"exchange mismatch: {symbol}")


def parse_klines(payload: dict[str, Any], start: str, end: str) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("klines"), list):
        raise ValueError("response has no data.klines")
    rows = []
    seen = set()
    for raw in data["klines"]:
        if not isinstance(raw, str):
            raise ValueError("kline item is not a string")
        fields = raw.split(",")
        if len(fields) < 7:
            raise ValueError(f"kline has too few fields: {raw!r}")
        day = fields[0]
        if len(day) != 10:
            raise ValueError(f"bad date: {day!r}")
        date.fromisoformat(day)
        if day < start or day > end:
            raise ValueError(f"date outside requested range: {day}")
        if day in seen:
            raise ValueError(f"duplicate date: {day}")
        if rows and day <= rows[-1]["date"]:
            raise ValueError(f"kline dates not strictly ascending: {day}")
        seen.add(day)
        try:
            open_, close, high, low = (float(fields[i]) for i in (1, 2, 3, 4))
            volume = float(fields[5])
            amount_text = fields[6].strip()
            amount = float(amount_text) if amount_text else None
        except ValueError as exc:
            raise ValueError(f"bad numeric kline: {raw!r}") from exc
        for name, value in (("open", open_), ("close", close), ("high", high), ("low", low)):
            finite(value, f"{day}.{name}")
            if value <= 0:
                raise ValueError(f"{day}.{name} must be positive")
        if high < low:
            raise ValueError(f"{day}: high < low")
        if not (low <= open_ <= high and low <= close <= high):
            raise ValueError(f"{day}: open/close outside low/high")
        finite(volume, f"{day}.volume")
        if volume < 0:
            raise ValueError(f"{day}.volume must be non-negative")
        if amount is not None:
            finite(amount, f"{day}.amount")
            if amount < 0:
                raise ValueError(f"{day}.amount must be non-negative")
        rows.append({
            "date": day, "open": open_, "high": high, "low": low, "close": close,
            "volume": volume, "amount": amount,
        })
    return rows


def read_csv_rows(path: Path, start: str, end: str) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    parsed = []
    seen = set()
    for row in rows:
        day = row["date"]
        if len(day) != 10:
            raise ValueError(f"bad CSV date: {day!r}")
        date.fromisoformat(day)
        if day < start or day > end:
            raise ValueError(f"CSV date outside requested range: {day}")
        if day in seen:
            raise ValueError(f"duplicate CSV date: {day}")
        if parsed and day <= parsed[-1]["date"]:
            raise ValueError(f"CSV dates not strictly ascending: {day}")
        seen.add(day)
        open_, high, low, close = (float(row[key]) for key in ("open", "high", "low", "close"))
        volume = float(row["volume"])
        amount = float(row["amount"]) if row.get("amount") else None
        for name, value in (("open", open_), ("high", high), ("low", low), ("close", close)):
            finite(value, f"{day}.{name}")
            if value <= 0:
                raise ValueError(f"{day}.{name} must be positive")
        finite(volume, f"{day}.volume")
        if amount is not None:
            finite(amount, f"{day}.amount")
        if high < low or not (low <= open_ <= high and low <= close <= high) or volume < 0 or (amount is not None and amount < 0):
            raise ValueError(f"bad CSV row: {row}")
        parsed.append({"date": day, "open": open_, "high": high, "low": low,
                       "close": close, "volume": volume, "amount": amount})
    return parsed


class PriceCollector:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.output = Path(args.output).expanduser().resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "raw").mkdir(exist_ok=True)
        self.requests_path = self.output / "requests.jsonl"
        self.failures_path = self.output / "failures.jsonl"
        self.failures_path.touch(exist_ok=True)
        self.manifest_path = self.output / "manifest.json"
        self.prior_requests = jsonl(self.requests_path)
        self.request_count = len(self.prior_requests)
        self.response_bytes = sum(int(row.get("bytes") or 0) for row in self.prior_requests)
        self.prior_manifest = {}
        self.prior_range = None
        if self.manifest_path.exists():
            try:
                old = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self.prior_range = old.get("requested_range")
                for item in old.get("series", []):
                    rel = item.get("relative_path")
                    try:
                        safe_relative_path(self.output, rel)
                    except (TypeError, ValueError):
                        continue
                    self.prior_manifest[rel] = item
            except Exception:
                self.prior_manifest = {}
        self.failure_keys = set()
        self.network_failure_streak = 0
        self.failures: list[dict[str, Any]] = []
        self.client = httpx.Client(timeout=httpx.Timeout(args.timeout), follow_redirects=False,
                                   headers={"User-Agent": "FinGraphAgent-price-collector/1.0 (public research)"})
        self.entries: list[dict[str, Any]] = []

    def close(self) -> None:
        self.client.close()

    def fail(self, stage: str, error: str, **extra: Any) -> None:
        key = (stage, error, extra.get("symbol"), extra.get("adjustment"))
        if key in self.failure_keys:
            return
        self.failure_keys.add(key)
        row = {"stage": stage, "error": error, "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), **extra}
        self.failures.append(row)
        append_jsonl(self.failures_path, row)

    def reserve(self) -> None:
        if self.request_count >= self.args.budget_requests:
            raise BudgetError("persistent HTTP request budget exhausted")
        if self.response_bytes >= self.args.budget_bytes:
            raise BudgetError("persistent response-byte budget exhausted")
        self.request_count += 1

    def get(self, symbol: str, adjustment: str, secid: str, label: str) -> tuple[list[dict[str, Any]], str]:
        url = self.args.base_url.rstrip("/") + ENDPOINT
        params = {
            "secid": secid,
            "fields1": FIELDS1,
            "fields2": FIELDS2,
            "klt": "101",
            "fqt": ADJUSTMENTS[adjustment],
            "beg": self.args.start.replace("-", ""),
            "end": self.args.end.replace("-", ""),
        }
        requested_url = str(httpx.URL(url).copy_merge_params(params))
        self.reserve()
        if self.request_count > 1 and self.args.delay:
            time.sleep(self.args.delay)
        started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        chunks: list[bytes] = []
        received = 0
        status = None
        logged = False
        try:
            with self.client.stream("GET", url, params=params) as response:
                status = response.status_code
                remaining = max(0, self.args.budget_bytes - self.response_bytes)
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    received += len(chunk)
                    if received > remaining:
                        self.response_bytes += received
                        append_jsonl(self.requests_path, {
                            "kind": f"prices_{adjustment}", "symbol": symbol, "adjustment": adjustment,
                            "url": str(response.url), "status": status, "bytes": received,
                            "error": "response-byte budget exceeded", "at": started,
                        })
                        self.fail("budget", "persistent response-byte budget exceeded",
                                  symbol=symbol, adjustment=adjustment)
                        raise BudgetError("persistent response-byte budget exceeded")
                    chunks.append(chunk)
                body = b"".join(chunks)
                self.response_bytes += received
                append_jsonl(self.requests_path, {
                    "kind": f"prices_{adjustment}", "symbol": symbol, "adjustment": adjustment,
                    "url": str(response.url), "status": status, "bytes": received,
                    "at": started,
                })
                logged = True
                if status != 200:
                    if status >= 500:
                        self.network_failure_streak += 1
                    else:
                        self.network_failure_streak = 0
                    self.fail("http", f"HTTP {status}", symbol=symbol, adjustment=adjustment,
                              url=str(response.url))
                    if self.network_failure_streak >= 2:
                        raise BudgetError("two consecutive provider network failures; stopping")
                    return [], str(response.url)
                self.network_failure_streak = 0
                raw_path = self.output / "raw" / f"{label}_{adjustment}.json"
                raw_path.write_bytes(body)
        except BudgetError:
            raise
        except Exception as exc:
            if not logged:
                self.response_bytes += received
                append_jsonl(self.requests_path, {
                    "kind": f"prices_{adjustment}", "symbol": symbol, "adjustment": adjustment,
                    "url": requested_url, "status": status, "bytes": received,
                    "error": f"{type(exc).__name__}: {exc}", "at": started,
                })
            self.network_failure_streak += 1
            self.fail("network", f"{type(exc).__name__}: {exc}", symbol=symbol, adjustment=adjustment)
            if self.network_failure_streak >= 2:
                raise BudgetError("two consecutive provider network failures; stopping") from exc
            return [], requested_url
        try:
            payload = json.loads(body)
            rows = parse_klines(payload, self.args.start, self.args.end)
        except Exception as exc:
            self.fail("data", f"{type(exc).__name__}: {exc}", symbol=symbol, adjustment=adjustment,
                      url=requested_url)
            return [], requested_url
        return rows, requested_url

    def _check_streak(self) -> None:
        if self.network_failure_streak >= 2:
            raise BudgetError("two consecutive provider network failures; stopping")

    def series_path(self, label: str, adjustment: str) -> Path:
        return self.output / f"{label}_{adjustment}.csv"

    def write_series(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["date", "open", "high", "low", "close", "volume", "amount"],
                                    lineterminator="\n")
            writer.writeheader()
            for row in rows:
                out = dict(row)
                out["amount"] = "" if out["amount"] is None else out["amount"]
                writer.writerow(out)

    def build_entry(self, symbol: str, company: str, exchange: str, adjustment: str,
                    path: Path, source_url: str, rows: list[dict[str, Any]],
                    volume_unit: str, source_id: str,
                    retrieved_at: str | None = None) -> dict[str, Any]:
        return {
            "symbol": symbol, "company": company, "exchange": exchange,
            "adjustment": adjustment, "currency": "CNY", "volume_unit": volume_unit,
            "source_id": source_id, "source_url": source_url,
            "retrieved_at": retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "data_start": rows[0]["date"] if rows else None,
            "data_end": rows[-1]["date"] if rows else None,
            "rows": len(rows), "file_sha256": sha256(path),
            "relative_path": str(path.relative_to(self.output)).replace("\\", "/"),
        }

    def existing_entry(self, symbol: str, company: str, exchange: str, adjustment: str,
                       path: Path, volume_unit: str) -> dict[str, Any] | None:
        if not path.exists():
            return None
        relative = str(path.relative_to(self.output)).replace("\\", "/")
        try:
            safe_relative_path(self.output, relative)
        except ValueError as exc:
            self.fail("resume_path", str(exc), symbol=symbol, adjustment=adjustment)
            return None
        prior = self.prior_manifest.get(relative)
        if not prior:
            self.fail("resume_manifest", "missing manifest entry", symbol=symbol, adjustment=adjustment)
            return None
        expected_range = {"start": self.args.start, "end": self.args.end}
        if self.prior_range != expected_range:
            self.fail("resume_range", "requested range differs from manifest", symbol=symbol, adjustment=adjustment)
            return None
        identity = {
            "symbol": symbol, "company": company, "exchange": exchange,
            "adjustment": adjustment, "currency": "CNY", "volume_unit": volume_unit,
        }
        for key, expected in identity.items():
            if prior.get(key) != expected:
                self.fail("resume_identity", f"{key} mismatch", symbol=symbol, adjustment=adjustment)
                return None
        source_url = prior.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith(("http://", "https://")):
            self.fail("resume_manifest", "empty or invalid source_url", symbol=symbol, adjustment=adjustment)
            return None
        try:
            rows = read_csv_rows(path, self.args.start, self.args.end)
        except Exception as exc:
            self.fail("resume_csv", f"{type(exc).__name__}: {exc}", symbol=symbol, adjustment=adjustment)
            return None
        if not rows:
            self.fail("resume_csv", "empty CSV cannot be reused", symbol=symbol, adjustment=adjustment)
            return None
        if sha256(path) != prior.get("file_sha256"):
            self.fail("resume_sha", "CSV SHA differs from manifest", symbol=symbol, adjustment=adjustment)
            return None
        if prior.get("rows") != len(rows) or prior.get("data_start") != rows[0]["date"] or prior.get("data_end") != rows[-1]["date"]:
            self.fail("resume_identity", "CSV rows/range differs from manifest", symbol=symbol, adjustment=adjustment)
            return None
        retrieved_at = prior.get("retrieved_at")
        if not retrieved_at:
            self.fail("resume_manifest", "missing retrieved_at", symbol=symbol, adjustment=adjustment)
            return None
        return self.build_entry(symbol, company, exchange, adjustment, path, source_url, rows,
                                volume_unit, prior.get("source_id") or "eastmoney_kline", retrieved_at)

    def run(self) -> int:
        universe = json.loads(Path(self.args.universe).expanduser().read_text(encoding="utf-8"))
        securities = [x for x in universe.get("securities", []) if x.get("market") == "A"]
        for sec in securities:
            try:
                validate_security(sec)
            except ValueError as exc:
                self.fail("universe", str(exc), symbol=sec.get("symbol"))
                continue
            symbol = sec["symbol"]
            code = sec["code"]
            label = symbol.replace(".", "_")
            exchange = "SSE" if symbol.endswith(".SH") else "SZSE"
            secid = f"{1 if symbol.endswith('.SH') else 0}.{code}"
            for adjustment in ("none", "qfq"):
                path = self.series_path(label, adjustment)
                entry = self.existing_entry(symbol, sec["name"], exchange, adjustment, path, "hand_100_shares")
                if entry:
                    self.entries.append(entry)
                    continue
                rows, source_url = self.get(symbol, adjustment, secid, label)
                if not rows:
                    continue
                self.write_series(path, rows)
                self.entries.append(self.build_entry(symbol, sec["name"], exchange, adjustment, path,
                                                     source_url, rows, "hand_100_shares", "eastmoney_kline"))
            # If both series existing/invalid, continue to next security.
        # CSI 300 is stored separately from stocks.
        index_path = self.output / "index_000300_none.csv"
        index_entry = self.existing_entry("sh000300", "沪深300", "INDEX", "none", index_path, "index_volume_native")
        if index_entry:
            self.entries.append(index_entry)
        else:
            rows, source_url = self.get("sh000300", "none", "1.000300", "index_000300")
            if rows:
                self.write_series(index_path, rows)
                self.entries.append(self.build_entry("sh000300", "沪深300", "INDEX", "none", index_path,
                                                     source_url, rows, "index_volume_native", "eastmoney_index"))
        self.entries.sort(key=lambda row: (row["symbol"], row["adjustment"]))
        rows_total = sum(row["rows"] for row in self.entries)
        manifest = {
            "schema_version": "prices-batch-v1",
            "snapshot_retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "requested_range": {"start": self.args.start, "end": self.args.end},
            "series": self.entries,
            "counts": {
                "stock_series": sum(1 for row in self.entries if row["symbol"] != "sh000300"),
                "index_series": sum(1 for row in self.entries if row["symbol"] == "sh000300"),
                "rows": rows_total,
            },
            "budget": {
                "request_limit": self.args.budget_requests,
                "response_byte_limit": self.args.budget_bytes,
                "requests_used_total": self.request_count,
                "response_bytes_total": self.response_bytes,
            },
            "source": {
                "provider": "Eastmoney kline endpoint (AKShare underlying source)",
                "endpoint": self.args.base_url.rstrip("/") + ENDPOINT,
                "akshare_reference_version": "1.20.37",
                "note": "Current download snapshot; qfq is not vintage/reconstructed price evidence.",
            },
            "adjustments": {"none": "unadjusted", "qfq": "current forward-adjusted"},
            "volume_units": {"stock": "hand_100_shares", "index": "index_volume_native"},
        }
        write_json(self.manifest_path, manifest)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--budget-requests", type=int, default=DEFAULT_REQUESTS)
    parser.add_argument("--budget-bytes", type=int, default=DEFAULT_BYTES)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--delay", type=float, default=0.5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        start = parse_date(args.start, "start")
        end = parse_date(args.end, "end")
        if end < start:
            raise ValueError("end must be on or after start")
        args.start, args.end = start.isoformat(), end.isoformat()
        if not 1 <= args.budget_requests <= 80:
            raise ValueError("budget-requests must be 1..80")
        if not 0 < args.budget_bytes <= 40_000_000:
            raise ValueError("budget-bytes must be 1..40000000")
        if args.timeout <= 0 or args.delay < 0:
            raise ValueError("timeout must be positive and delay non-negative")
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    collector = PriceCollector(args)
    try:
        return collector.run()
    except BudgetError as exc:
        collector.fail("budget", str(exc))
        print(f"stopped: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as exc:
        collector.fail("run", f"{type(exc).__name__}: {exc}")
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        collector.close()


if __name__ == "__main__":
    raise SystemExit(main())
