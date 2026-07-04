#!/usr/bin/env python3
"""Run UniversalFakeDetect and FSD on all image evidences from the local 'reais' case."""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import torch
from PIL import Image

from core.legacy.fsd.fsd_pipeline import clear_fsd_model_cache, infer_fsd_from_pil
from core.legacy.fsd.fsd_runtime import fsd_runtime_status
from core.legacy.universal_fake_detect.ufd_pipeline import clear_ufd_model_cache, infer_ufd_from_pil
from core.legacy.universal_fake_detect.ufd_runtime import ufd_runtime_status

CASE_TITLE = "reais"
DB_PATH = BACKEND / "vasuite_dev.db"
RUN_DIR = ROOT / "results-dev" / f"ufd_fsd_reais_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _load_evidences() -> list[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        select e.id, e.original_filename, e.filename, e.file_path, e.sha256
        from evidences e
        join cases c on c.id = e.case_id
        where lower(c.title) = lower(?)
          and c.deleted_at is null
          and e.deleted_at is null
          and e.file_type = 'imagem'
        order by coalesce(e.original_filename, e.filename), e.id
        """,
        (CASE_TITLE,),
    ).fetchall()
    conn.close()
    return rows


def _resolve_evidence_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (BACKEND / path).resolve()


def _write_histogram(
    scores: list[float],
    out_path: Path,
    *,
    title: str,
    xlabel: str,
    threshold: float,
    threshold_label: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 6), dpi=160)
    plt.hist(scores, bins=60, color="#2563eb", edgecolor="white", alpha=0.88)
    plt.axvline(threshold, color="#dc2626", linestyle="--", linewidth=2, label=threshold_label)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("Quantidade de imagens")
    plt.grid(axis="y", alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def _run_detector(
    *,
    detector_id: str,
    label: str,
    evidences: list[sqlite3.Row],
    infer: Callable[[Image.Image, torch.device], Any],
    parse: Callable[[Any], tuple[float, str, dict[str, Any]]],
    histogram_xlabel: str,
    histogram_threshold: float,
    histogram_threshold_label: str,
    clear_cache: Callable[[], None],
    device: torch.device,
) -> dict[str, Any]:
    out_dir = RUN_DIR / detector_id
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{detector_id}_reais_scores.csv"
    summary_path = out_dir / f"{detector_id}_reais_summary.json"
    histogram_path = out_dir / f"{detector_id}_reais_histogram.png"

    real_count = 0
    fake_count = 0
    error_count = 0
    scores: list[float] = []

    print(f"\n[{label}] Saida: {out_dir}", flush=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "idx",
            "evidence_id",
            "filename",
            "file_path",
            "sha256",
            "score",
            "decision",
            "details_json",
            "error",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()

        for idx, row in enumerate(evidences, start=1):
            filename = row["original_filename"] or row["filename"] or row["id"]
            path = _resolve_evidence_path(row["file_path"])
            try:
                with Image.open(path) as img:
                    raw = infer(img.convert("RGB"), device)
                score, decision, details = parse(raw)
                scores.append(score)
                if decision == "REAL":
                    real_count += 1
                else:
                    fake_count += 1
                writer.writerow(
                    {
                        "idx": idx,
                        "evidence_id": row["id"],
                        "filename": filename,
                        "file_path": str(path),
                        "sha256": row["sha256"],
                        "score": f"{score:.8f}",
                        "decision": decision,
                        "details_json": json.dumps(details, ensure_ascii=False, sort_keys=True),
                        "error": "",
                    }
                )
            except Exception as exc:
                error_count += 1
                writer.writerow(
                    {
                        "idx": idx,
                        "evidence_id": row["id"],
                        "filename": filename,
                        "file_path": str(path),
                        "sha256": row["sha256"],
                        "score": "",
                        "decision": "ERROR",
                        "details_json": "{}",
                        "error": repr(exc),
                    }
                )
            fh.flush()

            if idx == 1 or idx % 25 == 0 or idx == len(evidences):
                print(
                    f"[{label}] {idx}/{len(evidences)} | REAL={real_count} FAKE={fake_count} ERRO={error_count}",
                    flush=True,
                )

    if scores:
        _write_histogram(
            scores,
            histogram_path,
            title=f"{label} no caso 'reais' - distribuição dos escores",
            xlabel=histogram_xlabel,
            threshold=histogram_threshold,
            threshold_label=histogram_threshold_label,
        )

    total_valid = real_count + fake_count
    summary = {
        "case_title": CASE_TITLE,
        "detector": label,
        "total_evidences": len(evidences),
        "valid_scores": total_valid,
        "classified_real": real_count,
        "classified_fake": fake_count,
        "errors": error_count,
        "expected_all_real_accuracy": (real_count / total_valid) if total_valid else None,
        "fake_rate": (fake_count / total_valid) if total_valid else None,
        "score_mean": (sum(scores) / len(scores)) if scores else None,
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "csv_path": str(csv_path),
        "histogram_path": str(histogram_path) if scores else None,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    clear_cache()
    return summary


def _parse_ufd(prob: float) -> tuple[float, str, dict[str, Any]]:
    score = float(prob)
    return score, ("FAKE" if score > 0.5 else "REAL"), {"threshold": 0.5, "score_name": "prob_ai"}


def _parse_fsd(result: Any) -> tuple[float, str, dict[str, Any]]:
    score = float(result.z_score)
    threshold = float(result.threshold)
    return (
        score,
        ("FAKE" if bool(result.is_fake) else "REAL"),
        {"threshold": threshold, "score_name": "z_score", "is_fake": bool(result.is_fake)},
    )


def main() -> int:
    statuses = {
        "UniversalFakeDetect": ufd_runtime_status(),
        "FSD": fsd_runtime_status(),
    }
    for name, (ok, reason) in statuses.items():
        if not ok:
            print(f"{name} indisponivel: {reason}", flush=True)
            return 2

    evidences = _load_evidences()
    if not evidences:
        print(f"Nenhuma evidencia de imagem encontrada para o caso {CASE_TITLE!r}.", flush=True)
        return 1

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Saida geral: {RUN_DIR}", flush=True)
    print(f"Dispositivo inicial: {device}", flush=True)
    print(f"Evidencias: {len(evidences)}", flush=True)

    summaries = [
        _run_detector(
            detector_id="universal_fake_detect",
            label="UniversalFakeDetect",
            evidences=evidences,
            infer=infer_ufd_from_pil,
            parse=_parse_ufd,
            histogram_xlabel="Probabilidade AI do UniversalFakeDetect (prob > 0.5 => fake/AI)",
            histogram_threshold=0.5,
            histogram_threshold_label="limiar prob = 0.5",
            clear_cache=clear_ufd_model_cache,
            device=device,
        ),
        _run_detector(
            detector_id="fsd",
            label="FSD",
            evidences=evidences,
            infer=infer_fsd_from_pil,
            parse=_parse_fsd,
            histogram_xlabel="Z-score do FSD (regra is_fake do detector)",
            histogram_threshold=-2.0,
            histogram_threshold_label="limiar FSD z = -2",
            clear_cache=clear_fsd_model_cache,
            device=device,
        ),
    ]
    combined_path = RUN_DIR / "ufd_fsd_reais_summary.json"
    combined_path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResumo combinado: {combined_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
