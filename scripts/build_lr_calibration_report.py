#!/usr/bin/env python3
"""Build a compact markdown report from LR calibration JSON reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric_line(name: str, metrics: dict[str, Any]) -> str:
    return (
        f"| {name} | {metrics.get('rows', '')} | {metrics.get('cllr', float('nan')):.4f} | "
        f"{metrics.get('min_cllr', float('nan')):.4f} | {metrics.get('auc', float('nan')):.4f} | "
        f"{metrics.get('eer', float('nan')):.4f} | {metrics.get('wrong_extreme_lr_count', '')} |"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-report", required=True)
    parser.add_argument("--evaluation-report", action="append", required=True)
    parser.add_argument("--out", default="/home/bfl-pcf/VA Suite/outputs/lr_calibration/reports/final_lr_calibration_report.md")
    args = parser.parse_args()

    train = _load_json(Path(args.train_report))
    evaluations = [_load_json(Path(path)) for path in args.evaluation_report]

    lines = [
        "# Relatório De Calibração LR - Imagens Sintéticas",
        "",
        "## Modelo",
        f"- Modelo: `{train.get('model_path')}`",
        f"- Linhas de treino: `{train.get('rows')}`",
        f"- CLLR treino: `{train.get('train_cllr'):.4f}`",
        f"- AUC treino: `{train.get('train_auc'):.4f}`",
        "",
        "## Métricas Por Avaliação",
        "| Avaliação | Linhas | CLLR | minCLLR | AUC | EER | LRs extremas erradas |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for evaluation in evaluations:
        lines.append(_metric_line(str(evaluation.get("name", "evaluation")), evaluation["overall"]))

    lines.extend(
        [
            "",
            "## Métricas Por Base",
            "| Base | Linhas | CLLR | minCLLR | AUC | EER | LRs extremas erradas |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for evaluation in evaluations:
        for dataset, metrics in sorted(evaluation.get("by_dataset", {}).items()):
            lines.append(_metric_line(f"{evaluation.get('name')} / {dataset}", metrics))

    lines.extend(
        [
            "",
            "## Riscos E Controles",
            "- O que pode falhar: drift de geradores novos, viés de prompts/reais e LRs extremas em bases fora da população de calibração.",
            "- Como detectar: CLLR/minCLLR por base e gerador, Tippett por base, histogramas de LLR e contagem de LRs extremas erradas.",
            "- Como recuperar: recalibrar com amostra moderna adicional, aplicar truncagem conservadora e separar calibradores por domínio se houver evidência empírica.",
            "- Risco residual: qualquer gerador novo fora da população de referência pode alterar a calibração; o uso pericial deve declarar as bases de calibração.",
            "",
        ]
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
