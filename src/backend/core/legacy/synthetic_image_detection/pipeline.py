"""Pipeline de detecção de imagens sintéticas (port Gradio CNN + FFT + Effort + SAFE)."""

from __future__ import annotations

import io
import logging
import math
import os
import random
import threading
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np
from PIL import Image

from core.gpu_inference import (
    device_display_label,
    is_cuda_oom_or_device_error,
    release_gpu_memory as _core_release_gpu_memory,
    resolve_inference_device,
)
from core.legacy.synthetic_image_detection.runtime import (
    MODEL1_XGB_NAME,
    MODEL2_XGB_NAME,
    NPR_WEIGHTS_NAME,
    huggingface_cache_dir,
    resolve_hf_snapshot_path,
    resolve_models_dir,
)
from core.progress import report_progress

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# Limite para residuos NLM/mediana (CPU-bound em imagens grandes).
RESIDUE_MAX_SIDE = int(os.environ.get("SYNTHETIC_RESIDUE_MAX_SIDE", "2048"))
PIPELINE_CONFIG = {"use_models": ["model_1", "model_4"], "fft_feature_groups": {"texture": True}}
MODEL_PATHS = {
    "model_1": "haywoodsloan/ai-image-detector-deploy",
    "model_4": "cmckinle/sdxl-flux-detector_v1.1",
}
CLASS_NAMES = {
    "model_1": ["artificial", "real"],
    "model_4": ["AI", "Real"],
}
MODEL_DISPLAY = {
    "model_1": "ai-image-detector-deploy",
    "model_4": "sdxl-flux-detector_v1.1",
}

ProgressFn = Optional[Callable[[int, str], None]]

_DETECTION_MODELS: Any = None
_MODEL1_XGB: Any = None
_FFT_EXTRACTOR: Any = None
_DEVICE: Any = None
_MODEL_LOAD_LOCK = threading.Lock()
_LOAD_ERROR: Optional[BaseException] = None

# Import antecipado evita corrida lazy-import do transformers em threads paralelas.
try:
    import torch as _torch  # noqa: F401
    from transformers import (  # noqa: F401
        AutoFeatureExtractor,
        AutoImageProcessor,
        AutoModelForImageClassification,
        pipeline as _hf_pipeline,
    )
except ImportError:
    pass


def _configure_offline_env() -> None:
    for proxy_var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
        os.environ.pop(proxy_var, None)
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    cache = huggingface_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_CACHE"] = str(cache)


def seed_torch(seed: int = 100) -> None:
    import torch

    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.enabled = False


def softmax(x: np.ndarray) -> np.ndarray:
    exp_x = np.exp(x - np.max(x))
    return exp_x / np.sum(exp_x)


def _as_rgb(image: Image.Image) -> Image.Image:
    """Normaliza para RGB — legado Gradio fazia isso em NPR/ELA/FFT; HF falha em RGBA."""
    if image.mode == "RGB":
        return image
    return image.convert("RGB")


