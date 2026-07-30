"""Normalize plugin outputs into a stable per-job artifact directory."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from core.scaffolded_artifact_mappings import SCAFFOLDED_ARTIFACT_MAPPINGS

_BASE_ARTIFACT_MAPPINGS: list[tuple[str, str]] = [
    ("heatmap_path", "heatmap.png"),
    ("heatmap_base_path", "heatmap_base.png"),
    ("score_map_path", "score_map.png"),
    ("original_crop_path", "original.png"),
    ("artifact_image_path", "artifacts_upscaled.png"),
    ("matrix_image_path", "matrix.png"),
    ("estimated_matrix_image_path", "estimated_matrix.png"),
    ("jpegio_matrix_image_path", "jpegio_matrix.png"),
    ("mask_image_path", "mask.png"),
    ("overlay_image_path", "overlay.png"),
    ("dist_image_path", "dist_field.png"),
    ("deriv_v_image_path", "deriv_vertical.png"),
    ("deriv_h_image_path", "deriv_horizontal.png"),
    ("spectrum_v_image_path", "spectrum_vertical.png"),
    ("spectrum_h_image_path", "spectrum_horizontal.png"),
    ("bag_map_image_path", "bag_map.png"),
    ("detection_image_path", "detection.png"),
    ("interactive_html_path", "interactive.html"),
    ("ltas_normal_html_path", "ltas_normal.html"),
    ("ltas_6db_html_path", "ltas_6db.html"),
    ("ltas_sorted_html_path", "ltas_sorted.html"),
    ("ltas_derivative_html_path", "ltas_derivative.html"),
    ("colored_overlay_image_path", "colored_overlay.png"),
    ("vectors_image_path", "vectors.png"),
    ("vect_i_image_path", "vect_field_i.png"),
    ("vect_j_image_path", "vect_field_j.png"),
    ("spectrum_combined_image_path", "spectrum_combined.png"),
    ("ghost_map_image_path", "ghost_map.png"),
    ("metric_map_image_path", "metric_map.png"),
    ("shift_grid_image_path", "shift_grid.png"),
    ("quality_montage_image_path", "quality_montage.png"),
    ("votes_colored_image_path", "votes_colored.png"),
    ("forgery_image_path", "forgery_mask.png"),
    ("votes_simulated_image_path", "votes_simulated.png"),
    ("correlation_heatmap_path", "correlation_heatmap.png"),
    ("correlation_surface_html_path", "correlation_surface.html"),
    ("scale_curve_image_path", "scale_curve.png"),
    ("localized_map_image_path", "localized_map.png"),
    ("localized_positive_image_path", "localized_positive.png"),
    ("localized_overlay_image_path", "localized_overlay.png"),
    ("overlay_pdf_path", "font_overlay.pdf"),
    ("legend_txt_path", "font_legend.txt"),
    ("structure_graph_image_path", "structure_graph.png"),
    ("structure_graph_html_path", "structure_graph.html"),
    ("similarity_jaccard_image_path", "similarity_jaccard.png"),
    ("similarity_wl_kernel_image_path", "similarity_wl_kernel.png"),
    ("similarity_json_path", "similarity_matrices.json"),
    ("isom_structure_graph_path", "isom_structure_graph.json"),
    ("isom_tree_json_path", "isom_tree.json"),
    ("isom_tree_txt_path", "isom_tree.txt"),
    ("isom_metadata_json_path", "isom_metadata.json"),
    ("isom_metadata_txt_path", "isom_metadata.txt"),
    ("isom_udta_json_path", "udta_atoms.json"),
    ("isom_meta_atoms_json_path", "meta_atoms.json"),
    ("container_report_txt_path", "container_parser_report.txt"),
    ("container_summary_json_path", "container_parser_summary.json"),
    ("matrix_json_path", "jpeg_structure_matrix.json"),
    ("matrix_image_path", "jpeg_structure_matrix.png"),
    ("matrix_report_txt_path", "jpeg_structure_report.txt"),
    ("compare_json_path", "jpeg_structure_compare.json"),
    ("grid_json_path", "jpeg_structure_grid.json"),
    ("grid_report_txt_path", "jpeg_structure_grid.txt"),
    ("metadata_json_path", "metadata_report.json"),
    ("metadata_report_path", "metadata_report.txt"),
    ("c2pa_manifest_path", "c2pa_manifest.json"),
    ("xmp_packet_path", "xmp_packet.xml"),
    ("xmp_tree_json_path", "xmp_tree.json"),
    ("pdf_extract_metadata_json_path", "metadata.json"),
    ("incremental_report_path", "incremental_report.txt"),
    ("signatures_json_path", "signatures.json"),
    ("signatures_report_path", "signatures_report.txt"),
    ("extract_manifest_path", "extract_manifest.json"),
    ("spectrogram_path", "spectrogram_full.npz"),
    ("spectrogram_png_path", "spectrogram.png"),
    ("spectrogram_snapshot_path", "spectrogram_snapshot.png"),
    ("enf_overlay_snapshot_path", "enf_overlay_snapshot.png"),
    ("levels_overlay_snapshot_path", "levels_overlay_snapshot.png"),
    ("dc_overlay_snapshot_path", "dc_overlay_snapshot.png"),
    ("ltas_normal_overlay_snapshot_path", "ltas_normal_overlay_snapshot.png"),
    ("ltas_6db_overlay_snapshot_path", "ltas_6db_overlay_snapshot.png"),
    ("ltas_sorted_overlay_snapshot_path", "ltas_sorted_overlay_snapshot.png"),
    ("ltas_derivative_overlay_snapshot_path", "ltas_derivative_overlay_snapshot.png"),
    ("plot_traces_json_path", "plot_traces.json"),
    ("ltas_plot_data_json_path", "ltas_plot_data.json"),
    ("input_image_path", "input_image.png"),
    ("input_fft_image_path", "input_fft.png"),
    ("nlm_residue_image_path", "nlm_residue.png"),
    ("median_residue_image_path", "median_residue.png"),
    ("dwt_coefficients_path", "wnr_dwt_coefficients.npz"),
    ("nlm_fft_image_path", "nlm_fft.png"),
    ("median_fft_image_path", "median_fft.png"),
    ("multi_segment_image_path", "safire_multi_segment.png"),
    ("noiseprint_image_path", "noiseprint_map.png"),
    ("confidence_image_path", "confidence_map.png"),
    ("valid_mask_image_path", "valid_mask.png"),
    ("valid_overlay_image_path", "valid_overlay.png"),
    ("model_scores_txt_path", "model_scores.txt"),
    ("videofact_report_json_path", "videofact_report.json"),
    ("videofact_summary_txt_path", "videofact_summary.txt"),
    ("videofact_xfer_scores_chart_path", "videofact_xfer_scores.png"),
    ("videofact_df_scores_chart_path", "videofact_df_scores.png"),
    ("stil_report_json_path", "stil_report.json"),
    ("stil_summary_txt_path", "stil_summary.txt"),
    ("stil_scores_chart_path", "stil_scores_chart.png"),
    ("lfv_report_json_path", "lfv_report.json"),
    ("lfv_summary_txt_path", "lfv_summary.txt"),
    ("lfv_scores_chart_path", "lfv_scores_chart.png"),
    ("relayformer_report_json_path", "relayformer_report.json"),
    ("relayformer_summary_txt_path", "relayformer_summary.txt"),
    ("relayformer_scores_chart_path", "relayformer_scores_chart.png"),
    ("relayformer_overlay_preview_path", "relayformer_overlay_preview.png"),
    ("relayformer_mask_preview_path", "relayformer_mask_preview.png"),
    ("relayformer_heatmap_preview_path", "relayformer_heatmap_preview.png"),
    ("relayformer_input_preview_path", "relayformer_input_preview.png"),
    ("truvil_report_json_path", "truvil_report.json"),
    ("truvil_summary_txt_path", "truvil_summary.txt"),
    ("truvil_scores_chart_path", "truvil_scores_chart.png"),
    ("truvil_overlay_preview_path", "truvil_overlay_preview.png"),
    ("truvil_mask_preview_path", "truvil_mask_preview.png"),
    ("truvil_heatmap_preview_path", "truvil_heatmap_preview.png"),
    ("truvil_input_preview_path", "truvil_input_preview.png"),
    ("vilocal_report_json_path", "vilocal_report.json"),
    ("vilocal_summary_txt_path", "vilocal_summary.txt"),
    ("vilocal_scores_chart_path", "vilocal_scores_chart.png"),
    ("vilocal_overlay_preview_path", "vilocal_overlay_preview.png"),
    ("vilocal_mask_preview_path", "vilocal_mask_preview.png"),
    ("vilocal_heatmap_preview_path", "vilocal_heatmap_preview.png"),
    ("vilocal_input_preview_path", "vilocal_input_preview.png"),
    ("pad_result_json_path", "pad_result.json"),
    ("pad_face_crop_path", "pad_face_crop.png"),
    ("pad_annotated_image_path", "pad_annotated.png"),
    ("plot_filename", "audio_spoofing_plot.json"),
    ("details_filename", "audio_spoofing_details.json"),
    ("detector_scores_txt_path", "detector_scores.txt"),
]

ARTIFACT_MAPPINGS: list[tuple[str, str]] = [
    *_BASE_ARTIFACT_MAPPINGS,
    *SCAFFOLDED_ARTIFACT_MAPPINGS,
]


def stage_plugin_artifacts(result: dict[str, Any], result_dir: Path) -> None:
    """Copy plugin output files into ``result_dir`` using canonical names."""
    result_dir.mkdir(parents=True, exist_ok=True)

    for key, filename in ARTIFACT_MAPPINGS:
        if not result.get(key):
            continue
        src = Path(result[key])
        if not src.exists():
            continue
        dst = result_dir / filename
        if src.resolve() == dst.resolve():
            result[key] = str(dst)
            continue
        shutil.copy2(str(src), str(dst))
        result[key] = str(dst)

    qpaths = result.get("quality_ghost_paths")
    if isinstance(qpaths, dict):
        copied: dict[str, str] = {}
        for q, src_str in qpaths.items():
            src = Path(str(src_str))
            if not src.exists():
                continue
            fname = f"ghost_q{q}.png"
            dst = result_dir / fname
            if src.resolve() != dst.resolve():
                shutil.copy2(str(src), str(dst))
            copied[str(q)] = fname
        result["quality_ghost_filenames"] = copied

    bundle_dir = result.get("extract_bundle_dir")
    if bundle_dir:
        bundle_path = Path(str(bundle_dir))
        if bundle_path.is_dir():
            for src_file in bundle_path.rglob("*"):
                if not src_file.is_file():
                    continue
                rel = src_file.relative_to(bundle_path)
                dst = result_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src_file.resolve() != dst.resolve():
                    shutil.copy2(str(src_file), str(dst))
            result["extract_bundle_dir"] = str(result_dir)


def _collect_result_paths(result: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key, _filename in ARTIFACT_MAPPINGS:
        raw = result.get(key)
        if raw:
            paths.append(Path(str(raw)))
    qpaths = result.get("quality_ghost_paths")
    if isinstance(qpaths, dict):
        for src_str in qpaths.values():
            paths.append(Path(str(src_str)))
    bundle = result.get("extract_bundle_dir")
    if bundle:
        paths.append(Path(str(bundle)))
    return paths


def cleanup_ephemeral_artifact_sources(
    result: dict[str, Any],
    result_dir: Path,
) -> None:
    """Remove legacy tmp copies after staging into the job preview directory."""
    from app.config import get_settings

    results_root = Path(get_settings().RESULTS_DIR).resolve()
    result_dir = result_dir.resolve()

    for src in _collect_result_paths(result):
        if not src.exists():
            continue
        try:
            resolved = src.resolve()
        except OSError:
            continue
        if resolved == result_dir or result_dir in resolved.parents:
            continue
        try:
            if not resolved.is_relative_to(results_root):
                continue
        except ValueError:
            continue
        if src.is_file():
            src.unlink(missing_ok=True)
            logger.debug("Artefato temporario removido: %s", src)
        elif src.is_dir() and src != result_dir:
            shutil.rmtree(src, ignore_errors=True)
            logger.debug("Diretorio temporario removido: %s", src)
