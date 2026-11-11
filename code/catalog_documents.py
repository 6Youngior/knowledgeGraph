"""Merge prepared document batches into a portable, deduplicated catalogue."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PUBLIC_FIELDS = {
    "id", "title", "symbol", "url", "publisher", "published_at", "published_at_basis",
    "retrieved_at", "version_status", "available_at", "pdf_sha256", "text_sha256",
    "text_characters", "pages", "chunks", "complete",
}


def build_catalog(inputs, output: Path):
    candidates = []
    for directory in inputs:
        directory = Path(directory)
        for line in (directory / "documents.jsonl").read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if not record.get("complete"):
                continue
            body = (directory / record["text_file"]).read_text(encoding="utf-8")
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != record["text_sha256"]:
                raise ValueError(f"prepared text hash mismatch: {record['id']}")
            candidates.append(record)
    def preference(row):
        return (0 if row.get("version_status") in {"original_filing", "archived_version"} else 1,
                row.get("available_at") or "9999-12-31", row["pdf_sha256"])
    by_text = {}
    for row in sorted(candidates, key=preference):
        key = row["text_sha256"]
        if key not in by_text:
            item = {name: value for name, value in row.items() if name in PUBLIC_FIELDS}
            item["urls"] = [row["url"]]
            by_text[key] = item
        elif row["url"] not in by_text[key]["urls"]:
            by_text[key]["urls"].append(row["url"])
    records = sorted(by_text.values(), key=lambda row: (row["symbol"], row.get("published_at") or "", row["id"]))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "documents.jsonl"
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records)
    destination.write_text(body, encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "document-catalog-v1", "documents": len(records),
        "input_prepared_records": len(candidates), "duplicates": len(candidates) - len(records),
        "companies": len({row["symbol"] for row in records}),
        "pages": sum(row["pages"] for row in records),
        "chunks": sum(row["chunks"] for row in records),
        "text_characters": sum(row["text_characters"] for row in records),
        "version_counts": {name: sum(row.get("version_status") == name for row in records)
                           for name in sorted({row.get("version_status", "unknown") for row in records})},
        "catalog_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "text_included": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_catalog(args.inputs, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
