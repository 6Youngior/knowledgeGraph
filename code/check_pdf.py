"""Check the compiled deliverable, theme provenance and basic text geometry."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

import fitz

from graph_store import write_json

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_THEME_SHA256 = "493e458ec6cd955da6567c613374d2cc1faf25c51e7e21a1e5a959ddeabfa3d3"


def check(pdf_path=None):
    folder = ROOT / "docs" / "presentation"
    pdf_path = Path(pdf_path).resolve() if pdf_path else folder / "FinGraph-期中汇报.pdf"
    theme = folder / "vendor-fdu" / "beamerthemefdu.sty"
    theme_sha = hashlib.sha256(theme.read_bytes()).hexdigest()
    issues = []
    if theme_sha != EXPECTED_THEME_SHA256:
        issues.append("Vendored Fudan theme bytes differ from the documented original")
    main = (folder / "main.tex").read_text(encoding="utf-8-sig")
    if r"\usetheme{fdu}" not in main:
        issues.append("The Fudan theme is not actually selected")
    pages = []
    with fitz.open(pdf_path) as document:
        if not 12 <= len(document) <= 22:
            issues.append(f"Deck should contain readable main slides and necessary backup, got {len(document)} pages")
        for number, page in enumerate(document, start=1):
            text = page.get_text()
            if abs(page.rect.width / page.rect.height - 16 / 9) > .02:
                issues.append(f"Page {number} is not 16:9")
            if re.search(r"统计待生成|未完成占位|TODO|待补充|待集成", text):
                issues.append(f"Unfinished placeholder text on page {number}")
            if "\ufffd" in text:
                issues.append(f"Replacement characters on page {number}")
            outside = []
            footer_collisions = []
            font_sizes = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        x0, y0, x1, y1 = span["bbox"]
                        if x0 < -1 or y0 < -1 or x1 > page.rect.width + 1 or y1 > page.rect.height + 1:
                            outside.append(span["text"])
                        if number > 1 and span["size"] >= 8.5 and y1 > page.rect.height - 11 and y0 < page.rect.height - 5:
                            footer_collisions.append(span["text"])
                        if y0 > 30 and y1 < page.rect.height - 15 and span["text"].strip():
                            font_sizes.extend([round(span["size"], 2)] * len(span["text"]))
            if outside:
                issues.append(f"Text extends beyond page {number}: {outside[:3]}")
            if footer_collisions:
                issues.append(f"Body text collides with footer on page {number}: {footer_collisions[:3]}")
            pages.append({"page": number, "width_pt": page.rect.width, "height_pt": page.rect.height,
                          "text_chars": len(text), "images": len(page.get_images()), "outside_text": outside,
                          "footer_collisions": footer_collisions,
                          "median_content_font_pt": sorted(font_sizes)[len(font_sizes)//2] if font_sizes else None})
    log_path = folder / "build" / "main.log"
    warnings = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "Overfull" in line or line.startswith("!"):
                warnings.append(line)
    if warnings:
        issues.append("LaTeX overflow or error remains in the last build log")
    return {"passed": not issues, "created_at": datetime.now(timezone.utc).isoformat(), "issues": issues,
            "pdf": str(pdf_path.relative_to(ROOT)), "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            "theme_sha256": theme_sha, "theme_license": "Apache-2.0", "page_count": len(pages), "pages": pages,
            "latex_errors_or_overflows": warnings,
            "scope": "Mechanical PDF checks only. Content depth and visual quality require a separate rendered-page review."}


if __name__ == "__main__":
    report = check()
    write_json(ROOT / "docs" / "results" / "pdf_validation.json", report)
    print({k: v for k, v in report.items() if k != "pages"})
    raise SystemExit(0 if report["passed"] else 1)
