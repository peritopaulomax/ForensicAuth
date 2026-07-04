"""Adapter — FakeVLM (Large Multimodal Model-Based Synthetic Image Detection)."""

from __future__ import annotations

import gc
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from PIL import Image

import torch

from core.forensic_plugin import ForensicPlugin
from core.gpu_inference import (
    device_display_label,
    prepare_vram_for_heavy_model,
    release_gpu_memory,
    resolve_inference_device,
)
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, report_progress

_FAKEVLM_MODEL_PATH = Path(__file__).parent.parent.parent.parent.parent / "models" / "fakevlm"

_model_cache: dict[str, Any] = {}


def _load_fakevlm_stack(device):
    import torch
    from transformers import AutoProcessor, LlavaForConditionalGeneration

    cache_key = f"fakevlm:{device}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    if not _FAKEVLM_MODEL_PATH.exists():
        raise FileNotFoundError(f"FakeVLM weights not found at {_FAKEVLM_MODEL_PATH}")

    processor = AutoProcessor.from_pretrained(str(_FAKEVLM_MODEL_PATH))
    processor.patch_size = 14
    processor.num_additional_image_tokens = 1
    processor.vision_feature_select_strategy = "default"

    model = LlavaForConditionalGeneration.from_pretrained(
        str(_FAKEVLM_MODEL_PATH),
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        device_map="auto" if device.type == "cuda" else "cpu",
    )
    model.eval()

    stack = {"processor": processor, "model": model}
    _model_cache[cache_key] = stack
    return stack


def clear_fakevlm_model_cache() -> None:
    for key in list(_model_cache.keys()):
        stack = _model_cache.pop(key, None)
        if stack:
            release_gpu_memory(stack.get("model"))
    release_gpu_memory()
    gc.collect()


def _build_prompt(question: str | None = None) -> str:
    default_q = (
        "Esta imagem e real ou falsa? Responda com 'real' ou 'falsa' primeiro, "
        "depois explique brevemente o motivo."
    )
    q = question or default_q
    return (
        "USER: <image>\n"
        f"{q}\n"
        "ASSISTANT:"
    )


def _parse_verdict(response: str) -> Tuple[str, float]:
    text = response.strip()
    # Keep only the model's answer (after ASSISTANT:)
    if "ASSISTANT:" in text:
        text = text.split("ASSISTANT:", 1)[-1].strip()
    text_lower = text.lower()
    parts = re.split(r"[.\n]", text_lower)
    first_sentence = parts[0] if parts else text_lower

    fake_tokens = ("fake", "falsa", "falso", "sintetica", "sintetico", "gerada", "gerado", "artificial")
    real_tokens = ("real", "verdadeira", "verdadeiro", "autentica", "autentico", "genuina", "genuino")

    if any(token in first_sentence for token in fake_tokens):
        return "FAKE", 0.85
    if any(token in first_sentence for token in real_tokens):
        return "REAL", 0.15

    # fallback: scan full response
    fake_hits = sum(text_lower.count(token) for token in fake_tokens)
    real_hits = sum(text_lower.count(token) for token in real_tokens)
    if fake_hits > real_hits:
        return "FAKE", 0.7
    if real_hits > fake_hits:
        return "REAL", 0.3
    return "UNCERTAIN", 0.5


class FakeVlmAdapter(ForensicPlugin):
    """FakeVLM — detecção de imagens sintéticas via modelo multimodal (LLaVA 7B)."""

    @property
    def name(self) -> str:
        return "fakevlm"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return fakevlm_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = fakevlm_runtime_status()
        if not ok:
            return False, reason
        max_new_tokens = int(parameters.get("max_new_tokens", 100))
        if max_new_tokens < 1 or max_new_tokens > 512:
            return False, "max_new_tokens deve estar entre 1 e 512"
        keep_loaded = parameters.get("keep_model_loaded")
        if keep_loaded is not None and not isinstance(keep_loaded, bool):
            return False, "keep_model_loaded deve ser booleano"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = fakevlm_runtime_status()
        if not ok:
            return {"success": False, "error": reason, "adapter": "fakevlm", "status": "unavailable"}

        keep_loaded = bool(parameters.get("keep_model_loaded", False))

        try:
            report_progress(on_progress, 5, "Carregando FakeVLM")
            prepare_vram_for_heavy_model()
            device = resolve_inference_device()
            stack = _load_fakevlm_stack(device)
            processor = stack["processor"]
            model = stack["model"]

            report_progress(on_progress, 25, "Preparando imagem")
            image = Image.open(evidence_path).convert("RGB")

            max_new_tokens = int(parameters.get("max_new_tokens", 100))
            question = parameters.get("question") or None
            prompt = _build_prompt(question)

            report_progress(on_progress, 50, "Executando inferencia multimodal")
            inputs = processor(text=prompt, images=image, return_tensors="pt").to(model.device)
            with torch.no_grad():
                output = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
            response = processor.decode(output[0], skip_special_tokens=True).strip()

            report_progress(on_progress, 85, "Processando resultado")
            verdict, fake_score = _parse_verdict(response)
            real_score = 1.0 - fake_score

            out_dir = job_artifact_dir(parameters, fallback_subdir="fakevlm_tmp")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            report_path = out_dir / f"fakevlm_report_{stamp}.txt"
            report_path.write_text(
                f"Veredicto: {verdict}\n"
                f"Score AI (fake): {fake_score:.4f}\n"
                f"Score Real: {real_score:.4f}\n"
                f"Dispositivo: {device_display_label(device)}\n"
                f"\nResposta completa do modelo:\n{response}\n",
                encoding="utf-8",
            )
            json_path = out_dir / "fakevlm_report.json"
            json_path.write_text(
                __import__("json").dumps(
                    {
                        "prediction": verdict,
                        "fake_score": fake_score,
                        "real_score": real_score,
                        "response": response,
                        "inference_device": device_display_label(device),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result: Dict[str, Any] = {
                "success": True,
                "adapter": "fakevlm",
                "status": "completed",
                "prediction": verdict,
                "fake_score": fake_score,
                "real_score": real_score,
                "response": response,
                "inference_device": device_display_label(device),
                "report_path": str(report_path),
                "fakevlm_report_json_path": str(json_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "fakevlm"}

        finally:
            if not keep_loaded:
                clear_fakevlm_model_cache()


def fakevlm_runtime_status() -> Tuple[bool, str]:
    if not _FAKEVLM_MODEL_PATH.exists():
        return False, f"Pesos FakeVLM nao encontrados em {_FAKEVLM_MODEL_PATH}"
    required_files = ["config.json", "model.safetensors.index.json"]
    for fname in required_files:
        if not (_FAKEVLM_MODEL_PATH / fname).exists():
            return False, f"Arquivo necessario ausente: {fname}"
    return True, ""
