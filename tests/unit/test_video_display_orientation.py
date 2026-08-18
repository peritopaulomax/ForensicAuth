"""Tests for video display rotation parsing and VideoFACT frame geometry."""

from __future__ import annotations

import torch
import torchvision.transforms.functional as TF

from core.video_display_orientation import (
    css_rotation_if_needed,
    heatmap_export_rotation_degrees,
    normalize_rotation_degrees,
    rotation_from_ffprobe_stream,
)
from forensics.videofact.videofact_pipeline import (
    apply_nchw_rotate_clockwise,
    apply_videofact_frame_geometry,
    prepare_videofact_frames,
)


class TestRotationParsing:
    def test_normalize_wraps_and_snaps(self):
        assert normalize_rotation_degrees(90) == 90
        assert normalize_rotation_degrees(-90) == 270
        assert normalize_rotation_degrees(180.2) == 180
        assert normalize_rotation_degrees("270") == 270
        assert normalize_rotation_degrees(None) == 0

    def test_rotate_tag(self):
        assert rotation_from_ffprobe_stream({"tags": {"rotate": "90"}}) == 90
        assert rotation_from_ffprobe_stream({"tags": {"rotate": "180"}}) == 180

    def test_display_matrix_negates_counterclockwise(self):
        # ffprobe reports rotation=-90 for many phone portrait clips
        stream = {
            "side_data_list": [
                {"side_data_type": "Display Matrix", "rotation": -90.0},
            ]
        }
        assert rotation_from_ffprobe_stream(stream) == 90

    def test_css_skips_when_browser_already_swapped(self):
        assert (
            css_rotation_if_needed(
                metadata_rotation=90,
                coded_width=1920,
                coded_height=1080,
                displayed_width=1080,
                displayed_height=1920,
            )
            == 0
        )

    def test_css_applies_when_browser_shows_coded_size(self):
        assert (
            css_rotation_if_needed(
                metadata_rotation=90,
                coded_width=1920,
                coded_height=1080,
                displayed_width=1920,
                displayed_height=1080,
            )
            == 90
        )

    def test_heatmap_export_rotates_landscape_with_meta(self):
        assert (
            heatmap_export_rotation_degrees(
                metadata_rotation=90,
                coded_width=1920,
                coded_height=1080,
            )
            == 90
        )

    def test_heatmap_export_skips_portrait_coded(self):
        assert (
            heatmap_export_rotation_degrees(
                metadata_rotation=90,
                coded_width=1080,
                coded_height=1920,
            )
            == 0
        )


class TestVideofactGeometry:
    def test_landscape_no_vflip_only_resize(self):
        frames = torch.zeros(1, 3, 100, 200)
        frames[:, :, 0, :] = 1.0
        expected = TF.resize(frames, (1080, 1920), antialias=True)
        out = apply_videofact_frame_geometry(frames)
        assert out.shape == (1, 3, 1080, 1920)
        assert torch.allclose(out, expected)
        # Top band stays bright (vflip would move it to the bottom)
        assert float(out[0, 0, 0, :].mean()) > 0.5
        assert float(out[0, 0, -1, :].mean()) < 0.5

    def test_portrait_transposes_and_vflips(self):
        frames = torch.zeros(1, 3, 200, 100)
        frames[:, :, 0, :] = 1.0
        expected = frames.permute(0, 1, 3, 2)
        expected = TF.vflip(expected)
        expected = TF.resize(expected, (1080, 1920), antialias=True)
        out = apply_videofact_frame_geometry(frames)
        assert out.shape == (1, 3, 1080, 1920)
        assert torch.allclose(out, expected)

    def test_rotate_clockwise_90_swaps_hw(self):
        frames = torch.zeros(1, 3, 100, 200)
        frames[:, :, 0, 0] = 1.0  # top-left
        out = apply_nchw_rotate_clockwise(frames, 90)
        assert out.shape == (1, 3, 200, 100)
        # CW 90: old (0,0) → (0, H-1) in new coords → top-right of 200x100
        assert float(out[0, 0, 0, -1]) == 1.0

    def test_prepare_upright_skips_vendor_portrait_undo(self):
        # Landscape coded + 90° CW must NOT go through vendor transpose+vflip
        # (that composition is identity and would keep content sideways).
        frames = torch.zeros(1, 3, 100, 200)
        frames[:, :, :10, :10] = 1.0
        out = prepare_videofact_frames(frames, input_upright_rotation=90)
        assert out.shape == (1, 3, 1080, 1920)
        expected = TF.resize(
            apply_nchw_rotate_clockwise(frames, 90), (1080, 1920), antialias=True
        )
        assert torch.allclose(out, expected)
        vendor_undo = apply_videofact_frame_geometry(apply_nchw_rotate_clockwise(frames, 90))
        assert torch.allclose(vendor_undo, apply_videofact_frame_geometry(frames))
        assert not torch.allclose(out, vendor_undo, atol=1e-3)
