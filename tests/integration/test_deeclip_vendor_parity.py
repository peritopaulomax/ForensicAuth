"""Integration: ForensicAuth DeeCLIP score matches the vendored official call."""

from __future__ import annotations

import pytest
import torch
from PIL import Image


@pytest.mark.integration
class TestDeeclipVendorParity:
    def test_forensicauth_score_matches_direct_vendor_call(self):
        from core.legacy.deeclip.deeclip_pipeline import clear_deeclip_model_cache, infer_deeclip_from_pil
        from core.legacy.deeclip.deeclip_runtime import (
            any_deeclip_ready,
            resolve_checkpoint,
            resolve_clip_snapshot_path,
        )
        from core.legacy.deeclip.deeclip_vendor import load_deeclip_class

        ok, reason = any_deeclip_ready()
        if not ok:
            pytest.skip(reason)

        clip_path = resolve_clip_snapshot_path()
        ckpt_path = resolve_checkpoint()
        assert clip_path is not None
        assert ckpt_path is not None

        image = Image.new("RGB", (224, 224), color=(96, 128, 160))
        device = torch.device("cpu")

        DeeCLIP = load_deeclip_class()
        vendor_model = DeeCLIP(
            model_name=str(clip_path),
            layer_indices=[1, 3, 5, 8, 10, 13, 15, 17, 19, 21, 22, 23],
        ).to(device)
        try:
            state = torch.load(str(ckpt_path), map_location=device, weights_only=False)
        except TypeError:
            state = torch.load(str(ckpt_path), map_location=device)
        vendor_model.load_state_dict(state, strict=False)
        vendor_model.eval()

        from transformers import CLIPImageProcessor

        processor = CLIPImageProcessor.from_pretrained(str(clip_path), local_files_only=True)
        tensor = processor(images=image, return_tensors="pt")["pixel_values"].to(device)
        with torch.no_grad():
            _, _, outputs = vendor_model(tensor, train=False)
            vendor_score = torch.sigmoid(outputs).float().cpu().reshape(-1)[0].item()

        clear_deeclip_model_cache()
        ours = infer_deeclip_from_pil(image, device)

        assert ours == pytest.approx(float(vendor_score), abs=1e-8)
