"""Integration: ForensicAuth CLIDE likelihood matches the official computation."""

from __future__ import annotations

import math

import pytest
import torch
from PIL import Image


@pytest.mark.integration
class TestClideVendorParity:
    def test_forensicauth_likelihood_matches_direct_official_computation(self):
        from core.legacy.clide.clide_pipeline import clear_clide_model_cache, infer_clide_from_pil
        from core.legacy.clide.clide_runtime import (
            any_clide_ready,
            clide_clip_cache_dir,
            resolve_whitening_matrix,
        )

        ok, reason = any_clide_ready()
        if not ok:
            pytest.skip(reason)

        w_path = resolve_whitening_matrix("general")
        assert w_path is not None

        image = Image.new("RGB", (224, 224), color=(96, 128, 160))
        device = torch.device("cpu")

        import clip

        model, preprocess = clip.load(
            "ViT-L/14",
            device=device.type,
            download_root=str(clide_clip_cache_dir()),
        )
        model.eval()
        w_mat, w_mean = torch.load(str(w_path), map_location=device, weights_only=False)
        image_tensor = preprocess(image).unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = model.encode_image(image_tensor).squeeze(0).to(device, dtype=torch.float32)
        w_mat = w_mat.to(device)
        w_mean = w_mean.to(device)
        m = w_mat.shape[1]
        log_const = 0.5 * m * torch.log(torch.tensor(2 * math.pi, device=device))
        whitened_embedding = (embedding - w_mean) @ w_mat
        vendor_likelihood = float((-(log_const + 0.5 * whitened_embedding.norm() ** 2)).cpu().item())

        clear_clide_model_cache()
        ours = infer_clide_from_pil(image, device, mode="global").likelihood

        assert ours == pytest.approx(vendor_likelihood, abs=1e-6)

    def test_forensicauth_local_likelihood_matches_official_default(self):
        from core.legacy.clide.clide_pipeline import clear_clide_model_cache, infer_clide_from_pil
        from core.legacy.clide.clide_runtime import (
            any_clide_ready,
            clide_clip_cache_dir,
            resolve_rep_matrix,
        )
        from core.legacy.clide.clide_vendor import load_detection_module

        ok, reason = any_clide_ready()
        if not ok:
            pytest.skip(reason)

        rep_path = resolve_rep_matrix("general")
        assert rep_path is not None

        image = Image.new("RGB", (224, 224), color=(96, 128, 160))
        device = torch.device("cpu")

        import clip

        model, preprocess = clip.load(
            "ViT-L/14",
            device=device.type,
            download_root=str(clide_clip_cache_dir()),
        )
        model.eval()
        rep_mat = torch.load(str(rep_path), map_location=device, weights_only=False).to(device)
        image_tensor = preprocess(image).unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = model.encode_image(image_tensor).squeeze(0).to(device, dtype=torch.float32)
        similarities = torch.cosine_similarity(embedding, rep_mat, dim=1)
        top_k_indices = torch.topk(similarities, k=500, largest=True).indices
        selected_rep = rep_mat[top_k_indices]
        _, local_w = load_detection_module().sphx(selected_rep, m=400)
        log_const = 0.5 * 400 * torch.log(torch.tensor(2 * math.pi, device=device))
        whitened_embedding = (embedding - selected_rep.mean(dim=0)) @ local_w
        vendor_likelihood = float((-(log_const + 0.5 * whitened_embedding.norm() ** 2)).cpu().item())

        clear_clide_model_cache()
        ours = infer_clide_from_pil(image, device).likelihood

        assert ours == pytest.approx(vendor_likelihood, abs=1e-6)
