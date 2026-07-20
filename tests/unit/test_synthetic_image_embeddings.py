"""Unit tests for synthetic-image detector embedding extraction.

These tests verify that attaching an embedding hook does not change the
reported score (equivalence requirement under Regra Máxima 8).
"""

from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image


@pytest.fixture
def sample_image() -> Image.Image:
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "images" / "copymove.jpg"
    if not fixture.is_file():
        pytest.skip("Fixture image not available")
    return Image.open(fixture).convert("RGB")


class TestSafeEmbedding:
    def test_safe_score_equivalence_with_embedding_hook(self, sample_image: Image.Image):
        from core.legacy.safe.safe_pipeline import (
            infer_safe_from_pil,
            resolve_inference_device,
            safe_runtime_status,
        )
        from core.legacy.synthetic_image_detection.embedding_utils import extract_safe_embedding

        ok, reason = safe_runtime_status()
        if not ok:
            pytest.skip(f"SAFE unavailable: {reason}")

        device = resolve_inference_device()
        score_normal = infer_safe_from_pil(sample_image, device)
        emb = extract_safe_embedding(sample_image, device)
        score_with_hook = infer_safe_from_pil(sample_image, device)

        assert isinstance(emb, np.ndarray)
        assert emb.dtype == np.float32
        assert emb.ndim == 1
        assert emb.shape[0] == 512
        assert score_normal == pytest.approx(score_with_hook, abs=1e-6)


class TestSdxlFluxEmbedding:
    def test_sdxl_flux_score_equivalence_with_embedding_hook(self, sample_image: Image.Image):
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        from core.legacy.synthetic_image_detection.pipeline import (
            MODEL_PATHS,
            _as_rgb,
            _hf_local_path,
        )
        from core.legacy.synthetic_image_detection.embedding_utils import extract_sdxl_flux_embedding

        try:
            local_path = _hf_local_path(MODEL_PATHS["model_4"])
        except Exception as exc:
            pytest.skip(f"sdxl-flux detector snapshot not resolvable: {exc}")

        if not Path(local_path).is_dir():
            pytest.skip("sdxl-flux detector weights not available")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = AutoModelForImageClassification.from_pretrained(local_path, local_files_only=True).to(device).eval()
        image_processor = AutoImageProcessor.from_pretrained(local_path, local_files_only=True)

        rgb = _as_rgb(sample_image)
        inputs = image_processor(rgb, return_tensors="pt").to(device)
        with torch.no_grad():
            logits_normal = model(**inputs).logits.cpu().numpy()[0]

        emb = extract_sdxl_flux_embedding(sample_image, model, image_processor)

        with torch.no_grad():
            logits_with_hook = model(**inputs).logits.cpu().numpy()[0]

        assert isinstance(emb, np.ndarray)
        assert emb.dtype == np.float32
        assert emb.ndim == 1
        assert emb.shape[0] == 1024
        np.testing.assert_allclose(logits_normal, logits_with_hook, atol=1e-6)


class TestAiImageDetectorEmbedding:
    def test_ai_image_detector_score_equivalence_with_embedding_hook(self, sample_image: Image.Image):
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        from core.legacy.synthetic_image_detection.pipeline import (
            MODEL_PATHS,
            _as_rgb,
            _hf_local_path,
        )
        from core.legacy.synthetic_image_detection.embedding_utils import extract_ai_image_detector_embedding

        try:
            local_path = _hf_local_path(MODEL_PATHS["model_1"])
        except Exception as exc:
            pytest.skip(f"ai-image-detector snapshot not resolvable: {exc}")

        if not Path(local_path).is_dir():
            pytest.skip("ai-image-detector weights not available")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = AutoModelForImageClassification.from_pretrained(local_path, local_files_only=True).to(device).eval()
        image_processor = AutoImageProcessor.from_pretrained(local_path, local_files_only=True)

        rgb = _as_rgb(sample_image)
        inputs = image_processor(rgb, return_tensors="pt").to(device)
        with torch.no_grad():
            logits_normal = model(**inputs).logits.cpu().numpy()[0]

        emb = extract_ai_image_detector_embedding(sample_image, model, image_processor)

        with torch.no_grad():
            logits_with_hook = model(**inputs).logits.cpu().numpy()[0]

        assert isinstance(emb, np.ndarray)
        assert emb.dtype == np.float32
        assert emb.ndim == 1
        assert emb.shape[0] == 1536
        np.testing.assert_allclose(logits_normal, logits_with_hook, atol=1e-6)