def _cap_image_for_residue(image: Image.Image, max_side: int = RESIDUE_MAX_SIDE) -> Image.Image:
    """Reduz imagens muito grandes antes de NLM/mediana (evita minutos de CPU)."""
    w, h = image.size
    longest = max(w, h)
    if longest <= max_side:
        return image
    scale = max_side / longest
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    logger.info(
        "Detecção imagens sintéticas: reduzindo %sx%s → %sx%s para residuos/NLM",
        w,
        h,
        new_size[0],
        new_size[1],
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


class ResidueFFTFeatureExtractor:
    def __init__(self, config: dict[str, Any]) -> None:
        from torchvision import transforms

        self.config = config["fft_feature_groups"]
        self.TOTAL_FEATURES = 30 if self.config.get("texture") else 0
        self.npr_transform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    def _calculate_residues(self, i: np.ndarray) -> dict[str, np.ndarray]:
        r: dict[str, np.ndarray] = {}
        m = cv2.medianBlur(i, 5)
        r["median"] = i.astype(np.float32) - m.astype(np.float32)
        try:
            s = np.mean(cv2.estimateGaussNoise(i)) if hasattr(cv2, "estimateGaussNoise") else 10.0
            h = np.clip(0.8 * s, 5.0, 25.0)
            n = cv2.fastNlMeansDenoising(i, None, h=h, templateWindowSize=7, searchWindowSize=21)
            r["non_local_means"] = i.astype(np.float32) - n.astype(np.float32)
        except Exception:
            g = cv2.GaussianBlur(i, (5, 5), sigmaX=1.5)
            r["non_local_means"] = i.astype(np.float32) - g.astype(np.float32)
        return r

    def _calculate_npr_residue_raw(self, image: Image.Image) -> np.ndarray:
        import torch
        from torch.nn import functional as F

        img_tensor = self.npr_transform(image.convert("RGB")).unsqueeze(0)
        _, _, w, h = img_tensor.shape
        if w % 2 == 1:
            img_tensor = img_tensor[:, :, :-1, :]
        if h % 2 == 1:
            img_tensor = img_tensor[:, :, :, :-1]
        interpolated = F.interpolate(
            F.interpolate(img_tensor, scale_factor=0.5, mode="nearest", recompute_scale_factor=True),
            scale_factor=2.0,
            mode="nearest",
            recompute_scale_factor=True,
        )
        npr_tensor = img_tensor - interpolated
        npr_np = npr_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy()
        npr_gray = cv2.cvtColor(npr_np, cv2.COLOR_RGB2GRAY) if npr_np.shape[2] == 3 else npr_np.squeeze()
        return npr_gray

    def _process_fft(self, residue: np.ndarray) -> np.ndarray:
        if np.all(residue == 0):
            return np.zeros_like(residue, dtype=np.float32)
        fft = np.fft.fft2(residue)
        fft_shifted = np.fft.fftshift(fft)
        magnitude = np.abs(fft_shifted)
        rows, cols = residue.shape
        crow, ccol = rows // 2, cols // 2
        magnitude[crow, ccol] = 0
        magnitude_log = np.log1p(magnitude)
        min_val, max_val = np.min(magnitude_log), np.max(magnitude_log)
        if max_val > min_val:
            magnitude_log = (magnitude_log - min_val) / (max_val - min_val)
        return magnitude_log

    def _extract_texture_features(self, m: np.ndarray) -> np.ndarray:
        from skimage.feature import graycomatrix, graycoprops
        from skimage.measure import shannon_entropy

        q = (m * 255).astype(np.uint8)
        g = graycomatrix(q, [1], [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4], 256, True, True)
        return np.array(
            [
                shannon_entropy(m),
                np.mean(graycoprops(g, "contrast")),
                np.mean(graycoprops(g, "homogeneity")),
                np.mean(graycoprops(g, "energy")),
                np.mean(graycoprops(g, "correlation")),
            ]
        )

    def extract_ensemble_fft_features(self, i: Image.Image) -> np.ndarray:
        if not self.config.get("texture"):
            return np.array([])
        try:
            g = np.array(i.convert("L"))
            s, f, a = [1.0, 0.5, 0.25], ["median", "non_local_means"], []
            for sc in s:
                h, w = g.shape
                si = cv2.resize(g, (int(w * sc), int(h * sc)), interpolation=cv2.INTER_AREA) if sc != 1.0 else g
                rs = self._calculate_residues(si)
                for fn in f:
                    ml = self._process_fft(rs[fn])
                    ft = self._extract_texture_features(ml)
                    a.append(ft)
            return np.concatenate(a, dtype=np.float32)
        except Exception as e:
            logger.error("Erro em extract_ensemble_fft_features: %s", e, exc_info=False)
            return np.zeros(self.TOTAL_FEATURES, dtype=np.float32)

    def generate_visualizations(self, image: Image.Image) -> tuple[Image.Image, Image.Image, Image.Image, Image.Image]:
        """NLM residue, median residue, NLM FFT, median FFT."""
        try:
            capped = _cap_image_for_residue(_as_rgb(image))
            g = np.array(capped.convert("L"))
            r = self._calculate_residues(g)
            nr = r.get("non_local_means", np.zeros_like(g, dtype=np.float32))
            mr = r.get("median", np.zeros_like(g, dtype=np.float32))

            def visualize(ra: np.ndarray) -> Image.Image:
                n = cv2.normalize(ra, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
                e = cv2.equalizeHist(n)
                return Image.fromarray(e)

            nrv = visualize(nr)
            mrv = visualize(mr)
            nfv = visualize(self._process_fft(nr))
            mfv = visualize(self._process_fft(mr))
            return nrv, mrv, nfv, mfv
        except Exception as e:
            logger.error("Erro ao gerar visualizacoes: %s", e)
            d = Image.new("L", (224, 224), 0)
            return d, d, d, d


def gen_ela(image: Image.Image, quality: int = 80) -> Image.Image:
    try:
        img_copy = image.copy()
        if img_copy.mode != "RGB":
            img_copy = img_copy.convert("RGB")
        b = io.BytesIO()
        img_copy.save(b, format="JPEG", quality=quality)
        b.seek(0)
        try:
            c = Image.open(b)
        except Exception:
            return Image.new("RGB", img_copy.size, color="black")
        d = np.abs(np.array(img_copy, dtype=np.float32) - np.array(c, dtype=np.float32))
        ds = np.clip(d * 20, 0, 255)
        return Image.fromarray(ds.astype(np.uint8))
    except Exception as e:
        logger.error("Erro ELA: %s", e)
        return Image.new("RGB", (224, 224), color="black")


def create_and_load_npr_model(weights_path: Path) -> Any:
    import torch
    import torch.nn as nn
    from torchvision.models import resnet50

    if not weights_path.is_file():
        raise FileNotFoundError(f"Arquivo de pesos '{weights_path}' nao encontrado!")
    m = resnet50()
    m.fc1 = nn.Linear(512, 1)
    m.conv1 = nn.Conv2d(3, 64, 3, 2, 1, bias=False)
    del m.layer3, m.layer4, m.fc
    s = torch.load(str(weights_path), map_location="cpu")
    if all(k.startswith("module.") for k in s.keys()):
        s = OrderedDict([(k[7:], v) for k, v in s.items()])
    m.load_state_dict(s, strict=True)
    logger.info("Pesos NPR de '%s' carregados.", weights_path)
    return m


def predict_npr_unified(image: Image.Image, model: Any) -> dict[str, float]:
    import torch
    from torch.nn import functional as F
    from torchvision import transforms

    trans = transforms.Compose(
        [transforms.ToTensor(), transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])]
    )
    it = trans(image.convert("RGB")).unsqueeze(0)
    _, _, w, h = it.shape
    if w % 2 == 1:
        it = it[:, :, :-1, :]
    if h % 2 == 1:
        it = it[:, :, :, :-1]
    interp = F.interpolate(
        F.interpolate(it, scale_factor=0.5, mode="nearest", recompute_scale_factor=True),
        scale_factor=2.0,
        mode="nearest",
        recompute_scale_factor=True,
    )
    nt = it - interp
    with torch.no_grad():
        x = model.conv1(nt * 2.0 / 3.0)
        x = model.bn1(x)
        x = model.relu(x)
        x = model.maxpool(x)
        x = model.layer1(x)
        x = model.layer2(x).mean((2, 3), keepdim=False)
        x = model.fc1(x)
        p = x.sigmoid().cpu().numpy()[0][0]
    return {"Fake Image": float(p), "Real Image": 1.0 - float(p)}


