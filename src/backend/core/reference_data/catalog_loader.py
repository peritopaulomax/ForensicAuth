"""Load macros / populations from YAML under ``reference_data/*/catalog|populations``.

YAML is the source of truth for UI checkboxes when present; Python dicts remain
as fallback so runtime never breaks if files are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml

from core.reference_data.paths import get_reference_data_root

ItemFactory = Callable[[str, str], Any]
T = TypeVar("T")


@dataclass(frozen=True)
class LoadedMacros:
    macros: dict[str, dict[str, Any]]
    bases: dict[str, dict[str, Any]]
    source: str  # "yaml" | "fallback"
    path: Path | None = None


def _macros_path(domain: str) -> Path:
    return get_reference_data_root() / domain / "catalog" / "macros.yaml"


def _population_path(domain: str, population_id: str) -> Path:
    return get_reference_data_root() / domain / "populations" / f"{population_id}.yaml"


def _read_yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


@lru_cache(maxsize=8)
def _cached_macros_mtime(domain: str, mtime_ns: int) -> LoadedMacros | None:
    """Cache key includes mtime so edits to macros.yaml reload without restart."""
    del mtime_ns  # used only as cache key
    path = _macros_path(domain)
    doc = _read_yaml(path)
    if not doc:
        return None
    return None  # filled by load_macros — see below


def load_macros(
    domain: str,
    *,
    item_factory: ItemFactory,
    fallback_macros: dict[str, dict[str, Any]],
    fallback_bases: dict[str, dict[str, Any]] | None = None,
) -> LoadedMacros:
    """Load ``catalog/macros.yaml``; fall back to in-code macros/bases."""
    path = _macros_path(domain)
    doc = _read_yaml(path)
    if not doc or not isinstance(doc.get("macros"), dict):
        return LoadedMacros(
            macros=fallback_macros,
            bases=fallback_bases or {},
            source="fallback",
            path=None,
        )

    macros: dict[str, dict[str, Any]] = {}
    for macro_id, raw in doc["macros"].items():
        if not isinstance(raw, dict):
            continue
        items_raw = raw.get("items") or []
        items = []
        for row in items_raw:
            if not isinstance(row, dict):
                continue
            base = str(row.get("base_group") or row.get("base") or "").strip()
            subgroup = str(row.get("subgroup") or row.get("generator") or "").strip()
            if base and subgroup:
                items.append(item_factory(base, subgroup))
        macros[str(macro_id)] = {
            "label": str(raw.get("label") or macro_id),
            "year_range": raw.get("year_range"),
            "description": str(raw.get("description") or ""),
            "items": items,
        }

    bases: dict[str, dict[str, Any]] = {}
    raw_bases = doc.get("bases") if isinstance(doc.get("bases"), dict) else {}
    for base_id, raw in raw_bases.items():
        if not isinstance(raw, dict):
            continue
        gens = raw.get("generators") or []
        bases[str(base_id)] = {
            "label": str(raw.get("label") or base_id),
            "description": str(raw.get("description") or ""),
            "paper_title": raw.get("paper_title"),
            "paper_url": raw.get("paper_url"),
            "generators": [str(g) for g in gens],
        }

    if not macros:
        return LoadedMacros(
            macros=fallback_macros,
            bases=fallback_bases or {},
            source="fallback",
            path=path,
        )
    return LoadedMacros(macros=macros, bases=bases, source="yaml", path=path)


def load_population(
    domain: str,
    population_id: str,
) -> dict[str, Any] | None:
    """Return a population YAML document or None."""
    return _read_yaml(_population_path(domain, population_id))


def population_items(
    domain: str,
    population_id: str,
    *,
    item_factory: ItemFactory,
    which: str = "fit_items",
) -> list[Any]:
    """Parse fit_items / test_items from a population YAML."""
    doc = load_population(domain, population_id)
    if not doc:
        return []
    rows = doc.get(which) or doc.get("items") or []
    out: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        base = str(row.get("base_group") or row.get("base") or "").strip()
        subgroup = str(row.get("subgroup") or row.get("generator") or "").strip()
        if base and subgroup:
            out.append(item_factory(base, subgroup))
    return out


def population_as_dicts(domain: str, population_id: str, *, which: str = "fit_items") -> list[dict[str, str]]:
    doc = load_population(domain, population_id)
    if not doc:
        return []
    rows = doc.get(which) or doc.get("items") or []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        base = str(row.get("base_group") or row.get("base") or "").strip()
        subgroup = str(row.get("subgroup") or row.get("generator") or "").strip()
        if base and subgroup:
            out.append({"base_group": base, "subgroup": subgroup})
    return out


def register_base_in_macros_yaml(
    domain: str,
    *,
    base_id: str,
    label: str,
    generators: list[str],
    description: str = "",
    paper_title: str | None = None,
    paper_url: str | None = None,
    macro_id: str | None = None,
    macro_label: str | None = None,
) -> Path:
    """Append/update a base in macros.yaml (and optionally a new macro bucket)."""
    path = _macros_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = _read_yaml(path) or {
        "version": 1,
        "domain": domain,
        "macros": {},
        "bases": {},
    }
    bases = doc.setdefault("bases", {})
    bases[base_id] = {
        "label": label,
        "description": description,
        "paper_title": paper_title,
        "paper_url": paper_url,
        "generators": list(generators),
    }
    if macro_id:
        macros = doc.setdefault("macros", {})
        existing = macros.get(macro_id) if isinstance(macros.get(macro_id), dict) else None
        items = list((existing or {}).get("items") or [])
        known = {(i.get("base_group"), i.get("subgroup")) for i in items if isinstance(i, dict)}
        for gen in generators:
            key = (base_id, gen)
            if key not in known:
                items.append({"base_group": base_id, "subgroup": gen})
                known.add(key)
        macros[macro_id] = {
            "label": (existing or {}).get("label") or macro_label or macro_id,
            "year_range": (existing or {}).get("year_range"),
            "description": (existing or {}).get("description") or description,
            "items": items,
        }
    path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    clear_catalog_cache()
    return path


def clear_catalog_cache() -> None:
    _cached_macros_mtime.cache_clear()
