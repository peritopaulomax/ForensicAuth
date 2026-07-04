#!/usr/bin/env python3
"""Run official GRIP CLIP-D on all image evidences from the local 'reais' case."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import torch
from PIL import Image

from core.legacy.truebees_clip_d.clipd_pipeline import clear_clipd_model_cache, infer_clipd_from_pil
from core.legacy.truebees_clip_d.clipd_runtime import clipd_runtime_status

CASE_TITLE = "reais"
DB_PATH = BACKEND / "vasuite_dev.db"
OUT_DIR = ROOT / "results-dev" / f"clipd_reais_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _sigmoid_from_llr(llr: float) -> float:
    if llr >= 0:
        z = math.exp(-llr)
        return 1.0 / (1.0 + z)
    z = math.exp(llr)
    return z / (1.0 + z)


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


def _write_histogram(scores: list[float], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 6), dpi=160)
    plt.hist(scores, bins=60, color="#2563eb", edgecolor="white", alpha=0.88)
    plt.axvline(0.0, color="#dc2626", linestyle="--", linewidth=2, label="limiar oficial LLR = 0")
    plt.title("CLIP-D oficial GRIP no caso 'reais' - distribuição dos LLR")
    plt.xlabel("Score LLR do CLIP-D (LLR > 0 => fake/AI)")
    plt.ylabel("Quantidade de imagens")
    plt.grid(axis="y", alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def main() -> int:
    ok, reason = clipd_runtime_status()
    if not ok:
        print(f"CLIP-D indisponivel: {reason}", flush=True)
        return 2

    evidences = _load_evidences()
    if not evidences:
        print(f"Nenhuma evidencia de imagem encontrada para o caso {CASE_TITLE!r}.", flush=True)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "clipd_reais_scores.csv"
    summary_path = OUT_DIR / "clipd_reais_summary.json"
    histogram_path = OUT_DIR / "clipd_reais_histogram.png"

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Saida: {OUT_DIR}", flush=True)
    print(f"Dispositivo inicial: {device}", flush=True)
    print(f"Evidencias: {len(evidences)}", flush=True)

    real_count = 0
    fake_count = 0
    error_count = 0
    scores: list[float] = []

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "idx",
                "evidence_id",
                "filename",
                "file_path",
                "sha256",
                "clipd_llr",
                "score_ai_sigmoid",
                "decision",
                "error",
            ],
        )
        writer.writeheader()

        for idx, row in enumerate(evidences, start=1):
            filename = row["original_filename"] or row["filename"] or row["id"]
            path = _resolve_evidence_path(row["file_path"])
            try:
                with Image.open(path) as img:
                    llr = infer_clipd_from_pil(img.convert("RGB"), device)
                decision = "FAKE" if llr > 0 else "REAL"
                prob = _sigmoid_from_llr(llr)
                scores.append(llr)
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
                        "clipd_llr": f"{llr:.8f}",
                        "score_ai_sigmoid": f"{prob:.8f}",
                        "decision": decision,
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
                        "clipd_llr": "",
                        "score_ai_sigmoid": "",
                        "decision": "ERROR",
                        "error": repr(exc),
                    }
                )
            fh.flush()

            if idx == 1 or idx % 25 == 0 or idx == len(evidences):
                done = real_count + fake_count + error_count
                print(
                    f"{idx}/{len(evidences)} processadas | REAL={real_count} FAKE={fake_count} ERRO={error_count}",
                    flush=True,
                )

    if scores:
        _write_histogram(scores, histogram_path)

    total_valid = real_count + fake_count
    summary = {
        "case_title": CASE_TITLE,
        "total_evidences": len(evidences),
        "valid_scores": total_valid,
        "classified_real": real_count,
        "classified_fake": fake_count,
        "errors": error_count,
        "expected_all_real_accuracy": (real_count / total_valid) if total_valid else None,
        "fake_rate": (fake_count / total_valid) if total_valid else None,
        "threshold": "LLR > 0 => FAKE; LLR <= 0 => REAL",
        "llr_mean": (sum(scores) / len(scores)) if scores else None,
        "llr_min": min(scores) if scores else None,
        "llr_max": max(scores) if scores else None,
        "csv_path": str(csv_path),
        "histogram_path": str(histogram_path) if scores else None,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    clear_clipd_model_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