def _hf_local_path(model_id: str) -> str:
    return str(resolve_hf_snapshot_path(model_id))


def _load_model4_feature_extractor(model_id: str) -> Any:
    """Legado Gradio usa AutoFeatureExtractor para sdxl-flux-detector_v1.1."""
    from transformers import AutoFeatureExtractor, AutoImageProcessor

    local_path = _hf_local_path(model_id)
    try:
        return AutoFeatureExtractor.from_pretrained(local_path, local_files_only=True)
    except Exception:
        return AutoImageProcessor.from_pretrained(local_path, local_files_only=True)


def load_all_detection_models(
    device: Any,
    on_progress: ProgressFn = None,
) -> dict[str, Any]:
    import torch
    from transformers import AutoModelForImageClassification, pipeline

    pipeline_device: int | str = 0 if device.type == "cuda" else -1
    models: dict[str, Any] = {}
    logger.info("Carregando modelos de deteccao base Detecção imagens sintéticas em %s...", device)
    load_steps = list(PIPELINE_CONFIG["use_models"])
    for idx, mid in enumerate(load_steps):
        label = MODEL_DISPLAY.get(mid, mid)
        pct = 10 + int(16 * (idx + 1) / max(len(load_steps), 1))
        report_progress(on_progress, pct, f"Carregando {label}…")
        try:
            if mid == "model_4":
                local_path = _hf_local_path(MODEL_PATHS[mid])
                extractor = _load_model4_feature_extractor(MODEL_PATHS[mid])
                md = AutoModelForImageClassification.from_pretrained(
                    local_path,
                    local_files_only=True,
                ).to(device)

                def infer_fn(i: Image.Image, model=md, feature_extractor=extractor, dev=device):
                    rgb = _as_rgb(i)
                    inputs = feature_extractor(rgb, return_tensors="pt").to(dev)
                    with torch.no_grad():
                        return model(**inputs)

                models[mid] = {"model": infer_fn, "type": "logits", "_module": md}
            else:
                local_path = _hf_local_path(MODEL_PATHS[mid])
                pipe = pipeline(
                    "image-classification",
                    model=local_path,
                    device=pipeline_device,
                )
                models[mid] = {
                    "model": pipe,
                    "type": "pipeline",
                    "_pipeline": pipe,
                }
        except Exception as e:
            logger.error("Falha ao carregar %s: %s", mid, e)
            raise
    logger.info("%d modelos de deteccao base carregados.", len(models))
    return models


