"""Local IMDL/DL technique paper PDFs (docs/references/papers/imdl/)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_MANIFEST_NAME = "manifest.json"
_PAPERS_SUBDIR = Path("docs") / "references" / "papers" / "imdl"
_TECHNIQUE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def papers_root() -> Path:
    return (_workspace_root() / _PAPERS_SUBDIR).resolve()


@lru_cache(maxsize=1)
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
    local_file = entry.get("local_file")
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


def suggested_download_filename(technique_id: str) -> str:
    tid = _normalize_technique_id(technique_id)
    entry = load_manifest().get("techniques", {}).get(tid, {})
    venue = ""
    if isinstance(entry, dict) and isinstance(entry.get("venue"), str):
        venue = entry["venue"].replace(" ", "")
    slug = tid.replace("_", "-")
    if venue:
        return f"{slug}_{venue}.pdf"
    return f"{slug}_paper.pdf"


def get_paper_metadata(technique_id: str) -> dict[str, Any] | None:
    tid = _normalize_technique_id(technique_id)
    entry = load_manifest().get("techniques", {}).get(tid)
    if not isinstance(entry, dict):
        return None
    path = resolve_paper_path(tid)
    sources = entry.get("sources")
    source_urls = [str(url) for url in sources] if isinstance(sources, list) else []
    size_bytes = path.stat().st_size if path else None
    return {
        "technique_id": tid,
        "title": entry.get("title"),
        "venue": entry.get("venue"),
        "repo_url": entry.get("repo"),
        "source_urls": source_urls,
        "available": path is not None,
        "size_bytes": size_bytes,
        "suggested_filename": suggested_download_filename(tid),
    }
