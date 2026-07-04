"""Unit tests for Effort rows inside synthetic image detection table."""

from __future__ import annotations


class TestEffortRows:
    def test_effort_row_format(self):
        from core.legacy.effort.effort_pipeline import effort_row

        row = effort_row("Effort (GenImage (SD v1.4))", 0.42, inference_device="cuda")
        assert len(row) == 6
        assert row[0].startswith("Effort (")
        assert row[1] == "0.4200"
        assert row[2] == "0.5800"
        assert row[4] == "Incerto"
        assert row[5] == "GPU"

        row_cpu = effort_row("Effort (Chameleon)", 0.1, inference_device="cpu")
        assert row_cpu[5] == "CPU"

    def test_decision_labels(self):
        from core.legacy.effort.effort_pipeline import _decision_label

        assert _decision_label(0.9) == "AI"
        assert _decision_label(0.1) == "REAL"
        assert _decision_label(0.5) == "Incerto"

    def test_predict_effort_rows_does_not_clear_cache(self, monkeypatch):
        import torch
        from PIL import Image

        from core.legacy.effort import effort_pipeline
        from core.legacy.effort.effort_pipeline import EffortAnalysisResult

        cleared = {"count": 0}

        def _track_clear():
            cleared["count"] += 1

        monkeypatch.setattr(effort_pipeline, "clear_effort_model_cache", _track_clear)

        def _fake_infer(_image, *, variant: str, device: torch.device) -> EffortAnalysisResult:
            return EffortAnalysisResult(
                fake_probability=0.5,
                predicted_label=0,
                classification="AUTENTICA",
                variant=variant,
                variant_label=variant,
                inference_device=device.type,
                logits=[0.0, 0.0],
            )

        monkeypatch.setattr(effort_pipeline, "infer_effort_from_pil", _fake_infer)
        monkeypatch.setattr(
            effort_pipeline,
            "run_with_device_fallback",
            lambda run_fn, **kwargs: (run_fn(torch.device("cpu")), torch.device("cpu")),
        )
        monkeypatch.setattr(
            "core.legacy.effort.effort_runtime.effort_runtime_status",
            lambda *, variant: (True, ""),
        )
        monkeypatch.setattr(
            "core.legacy.effort.effort_runtime.EFFORT_VARIANTS",
            {
                "genimage": {"id": "genimage", "label": "GenImage (SD v1.4)"},
                "chameleon": {"id": "chameleon", "label": "Chameleon (SD v1.4)"},
            },
        )

        rows = effort_pipeline.predict_effort_rows(Image.new("RGB", (64, 64)))
        assert len(rows) == 2
        assert cleared["count"] == 0

    def test_warm_effort_skips_missing_weights(self, monkeypatch):
        from core.legacy.effort.effort_warmup import warm_effort_models

        monkeypatch.setattr(
            "core.legacy.effort.effort_warmup.effort_runtime_status",
            lambda *, variant: (False, "pesos ausentes"),
        )
        result = warm_effort_models(
            variants=["genimage", "chameleon"],
            device=__import__("torch").device("cpu"),
        )
        assert result.loaded_variants == []
        assert len(result.skipped_variants) == 2
