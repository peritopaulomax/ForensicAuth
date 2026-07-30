"""Bootstrap do vendor VideoFACT para inferência local (sem dependência de UI)."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from forensics.videofact.videofact_runtime import videofact_vendor_dir

_INSERTED_PATHS: list[str] = []


def _insert_sys_paths(vendor: Path) -> None:
    global _INSERTED_PATHS
    for path in (vendor,):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
            _INSERTED_PATHS.append(text)


def bootstrap_videofact_vendor() -> Path:
    vendor = videofact_vendor_dir()
    if not vendor.is_dir():
        raise FileNotFoundError(f"Vendor VideoFACT nao encontrado: {vendor}")
    _insert_sys_paths(vendor)
    return vendor


@contextmanager
def videofact_vendor_context():
    """Ativa o vendor VideoFACT isolando conflitos de importacao `model`.

    Outros motores (ex.: SLS audio spoofing) tambem inserem um modulo
    top-level `model.py` no ``sys.path``. Sem isolamento, o modulo arquivo
    vence o namespace package `model/` do VideoFACT e a importacao de
    ``model.common`` falha com "'model' is not a package". Este contexto
    coloca o vendor no inicio de ``sys.path``, remove do cache modulos
    `model` conflitantes e restaura o estado ao sair, para nao afetar
    outros componentes que dependem da ordem previa do path.
    """
    vendor = bootstrap_videofact_vendor()
    vendor_text = str(vendor)

    # Salva a posicao original do vendor em sys.path para restaurar depois.
    had_vendor = vendor_text in sys.path
    original_index = sys.path.index(vendor_text) if had_vendor else None

    # Move o vendor para o topo durante o contexto.
    if had_vendor:
        sys.path.remove(vendor_text)
    sys.path.insert(0, vendor_text)

    # Salva e remove modulos `model` de outros vendors que possam estar
    # cacheados; isso evita que Python reuse um `model.py` estranho.
    conflicting_prefixes = ("model", "model.common", "model.videofact_pl_wrapper")
    removed_modules: dict[str, Any] = {}
    for key in list(sys.modules.keys()):
        if key in conflicting_prefixes or key.startswith("model."):
            removed_modules[key] = sys.modules.pop(key)

    try:
        yield
    finally:
        # Restaura sys.path.
        sys.path.remove(vendor_text)
        if had_vendor and original_index is not None:
            sys.path.insert(original_index, vendor_text)

        # Restaura sys.modules para outros detectores (ex.: SLS) que
        # compartilham o mesmo nome de pacote ``model``.
        # Se ``model`` nao existia antes, remove o que o VideoFACT cacheou.
        for key in list(sys.modules.keys()):
            if key in conflicting_prefixes or key.startswith("model."):
                if key not in removed_modules:
                    sys.modules.pop(key, None)
        for key, module in removed_modules.items():
            sys.modules[key] = module