def load_xgb_model(models_dir: Path) -> Any:
    import xgboost as xgb

    model1 = xgb.XGBClassifier()
    model1.load_model(str(models_dir / MODEL1_XGB_NAME))
    logger.info("Modelo XGB FFT (model1) carregado de %s", models_dir)
    return model1


def get_decision(score_ai: float) -> str:
    if score_ai > 0.66:
        return "AI"
    if score_ai < 0.34:
        return "REAL"
    return "Incerto"


def release_gpu_memory() -> None:
    """Unload GPU-backed detection models and free CUDA memory after a job."""
    global _DETECTION_MODELS, _DEVICE

    handles: list[Any] = []
    if _DETECTION_MODELS is not None:
        for info in _DETECTION_MODELS.values():
            module = info.get("_module")
            pipeline_obj = info.get("_pipeline")
            if module is not None:
                handles.append(module)
            if pipeline_obj is not None:
                handles.append(pipeline_obj)

    _DETECTION_MODELS = None
    _DEVICE = None
    _core_release_gpu_memory(*handles)


def _load_models_on_device(device: Any, on_progress: ProgressFn = None) -> None:
    global _DETECTION_MODELS, _MODEL1_XGB, _FFT_EXTRACTOR, _DEVICE

    import torch

    _configure_offline_env()
    torch.set_num_threads(1)
    seed_torch(100)
    _DEVICE = device
    logger.info("Detecção imagens sintéticas usando device: %s", _DEVICE)
    report_progress(on_progress, 8, f"Preparando inferencia em {device_display_label(device)}…")

    models_dir = resolve_models_dir()
    if models_dir is None:
        raise FileNotFoundError("Pesos Detecção imagens sintéticas nao encontrados")

    _DETECTION_MODELS = load_all_detection_models(_DEVICE, on_progress=on_progress)
    if _MODEL1_XGB is None:
        report_progress(on_progress, 24, "Carregando model1_xgb (FFT) em CPU…")
        _MODEL1_XGB = load_xgb_model(models_dir)
    if _FFT_EXTRACTOR is None:
        report_progress(on_progress, 27, "Inicializando extrator FFT…")
        _FFT_EXTRACTOR = ResidueFFTFeatureExtractor(PIPELINE_CONFIG)
    report_progress(on_progress, 30, f"Modelos Detecção imagens sintéticas prontos em {device_display_label(_DEVICE)}")
    logger.info("Detecção imagens sintéticas: todos os modelos carregados.")


