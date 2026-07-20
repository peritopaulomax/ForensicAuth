#!/usr/bin/env python3
"""Generate markdown report from POC results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml


def load_poc_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="experiments/poc_latent_typicality/config/poc_typicality.yaml")
    parser.add_argument("--results-dir", default="")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    poc = load_poc_config(project_root / args.config)
    results_dir = Path(args.results_dir) if args.results_dir else project_root / poc["output_root"] / "results"
    results_csv = results_dir / "poc_results.csv"
    best_json = results_dir / "best_config.json"

    df = pd.read_csv(results_csv)
    best = json.loads(best_json.read_text(encoding="utf-8"))
    baseline = df[df["system"].eq("A")].iloc[0]
    best_row = df.sort_values(["test_cllr", "test_min_cllr"]).iloc[0]

    lines = [
        "# POC Tipicidade Latente — Resumo",
        "",
        "## Bases utilizadas",
    ]
    for spec in poc["datasets"]:
        lines.append(f"- **{spec['dataset']}** / {spec.get('subset') or '(sem subset)'} — {spec.get('description', '')}")

    lines.extend(
        [
            "",
            "## Melhor configuração (teste)",
            f"- Sistema: **{best_row['system']}**",
            f"- Distância: `{best_row['distance']}`",
            f"- k: `{best_row['k']}`",
            f"- Cllr teste: `{best_row['test_cllr']:.4f}`",
            f"- minCLLR teste: `{best_row['test_min_cllr']:.4f}`",
            "",
            "## Baseline (sistema A)",
            f"- Cllr teste: `{baseline['test_cllr']:.4f}`",
            f"- minCLLR teste: `{baseline['test_min_cllr']:.4f}`",
            "",
            "## Respostas objetivas",
            f"1. Tipicidade melhora baseline? **{'Sim' if best_row['test_cllr'] < baseline['test_cllr'] else 'Não'}** "
            f"(ΔCllr={best_row['test_cllr'] - baseline['test_cllr']:.4f})",
            f"2. Melhor k: `{best_row['k']}` com distância `{best_row['distance']}`",
            "3. Cosine vs euclidiana: ver `poc_results.csv` agrupando por distance.",
            "4. OOD: comparar sistemas C/D vs B no mesmo k/distância.",
            "5. Sistema completo (D) vs parcial (C): ver tabela completa.",
            "6. Por dataset: ver `plots/cllr_by_dataset.png` e `metrics_by_dataset_*.csv`.",
            "",
            "## Artefatos",
            f"- `{results_csv}`",
            f"- `{best_json}`",
            f"- `{results_dir / 'plots'}`",
            f"- `{results_dir / 'models'}`",
        ]
    )

    out_path = results_dir / "poc_summary.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
