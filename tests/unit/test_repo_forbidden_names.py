"""Freio minimo: nomes legados nao devem voltar a raiz do repo."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

FORBIDDEN_ROOT_NAMES = frozenset(
    {
        "uploads-dev",
        "results-dev",
        "derivatives-dev",
        "peritus_cases-dev",
        "vasuite_dev.db",
        "Legados",
        "archive",
        "adapters",
        "scripts",
        "tools",
        "tmp",
        "brains",
        "knowledge",
        "summaries",
        "experiments",
        "prompts",
        "attic",
    }
)


def _has_payload(path: Path) -> bool:
    if path.is_file():
        return True
    if not path.is_dir():
        return False
    try:
        return any(p.is_file() for p in path.rglob("*"))
    except OSError:
        return True


def test_forbidden_legacy_names_absent_from_root():
    present = {
        name
        for name in FORBIDDEN_ROOT_NAMES
        if (REPO / name).exists() and _has_payload(REPO / name)
    }
    assert not present, f"sobras na raiz: {sorted(present)}"