def _ensure_models_loaded(on_progress: ProgressFn = None) -> None:
    global _DETECTION_MODELS, _MODEL1_XGB, _FFT_EXTRACTOR, _DEVICE, _LOAD_ERROR
    if _DETECTION_MODELS is not None:
        dev = device_display_label(_DEVICE.type if _DEVICE is not None else "cpu")
        report_progress(on_progress, 30, f"Modelos em cache — inferencia em {dev}")
        return
    if _LOAD_ERROR is not None:
        raise _LOAD_ERROR

    with _MODEL_LOAD_LOCK:
        if _DETECTION_MODELS is not None:
            dev = device_display_label(_DEVICE.type if _DEVICE is not None else "cpu")
            report_progress(on_progress, 30, f"Modelos em cache — inferencia em {dev}")
            return
        if _LOAD_ERROR is not None:
            raise _LOAD_ERROR

        import torch

        device = resolve_inference_device()
        dev_label = device_display_label(device)
        report_progress(on_progress, 6, f"Carregando modelos Detecção imagens sintéticas em {dev_label} (primeira execucao)…")
        try:
            _load_models_on_device(device, on_progress=on_progress)
        except RuntimeError as exc:
            if device.type != "cuda" or not is_cuda_oom_or_device_error(exc):
                _LOAD_ERROR = exc
                logger.error("Detecção imagens sintéticas: falha ao carregar modelos: %s", exc)
                raise
            logger.warning("Detecção imagens sintéticas: falha em CUDA (%s); tentando CPU.", exc)
            release_gpu_memory()
            report_progress(on_progress, 8, "VRAM insuficiente — recarregando em CPU…")
            try:
                _load_models_on_device(torch.device("cpu"), on_progress=on_progress)
            except BaseException as exc:
                _LOAD_ERROR = exc
                logger.error("Detecção imagens sintéticas: falha ao carregar modelos em CPU: %s", exc)
                raise
        except BaseException as exc:
            _LOAD_ERROR = exc
            logger.error("Detecção imagens sintéticas: falha ao carregar modelos: %s", exc)
            raise


def predict_ensemble(image: Image.Image, on_progress: ProgressFn = None) -> list[list[str]]:
    _ensure_models_loaded(on_progress)
    assert _DETECTION_MODELS is not None
    assert _MODEL1_XGB is not None
    assert _FFT_EXTRACTOR is not None

    image = _as_rgb(image)
    individual_results: list[list[str]] = []
    ai_keywords = ["artificial", "ai", "fake", "deepfake", "ai_gen", "aigenerated"]
    real_keywords = ["real", "human", "realism", "natural"]
    ml_device_label = device_display_label(_DEVICE.type if _DEVICE is not None else "cpu")

    infer_models = list(PIPELINE_CONFIG["use_models"])
    for idx, model_id in enumerate(infer_models):
        label = MODEL_DISPLAY.get(model_id, model_id)
        pct = 32 + int(14 * idx / max(len(infer_models), 1))
        report_progress(on_progress, pct, f"Inferindo {label} em {ml_device_label}…")
        model_info = _DETECTION_MODELS[model_id]
        try:
            if model_info.get("type") == "pipeline":
                prediction = model_info["model"](image, top_k=5)
                scores = {p["label"]: p["score"] for p in prediction}
            else:
                prediction = model_info["model"](image)
                logits = prediction.logits.cpu().numpy()[0]
                probs = softmax(logits)
                scores = {CLASS_NAMES[model_id][j]: probs[j] for j in range(len(probs))}

            ai_score = 0.5
            found_score = False
            for class_name, score in scores.items():
                if any(keyword in class_name.lower().replace("_", "") for keyword in ai_keywords):
                    ai_score = float(score)
                    found_score = True
                    break
            if not found_score:
                for class_name, score in scores.items():
                    if any(keyword in class_name.lower().replace("_", "") for keyword in real_keywords):
                        ai_score = 1.0 - float(score)
                        break

            real_score = 1 - ai_score
            razao = real_score / ai_score if ai_score > 1e-9 else float("inf")
            decision = get_decision(ai_score)
            individual_results.append(
                [
                    MODEL_PATHS[model_id].split("/")[-1],
                    f"{ai_score:.4f}",
                    f"{real_score:.4f}",
                    f"{math.log10(razao):.2f}",
                    decision,
                    ml_device_label,
                ]
            )
        except Exception as e:
            logger.error("Erro na inferencia do %s: %s", model_id, e)

    report_progress(on_progress, 48, "Inferindo model1_xgb (FFT) em CPU…")
    fft_features = _FFT_EXTRACTOR.extract_ensemble_fft_features(image).reshape(1, -1)
    prob_model1_xgb_ai = _MODEL1_XGB.predict_proba(fft_features)[:, 0][0]
    real_score_m1_xgb = 1 - prob_model1_xgb_ai
    razao_m1_xgb = real_score_m1_xgb / prob_model1_xgb_ai if prob_model1_xgb_ai > 1e-9 else float("inf")
    decision_m1_xgb = get_decision(prob_model1_xgb_ai)
    individual_results.append(
        [
            "model1_xgb (FFT)",
            f"{prob_model1_xgb_ai:.4f}",
            f"{real_score_m1_xgb:.4f}",
            f"{math.log10(razao_m1_xgb):.2f}",
            decision_m1_xgb,
            "CPU",
        ]
    )

    try:
        from core.legacy.effort.effort_pipeline import predict_effort_rows

        individual_results.extend(predict_effort_rows(image, on_progress=on_progress))
    except Exception as exc:
        logger.warning("Effort indisponivel ou falhou no Detecção imagens sintéticas: %s", exc)

    try:
        from core.legacy.safe.safe_pipeline import predict_safe_row

        safe_row = predict_safe_row(image, on_progress=on_progress)
        if safe_row is not None:
            individual_results.append(safe_row)
    except Exception as exc:
        logger.warning("SAFE indisponivel ou falhou no Detecção imagens sintéticas: %s", exc)

    try:
        from core.legacy.camo.camo_pipeline import predict_camo_row

        camo_row = predict_camo_row(image, on_progress=on_progress)
        if camo_row is not None:
            individual_results.append(camo_row)
    except Exception as exc:
        logger.warning("CAMO indisponivel ou falhou no Detecção imagens sintéticas: %s", exc)

    try:
        from core.legacy.iapl.iapl_pipeline import predict_iapl_rows

        individual_results.extend(
            predict_iapl_rows(image, on_progress=on_progress, vram_prepared=False)
        )
    except Exception as exc:
        logger.warning("IAPL indisponivel ou falhou no Detecção imagens sintéticas: %s", exc)

    report_progress(on_progress, 66, "Tabela de modelos concluida")
    return individual_results


