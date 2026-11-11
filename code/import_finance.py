#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Import standardized financial captures into a portable data package.

Usage:
    python code/import_finance.py --input <capture-dir> [--output data/finance]

The input directory is never defaulted to an ignored task directory. Output is
deterministic for the same input: the snapshot time comes from the input
manifest, records are sorted, JSON keys are sorted, and the manifest contains
relative file names and SHA-256 hashes only. Original PDFs are validated but
not copied.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "finance"

REQUIRED_FILES = (
    "financial_indicators.csv",
    "business_mix.csv",
    "prices.csv",
    "index_prices.csv",
    "disclosures.jsonl",
    "manifest.json",
    "source_registry.json",
)

SOURCE_IDS = {
    "A_financial": "eastmoney_akshare_financial_a",
    "HK_financial": "eastmoney_akshare_financial_hk",
    "business": "eastmoney_akshare_business_mix",
    "prices_a": "eastmoney_akshare_prices_a",
    "prices_hk": "eastmoney_akshare_prices_hk",
    "index": "eastmoney_akshare_index",
    "cninfo": "cninfo_annual_reports",
    "alibaba_ir": "alibaba_ir_annual_reports",
    "tencent_ir": "tencent_ir_annual_reports",
}

PERIOD_BASIS = {
    "一季报": "cumulative_ytd_q1",
    "中报": "cumulative_ytd_h1",
    "三季报": "cumulative_ytd_9m",
    "年报": "annual",
    "年度": "annual",
}


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "na", "n/a", "null", "nat"}:
        return None
    return text


def number(value: Any, field: str) -> float | None:
    text = clean(value)
    if text is None:
        return None
    try:
        parsed = float(text)
    except ValueError as exc:
        raise ValueError(f"{field}: invalid number {text!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field}: non-finite number {text!r}")
    return parsed


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def iso_date(value: Any) -> str:
    text = clean(value)
    if not text:
        raise ValueError("missing date")
    if len(text) != 10:
        raise ValueError(f"date must be exactly YYYY-MM-DD: {text!r}")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid date: {text!r}") from exc


def snapshot_from_manifest(manifest: dict[str, Any]) -> tuple[str, str]:
    raw = clean(manifest.get("generated_at"))
    if not raw:
        raise ValueError("input manifest.generated_at is required as snapshot time")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("manifest.generated_at must include a timezone")
    return parsed.astimezone(timezone(timedelta(hours=8))).date().isoformat(), raw


