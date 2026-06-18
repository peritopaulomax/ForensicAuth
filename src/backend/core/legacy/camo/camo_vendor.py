"""Carrega CAMO/UCF do vendor BitMind sem NPR/diffusers/bittensor."""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from contextlib import contextmanager
from pathlib import Path

from core.legacy.camo.camo_runtime import (
    camo_configs_dir,
    camo_vendor_dir,
    camo_weights_dir,
    resolve_dlib_predictor,
)

logger = logging.getLogger(__name__)

_CAMO_BOOTSTRAPPED = False
_INSERTED_PATHS: list[str] = []


def _install_bittensor_stub() -> None:
    if "bittensor" in sys.modules:
        return
    bt_logging = types.SimpleNamespace(
        info=lambda *args, **kwargs: logger.info(*args),
        warning=lambda *args, **kwargs: logger.warning(*args),
        error=lambda *args, **kwargs: logger.error(*args),
        debug=lambda *args, **kwargs: logger.debug(*args),
    )
    sys.modules["bittensor"] = types.SimpleNamespace(logging=bt_logging)


def _ensure_package(name: str, path: Path | None = None) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        if path is not None:
            mod.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = mod
    return sys.modules[name]


def _load_file(module_name: str, file_path: Path) -> types.ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Nao foi possivel carregar {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _insert_sys_paths(vendor: Path) -> None:
    global _INSERTED_PATHS
    candidates = (
        vendor,
        vendor / "base_miner",
        vendor / "base_miner" / "DFB",
    )
    for path in candidates:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
            _INSERTED_PATHS.append(text)


def _patch_dfb_constants() -> dict[str, str]:
    import base_miner.DFB.config.constants as constants

    saved = {
        "WEIGHTS_DIR": constants.WEIGHTS_DIR,
        "CONFIGS_DIR": constants.CONFIGS_DIR,
        "DLIB_FACE_PREDICTOR_PATH": constants.DLIB_FACE_PREDICTOR_PATH,
    }
    weights = str(camo_weights_dir())
    configs = str(camo_configs_dir())
    predictor = resolve_dlib_predictor()
    constants.WEIGHTS_DIR = weights
    constants.CONFIGS_DIR = configs
    if predictor is not None:
        constants.DLIB_FACE_PREDICTOR_PATH = str(predictor)
    dfb_const = sys.modules.get("DFB.config.constants")
    if dfb_const is not None and dfb_const is not constants:
        dfb_const.WEIGHTS_DIR = weights
        dfb_const.CONFIGS_DIR = configs
        if predictor is not None:
            dfb_const.DLIB_FACE_PREDICTOR_PATH = str(predictor)
    return saved


def _restore_dfb_constants(saved: dict[str, str]) -> None:
    try:
        import base_miner.DFB.config.constants as constants

        constants.WEIGHTS_DIR = saved["WEIGHTS_DIR"]
        constants.CONFIGS_DIR = saved["CONFIGS_DIR"]
        constants.DLIB_FACE_PREDICTOR_PATH = saved["DLIB_FACE_PREDICTOR_PATH"]
    except Exception:
        pass


def bootstrap_camo_modules(vendor: Path) -> None:
    """Carrega UCF + CAMO sem importar NPR (evita diffusers)."""
    global _CAMO_BOOTSTRAPPED
    if _CAMO_BOOTSTRAPPED and "base_miner.deepfake_detectors.camo_detector" in sys.modules:
        return

    _insert_sys_paths(vendor)
    dfb = vendor / "base_miner" / "DFB"

    _ensure_package("base_miner")
    _ensure_package("base_miner.DFB", dfb)
    _ensure_package("base_miner.DFB.config", dfb / "config")
    const_mod = _load_file("base_miner.DFB.config.constants", dfb / "config" / "constants.py")
    _ensure_package("DFB.config", dfb / "config")
    sys.modules["DFB.config.constants"] = const_mod
    _patch_dfb_constants()

    _ensure_package("metrics", dfb / "metrics")
    for rel in ("base_metrics_class.py", "utils.py", "registry.py", "__init__.py"):
        _load_file(f"metrics.{rel.removesuffix('.py')}", dfb / "metrics" / rel)

    _ensure_package("DFB", dfb)
    _ensure_package("DFB.networks", dfb / "networks")
    _load_file("DFB.networks.xception", dfb / "networks" / "xception.py")
    sys.modules.pop("DFB.networks", None)
    _load_file("DFB.networks", dfb / "networks" / "__init__.py")

    _ensure_package("DFB.loss", dfb / "loss")
    for rel in (
        "abstract_loss_func.py",
        "cross_entropy_loss.py",
        "l1_loss.py",
        "contrastive_regularization.py",
    ):
        _load_file(f"DFB.loss.{rel.removesuffix('.py')}", dfb / "loss" / rel)
    sys.modules.pop("DFB.loss", None)
    _load_file("DFB.loss", dfb / "loss" / "__init__.py")

    _ensure_package("DFB.detectors", dfb / "detectors")
    _load_file("DFB.detectors.base_detector", dfb / "detectors" / "base_detector.py")
    det_pkg = sys.modules["DFB.detectors"]
    det_pkg.DETECTOR = sys.modules["metrics.registry"].DETECTOR
    _load_file("DFB.detectors.ucf_detector", dfb / "detectors" / "ucf_detector.py")
    det_pkg.UCFDetector = sys.modules["DFB.detectors.ucf_detector"].UCFDetector

    _load_file("base_miner.registry", vendor / "base_miner" / "registry.py")

    _ensure_package("base_miner.gating_mechanisms", vendor / "base_miner" / "gating_mechanisms")
    _ensure_package("base_miner.gating_mechanisms.utils", vendor / "base_miner" / "gating_mechanisms" / "utils")
    gating = sys.modules["base_miner.gating_mechanisms"]
    gate_mod = _load_file(
        "base_miner.gating_mechanisms.gate",
        vendor / "base_miner" / "gating_mechanisms" / "gate.py",
    )
    gating.Gate = gate_mod.Gate
    utils_pkg = sys.modules["base_miner.gating_mechanisms.utils"]
    face_utils = _load_file(
        "base_miner.gating_mechanisms.utils.face_utils",
        vendor / "base_miner" / "gating_mechanisms" / "utils" / "face_utils.py",
    )
    utils_pkg.get_face_landmarks = face_utils.get_face_landmarks
    utils_pkg.align_and_crop_face = face_utils.align_and_crop_face
    face_gate = _load_file(
        "base_miner.gating_mechanisms.face_gate",
        vendor / "base_miner" / "gating_mechanisms" / "face_gate.py",
    )
    _load_file(
        "base_miner.gating_mechanisms.gating_mechanism",
        vendor / "base_miner" / "gating_mechanisms" / "gating_mechanism.py",
    )
    gating = sys.modules["base_miner.gating_mechanisms"]
    gating.GatingMechanism = sys.modules["base_miner.gating_mechanisms.gating_mechanism"].GatingMechanism
    gating.FaceGate = face_gate.FaceGate

    _ensure_package("base_miner.deepfake_detectors", vendor / "base_miner" / "deepfake_detectors")
    df_pkg = sys.modules["base_miner.deepfake_detectors"]
    df_base = _load_file(
        "base_miner.deepfake_detectors.deepfake_detector",
        vendor / "base_miner" / "deepfake_detectors" / "deepfake_detector.py",
    )
    df_pkg.DeepfakeDetector = df_base.DeepfakeDetector

    ucf_wrap = _load_file(
        "base_miner.deepfake_detectors.ucf_detector",
        vendor / "base_miner" / "deepfake_detectors" / "ucf_detector.py",
    )
    df_pkg.UCFImageDetector = ucf_wrap.UCFImageDetector

    camo_mod = _load_file(
        "base_miner.deepfake_detectors.camo_detector",
        vendor / "base_miner" / "deepfake_detectors" / "camo_detector.py",
    )
    df_pkg.CAMOImageDetector = camo_mod.CAMOImageDetector

    _CAMO_BOOTSTRAPPED = True


@contextmanager
def camo_vendor_context():
    vendor = camo_vendor_dir().resolve()
    _install_bittensor_stub()
    saved_constants: dict[str, str] | None = None

    try:
        importlib.invalidate_caches()
        bootstrap_camo_modules(vendor)
        saved_constants = _patch_dfb_constants()
        yield
    finally:
        if saved_constants is not None:
            _restore_dfb_constants(saved_constants)


def reset_camo_bootstrap_for_tests() -> None:
    global _CAMO_BOOTSTRAPPED
    _CAMO_BOOTSTRAPPED = False
    for key in list(sys.modules):
        if key == "base_miner" or key.startswith("base_miner.") or key.startswith("DFB.") or key == "DFB":
            sys.modules.pop(key, None)
        if key == "metrics" or key.startswith("metrics."):
            sys.modules.pop(key, None)
