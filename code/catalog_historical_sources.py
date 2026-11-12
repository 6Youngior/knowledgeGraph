"""Build a public historical-source catalogue from private source metadata.

The private metadata/cache are read-only inputs. The public output contains
only URLs, hashes, dates/date bases, and limitations; it never contains cached
bodies, absolute cache paths, session data, or credentials.

Run:
    python code/catalog_historical_sources.py \
      --metadata <private metadata.jsonl> \
      --cache-dir <private cache directory> \
      --output data/history
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "fingraph-historical-source-catalog-v2"
SHANGHAI = ZoneInfo("Asia/Shanghai")

# Official release dates are lower bounds for a public release; a fixed Git/HF
# SHA proves only that a version exists. The URLs are kept beside the dates so
# the public catalogue can show the date basis without copying web bodies.
OFFICIAL_RELEASE_SOURCES = {
    "event:deepseek-r1-release": {
        "date": "2025-01-20",
        "url": "https://api-docs.deepseek.com/news/news250120/",
    },
    "event:glm5-release": {
        "date": "2026-02-12",
        "url": "https://z.ai/blog/glm-5",
    },
    "event:qwen3-release": {
        "date": "2025-04-29",
        "url": "https://qwenlm.github.io/blog/qwen3/",
    },
}

STRICT_REPLAY_STATUSES = {"original_filing", "retrospective_filing"}
ASSUMPTION_STATUSES = {"historical_commit", "historical_revision"}


def _day(value: Any) -> str | None:
    """Return a research day in Asia/Shanghai, validating strictly.

    Date-only values are accepted. Timestamp values must carry a timezone;
    naive timestamps are rejected. An aware timestamp is converted to
    Asia/Shanghai before taking its calendar day.
    """
    text = str(value or "").strip()
    if not text:
        return None

    if "T" not in text and " " not in text:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise ValueError(f"invalid date-only value: {text}") from exc

    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {text}") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"naive timestamp is not allowed: {text}")
    return moment.astimezone(SHANGHAI).date().isoformat()


def _max_day(*values: str | None) -> str | None:
    days = [value for value in values if value]
    return max(days) if days else None


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_file(cache_dir: Path, relative: str) -> Path:
    """Resolve a metadata path inside the explicit private cache directory."""
    if not relative or not isinstance(relative, str):
        raise ValueError("private file path is missing")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError("private file path must be relative to --cache-dir")
    root = cache_dir.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"private file escapes --cache-dir: {relative}") from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"private file not found: {relative}")
    return resolved


def _load_rows(metadata: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(metadata.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("id"):
            raise ValueError(f"metadata line {number} has no id")
        rows.append(row)
    if not rows:
        raise ValueError("metadata has no records")
    return rows


def _date_basis(row: dict[str, Any], release: dict[str, str] | None, official_day: str) -> str:
    if release:
        return f"official release date: {release['url']}"
    return str(row.get("available_at_basis") or f"filing date: {official_day}")


def build_catalog(metadata: Path, cache_dir: Path, output: Path) -> dict[str, Any]:
    """Validate private hashes, then write public metadata-only JSONL files."""
    metadata = Path(metadata)
    cache_dir = Path(cache_dir)
    output = Path(output)
    source_records: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {}

    for row in _load_rows(metadata):
        body_path = _private_file(cache_dir, row.get("cache_file", ""))
        text_path = _private_file(cache_dir, row.get("text_path") or row.get("cache_file", ""))
        body_sha = _sha(body_path)
        text_sha = _sha(text_path)

        declared_body = row.get("content_hash")
        declared_text = row.get("text_hash")
        if declared_body and declared_body != body_sha:
            raise ValueError(f"body hash mismatch: {row['id']}")
        if declared_text and declared_text != text_sha:
            raise ValueError(f"text hash mismatch: {row['id']}")

        version_time = row.get("commit_time") or row.get("published_at")
        version_day = _day(version_time)
        if not version_day:
            raise ValueError(f"missing version date: {row['id']}")

        event_id = str(row.get("event_id") or "")
        release = OFFICIAL_RELEASE_SOURCES.get(event_id)
        if release:
            official_day = _day(release["date"])
            official_url = release["url"]
        else:
            official_day = _day(row.get("published_at")) or version_day
            official_url = ""

        available_at = _max_day(version_day, official_day)
        if not available_at:
            raise ValueError(f"cannot establish a day-level available_at: {row['id']}")

        status = str(row.get("source_version_status") or "")
        strict_eligible = status in STRICT_REPLAY_STATUSES
        if status in ASSUMPTION_STATUSES:
            availability_status = "release_date_assumption"
            available_at_basis = (
                "day-level candidate max(version_date, official release date); "
                "does not prove the SHA body was public that day"
            )
        elif strict_eligible:
            availability_status = "original_filing_date"
            available_at_basis = f"actual filing date: {official_day}"
        else:
            availability_status = "unknown"
            available_at_basis = "unknown filing/version status"

        date_basis = _date_basis(row, release, official_day or "")
        limitations = [
            "fixed version/hash proves body identity, not first public publication",
            "available_at is day-level only; no intraday publication time is claimed",
        ]
        if status in ASSUMPTION_STATUSES:
            limitations.append("availability_status=release_date_assumption; eligible_for_strict_replay=false")
        if status == "retrospective_filing":
            limitations.append("retrospective filing confirms a prior fact but is available only at its filing date")
        if event_id == "listing:zhipu-02513":
            if "prospectus" in str(row.get("id", "")):
                limitations.append("prospectus states an expected listing date; actual confirmation is a later filing")
            else:
                limitations.append("actual listing confirmation must not be backfilled into January/February views")

        group_id = "body:" + body_sha[:24]
        record = {
            "source_id": row["id"],
            "event_id": event_id,
            "title": row.get("title", ""),
            "publisher": row.get("publisher", ""),
            "url": row.get("url", ""),
            "source_type": row.get("source_type", ""),
            "source_version_status": status,
            "version_time": version_time or "",
            "version_date": version_day,
            "official_publication_date": official_day,
            "official_release_url": official_url,
            "date_basis": date_basis,
            "available_at": available_at,
            "available_at_granularity": "day",
            "available_at_basis": available_at_basis,
            "availability_status": availability_status,
            "eligible_for_strict_replay": strict_eligible,
            "intraday_available_at": None,
            "intraday_claim": False,
            "body_sha256": body_sha,
            "text_sha256": text_sha,
            "body_bytes": body_path.stat().st_size,
            "text_characters": int(row.get("text_chars") or len(text_path.read_text(encoding="utf-8"))),
            "body_group_id": group_id,
            "can_prove_version_exists": True,
            "limitations": limitations,
        }
        source_records.append(record)
        groups.setdefault(group_id, []).append(record)

    source_records.sort(key=lambda item: item["source_id"])
    body_records = []
    for group_id, members in sorted(groups.items()):
        body_records.append({
            "body_group_id": group_id,
            "body_sha256": members[0]["body_sha256"],
            "text_sha256s": sorted({item["text_sha256"] for item in members}),
            "source_ids": sorted(item["source_id"] for item in members),
            "urls": sorted(item["url"] for item in members),
            "event_ids": sorted({item["event_id"] for item in members if item["event_id"]}),
            "source_version_statuses": sorted({item["source_version_status"] for item in members}),
            "body_bytes": members[0]["body_bytes"],
            "source_count": len(members),
        })

    output.mkdir(parents=True, exist_ok=True)
    sources_body = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                           for item in source_records)
    bodies_body = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                          for item in body_records)
    (output / "sources.jsonl").write_text(sources_body, encoding="utf-8", newline="\n")
    (output / "bodies.jsonl").write_text(bodies_body, encoding="utf-8", newline="\n")

    duplicate_groups = [item["body_group_id"] for item in body_records if item["source_count"] > 1]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "sources": len(source_records),
        "independent_bodies": len(body_records),
        "duplicate_sources": len(source_records) - len(body_records),
        "duplicate_body_groups": duplicate_groups,
        "source_version_status_counts": {
            status: sum(item["source_version_status"] == status for item in source_records)
            for status in sorted({item["source_version_status"] for item in source_records})
        },
        "availability_status_counts": {
            status: sum(item["availability_status"] == status for item in source_records)
            for status in sorted({item["availability_status"] for item in source_records})
        },
        "available_at_counts": {
            day: sum(item["available_at"] == day for item in source_records)
            for day in sorted({item["available_at"] for item in source_records})
        },
        "strict_replay_eligible_count": sum(item["eligible_for_strict_replay"] for item in source_records),
        "release_date_assumption_count": sum(
            item["availability_status"] == "release_date_assumption" for item in source_records
        ),
        "intraday_claims": 0,
        "text_included": False,
        "private_paths_included": False,
        "sources_sha256": hashlib.sha256(sources_body.encode("utf-8")).hexdigest(),
        "bodies_sha256": hashlib.sha256(bodies_body.encode("utf-8")).hexdigest(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True,
                        help="private metadata.jsonl; never copied to output")
    parser.add_argument("--cache-dir", type=Path, required=True,
                        help="explicit private cache directory")
    parser.add_argument("--output", type=Path, required=True,
                        help="public metadata-only output directory")
    args = parser.parse_args()
    print(json.dumps(build_catalog(args.metadata, args.cache_dir, args.output),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