def source_urls(
    config: dict[str, Any], symbol: str, registry: dict[str, Any]
) -> dict[str, str]:
    """Resolve disclosure source metadata from the input, not the ticker alone."""
    if not symbol.endswith(".HK"):
        source_id = clean(config.get("source_id")) or SOURCE_IDS["cninfo"]
        if source_id == "cninfo":
            source_id = SOURCE_IDS["cninfo"]
        return {
            "source_page_url": clean(config.get("source_page_url")) or clean(config.get("detail_url")) or "",
            "source_id": source_id,
        }
    sources = [row for row in registry.get("sources", []) if isinstance(row, dict)]
    explicit_page = clean(config.get("source_page_url"))
    source_id = clean(config.get("source_id"))
    local_page = (clean(config.get("source_page")) or "").lower()
    matched = None
    for source in sources:
        sid = (clean(source.get("id")) or "").lower()
        if source_id and source_id.lower() == sid:
            matched = source
            break
        token = sid.rsplit("_", 1)[-1]
        if token and token in local_page:
            matched = source
            break
    if matched and not source_id:
        source_id = clean(matched.get("id"))
    # Keep the public source IDs aligned with sources.json for the two
    # explicit company-IR sources; do not infer a company from the ticker.
    if source_id == "company_ir_alibaba":
        source_id = SOURCE_IDS["alibaba_ir"]
    elif source_id == "company_ir_tencent":
        source_id = SOURCE_IDS["tencent_ir"]
    page = explicit_page or (clean(matched.get("url")) if matched else "")
    return {
        "source_page_url": page or "",
        "source_id": source_id or "company_ir_unresolved",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import verified financial captures into data/finance")
    parser.add_argument("--input", required=True, help="explicit capture directory containing the seven required files")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="public package output directory")
    args = parser.parse_args()

    source_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not source_dir.is_dir():
        print(f"input directory not found: {source_dir}", file=sys.stderr)
        return 2
    missing = [name for name in REQUIRED_FILES if not (source_dir / name).is_file()]
    if missing:
        print(f"input is missing required files: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        input_manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
        snapshot_date, snapshot_time = snapshot_from_manifest(input_manifest)
        registry = json.loads((source_dir / "source_registry.json").read_text(encoding="utf-8"))
        financial_raw = read_csv(source_dir / "financial_indicators.csv")
        business_raw = read_csv(source_dir / "business_mix.csv")
        prices_raw = read_csv(source_dir / "prices.csv")
        index_raw = read_csv(source_dir / "index_prices.csv")
        disclosures_raw = read_jsonl(source_dir / "disclosures.jsonl")
    except Exception as exc:
        print(f"input read failed: {exc}", file=sys.stderr)
        return 2

    expected = {row["symbol"]: row for row in registry.get("securities", [])}
    if not expected:
        print("source_registry contains no securities", file=sys.stderr)
        return 2
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    # Financial record checks.
    financial_rows: list[dict[str, Any]] = []
    for row in financial_raw:
        symbol = (clean(row.get("security")) or "").upper()
        require(symbol in expected, f"unknown financial symbol: {symbol!r}")
        if symbol not in expected:
            continue
        report_period = iso_date(row.get("report_date"))
        require(report_period <= snapshot_date, f"report period after snapshot: {symbol} {report_period}")
        notice = clean(row.get("notice_date"))
        notice = iso_date(notice) if notice else None
        currency = clean(row.get("currency_iso")) or "CNY"
        require(currency == "CNY", f"unexpected financial currency: {symbol} {currency}")
        report_type = clean(row.get("report_type")) or "年度"
        basis = PERIOD_BASIS.get(report_type)
        require(basis is not None, f"unknown report type: {symbol} {report_type}")
        market = "HK" if symbol.endswith(".HK") else "A"
        if market == "HK":
            require(basis == "annual", f"HK record must be annual: {symbol} {report_type}")
        values = {
            "revenue": number(row.get("revenue"), f"{symbol}.revenue"),
            "net_profit": number(row.get("net_profit"), f"{symbol}.net_profit"),
            "eps": number(row.get("eps"), f"{symbol}.eps"),
            "roe": number(row.get("roe"), f"{symbol}.roe"),
            "gross_margin": number(row.get("gross_margin"), f"{symbol}.gross_margin"),
        }
        source_id = SOURCE_IDS["HK_financial"] if market == "HK" else SOURCE_IDS["A_financial"]
        fiscal_year_end_md = expected[symbol].get("fiscal_year_end_md")
        if not fiscal_year_end_md:
            fiscal_year_end_md = "12-31" if market == "A" or symbol == "00700.HK" else ("03-31" if symbol == "09988.HK" else None)
        financial_rows.append({
            "symbol": symbol,
            "company": expected[symbol]["name"],
            "market": market,
            "report_period": report_period,
            "report_type": report_type,
            "period_basis": basis,
            "fiscal_year": report_period[:4],
            "fiscal_year_end": f"{report_period[:4]}-{fiscal_year_end_md}" if fiscal_year_end_md else None,
            "fiscal_year_end_md": fiscal_year_end_md,
            "fiscal_year_end_basis": "company fiscal-year-end convention, not the report period end",
            "notice_date": notice,
            "notice_date_source": "Eastmoney NOTICE_DATE" if notice else None,
            "collected_at": clean(row.get("retrieved_at")) or snapshot_time,
            "available_at": snapshot_date,
            "availability_basis": "aggregate snapshot collected at snapshot date; no revision history",
            "currency": "CNY",
            "amount_unit": "whole CNY",
            "eps_unit": "CNY/share",
            "ratio_unit": "percent",
            "revenue": values["revenue"],
            "net_profit": values["net_profit"],
            "eps": values["eps"],
            "roe": values["roe"],
            "gross_margin": values["gross_margin"],
            "gross_margin_unit": "percent",
            "profit_definition": (
                "HOLDER_PROFIT（股东应占利润）" if market == "HK" else
                "PARENTNETPROFIT（归属于母公司股东的净利润）"
            ),
            "revenue_definition": (
                "OPERATE_INCOME（经营收入）" if market == "HK" else
                "TOTALOPERATEREVE（总营业收入）"
            ),
            "eps_definition": "基本每股收益（basic EPS）",
            "roe_definition": "接口 ROE_AVG / ROEJQ（百分比）",
            "gross_margin_definition": "接口 GROSS_PROFIT_RATIO / XSMLL（百分比）",
            "source_id": source_id,
            "quality_flags": [
                "current_aggregate_snapshot",
                *(["notice_date_missing"] if notice is None else []),
                *(["fiscal_year_end_missing"] if not fiscal_year_end_md else []),
            ],
        })

    require(len(financial_rows) > 0, "no financial rows")
    financial_rows.sort(key=lambda row: (row["symbol"], row["report_period"], row["report_type"]))
    require(len({(r["symbol"], r["report_period"], r["report_type"]) for r in financial_rows}) == len(financial_rows),
            "duplicate financial rows")

    # Business mix checks.
    business_rows: list[dict[str, Any]] = []
    for row in business_raw:
        symbol = (clean(row.get("security")) or "").upper()
        require(symbol in expected, f"unknown business symbol: {symbol!r}")
        if symbol not in expected:
            continue
        report_period = iso_date(row.get("报告日期"))
        require(report_period <= snapshot_date, f"business report after snapshot: {symbol} {report_period}")
        business_rows.append({
            "symbol": symbol,
            "company": expected[symbol]["name"],
            "report_period": report_period,
            "category": clean(row.get("分类类型")),
            "item": clean(row.get("主营构成")),
            "revenue": number(row.get("主营收入"), f"{symbol}.business_revenue"),
            "revenue_ratio": number(row.get("收入比例"), f"{symbol}.business_revenue_ratio"),
            "cost": number(row.get("主营成本"), f"{symbol}.business_cost"),
            "cost_ratio": number(row.get("成本比例"), f"{symbol}.business_cost_ratio"),
            "profit": number(row.get("主营利润"), f"{symbol}.business_profit"),
            "profit_ratio": number(row.get("利润比例"), f"{symbol}.business_profit_ratio"),
            "gross_margin_ratio": number(row.get("毛利率"), f"{symbol}.business_gross_margin"),
            "gross_margin_ratio_unit": "fraction",
            "currency": "CNY",
            "amount_unit": "whole CNY",
            "ratio_unit": "fraction",
            "available_at": snapshot_date,
            "availability_basis": "current aggregate snapshot; no revision history",
            "source_id": SOURCE_IDS["business"],
        })
    business_rows.sort(key=lambda row: (row["symbol"], row["report_period"], row["category"] or "", row["item"] or ""))

    # Quote checks.
    price_rows: list[dict[str, Any]] = []
    for row in prices_raw:
        symbol = (clean(row.get("security")) or "").upper()
        require(symbol in expected, f"unknown price symbol: {symbol!r}")
        if symbol not in expected:
            continue
        day = iso_date(row.get("date"))
        price_rows.append({
            "symbol": symbol,
            "market": clean(row.get("market")),
            "date": day,
            "open": number(row.get("open"), f"{symbol}.{day}.open"),
            "high": number(row.get("high"), f"{symbol}.{day}.high"),
            "low": number(row.get("low"), f"{symbol}.{day}.low"),
            "close": number(row.get("close"), f"{symbol}.{day}.close"),
            "volume": number(row.get("volume"), f"{symbol}.{day}.volume"),
            "amount": number(row.get("amount"), f"{symbol}.{day}.amount"),
            "currency": clean(row.get("currency")),
            "adjustment": clean(row.get("adjustment")),
            "volume_unit": clean(row.get("volume_unit")),
            "amount_unit": clean(row.get("amount_unit")),
            "price_unit": clean(row.get("price_unit")),
            "snapshot_available_at": snapshot_date,
            "source_id": SOURCE_IDS["prices_hk"] if symbol.endswith(".HK") else SOURCE_IDS["prices_a"],
        })
    price_rows.sort(key=lambda row: (row["symbol"], row["date"]))
    require(len({(r["symbol"], r["date"]) for r in price_rows}) == len(price_rows), "duplicate price dates")

    index_rows: list[dict[str, Any]] = []
    for row in index_raw:
        index_rows.append({
            "index_code": clean(row.get("index_code")),
            "date": iso_date(row.get("date")),
            "open": number(row.get("open"), "index.open"),
            "high": number(row.get("high"), "index.high"),
            "low": number(row.get("low"), "index.low"),
            "close": number(row.get("close"), "index.close"),
            "volume": number(row.get("volume"), "index.volume"),
            "amount": number(row.get("amount"), "index.amount"),
            "currency": clean(row.get("currency")),
            "adjustment": clean(row.get("adjustment")),
            "volume_unit": clean(row.get("volume_unit")),
            "amount_unit": clean(row.get("amount_unit")),
            "price_unit": clean(row.get("price_unit")),
            "snapshot_available_at": snapshot_date,
            "source_id": SOURCE_IDS["index"],
        })
    index_rows.sort(key=lambda row: (row["index_code"], row["date"]))
    require(len({(r["index_code"], r["date"]) for r in index_rows}) == len(index_rows), "duplicate index dates")

    # Disclosure metadata and input PDF integrity; PDFs are not copied.
    disclosures: list[dict[str, Any]] = []
    for row in disclosures_raw:
        symbol = (clean(row.get("security")) or "").upper()
        require(symbol in expected, f"unknown disclosure symbol: {symbol!r}")
        if symbol not in expected:
            continue
        local = source_dir / (clean(row.get("local_file")) or "")
        require(local.is_file(), f"missing input PDF for {symbol}")
        if local.is_file():
            body = local.read_bytes()
            require(body.startswith(b"%PDF-"), f"not a PDF: {symbol}")
            require(len(body) == int(row.get("bytes") or -1), f"PDF byte mismatch: {symbol}")
            require(sha256(local) == row.get("sha256"), f"PDF SHA mismatch: {symbol}")
        source = source_urls(row, symbol, registry)
        title = clean(row.get("title")) or ""
        report_period_label = clean(row.get("report_period"))
        if not report_period_label:
            year_match = re.search(r"(20\d{2})年年度报告", title)
            if year_match:
                report_period_label = f"FY{year_match.group(1)}"
        disclosures.append({
            "symbol": symbol,
            "company": expected[symbol]["name"],
            "market": "HK" if symbol.endswith(".HK") else "A",
            "document_type": clean(row.get("document_type")) or "annual_report",
            "title": title,
            "report_period": report_period_label,
            "published_at": clean(row.get("published_at")),
            "published_at_basis": clean(row.get("published_at_basis")),
            "retrieved_at": clean(row.get("retrieved_at")) or snapshot_time,
            "source_id": source["source_id"],
            "source_page_url": source["source_page_url"],
            "source_url": clean(row.get("source_url")) or "",
            "sha256": clean(row.get("sha256")),
            "bytes": int(row.get("bytes") or 0),
            "pages": int(row.get("pages") or 0),
        })
    disclosures.sort(key=lambda row: row["symbol"])

    if errors:
        print("validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    # Build clean company metadata from the explicit source registry and data.
    reporting_currency = {}
    quote_currency = {}
    for row in financial_rows:
        reporting_currency[row["symbol"]] = row["currency"]
    for row in price_rows:
        quote_currency[row["symbol"]] = row["currency"]
    fiscal_year_end = {}
    for row in financial_rows:
        if row.get("fiscal_year_end_md"):
            fiscal_year_end[row["symbol"]] = row["fiscal_year_end_md"]
    companies = []
    for symbol in sorted(expected):
        item = expected[symbol]
        market = "HK" if symbol.endswith(".HK") else "A"
        exchange = "HKEX" if market == "HK" else ("SSE" if symbol.endswith(".SH") else "SZSE")
        companies.append({
            "symbol": symbol,
            "name": item["name"],
            "market": market,
            "exchange": exchange,
            "security_type": "equity",
            "role": item.get("role"),
            "reporting_currency": reporting_currency.get(symbol, "CNY"),
            "quote_currency": quote_currency.get(symbol),
            "fiscal_year_end_md": fiscal_year_end.get(symbol),
            "financial_source_id": SOURCE_IDS["HK_financial"] if market == "HK" else SOURCE_IDS["A_financial"],
        })

    definitions = {
        "schema_version": "finance-metrics-v1",
        "as_of_semantics": (
            "财务记录只有在 available_at <= as_of 时才可见；available_at 是本次聚合快照采集日，"
            "不是报告期结束日或披露日。"
        ),
        "metrics": {
            "revenue": {
                "label": "营业收入",
                "definition": "A 股取总营业收入；港股取经营收入。报表金额为人民币元。",
                "unit": "元（整数人民币）",
                "raw_fields": {"A": "TOTALOPERATEREVE", "HK": "OPERATE_INCOME"},
            },
            "net_profit": {
                "label": "净利润（口径见定义）",
                "definition": "A 股为归属于母公司股东的净利润；港股为股东应占利润。两个口径不能直接混用。",
                "unit": "元（整数人民币）",
                "raw_fields": {"A": "PARENTNETPROFIT", "HK": "HOLDER_PROFIT"},
            },
            "eps": {
                "label": "基本每股收益",
                "definition": "基本每股收益，人民币元/股；不代表摊薄每股收益。",
                "unit": "元/股",
                "raw_fields": {"A": "EPSJB", "HK": "BASIC_EPS"},
            },
            "roe": {
                "label": "净资产收益率",
                "definition": "接口提供的 ROE 指标，单位为百分比；A 股用 ROEJQ，港股用 ROE_AVG，具体计算口径仍以数据源为准。",
                "unit": "百分比",
                "raw_fields": {"A": "ROEJQ", "HK": "ROE_AVG"},
            },
            "gross_margin": {
                "label": "毛利率（财务指标）",
                "definition": "财务指标表中的毛利率，单位为百分比；不是主营构成表中的 0—1 比例。",
                "unit": "百分比",
                "raw_fields": {"A": "XSMLL", "HK": "GROSS_PROFIT_RATIO"},
            },
            "business_mix_gross_margin_ratio": {
                "label": "主营构成毛利率（比例）",
                "definition": "主营构成表中的毛利率，按 0—1 小数保存，不能和财务指标毛利率百分比混用。",
                "unit": "0—1 小数",
            },
            "period_basis": {
                "label": "报告期口径",
                "definition": "A 股一季报/中报/三季报是年初至今累计值，不是单季度值；港股样本为年度值。",
                "values": sorted(set(PERIOD_BASIS.values())),
            },
        },
        "gross_margin_units": {
            "financial_metric": "percent",
            "business_mix": "fraction_0_1",
        },
    }

    sources = [
        {
            "id": SOURCE_IDS["A_financial"],
            "provider": "Eastmoney via AKShare",
            "type": "structured_financial_provider",
            "url": "https://akshare.akfamily.xyz/data/stock/stock_finance.html",
            "used_for": "A-share financial indicator snapshot",
            "akshare_version": "1.20.37",
            "retrieved_at": snapshot_time,
            "terms": "provider terms; AKShare is an access library, not the data owner",
        },
        {
            "id": SOURCE_IDS["HK_financial"],
            "provider": "Eastmoney via AKShare",
            "type": "structured_financial_provider",
            "url": "https://akshare.akfamily.xyz/data/stock/stock_finance.html",
            "used_for": "HK financial indicator snapshot",
            "akshare_version": "1.20.37",
            "retrieved_at": snapshot_time,
            "terms": "provider terms; AKShare is an access library, not the data owner",
        },
        {
            "id": SOURCE_IDS["business"],
            "provider": "Eastmoney via AKShare",
            "type": "structured_business_provider",
            "url": "https://akshare.akfamily.xyz/data/stock/stock_finance.html",
            "used_for": "A-share business mix snapshot",
            "akshare_version": "1.20.37",
            "retrieved_at": snapshot_time,
            "terms": "provider terms; current aggregate only",
        },
        {
            "id": SOURCE_IDS["prices_a"],
            "provider": "Eastmoney via AKShare",
            "type": "daily_quotes",
            "url": "https://akshare.akfamily.xyz/data/stock/stock_quote.html",
            "used_for": "A-share daily qfq quotes",
            "akshare_version": "1.20.37",
            "retrieved_at": snapshot_time,
            "terms": "provider terms",
        },
        {
            "id": SOURCE_IDS["prices_hk"],
            "provider": "Eastmoney via AKShare",
            "type": "daily_quotes",
            "url": "https://akshare.akfamily.xyz/data/stock/stock_quote.html",
            "used_for": "HK daily qfq quotes",
            "akshare_version": "1.20.37",
            "retrieved_at": snapshot_time,
            "terms": "provider terms",
        },
        {
            "id": SOURCE_IDS["index"],
            "provider": "Eastmoney via AKShare",
            "type": "daily_index",
            "url": "https://akshare.akfamily.xyz/data/stock/stock_quote.html",
            "used_for": "CSI 300 daily index",
            "akshare_version": "1.20.37",
            "retrieved_at": snapshot_time,
            "terms": "provider terms",
        },
        {
            "id": SOURCE_IDS["cninfo"],
            "provider": "巨潮资讯 CNINFO",
            "type": "official_disclosure_metadata",
            "url": "http://www.cninfo.com.cn/",
            "used_for": "A-share annual report metadata and PDF verification",
            "retrieved_at": snapshot_time,
            "terms": "public disclosure site; attribution and site terms apply",
        },
        {
            "id": SOURCE_IDS["alibaba_ir"],
            "provider": "Alibaba Group IR",
            "type": "official_disclosure_metadata",
            "url": "https://www.alibabagroup.com/en-US/ir-financial-reports-financial-results",
            "used_for": "Alibaba FY2026 annual report metadata",
            "retrieved_at": snapshot_time,
            "terms": "company website terms",
        },
        {
            "id": SOURCE_IDS["tencent_ir"],
            "provider": "Tencent IR",
            "type": "official_disclosure_metadata",
            "url": "https://www.tencent.com/en-us/investors/financial-reports.html",
            "used_for": "Tencent FY2025 annual report metadata",
            "retrieved_at": snapshot_time,
            "terms": "company website terms",
        },
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "companies.json", companies)
    write_json(output_dir / "metric_definitions.json", definitions)
    write_json(output_dir / "sources.json", sources)
    write_json(output_dir / "disclosures.json", disclosures)
    write_jsonl(output_dir / "financials.jsonl", financial_rows)
    write_jsonl(output_dir / "business_mix.jsonl", business_rows)
    write_jsonl(output_dir / "prices.jsonl", price_rows)
    write_jsonl(output_dir / "index_prices.jsonl", index_rows)

    package_files = (
        "business_mix.jsonl", "companies.json", "disclosures.json",
        "financials.jsonl", "index_prices.jsonl", "metric_definitions.json",
        "prices.jsonl", "sources.json",
    )
    files = {}
    for name in package_files:
        path = output_dir / name
        files[name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    manifest = {
        "schema_version": "finance-package-v1",
        "snapshot": {"available_at": snapshot_date, "collected_at": snapshot_time},
        "generated_from": "explicit standardized capture; original PDFs validated but not copied",
        "counts": {
            "companies": len(companies),
            "financial_records": len(financial_rows),
            "business_mix_records": len(business_rows),
            "price_rows": len(price_rows),
            "index_rows": len(index_rows),
            "disclosures": len(disclosures),
            "disclosure_pages": sum(int(row["pages"]) for row in disclosures),
        },
        "date_ranges": {
            "financial_report_periods": {
                "min": min(row["report_period"] for row in financial_rows),
                "max": max(row["report_period"] for row in financial_rows),
            },
            "prices": {
                "min": min(row["date"] for row in price_rows),
                "max": max(row["date"] for row in price_rows),
            },
            "index": {
                "min": min(row["date"] for row in index_rows),
                "max": max(row["date"] for row in index_rows),
            },
        },
        "period_basis_counts": {
            basis: sum(1 for row in financial_rows if row["period_basis"] == basis)
            for basis in sorted(PERIOD_BASIS.values())
        },
        "units": {
            "financial_amount": "whole CNY",
            "eps": "CNY/share",
            "financial_ratios": "percent",
            "business_mix_ratios": "fraction 0-1",
            "financial_gross_margin": "percent",
            "business_mix_gross_margin": "fraction 0-1",
            "quote_price": "quote currency per share",
            "A_volume": "lot_100_shares",
            "HK_volume": "shares",
            "index": "index points",
        },
        "source_ids": sorted(source["id"] for source in sources),
        "files": files,
        "not_included": [
            "PDF binaries (metadata, SHA-256, byte count and page count only)",
            "financial revision history / as-of versions",
            "HK notice dates (not supplied by aggregate interface)",
            "HK business-mix table",
            "news-event table",
            "graph entities, relationships and LLM extraction",
        ],
        "data_units": {
            "financial_records": "security/report-period rows, not filings",
            "business_mix_records": "security/report-period/segment rows",
            "prices": "security/date rows",
            "index_prices": "index/date rows",
            "disclosures": "annual-report PDFs",
            "chunks": 0,
            "triples": 0,
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps({
        "output": str(output_dir),
        "companies": len(companies),
        "financial_records": len(financial_rows),
        "business_mix_records": len(business_rows),
        "price_rows": len(price_rows),
        "index_rows": len(index_rows),
        "disclosures": len(disclosures),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except (ValueError, KeyError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        code = 2
    raise SystemExit(code)
