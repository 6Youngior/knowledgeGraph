#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Low-frequency CNINFO disclosure collector for the public A-share universe.

The tool intentionally does one small job: fetch full annual/interim report PDFs
for A-share securities in an explicit universe, write metadata and request logs,
and resume from cached files. It does not parse PDF text, call an LLM, schedule
jobs, or touch the knowledge graph.

Example:
    python code/collect_disclosures.py --universe data/universe.json \
        --output .fingraph/disclosures --limit 4 --max-bytes 50000000 \
        --start 2024-01-01 --end 2026-11-11
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIVERSE = ROOT / "data" / "universe.json"
CNINFO_STOCK_PATH = "/new/data/szse_stock.json"
CNINFO_QUERY_PATH = "/new/hisAnnouncement/query"
DEFAULT_CNINFO_BASE = "http://www.cninfo.com.cn"
DEFAULT_PDF_BASE = "https://static.cninfo.com.cn"
REQUEST_BUDGET = 120
CATEGORY = {
    "annual_report": "category_ndbg_szsh",
    "interim_report": "category_bndbg_szsh",
}
DOC_LABEL = {"annual_report": "年度报告", "interim_report": "半年度报告"}


class BudgetError(RuntimeError):
    pass


def parse_date(value: str, field: str) -> date:
    if not isinstance(value, str) or len(value.strip()) != 10:
        raise ValueError(f"{field} must be exactly YYYY-MM-DD")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def announcement_date(value: Any) -> tuple[str | None, str]:
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None, "missing or invalid announcementTime"
    if millis <= 0:
        return None, "announcementTime is not positive"
    moment = datetime.fromtimestamp(millis / 1000, tz=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
    return moment.date().isoformat(), "CNINFO announcementTime epoch ms, Asia/Shanghai date"


def report_period_from_title(title: str, document_type: str) -> str | None:
    if document_type == "annual_report":
        match = re.search(r"(20\d{2})年年度报告", title)
        return f"{match.group(1)}-12-31" if match else None
    match = re.search(r"(20\d{2})年半年度报告", title)
    return f"{match.group(1)}-06-30" if match else None


def version_status_from_title(title: str) -> str:
    if any(token in title for token in ("修订版", "更正后", "更新版")):
        return "updated_filing"
    return "original_filing"


def eligible_title(title: str, document_type: str) -> bool:
    """Allow full reports, including revised full reports; reject notices/summaries."""
    if not title:
        return False
    if any(token in title for token in ("摘要", "英文", "英文版", "取消", "已取消")):
        return False
    marker = "年度报告" if document_type == "annual_report" else "半年度报告"
    if marker not in title:
        return False
    # "关于……年度报告……的公告/说明" is an announcement about a report, not
    # the full report body. A full revised report may contain 更正/修订.
    if title.strip().startswith("关于") and "公告" in title:
        return False
    if "说明" in title and "报告" in title:
        return False
    return True


def safe_component(value: str, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"{field} contains unsafe path characters")
    return value


def safe_cache_path(output: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("cache_path must be non-empty")
    path = (output / relative).resolve()
    if not path.is_relative_to(output.resolve()):
        raise ValueError("cache_path escapes batch directory")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Collector:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.output = Path(args.output).expanduser().resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.output / "cache"
        self.pdf_dir = self.cache_dir / "pdfs"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.output / "metadata.jsonl"
        self.requests_path = self.output / "requests.jsonl"
        self.failures_path = self.output / "failures.jsonl"
        self.batch_path = self.output / "batch.json"
        self.failures_path.touch(exist_ok=True)
        self.universe = read_json(Path(args.universe).expanduser().resolve())
        self.requests: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.existing = {
            row.get("source_url"): self.normalize_existing(row)
            for row in read_jsonl(self.metadata_path)
            if row.get("source_url")
        }
        self.requests_before = len(read_jsonl(self.requests_path))
        self.request_count = self.requests_before
        self.new_count = 0
        self.new_bytes = 0
        self.skipped_duplicates = 0
        self.stop_after_budget = False
        self.client = httpx.Client(
            timeout=httpx.Timeout(args.timeout),
            follow_redirects=True,
            headers={
                "User-Agent": "FinGraphAgent-disclosure-collector/1.0 (public low-frequency research)",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def normalize_existing(row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        title = str(item.get("title") or "")
        item.setdefault("publisher", "巨潮资讯")
        item.setdefault("version_status", version_status_from_title(title))
        if item.get("published_at"):
            item.setdefault("available_at", item["published_at"])
            item.setdefault(
                "availability_basis",
                f"CNINFO announcementId={item.get('announcement_id')}; announcementTime={item.get('published_at')}; original PDF",
            )
        if item.get("cache_path"):
            item.setdefault("local_file", item["cache_path"])
        if item.get("sha256"):
            item.setdefault("download_sha256", item["sha256"])
        return item

    def reserve_request(self) -> None:
        budget = getattr(self.args, "request_budget", REQUEST_BUDGET)
        if self.request_count >= budget:
            raise BudgetError(f"request budget {budget} exceeded before HTTP request")
        self.request_count += 1

    def log_request(self, kind: str, method: str, url: str, status: int | None,
                    byte_count: int | None, error: str | None = None) -> None:
        row = {
            "kind": kind,
            "method": method,
            "url": url,
            "status": status,
            "bytes": byte_count,
            "error": error,
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        self.requests.append(row)
        append_jsonl(self.requests_path, row)
        if self.args.delay:
            time.sleep(self.args.delay)

    def fail(self, stage: str, message: str, **extra: Any) -> None:
        row = {"stage": stage, "error": message, "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), **extra}
        self.failures.append(row)
        append_jsonl(self.failures_path, row)

    def get_json(self, kind: str, path: str) -> dict[str, Any] | None:
        url = self.args.cninfo_base.rstrip("/") + path
        self.reserve_request()
        try:
            response = self.client.get(url)
        except Exception as exc:
            self.log_request(kind, "GET", url, None, None, f"{type(exc).__name__}: {exc}")
            self.fail(kind, f"{type(exc).__name__}: {exc}", url=url)
            return None
        self.log_request(kind, "GET", url, response.status_code, len(response.content))
        if response.status_code != 200:
            self.fail(kind, f"HTTP {response.status_code}", url=url)
            return None
        try:
            data = response.json()
        except Exception as exc:
            self.fail(kind, f"JSON decode: {exc}", url=url)
            return None
        return data if isinstance(data, dict) else None

    def get_directory(self) -> dict[str, dict[str, Any]]:
        cache = self.cache_dir / "szse_stock.json"
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
            except Exception as exc:
                self.fail("directory_cache", str(exc), cache="cache/szse_stock.json")
                data = {}
        else:
            data = self.get_json("directory", CNINFO_STOCK_PATH) or {}
            if data:
                write_json(cache, data)
        stock_list = data.get("stockList") if isinstance(data, dict) else None
        if not isinstance(stock_list, list):
            self.fail("directory", "stockList missing")
            return {}
        result = {}
        for item in stock_list:
            if not isinstance(item, dict) or not item.get("code"):
                continue
            result[str(item["code"])] = item
        return result

    def query_announcements(self, security: dict[str, Any], org_id: str,
                            document_type: str) -> list[dict[str, Any]]:
        category = CATEGORY[document_type]
        url = self.args.cninfo_base.rstrip("/") + CNINFO_QUERY_PATH
        payload = {
            "pageNum": "1",
            "pageSize": "30",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{security['code']},{org_id}",
            "searchkey": "",
            "secid": "",
            "category": category,
            "trade": "",
            "seDate": f"{self.args.start}~{self.args.end}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        self.reserve_request()
        try:
            response = self.client.post(url, data=payload)
        except Exception as exc:
            self.log_request("query", "POST", url, None, None, f"{type(exc).__name__}: {exc}")
            self.fail("query", f"{type(exc).__name__}: {exc}", security=security["symbol"], document_type=document_type)
            return []
        self.log_request("query", "POST", url, response.status_code, len(response.content))
        if response.status_code != 200:
            self.fail("query", f"HTTP {response.status_code}", security=security["symbol"], document_type=document_type)
            return []
        try:
            data = response.json()
        except Exception as exc:
            self.fail("query", f"JSON decode: {exc}", security=security["symbol"], document_type=document_type)
            return []
        announcements = data.get("announcements") if isinstance(data, dict) else None
        if not isinstance(announcements, list):
            self.fail("query", "announcements missing", security=security["symbol"], document_type=document_type)
            return []
        candidates = []
        for item in announcements:
            title = str(item.get("announcementTitle") or "")
            if not eligible_title(title, document_type):
                continue
            period = report_period_from_title(title, document_type)
            if not period:
                self.fail("report_period", "cannot derive report period from title", security=security["symbol"], title=title)
                continue
            published, basis = announcement_date(item.get("announcementTime"))
            if not published:
                self.fail("announcement_date", basis, security=security["symbol"], title=title)
                continue
            if not (self.args.start <= published <= self.args.end):
                self.fail("date_range", "announcement date outside requested range",
                          security=security["symbol"], title=title, published_at=published)
                continue
            announcement_id = str(item.get("announcementId") or "")
            try:
                safe_component(announcement_id, "announcement_id")
            except ValueError as exc:
                self.fail("announcement_id", str(exc), security=security["symbol"], title=title)
                continue
            adjunct = str(item.get("adjunctUrl") or "").lstrip("/")
            if not adjunct:
                self.fail("pdf_url", "adjunctUrl missing", security=security["symbol"], title=title)
                continue
            pdf_url = adjunct if adjunct.lower().startswith(("http://", "https://")) else self.args.pdf_base.rstrip("/") + "/" + adjunct
            detail = (self.args.cninfo_base.rstrip("/") + "/new/disclosure/detail?"
                      f"stockCode={security['code']}&announcementId={announcement_id}&orgId={org_id}")
            candidates.append({
                "security": security["symbol"],
                "company": security["name"],
                "market": "A",
                "exchange": security["exchange"],
                "document_type": document_type,
                "title": title,
                "report_period": period,
                "published_at": published,
                "published_at_basis": basis,
                "source_url": pdf_url,
                "source_page_url": detail,
                "announcement_id": announcement_id,
                "publisher": "巨潮资讯",
                "version_status": version_status_from_title(title),
                "available_at": published,
                "availability_basis": (
                    f"CNINFO announcementId={announcement_id}; announcementTime={published}; original PDF"
                ),
            })
        candidates.sort(key=lambda row: (row["report_period"], row["published_at"]), reverse=True)
        return candidates

    def select_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep up to per-kind report periods, preserving every version of a period."""
        periods: list[str] = []
        for row in candidates:
            if row["report_period"] not in periods:
                periods.append(row["report_period"])
        keep = set(periods[: self.args.per_kind])
        return [row for row in candidates if row["report_period"] in keep]

    def remaining_bytes(self) -> int:
        return max(0, self.args.max_bytes - self.new_bytes)

    def download(self, candidate: dict[str, Any]) -> bool:
        if self.new_count >= self.args.limit:
            return False
        if self.new_bytes >= self.args.max_bytes:
            self.fail("byte_budget", "max-bytes already reached", security=candidate["security"])
            self.stop_after_budget = True
            return False
        existing = self.existing.get(candidate["source_url"])
        if existing:
            try:
                cache_path = safe_cache_path(self.output, existing.get("cache_path", ""))
                valid = (
                    cache_path.is_file()
                    and cache_path.stat().st_size == existing.get("bytes")
                    and sha256_file(cache_path) == existing.get("sha256")
                )
            except (OSError, ValueError):
                valid = False
            if valid:
                self.skipped_duplicates += 1
                return False
        file_name = f"{candidate['security'].replace('.', '_')}_{candidate['announcement_id']}.pdf"
        cache_path = self.pdf_dir / file_name
        temp_path = cache_path.with_suffix(".part")
        logged = False
        self.reserve_request()
        try:
            with self.client.stream("GET", candidate["source_url"]) as response:
                content_type = (response.headers.get("content-type") or "").lower()
                content_length = response.headers.get("content-length")
                self.log_request("pdf", "GET", candidate["source_url"], response.status_code,
                                 int(content_length) if content_length and content_length.isdigit() else None)
                logged = True
                if response.status_code != 200:
                    self.fail("pdf", f"HTTP {response.status_code}", security=candidate["security"], title=candidate["title"])
                    return False
                if content_type and "application/pdf" not in content_type and "octet-stream" not in content_type:
                    self.fail("pdf", f"unexpected content-type {content_type}", security=candidate["security"], title=candidate["title"])
                    return False
                if content_length and content_length.isdigit() and int(content_length) > self.remaining_bytes():
                    self.fail("byte_budget", "PDF exceeds remaining max-bytes", security=candidate["security"], title=candidate["title"])
                    self.stop_after_budget = True
                    return False
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                byte_count = 0
                with temp_path.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if self.new_bytes + byte_count > self.args.max_bytes:
                            temp_path.unlink(missing_ok=True)
                            self.fail("byte_budget", "PDF exceeds max-bytes", security=candidate["security"], title=candidate["title"])
                            self.stop_after_budget = True
                            return False
                        digest.update(chunk)
                        handle.write(chunk)
                if not temp_path.read_bytes().startswith(b"%PDF-"):
                    temp_path.unlink(missing_ok=True)
                    self.fail("pdf", "response is not a PDF", security=candidate["security"], title=candidate["title"])
                    return False
            temp_path.replace(cache_path)
            download_hash = digest.hexdigest()
            record = {
                **candidate,
                "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "bytes": byte_count,
                "sha256": download_hash,
                "download_sha256": download_hash,
                "content_type": content_type,
                "local_file": f"cache/pdfs/{file_name}",
                "cache_path": f"cache/pdfs/{file_name}",
                "source_id": "cninfo",
            }
            self.existing[record["source_url"]] = record
            append_jsonl(self.metadata_path, record)
            self.new_count += 1
            self.new_bytes += byte_count
            return True
        except BudgetError:
            temp_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            if not logged:
                self.log_request("pdf", "GET", candidate["source_url"], None, None, f"{type(exc).__name__}: {exc}")
            self.fail("pdf", f"{type(exc).__name__}: {exc}", security=candidate["security"], title=candidate["title"])
            return False

    def run(self) -> dict[str, Any]:
        securities = self.universe.get("securities") if isinstance(self.universe, dict) else None
        if not isinstance(securities, list):
            raise ValueError("universe.securities must be a list")
        a_securities = [
            item for item in securities
            if isinstance(item, dict) and item.get("market") == "A" and item.get("collection", "A_primary") == "A_primary"
        ]
        if not a_securities:
            raise ValueError("universe has no A_primary securities")
        directory = self.get_directory()
        for security in a_securities:
            if self.new_count >= self.args.limit or self.new_bytes >= self.args.max_bytes:
                break
            code = str(security.get("code") or "")
            item = directory.get(code)
            if not item:
                self.fail("directory", "security code not found in CNINFO directory", security=security.get("symbol"))
                continue
            if str(item.get("zwjc") or "") != str(security.get("name") or ""):
                self.fail(
                    "identity",
                    "universe name differs from CNINFO directory",
                    security=security.get("symbol"),
                    universe_name=security.get("name"),
                    directory_name=item.get("zwjc"),
                )
                continue
            org_id = str(item.get("orgId") or "")
            if not org_id:
                self.fail("directory", "orgId missing", security=security.get("symbol"))
                continue
            for document_type in CATEGORY:
                candidates = self.select_candidates(
                    self.query_announcements(security, org_id, document_type)
                )
                if candidates:
                    for candidate in candidates:
                        self.download(candidate)
                        if (self.stop_after_budget or self.new_count >= self.args.limit
                                or self.new_bytes >= self.args.max_bytes):
                            break
                else:
                    self.fail("no_eligible_announcement", f"no full {DOC_LABEL[document_type]}",
                              security=security.get("symbol"), document_type=document_type)
                if (self.stop_after_budget or self.new_count >= self.args.limit
                        or self.new_bytes >= self.args.max_bytes):
                    break
            if self.stop_after_budget:
                break
        metadata = sorted(self.existing.values(), key=lambda row: (row.get("security", ""), row.get("report_period", ""), row.get("document_type", "")))
        with self.metadata_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in metadata:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        batch = {
            "schema_version": "disclosure-batch-v1",
            "universe": Path(self.args.universe).name,
            "start": self.args.start,
            "end": self.args.end,
            "limit": self.args.limit,
            "max_bytes": self.args.max_bytes,
            "per_kind": self.args.per_kind,
            "request_budget": getattr(self.args, "request_budget", REQUEST_BUDGET),
            "requests_before": self.requests_before,
            "requests_this_run": len(self.requests),
            "requests": self.request_count,
            "downloaded": self.new_count,
            "downloaded_bytes": self.new_bytes,
            "skipped_duplicates": self.skipped_duplicates,
            "metadata_records": len(metadata),
            "failures": len(self.failures),
            "metadata_file": "metadata.jsonl",
            "request_log": "requests.jsonl",
            "failure_log": "failures.jsonl",
            "cache_dir": "cache/pdfs",
        }
        write_json(self.batch_path, batch)
        return batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE), help="universe JSON (default: data/universe.json)")
    parser.add_argument("--output", required=True, help="batch directory for metadata, logs and PDF cache")
    parser.add_argument("--limit", type=int, default=4, help="maximum new PDFs in this run (1-40)")
    parser.add_argument("--per-kind", type=int, default=1, help="distinct report periods per document type (1-3)")
    parser.add_argument("--request-budget", type=int, default=120, help="hard HTTP request budget (1-120)")
    parser.add_argument("--max-bytes", type=int, default=50_000_000, help="maximum new PDF bytes in this run (<=300MB)")
    parser.add_argument("--start", default="2024-01-01", help="announcement start date YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().isoformat(), help="announcement end date YYYY-MM-DD")
    parser.add_argument("--cninfo-base", default=DEFAULT_CNINFO_BASE, help="CNINFO API base URL")
    parser.add_argument("--pdf-base", default=DEFAULT_PDF_BASE, help="CNINFO PDF static base URL")
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout seconds")
    parser.add_argument("--delay", type=float, default=0.4, help="delay between HTTP requests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        start = parse_date(args.start, "start")
        end = parse_date(args.end, "end")
        if end < start:
            raise ValueError("end must be on or after start")
        args.start = start.isoformat()
        args.end = end.isoformat()
        if not 1 <= args.limit <= 40:
            raise ValueError("limit must be 1..40")
        if not 1 <= args.per_kind <= 3:
            raise ValueError("per-kind must be 1..3")
        if not 1 <= args.request_budget <= 120:
            raise ValueError("request-budget must be 1..120")
        if not 0 < args.max_bytes <= 300_000_000:
            raise ValueError("max-bytes must be in 1..300000000")
        if args.timeout <= 0:
            raise ValueError("timeout must be positive")
        if args.delay < 0:
            raise ValueError("delay must be non-negative")
        universe = read_json(Path(args.universe).expanduser().resolve())
        if not isinstance(universe.get("securities"), list):
            raise ValueError("universe.securities must be a list")
        seen = set()
        for item in universe["securities"]:
            if not isinstance(item, dict):
                raise ValueError("universe security must be an object")
            symbol = item.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("universe security missing symbol")
            if symbol in seen:
                raise ValueError(f"duplicate symbol in universe: {symbol}")
            seen.add(symbol)
            if item.get("market") == "A":
                code = str(item.get("code") or "")
                if not re.fullmatch(r"\d{6}", code):
                    raise ValueError(f"A-share code must be six digits: {symbol}")
                if not item.get("name"):
                    raise ValueError(f"A-share name missing: {symbol}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    collector = Collector(args)
    try:
        batch = collector.run()
    except BudgetError as exc:
        collector.fail("request_budget", str(exc))
        batch = {"error": str(exc)}
        code = 2
    except (OSError, ValueError, KeyError) as exc:
        collector.fail("run", f"{type(exc).__name__}: {exc}")
        batch = {"error": str(exc)}
        code = 2
    else:
        code = 0
    finally:
        collector.close()
    print(json.dumps(batch, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