class TestBFreeEmbedding:
    def test_bfree_score_equivalence_with_embedding_hook(self, sample_image: Image.Image):
        from core.legacy.bfree.bfree_pipeline import (
            bfree_runtime_status,
            infer_bfree_from_pil,
            resolve_inference_device,
        )
        from core.legacy.synthetic_image_detection.embedding_utils import extract_bfree_embedding

        ok, reason = bfree_runtime_status()
        if not ok:
            pytest.skip(f"B-Free unavailable: {reason}")

        device = resolve_inference_device()
        score_normal = infer_bfree_from_pil(sample_image, device)
        emb = extract_bfree_embedding(sample_image, device)
        score_with_hook = infer_bfree_from_pil(sample_image, device)

        assert isinstance(emb, np.ndarray)
        assert emb.dtype == np.float32
        assert emb.ndim == 1
        assert emb.shape[0] == 768
        assert score_normal == pytest.approx(score_with_hook, abs=1e-6)


class TestClipdEmbedding:
    def test_clipd_score_equivalence_with_embedding_hook(self, sample_image: Image.Image):
        from core.legacy.truebees_clip_d.clipd_pipeline import (
            MODEL_NAME,
            clipd_runtime_status,
            infer_clipd_from_pil,
            resolve_inference_device,
        )
        from core.legacy.synthetic_image_detection.embedding_utils import extract_clipd_embedding

        ok, reason = clipd_runtime_status(MODEL_NAME)
        if not ok:
            pytest.skip(f"CLIP-D unavailable: {reason}")

        device = resolve_inference_device()
        score_normal = infer_clipd_from_pil(sample_image, device)
        emb = extract_clipd_embedding(sample_image, device)
        score_with_hook = infer_clipd_from_pil(sample_image, device)

        assert isinstance(emb, np.ndarray)
        assert emb.dtype == np.float32
        assert emb.ndim == 1
        assert emb.shape[0] == 1024
        assert score_normal == pytest.approx(score_with_hook, abs=1e-6)


class TestCorvi2023Embedding:
    def test_corvi2023_score_equivalence_with_embedding_hook(self, sample_image: Image.Image):
        from core.legacy.truebees_clip_d.clipd_pipeline import (
            CORVI2023_MODEL_NAME,
            clipd_runtime_status,
            infer_corvi2023_from_pil,
            resolve_inference_device,
        )
        from core.legacy.synthetic_image_detection.embedding_utils import extract_corvi2023_embedding

        ok, reason = clipd_runtime_status(CORVI2023_MODEL_NAME)
        if not ok:
            pytest.skip(f"Corvi2023 unavailable: {reason}")

        device = resolve_inference_device()
        score_normal, n_tiles, tiled = infer_corvi2023_from_pil(sample_image, device)
        emb = extract_corvi2023_embedding(sample_image, device)
        score_with_hook, _, _ = infer_corvi2023_from_pil(sample_image, device)

        assert isinstance(emb, np.ndarray)
        assert emb.dtype == np.float32
        assert emb.ndim == 1
        assert emb.shape[0] == 2048
        assert score_normal == pytest.approx(score_with_hook, abs=1e-6)


class TestCorvi2023UnifiedForward:
    def test_corvi2023_unified_forward_matches_score_only(self, sample_image: Image.Image):
        from core.legacy.truebees_clip_d.clipd_pipeline import (
            CORVI2023_MODEL_NAME,
            clipd_runtime_status,
            infer_corvi2023_from_pil,
            resolve_inference_device,
        )

        ok, reason = clipd_runtime_status(CORVI2023_MODEL_NAME)
        if not ok:
            pytest.skip(f"Corvi2023 unavailable: {reason}")

        device = resolve_inference_device()
        score_only, _, _ = infer_corvi2023_from_pil(sample_image, device)
        score_unified, _, _, emb = infer_corvi2023_from_pil(
            sample_image, device, return_embedding=True
        )
        assert isinstance(emb, np.ndarray)
        assert score_only == pytest.approx(score_unified, abs=1e-6)


class TestPipelineReturnEmbedding:
    def test_run_synthetic_image_detection_analysis_returns_embeddings(self, sample_image: Image.Image):
        from core.legacy.safe.safe_pipeline import safe_runtime_status
        from core.legacy.synthetic_image_detection.pipeline import run_synthetic_image_detection_analysis

        ok, reason = safe_runtime_status()
        if not ok:
            pytest.skip(f"SAFE unavailable: {reason}")

        result = run_synthetic_image_detection_analysis(
            sample_image,
            generate_visuals=False,
            selected_analyses=["safe"],
            return_embedding=True,
        )

        assert "detector_scores" in result
        assert "safe" in result["detector_scores"]
        safe_score = result["detector_scores"]["safe"]
        assert "embedding" in safe_score
        assert "embedding_dim" in safe_score
        assert isinstance(safe_score["embedding"], np.ndarray)
        assert safe_score["embedding_dim"] == 512