def _fft_preview_image(fft_extractor: ResidueFFTFeatureExtractor, gray_np: np.ndarray) -> Image.Image:
    original_fft_log_mag = fft_extractor._process_fft(gray_np)
    return Image.fromarray(cv2.equalizeHist((original_fft_log_mag * 255).astype(np.uint8)))


def run_synthetic_image_detection_analysis(
    image: Image.Image,
    *,
    generate_visuals: bool = True,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> dict[str, Any]:
    """Run full Detecção imagens sintéticas analysis and return structured results (no file I/O)."""
    image = _as_rgb(image)
    device_type = "cpu"
    try:
        report_progress(on_progress, 5, f"Iniciando pipeline Detecção imagens sintéticas + Effort em {device_display_label(resolve_inference_device())}")
        _ensure_models_loaded(on_progress)
        assert _FFT_EXTRACTOR is not None
        device_type = _DEVICE.type if _DEVICE is not None else "cpu"

        try:
            individual_results = predict_ensemble(image, on_progress=on_progress)
        except RuntimeError as exc:
            if _DEVICE is None or _DEVICE.type != "cuda" or not is_cuda_oom_or_device_error(exc):
                raise
            logger.warning("Detecção imagens sintéticas: inferencia falhou em CUDA (%s); tentando CPU.", exc)
            release_gpu_memory()
            report_progress(on_progress, 8, "Inferencia em CPU (fallback)…")
            _ensure_models_loaded(on_progress)
            device_type = _DEVICE.type if _DEVICE is not None else "cpu"
            individual_results = predict_ensemble(image, on_progress=on_progress)

        report_progress(on_progress, 68, "Gerando FFT da imagem de entrada…")
        gray = np.array(image.convert("L"))
        input_fft = _fft_preview_image(_FFT_EXTRACTOR, gray)

        visuals: dict[str, Optional[Image.Image]] = {
            "input_image": image.copy(),
            "input_fft": input_fft,
            "nlm_residue": None,
            "median_residue": None,
            "nlm_fft": None,
            "median_fft": None,
        }

        if generate_visuals:
            report_progress(on_progress, 72, "Residuos NLM e mediana…")
            nlm_residue_img, median_residue_img, nlm_fft_img, median_fft_img = (
                _FFT_EXTRACTOR.generate_visualizations(image)
            )
            report_progress(on_progress, 82, "Visualizacoes forenses prontas")
            visuals.update(
                {
                    "nlm_residue": nlm_residue_img,
                    "median_residue": median_residue_img,
                    "nlm_fft": nlm_fft_img,
                    "median_fft": median_fft_img,
                }
            )

        report_progress(on_progress, 86, "Montando resultado Detecção imagens sintéticas")

        return {
            "individual_results": individual_results,
            "generate_visuals": generate_visuals,
            "inference_device": device_type,
            **visuals,
        }
    finally:
        from core.gpu_residency import release_synthetic_if_not_resident

        release_synthetic_if_not_resident()
