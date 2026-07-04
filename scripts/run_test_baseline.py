#!/usr/bin/env python3
"""Run the ForensicAuth test baseline in batches and emit a JSON report.

The full unit test suite currently hangs when executed in a single pytest
process (likely due to GPU/threads/file-handle accumulation). This script
runs the tests in curated batches and merges the results.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIT_DIR = PROJECT_ROOT / "tests" / "unit"

# Curated batches: each batch completes in a reasonable time without hanging.
UNIT_BATCHES: list[list[str]] = [
    [
        "test_adobe_icc_makernote_hints.py",
        "test_audio_plot_snapshot.py",
        "test_audio_plot_traces.py",
        "test_audio_plugins.py",
        "test_audio_prepare.py",
        "test_audio_probe.py",
        "test_auth.py",
        "test_case_access.py",
        "test_case_deletion.py",
        "test_case_lifecycle.py",
        "test_case_shares.py",
        "test_case_transfer.py",
        "test_core.py",
        "test_custody_integration.py",
        "test_custody_narrative_report.py",
        "test_custody.py",
        "test_custody_signing_persist.py",
        "test_custody_signing.py",
        "test_dct_reference_submit.py",
        "test_derivation_lineage.py",
        "test_derivative.py",
        "test_evidence.py",
        "test_evidence_references.py",
        "test_exif_property_hints.py",
        "test_forensic_integrity.py",
        "test_forensic_metadata_insights.py",
        "test_gpu_inference.py",
        "test_gpu_lock.py",
        "test_gpu_queue_service.py",
        "test_iapl_gpu_retry.py",
    ],
    [
        "test_image_plugins.py",
        "test_isom_parser.py",
        "test_isom_similarity.py",
        "test_job_dispatch.py",
        "test_job_preview_reproducibility.py",
        "test_jobs.py",
        "test_jpeg_markers.py",
        "test_jpeg_structure_compare_integration.py",
        "test_jpeg_structure_compare.py",
        "test_jpeg_structure_grid_export.py",
        "test_jpeg_structure_matrix_export.py",
        "test_metadata_extractor.py",
        "test_peritus_bridge.py",
        "test_phase1_security.py",
        "test_phase2_domain.py",
        "test_phase3_jobs.py",
        "test_phase4_infra.py",
        "test_phase5_frontend.py",
        "test_presentation_attack_detection.py",
        "test_preview_effective.py",
        "test_provenance_contract.py",
        "test_reproducibility.py",
        "test_safe.py",
        "test_safire.py",
        "test_spectrogram_decimate.py",
        "test_spectrogram_display_api.py",
        "test_spectrogram_export.py",
        "test_spectrogram_scipy.py",
        "test_synthetic_image_detection.py",
        "test_thumbnail.py",
        "test_videofact.py",
        "test_wavelet_noise_residue.py",
        "test_xmp_packet.py",
        "test_xmp_property_hints.py",
        "test_xmp_structural_tree.py",
    ],
    [
        "test_camo.py",
        "test_clide_runtime.py",
        "test_deeclip_runtime.py",
        "test_distildire.py",
        "test_effort.py",
    ],
    [
        "test_gpu_residency.py",
        "test_gpu_vram_iapl.py",
        "test_iapl.py",
        "test_imdlbenco.py",
        "test_imdl_papers.py",
    ],
    [
        "test_noiseprint.py",
        "test_copy_move_pca.py",
        "test_lfv.py",
        "test_legacy_plugins.py",
        "test_pdf_forensic_extract.py",
        "test_pdf_plugins.py",
        "test_pdf_structure_graph.py",
        "test_pdf_structure_similarity.py",
    ],
]


def _run_batch(batch: list[str]) -> dict:
    paths = [str(UNIT_DIR / name) for name in batch]
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".json", delete=False, dir=PROJECT_ROOT
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            *paths,
            "--tb=short",
            "-q",
            "--disable-warnings",
            "--json-report",
            "--json-report-file",
            str(tmp_path),
        ]
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        report: dict = {}
        if tmp_path.exists():
            try:
                report = json.loads(tmp_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report = {}
        return {
            "returncode": result.returncode,
            "summary": report.get("summary", {}),
            "tests": report.get("tests", []),
            "stderr_tail": result.stderr[-2000:] if result.stderr else "",
        }
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def main() -> int:
    all_results: list[dict] = []
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_errors = 0

    for idx, batch in enumerate(UNIT_BATCHES, 1):
        print(f"Running batch {idx}/{len(UNIT_BATCHES)} ({len(batch)} files)...")
        res = _run_batch(batch)
        all_results.append(res)
        summary = res.get("summary", {})
        total_passed += summary.get("passed", 0)
        total_failed += summary.get("failed", 0)
        total_skipped += summary.get("skipped", 0)
        total_errors += summary.get("error", 0)
        print(
            f"  passed={summary.get('passed', 0)} failed={summary.get('failed', 0)} "
            f"skipped={summary.get('skipped', 0)} error={summary.get('error', 0)}"
        )

    report = {
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "total_errors": total_errors,
        "batches": all_results,
    }
    out_path = PROJECT_ROOT / "tests" / "unit_baseline_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nBaseline report written to {out_path}")
    print(
        f"TOTAL: {total_passed} passed, {total_failed} failed, "
        f"{total_skipped} skipped, {total_errors} error"
    )
    return 1 if (total_failed + total_errors) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
