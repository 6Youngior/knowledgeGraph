"""Prepare cited PDF text and page-aware chunks with PyMuPDF and LangChain.

Run after disclosure collection. The catalogue counts original documents;
pages and chunks have separate counts and retain their parent document IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path

from research_tools import source_available_on


def read_records(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
        return value if isinstance(value, list) else value["documents"]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def write_jsonl(path: Path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def checked_pdf(record, cache_dir: Path, max_bytes: int):
    name = record.get("local_file") or record.get("cache_path") or record.get("file") or record.get("path")
    if not name:
        raise ValueError("metadata has no local_file")
    path = (cache_dir / name).resolve()
    if not path.is_relative_to(cache_dir.resolve()) or path.suffix.lower() != ".pdf":
        raise ValueError("PDF path must remain inside the input cache")
    if path.stat().st_size > max_bytes:
        raise ValueError("PDF exceeds the per-file size limit")
    body = path.read_bytes()
    if not body.startswith(b"%PDF-"):
        raise ValueError("file has no PDF header")
    digest = hashlib.sha256(body).hexdigest()
    if not record.get("sha256") or digest != record["sha256"]:
        raise ValueError("PDF SHA-256 does not match metadata")
    return path, digest


def pdf_pages(path: Path, output_format: str, max_pages: int):
    import pymupdf

    with pymupdf.open(path) as document:
        if document.is_encrypted:
            raise ValueError("encrypted PDF requires a separate authorised extraction")
        if document.page_count > max_pages:
            raise ValueError("PDF exceeds the page limit; no partial document was counted")
        if output_format == "markdown":
            import pymupdf4llm
            pages = pymupdf4llm.to_markdown(document, page_chunks=True, show_progress=False, write_images=False)
            return [{"page": i + 1, "text": item["text"]} for i, item in enumerate(pages)]
        return [{"page": i + 1, "text": page.get_text("text", sort=True)} for i, page in enumerate(document)]


def prepare(records, cache_dir: Path, output_dir: Path, *, output_format="text",
            chunk_size=1800, chunk_overlap=200, max_pdf_bytes=40 * 1024 * 1024,
            max_pages=600, limit=40):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if output_format not in {"text", "markdown"}:
        raise ValueError("format must be text or markdown")
    if chunk_size < 100 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk size must be at least 100, with smaller non-negative overlap")
    if min(max_pdf_bytes, max_pages, limit) <= 0:
        raise ValueError("document limits must be positive")
    cache_dir, output_dir = Path(cache_dir), Path(output_dir)
    if cache_dir.resolve() == output_dir.resolve():
        raise ValueError("input cache and prepared output must be separate directories")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, add_start_index=True,
        separators=["\n\n", "\n", "。", "；", ". ", "，", " ", ""],
    )
    docs, chunks, failures, duplicates = [], [], [], []
    seen_raw, seen_text = {}, {}
    records = list(records)
    for record in records[:limit]:
        try:
            path, raw_hash = checked_pdf(record, cache_dir, max_pdf_bytes)
            if raw_hash in seen_raw:
                duplicates.append({"symbol": record.get("symbol") or record.get("security"),
                                   "duplicate_of": seen_raw[raw_hash], "basis": "pdf_sha256"})
                continue
            pages = pdf_pages(path, output_format, max_pages)
            body = "\n\n".join(page["text"].strip() for page in pages).strip()
            if len(body) < 200:
                raise ValueError("too little extracted text; inspect the PDF or use OCR")
            text_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if text_hash in seen_text:
                duplicates.append({"symbol": record.get("symbol") or record.get("security"),
                                   "duplicate_of": seen_text[text_hash], "basis": "text_sha256"})
                continue
            doc_id = "src:filing-" + raw_hash[:24]
            source = {
                "id": doc_id, "title": record.get("title", ""),
                "symbol": record.get("symbol") or record.get("security", ""),
                "url": record.get("source_url") or record.get("url", ""),
                "publisher": record.get("publisher") or record.get("source", ""),
                "published_at_basis": record.get("published_at_basis", ""),
                "published_at": record.get("published_at") or "",
                "retrieved_at": record.get("retrieved_at") or datetime.now(timezone.utc).isoformat(),
                "version_status": record.get("version_status") or "observed_version",
            }
            if record.get("available_at"):
                source["available_at"] = record["available_at"]
            source["available_at"] = source_available_on(source)
            filename = raw_hash[:24]
            suffix = ".md" if output_format == "markdown" else ".txt"
            body_file = "text/" + filename + suffix
            pages_file = "pages/" + filename + ".jsonl"
            doc_chunks = []
            for page in pages:
                for i, item in enumerate(splitter.create_documents([page["text"]])):
                    start = item.metadata["start_index"]
                    if start < 0:
                        raise ValueError("splitter could not locate a chunk in its original page")
                    doc_chunks.append({"id": f"{doc_id}:p{page['page']}:{i}", "source_id": doc_id,
                                   "page": page["page"], "char_start": start,
                                   "char_end": start + len(item.page_content), "text": item.page_content,
                                   "available_at": source["available_at"]})
            (output_dir / "text").mkdir(parents=True, exist_ok=True)
            (output_dir / body_file).write_text(body, encoding="utf-8", newline="\n")
            write_jsonl(output_dir / pages_file, pages)
            source.update({"pdf_sha256": raw_hash, "text_sha256": text_hash,
                           "text_file": body_file, "pages_file": pages_file,
                           "text_characters": len(body), "pages": len(pages),
                           "chunks": len(doc_chunks), "complete": True})
            docs.append(source)
            chunks.extend(doc_chunks)
            seen_raw[raw_hash], seen_text[text_hash] = doc_id, doc_id
        except (ValueError, KeyError, OSError, RuntimeError) as error:
            failures.append({"title": record.get("title", ""),
                             "symbol": record.get("symbol") or record.get("security", ""),
                             "error": str(error)})
    write_jsonl(output_dir / "documents.jsonl", docs)
    write_jsonl(output_dir / "chunks.jsonl", chunks)
    write_jsonl(output_dir / "failures.jsonl", failures)
    write_jsonl(output_dir / "duplicates.jsonl", duplicates)
    report = {
        "input_records": len(records), "selected_records": min(len(records), limit),
        "documents": len(docs), "pages": sum(row["pages"] for row in docs), "chunks": len(chunks),
        "text_characters": sum(row["text_characters"] for row in docs),
        "duplicates": len(duplicates), "failures": len(failures), "format": output_format,
        "versions": {name: importlib.metadata.version(name) for name in ["PyMuPDF", "langchain-text-splitters"]},
    }
    (output_dir / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="Prepare cited PDF text and page-aware chunks")
    parser.add_argument("--input", required=True, type=Path, help="disclosure metadata JSONL or JSON")
    parser.add_argument("--cache-dir", type=Path, help="base directory for local_file; defaults to metadata directory")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--format", choices=["text", "markdown"], default="text")
    parser.add_argument("--chunk-size", type=int, default=1800)
    parser.add_argument("--overlap", type=int, default=200)
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    report = prepare(read_records(args.input), args.cache_dir or args.input.parent, args.output,
                     output_format=args.format, chunk_size=args.chunk_size,
                     chunk_overlap=args.overlap, limit=args.limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
