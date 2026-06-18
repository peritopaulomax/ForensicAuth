"""E2E SAFIRE — safire_example.png vs outputs oficiais (GRIP README)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
VENDOR = WORKSPACE / "vendor" / "SAFIRE-main"
EXAMPLE = VENDOR / "ForensicsEval" / "inputs" / "safire_example.png"
REF_BINARY = VENDOR / "ForensicsEval" / "outputs_binary" / "safire_example.png.png"
REF_MULTI = VENDOR / "ForensicsEval" / "outputs_multi" / "safire_example.png.png"

MULTI_COLOR_MAP = {
    0: (190, 174, 212),
    1: (127, 201, 127),
    2: (253, 192, 134),
    3: (255, 255, 153),
    4: (251, 128, 114),
    5: (128, 177, 211),
    6: (179, 222, 105),
    7: (255, 255, 255),
}

INFERENCE_SIZE = (1024, 1024)


def _downsample_for_official_compare(arr: np.ndarray) -> np.ndarray:
    """Official ForensicsEval outputs are 1024×1024."""
    import cv2

    h, w = arr.shape[:2]
    if (h, w) == INFERENCE_SIZE:
        return arr
    if arr.ndim == 2:
        return cv2.resize(arr, INFERENCE_SIZE, interpolation=cv2.INTER_NEAREST)
    return cv2.resize(arr, INFERENCE_SIZE, interpolation=cv2.INTER_NEAREST)


def _best_color_remap_match(our: np.ndarray, ref: np.ndarray) -> float:
    """k-means cluster IDs are arbitrary — compare up to color permutation."""
    our_u = [tuple(map(int, c)) for c in np.unique(our.reshape(-1, 3), axis=0)]
    ref_u = [tuple(map(int, c)) for c in np.unique(ref.reshape(-1, 3), axis=0)]
    mapped = our.copy()
    used_ref: set[tuple[int, ...]] = set()
    for oc in our_u:
        oc_arr = np.array(oc, dtype=np.uint8)
        mask_o = (our == oc_arr).all(axis=-1)
        best_iou = -1.0
        best_rc: tuple[int, ...] | None = None
        for rc in ref_u:
            if rc in used_ref:
                continue
            rc_arr = np.array(rc, dtype=np.uint8)
            mask_r = (ref == rc_arr).all(axis=-1)
            inter = float((mask_o & mask_r).sum())
            union = float((mask_o | mask_r).sum())
            iou = inter / union if union else 0.0
            if iou > best_iou:
                best_iou = iou
                best_rc = rc
        if best_rc is not None:
            used_ref.add(best_rc)
            mapped[mask_o] = np.array(best_rc, dtype=np.uint8)
    return float((mapped == ref).all(axis=-1).mean())


@pytest.mark.integration
class TestSafireOfficialSafireExample:
    def test_runtime_ready(self):
        from core.legacy.safire.safire_runtime import safire_runtime_status

        ok, reason = safire_runtime_status()
        if not ok:
            pytest.skip(reason)
        assert ok

    @pytest.mark.skipif(not EXAMPLE.is_file(), reason="safire_example.png ausente")
    @pytest.mark.skipif(not REF_BINARY.is_file(), reason="referencia binary ausente")
    def test_binary_matches_official_output(self):
        from core.legacy.safire.safire_runtime import safire_runtime_status
        from core.legacy.safire.safire_pipeline import run_safire_analysis

        ok, reason = safire_runtime_status()
        if not ok:
            pytest.skip(reason)

        result = run_safire_analysis(str(EXAMPLE), mode="binary", points_per_side=16, points_per_batch=256)
        assert result.points_per_side_effective == 16
        assert result.heatmap_image.size == (2048, 2048)
        our = _downsample_for_official_compare(
            np.array(result.heatmap_image.convert("L"), dtype=np.float32)
        )
        ref = np.array(Image.open(REF_BINARY).convert("L"), dtype=np.float32)
        assert our.shape == ref.shape == INFERENCE_SIZE
        mae = float(np.abs(our - ref).mean())
        assert mae < 1.0, f"Binary heatmap diverge do oficial (MAE={mae:.3f})"

    @pytest.mark.skipif(not EXAMPLE.is_file(), reason="safire_example.png ausente")
    @pytest.mark.skipif(not REF_MULTI.is_file(), reason="referencia multi ausente")
    def test_multi_matches_official_output(self):
        from core.legacy.safire.safire_pipeline import run_safire_analysis
        from core.legacy.safire.safire_runtime import safire_runtime_status

        ok, reason = safire_runtime_status()
        if not ok:
            pytest.skip(reason)

        result = run_safire_analysis(
            str(EXAMPLE),
            mode="multi",
            cluster_type="kmeans",
            kmeans_cluster_num=3,
            points_per_side=16,
            points_per_batch=256,
        )
        assert result.multi_segment_image is not None
        assert result.cluster_count == 3
        assert result.multi_segment_image.size == (2048, 2048)
        our = _downsample_for_official_compare(np.array(result.multi_segment_image.convert("RGB")))
        ref = np.array(Image.open(REF_MULTI).convert("RGB"))
        assert our.shape == ref.shape == (*INFERENCE_SIZE, 3)
        match = _best_color_remap_match(our, ref)
        assert match >= 0.85, f"Multi segment diverge do oficial (match={match:.3f})"
