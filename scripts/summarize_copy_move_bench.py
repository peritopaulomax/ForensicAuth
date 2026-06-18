#!/usr/bin/env python3
"""Plot summary from latest copy_move_pca_jobs benchmark CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
OUT_DIR = WORKSPACE / "results" / "benchmarks"


def main() -> None:
    csv_files = sorted(OUT_DIR.glob("copy_move_pca_jobs_*.csv"))
    if not csv_files:
        print("Nenhum CSV de benchmark encontrado.")
        return
    csv_path = csv_files[-1]
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    md_path = csv_path.with_suffix(".md")
    lines = [
        "# Copy-Move PCA — benchmark de paralelismo",
        "",
        f"Fonte: `{csv_path.name}`",
        "",
        "| Cenario | Largura | Altura | N_JOBS | Tempo (s) |",
        "|---------|---------|--------|--------|-----------|",
    ]
    best: dict[str, tuple[int, float]] = {}
    for row in rows:
        sec = row.get("seconds_min")
        if not sec:
            continue
        t = float(sec)
        n = int(row["n_jobs"])
        sc = row["scenario"]
        lines.append(
            f"| {sc} | {row['width']} | {row['height']} | {n} | {t:.3f} |"
        )
        if sc not in best or t < best[sc][1]:
            best[sc] = (n, t)

    lines.extend(["", "## Recomendacao por cenario", ""])
    for sc, (n, t) in best.items():
        lines.append(f"- **{sc}**: `COPY_MOVE_PCA_N_JOBS={n}` (~{t:.2f}s minimo medido)")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Resumo: {md_path}")


if __name__ == "__main__":
    main()
