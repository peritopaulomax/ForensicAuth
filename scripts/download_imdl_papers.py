#!/usr/bin/env python3
"""Baixa PDFs oficiais das técnicas IML/DL para docs/references/papers/imdl/."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs" / "references" / "papers" / "imdl"
MANIFEST = BASE / "manifest.json"

HEADERS = {"User-Agent": "VA-Suite-paper-downloader/1.0 (research)"}


def download(tech_id: str, url: str) -> bool:
    out_dir = BASE / tech_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "paper.pdf"
    print(f"-> {tech_id}: {url}")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        out_path.write_bytes(data)
        ok = len(data) > 50_000 and data[:4] == b"%PDF"
        print(f"  {'OK' if ok else 'AVISO'} ({len(data)} bytes)")
        return ok
    except Exception as exc:
        print(f"  FALHOU: {exc}")
        return False


def main() -> None:
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        items = manifest.get("techniques", {})
        ok_all = True
        for tech_id, meta in items.items():
            url = meta["sources"][0]
            if not download(tech_id, url):
                ok_all = False
        if not ok_all:
            raise SystemExit(1)
    else:
        raise SystemExit(f"Manifest ausente: {MANIFEST}")

    print(f"\nConcluido. PDFs em: {BASE}")


if __name__ == "__main__":
    main()
