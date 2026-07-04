"""Local IMDL/DL technique paper PDFs (docs/references/papers/imdl/)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_MANIFEST_NAME = "manifest.json"
_PAPERS_SUBDIR = Path("docs") / "references" / "papers" / "imdl"
_TECHNIQUE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def papers_root() -> Path:
    return (_workspace_root() / _PAPERS_SUBDIR).resolve()


def load_manifest() -> dict[str, Any]:
    path = papers_root() / _MANIFEST_NAME
    if not path.is_file():
        return {"techniques": {}}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"techniques": {}}
    techniques = data.get("techniques")
    if not isinstance(techniques, dict):
        data["techniques"] = {}
    return data


def list_paper_technique_ids() -> list[str]:
    techniques = load_manifest().get("techniques", {})
    return sorted(str(key) for key in techniques.keys())


def _normalize_technique_id(technique_id: str) -> str:
    tid = (technique_id or "").strip().lower()
    if not _TECHNIQUE_ID_RE.fullmatch(tid):
        raise ValueError(f"ID de tecnica invalido: {technique_id!r}")
    return tid


def resolve_paper_path(technique_id: str) -> Path | None:
    tid = _normalize_technique_id(technique_id)
    entry = load_manifest().get("techniques", {}).get(tid)
    if not isinstance(entry, dict):
        return None
    local_file = _paper_file_entry(entry, 0).get("local_file")
    if not isinstance(local_file, str) or not local_file.strip():
        return None
    rel = Path(local_file)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    path = (papers_root() / rel).resolve()
    if not str(path).startswith(str(papers_root())):
        return None
    if path.is_file() and path.stat().st_size > 1_000:
        return path
    return None


def _paper_file_entry(entry: dict[str, Any], index: int) -> dict[str, Any]:
    files = entry.get("files")
    if isinstance(files, list) and files:
        if index < 0 or index >= len(files):
            return {}
        item = files[index]
        return item if isinstance(item, dict) else {}
    if index != 0:
        return {}
    return {
        "title": entry.get("title"),
        "venue": entry.get("venue"),
        "local_file": entry.get("local_file"),
    }


def resolve_paper_file_path(technique_id: str, index: int = 0) -> Path | None:
    tid = _normalize_technique_id(technique_id)
    entry = load_manifest().get("techniques", {}).get(tid)
    if not isinstance(entry, dict):
        return None
    local_file = _paper_file_entry(entry, index).get("local_file")
    if not isinstance(local_file, str) or not local_file.strip():
        return None
    rel = Path(local_file)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    path = (papers_root() / rel).resolve()
    if not str(path).startswith(str(papers_root())):
        return None
    if path.is_file() and path.stat().st_size > 1_000:
        return path
    return None


def suggested_download_filename(technique_id: str, index: int = 0) -> str:
    tid = _normalize_technique_id(technique_id)
    entry = load_manifest().get("techniques", {}).get(tid, {})
    venue = ""
    if isinstance(entry, dict):
        paper = _paper_file_entry(entry, index)
        if isinstance(paper.get("venue"), str):
            venue = paper["venue"].replace(" ", "")
        elif isinstance(entry.get("venue"), str):
            venue = entry["venue"].replace(" ", "")
    slug = tid.replace("_", "-")
    if venue:
        suffix = "" if index == 0 else f"_{index + 1}"
        return f"{slug}{suffix}_{venue}.pdf"
    return f"{slug}_paper.pdf"


def get_paper_files_metadata(technique_id: str) -> list[dict[str, Any]]:
    tid = _normalize_technique_id(technique_id)
    entry = load_manifest().get("techniques", {}).get(tid)
    if not isinstance(entry, dict):
        return []
    raw_files = entry.get("files")
    count = len(raw_files) if isinstance(raw_files, list) and raw_files else 1
    files: list[dict[str, Any]] = []
    for index in range(count):
        paper = _paper_file_entry(entry, index)
        if not paper:
            continue
        path = resolve_paper_file_path(tid, index)
        files.append(
            {
                "index": index,
                "title": paper.get("title") or entry.get("title"),
                "venue": paper.get("venue") or entry.get("venue"),
                "available": path is not None,
                "size_bytes": path.stat().st_size if path else None,
                "suggested_filename": suggested_download_filename(tid, index),
            }
        )
    return files


def get_paper_metadata(technique_id: str) -> dict[str, Any] | None:
    tid = _normalize_technique_id(technique_id)
    entry = load_manifest().get("techniques", {}).get(tid)
    if not isinstance(entry, dict):
        return None
    files = get_paper_files_metadata(tid)
    primary = files[0] if files else {}
    sources = entry.get("sources")
    source_urls = [str(url) for url in sources] if isinstance(sources, list) else []
    return {
        "technique_id": tid,
        "title": primary.get("title") or entry.get("title"),
        "venue": primary.get("venue") or entry.get("venue"),
        "repo_url": entry.get("repo"),
        "source_urls": source_urls,
        "available": any(bool(item.get("available")) for item in files),
        "size_bytes": primary.get("size_bytes"),
        "suggested_filename": suggested_download_filename(tid),
        "files": files,
    }
