"""Package source, real data, built demo and slides, excluding local state."""
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "FinGraph-期中展示交付.zip"
ROOT_FILES = {"README.md", "ATTRIBUTIONS.md", "start.ps1", ".env.example", ".gitignore"}
FOLDERS = {"code", "data", "docs", "visualization"}
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "runtime", "build", ".cache", "pdf_preview", "video_preview",
             "preview", "tasks", "ui_review", "new_pdf_preview"}
SKIP_FILES = {"CHECKPOINT.md", "rendered_sources.json", "browser_failure.png", "ui_initial.png",
              "OPTIMIZATION_BRIEF.md", "OPTIMIZATION_CHECKPOINT.md", "OPTIMIZATION_STATUS.md",
              "PROJECT_PLAN.md", "IMPLEMENTATION_CONTRACT.md", "source_verification_local.json",
              "_patch_edges2.py", "_probe_glm5.py"}
SKIP_SUFFIXES = {".ndjson", ".log", ".pyc", ".zip", ".aux", ".out", ".nav", ".snm", ".toc"}


def files():
    if (ROOT / '.git').is_dir():
        result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                                cwd=ROOT, capture_output=True, check=True)
        paths = set(result.stdout.decode('utf-8').split('\0')) - {''}
        # Keep the original recording in the local delivery archive only.
        if (ROOT / 'visualization/FinGraph-demo.webm').is_file():
            paths.add('visualization/FinGraph-demo.webm')
        for name in sorted(paths):
            path = ROOT / name
            if path.is_file() and not path.is_symlink():
                yield path, Path(name)
        return
    for folder, directories, names in os.walk(ROOT):
        here = Path(folder)
        relative = here.relative_to(ROOT)
        if relative == Path("."):
            directories[:] = sorted(d for d in directories if d in FOLDERS)
        else:
            directories[:] = sorted(d for d in directories if d not in SKIP_DIRS)
        for name in sorted(names):
            path = here / name
            rel = path.relative_to(ROOT)
            if relative == Path(".") and name not in ROOT_FILES:
                continue
            if name in SKIP_FILES or path.suffix.lower() in SKIP_SUFFIXES or name == ".env":
                continue
            if path.is_symlink() or name.startswith("subagent") or (rel.parts[0] == "docs" and name.startswith("task_")):
                continue
            if rel.parts[:2] == ("docs", "results") and path.suffix.lower() not in {".json", ".md"}:
                continue
            if name == "release_manifest.json":
                continue
            yield path, rel


def package():
    entries = []
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, relative in files():
            data = path.read_bytes()
            archive.writestr("FinGraph/" + relative.as_posix(), data)
            entries.append({"path": relative.as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    with zipfile.ZipFile(OUTPUT) as archive:
        assert archive.testzip() is None, "Archive CRC check failed"
        names = set(archive.namelist())
        required = ["README.md", "start.ps1", "code/app.py", "data/knowledge_graph.json", "data/market/02513.HK.csv",
                    "visualization/dist/index.html", "visualization/FinGraph-demo.webm", "visualization/FinGraph-demo.mp4", "docs/presentation/main.tex",
                    "docs/presentation/FinGraph-期中汇报.pdf", "docs/presentation/vendor-fdu/LICENSE",
                    "docs/presentation/generated/new_update.png", "docs/presentation/generated/market_roles.pdf",
                    "code/research.py", "docs/results/research_results.json"]
        assert all("FinGraph/" + name in names for name in required), "A required deliverable is absent"
        assert not any("node_modules/" in name or "/runtime/" in name or name.endswith("/.env") for name in names)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "archive": str(OUTPUT.relative_to(ROOT)),
              "archive_bytes": OUTPUT.stat().st_size, "archive_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
              "file_count": len(entries), "crc_passed": True, "files": entries}
    (ROOT / "docs" / "results" / "release_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    package()
