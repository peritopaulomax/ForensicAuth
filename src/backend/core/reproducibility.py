"""Runtime fingerprint and canonical artifact hashing for forensic reproducibility."""

from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import os
import platform
import socket
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.technique_ids import resolve_technique_id
from services.custody_utils import hash_canonical_json

try:
    import fcntl
except ImportError:  # pragma: no cover (Windows / non-Unix)
    fcntl = None  # type: ignore[assignment]


def reproducibility_spec(technique: str) -> dict[str, Any]:
    """Spec de reprodutibilidade (aceita aliases legados de técnica)."""
    canonical = resolve_technique_id(technique)
    return REPRODUCIBILITY_REGISTRY.get(canonical, {})

RUNTIME_SCHEMA_VERSION = "1"
JOB_RECEIPT_SCHEMA_VERSION = "1"
PROMOTED_REPRO_SCHEMA_VERSION = "1"

# Determinism profiles:
#   strict       — byte-identical artifact expected on same image + inputs
#   numeric      — floating-point / STFT; hash match expected on same stack
#   parallel     — joblib/numba; hash may differ; metrics should match
#   gpu_ml       — PyTorch/CUDA; best-effort reproduction
#   canonical    — no file artifact; hash of canonical result payload

REPRODUCIBILITY_REGISTRY: dict[str, dict[str, Any]] = {
    "ela": {"primary": "heatmap.png", "profile": "strict"},
    "metadata": {"primary": "metadata_report.json", "profile": "strict"},
    "prnu": {"primary": "correlation_surface.html", "profile": "parallel"},
    "dct_quantization": {"primary": "artifacts_upscaled.png", "profile": "numeric"},
    "jpeg_ghosts": {"primary": "ghost_map.png", "profile": "numeric"},
    "resampling": {"primary": "spectrum_combined.png", "profile": "numeric"},
    "patchmatch": {"primary": "overlay.png", "profile": "parallel"},
    "copy_move_pca": {"primary": "overlay.png", "profile": "parallel"},
    "wavelet_noise_residue": {"primary": "overlay.png", "profile": "deterministic"},
    "double_compression": {"primary": "interactive.html", "profile": "numeric"},
    "bag_extraction": {"primary": "bag_map.png", "profile": "strict"},
    "zero_grid": {"primary": "votes_colored.png", "profile": "strict"},
    "synthetic_image_detection": {"primary": "model_scores.txt", "profile": "gpu_ml"},
    "safire": {"mode": "canonical_result", "profile": "gpu_ml"},
    "noiseprint": {"mode": "canonical_result", "profile": "gpu_ml"},
    "imdlbenco": {"mode": "canonical_result", "profile": "gpu_ml"},
    "deepfake_similarity": {"mode": "canonical_result", "profile": "gpu_ml"},
    "mp3_parser": {"mode": "canonical_result", "profile": "strict"},
    "opus_parser": {"mode": "canonical_result", "profile": "strict"},
    "wav_ima_adpcm": {"mode": "canonical_result", "profile": "strict"},
    "audio_spectrogram": {"primary": "spectrogram.png", "profile": "numeric"},
    "audio_spoofing_detection": {"primary": "detector_scores.txt", "profile": "gpu_ml"},
    "audio_enf": {"primary": "plot_traces.json", "profile": "numeric"},
    "audio_ltas": {"primary": "ltas_plot_data.json", "profile": "numeric"},
    "audio_levels": {"primary": "plot_traces.json", "profile": "numeric"},
    "audio_dc_local": {"primary": "plot_traces.json", "profile": "numeric"},
    "pdf_font_color_overlay": {"primary": "font_overlay.pdf", "profile": "strict"},
    "pdf_structure_metrics": {"primary": "structure_graph.json", "profile": "strict"},
    "pdf_structure_similarity": {"primary": "similarity_matrices.json", "profile": "strict"},
    "pdf_forensic_extract": {"mode": "directory_manifest", "profile": "strict"},
    "isomedia_parser": {"primary": "isom_tree.json", "profile": "strict"},
    "isomedia_compare": {"primary": "similarity_matrices.json", "profile": "strict"},
    "videofact": {"primary": "videofact_report.json", "profile": "gpu_ml"},
    "stil_video_detection": {"primary": "stil_report.json", "profile": "gpu_ml"},
    "lowres_fake_video": {"primary": "lfv_report.json", "profile": "gpu_ml"},
    "jpeg_structure_compare": {
        "primary": "jpeg_structure_matrix.json",
        "profile": "strict",
    },
    "mock_technique": {"mode": "canonical_result", "profile": "strict"},
    "presentation_attack_detection": {"primary": "pad_result.json", "profile": "gpu_ml"},
    "moe_ffd": {"primary": "moe_ffd_result.json", "profile": "gpu_ml"},
}

_VOLATILE_RESULT_KEYS = frozenset(
    {
        "timestamp",
        "heatmap_path",
        "original_crop_path",
        "result_path",
        "note",
    }
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _library_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": platform.python_version()}
    try:
        import numpy as np

        versions["numpy"] = np.__version__
    except ImportError:
        pass
    try:
        import cv2

        versions["opencv"] = cv2.__version__
    except ImportError:
        pass
    try:
        import scipy

        versions["scipy"] = scipy.__version__
    except ImportError:
        pass
    try:
        import torch

        versions["torch"] = torch.__version__
        if torch.cuda.is_available():
            versions["cuda_runtime"] = torch.version.cuda or ""
    except ImportError:
        pass
    return versions


_MODEL_GLOB_PATTERNS = ("**/*.pth", "**/*.pt", "**/*.onnx", "**/*.bin", "**/*.safetensors")
# Cache: models_dir -> (file index fingerprint, hashes). Invalidates when mtimes/sizes change.
_MODEL_HASH_CACHE: dict[str, tuple[frozenset[tuple[str, int, int]], dict[str, str]]] = {}

MODEL_HASH_CACHE_SCHEMA_VERSION = "1"
MODEL_HASH_CACHE_FILENAME = ".forensicauth_model_hash_cache.json"


def clear_model_file_hash_cache() -> None:
    """Clear in-process model hash cache (tests or after model deploy)."""
    _MODEL_HASH_CACHE.clear()


def _model_hash_cache_path(models_dir: str) -> Path:
    return Path(models_dir) / MODEL_HASH_CACHE_FILENAME


def _system_boot_time() -> int | None:
    """Return system boot time in seconds since epoch (Linux only).

    Used to invalidate the durable model hash cache after a system reboot,
    so model hashes are recomputed at least once per boot.
    """
    try:
        with open("/proc/stat", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("btime "):
                    return int(line.split()[1].strip())
    except (OSError, ValueError, IndexError):
        pass
    return None


@contextmanager
def _model_hash_cache_lock(cache_path: Path):
    """Exclusive lock for the persistent cache file (process-safe on Unix)."""
    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    fd: int | None = None
    try:
        if fcntl is not None:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            except OSError:
                pass
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def _model_hash_cache_signing_key() -> bytes:
    """Return a stable key for HMAC-protecting the persistent cache.

    Prefer SECRET_KEY from environment. If unavailable, fall back to a
    deterministic key derived from this module's path. The fallback protects
    against accidental corruption but is NOT tamper-proof against an attacker
    with filesystem access.
    """
    secret = os.environ.get("SECRET_KEY", "")
    if secret:
        return hashlib.sha256(secret.encode("utf-8")).digest()
    return hashlib.sha256(Path(__file__).resolve().as_posix().encode("utf-8")).digest()


def _hmac_for_cache(payload: dict[str, Any]) -> str:
    canonical = hash_canonical_json(payload)
    return _hmac.new(
        _model_hash_cache_signing_key(), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _load_persistent_model_hash_cache(models_dir: str) -> dict[str, str] | None:
    """Load model hashes from durable cache if index matches and HMAC is valid."""
    cache_path = _model_hash_cache_path(models_dir)
    if not cache_path.is_file():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if data.get("cache_schema_version") != MODEL_HASH_CACHE_SCHEMA_VERSION:
        return None
    if data.get("models_dir") != str(Path(models_dir).resolve()):
        return None

    current_boot_time = _system_boot_time()
    cached_boot_time = data.get("system_boot_time")
    if current_boot_time is not None and cached_boot_time != current_boot_time:
        return None

    stored_hmac = data.pop("hmac", None)
    if not isinstance(stored_hmac, str):
        return None
    if not _hmac.compare_digest(stored_hmac, _hmac_for_cache(data)):
        return None

    current_index = _model_files_index(Path(models_dir))
    try:
        saved_index = frozenset(tuple(entry) for entry in data.get("index", []))
    except TypeError:
        return None
    if current_index != saved_index:
        return None

    hashes = data.get("hashes")
    if not isinstance(hashes, dict):
        return None
    return {str(k): str(v) for k, v in hashes.items()}


def _save_persistent_model_hash_cache(
    models_dir: str,
    index: frozenset[tuple[str, int, int]],
    hashes: dict[str, str],
) -> None:
    """Persist validated model hashes to disk with HMAC integrity protection."""
    cache_path = _model_hash_cache_path(models_dir)
    payload: dict[str, Any] = {
        "cache_schema_version": MODEL_HASH_CACHE_SCHEMA_VERSION,
        "models_dir": str(Path(models_dir).resolve()),
        "system_boot_time": _system_boot_time(),
        "index": sorted(index),
        "hashes": dict(sorted(hashes.items())),
    }
    payload["hmac"] = _hmac_for_cache(payload)

    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    with _model_hash_cache_lock(cache_path):
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp_path.replace(cache_path)
        except OSError:
            # Persistent cache is an optimization; failures must not break analysis.
            pass
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _model_files_index(root: Path) -> frozenset[tuple[str, int, int]]:
    entries: list[tuple[str, int, int]] = []
    for pattern in _MODEL_GLOB_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                st = path.stat()
                rel = path.relative_to(root).as_posix()
                entries.append((rel, st.st_mtime_ns, st.st_size))
    return frozenset(entries)


def _model_file_hashes(models_dir: str) -> dict[str, str]:
    """SHA-256 of model weight files present on disk (for ML techniques).

    Uses an in-process cache first, then a durable on-disk cache protected by
    HMAC and indexed by file mtime/size. The on-disk cache survives process
    restarts and is only recomputed when model files change.
    """
    root = Path(models_dir)
    if not root.is_dir():
        return {}

    cache_key = str(root.resolve())
    index = _model_files_index(root)

    # 1. In-process cache (fastest, same process).
    cached = _MODEL_HASH_CACHE.get(cache_key)
    if cached is not None and cached[0] == index:
        return dict(cached[1])

    # 2. Durable cache (survives restarts; invalidated by index or HMAC mismatch).
    persistent = _load_persistent_model_hash_cache(models_dir)
    if persistent is not None:
        _MODEL_HASH_CACHE[cache_key] = (index, dict(persistent))
        return persistent

    # 3. Compute from disk and update both caches.
    out: dict[str, str] = {}
    for rel, _, _size in sorted(index):
        out[rel] = _sha256_file(root / rel)
    _MODEL_HASH_CACHE[cache_key] = (index, dict(out))
    _save_persistent_model_hash_cache(models_dir, index, out)
    return out


ML_MODEL_HASH_TECHNIQUES = frozenset(
    {
        "synthetic_image_detection",
        "deepfake_similarity",
        "safire",
        "noiseprint",
        "imdlbenco",
        "videofact",
        "stil_video_detection",
        "lowres_fake_video",
        "sepael",
        "prnu",
    }
)


def build_runtime_manifest(
    *,
    app_version: str,
    gpu_available: bool,
    models_dir: str,
    image_tag: str = "",
    image_digest: str = "",
    worker_queue: str = "",
    technique: str = "",
    include_model_hashes: bool | None = None,
) -> dict[str, Any]:
    """Build environment fingerprint for a completed analysis job."""
    tag = image_tag or os.environ.get("FORENSICAUTH_IMAGE_TAG", "")
    digest = image_digest or os.environ.get("FORENSICAUTH_IMAGE_DIGEST", "")
    queue = worker_queue or os.environ.get("FORENSICAUTH_WORKER_QUEUE", "")
    if not queue:
        queue = "gpu" if gpu_available else "celery"

    profile = "gpu_ml" if queue == "gpu" or gpu_available else "strict"

    manifest: dict[str, Any] = {
        "runtime_schema_version": RUNTIME_SCHEMA_VERSION,
        "forensicauth_version": app_version,
        "docker_image": tag,
        "docker_image_digest": digest,
        "worker_queue": queue,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "gpu_available": bool(gpu_available),
        "default_determinism_profile": profile,
        "libraries": _library_versions(),
    }
    want_hashes = include_model_hashes
    if want_hashes is None:
        want_hashes = technique in ML_MODEL_HASH_TECHNIQUES
    if want_hashes:
        model_hashes = _model_file_hashes(models_dir)
        if model_hashes:
            manifest["model_file_hashes"] = model_hashes
    return manifest


def _strip_volatile_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove paths and volatile keys for canonical result hashing."""

    def _clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            cleaned: dict[str, Any] = {}
            for k, v in sorted(obj.items(), key=lambda item: str(item[0])):
                if k in _VOLATILE_RESULT_KEYS:
                    continue
                if isinstance(k, str) and (k.endswith("_path") or k.endswith("_paths")):
                    continue
                if k == "extract_bundle_dir":
                    continue
                cleaned[k] = _clean(v)
            return cleaned
        if isinstance(obj, list):
            return [_clean(x) for x in obj]
        return obj

    return _clean(result)


def _hash_directory_manifest(result_dir: Path, *, exclude: frozenset[str]) -> str:
    entries: list[dict[str, str]] = []
    for path in sorted(result_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(result_dir).as_posix()
        if rel in exclude:
            continue
        entries.append({"file": rel, "sha256": _sha256_file(path)})
    return hash_canonical_json({"files": entries})


def compute_artifact_sha256(
    technique: str,
    result_dir: Path,
    result: dict[str, Any],
) -> tuple[str, str, str | None]:
    """Return (artifact_sha256, determinism_profile, primary_artifact_name).

    primary_artifact_name is the relative path used for hashing, if any.
    """
    spec = reproducibility_spec(technique)
    profile = spec.get("profile", "numeric")
    mode = spec.get("mode", "primary")
    primary_name: str | None = None

    if mode == "canonical_result":
        canonical = _strip_volatile_result(result)
        digest = hashlib.sha256(
            hash_canonical_json(canonical).encode("utf-8")
        ).hexdigest()
        return digest, profile, None

    if mode == "directory_manifest":
        digest = _hash_directory_manifest(
            result_dir,
            exclude=frozenset({"result.json", "reproducibility_manifest.json"}),
        )
        return digest, profile, "(directory_manifest)"

    primary = spec.get("primary")
    if primary:
        candidate = result_dir / primary
        if candidate.is_file():
            primary_name = primary
            return _sha256_file(candidate), profile, primary_name

    # Fallback: manifest of all artifacts in job result dir
    digest = _hash_directory_manifest(
        result_dir,
        exclude=frozenset({"result.json", "reproducibility_manifest.json"}),
    )
    return digest, profile, "(auto_manifest)"


def compare_reproduction(
    *,
    technique: str,
    determinism_profile: str | None,
    original_artifact_sha256: str | None,
    reproduced_artifact_sha256: str,
    original_runtime: dict[str, Any] | None,
    current_runtime: dict[str, Any],
) -> dict[str, Any]:
    """Build verification report comparing stored vs re-executed analysis."""
    profile = determinism_profile or reproducibility_spec(technique).get(
        "profile", "numeric"
    )
    orig_digest = (original_runtime or {}).get("docker_image_digest") or ""
    curr_digest = current_runtime.get("docker_image_digest") or ""
    runtime_match = bool(orig_digest and curr_digest and orig_digest == curr_digest)

    if not original_artifact_sha256:
        status = "NO_BASELINE"
        message = "Job sem artifact_sha256 registrado (analise anterior a reproducibilidade)."
    elif original_artifact_sha256 == reproduced_artifact_sha256:
        status = "MATCH"
        message = "Artefato canonico reproduzido com hash identico."
    elif profile in ("parallel", "gpu_ml"):
        status = "BEST_EFFORT_MISMATCH"
        message = (
            f"Hash diferente (perfil {profile}). Divergencia pode ser esperada "
            "em tecnicas paralelas ou GPU/ML."
        )
    else:
        status = "MISMATCH"
        message = "Hash do artefato canonico difere do registrado originalmente."

    if original_artifact_sha256 and not runtime_match:
        if orig_digest and curr_digest:
            message += " Runtime Docker atual difere do original."
        elif not orig_digest:
            message += " Job original sem docker_image_digest registrado."

    return {
        "status": status,
        "artifact_match": original_artifact_sha256 == reproduced_artifact_sha256,
        "runtime_digest_match": runtime_match,
        "determinism_profile": profile,
        "original_artifact_sha256": original_artifact_sha256,
        "reproduced_artifact_sha256": reproduced_artifact_sha256,
        "original_runtime": original_runtime or {},
        "current_runtime": current_runtime,
        "message": message,
    }


def build_reproducibility_record(
    technique: str,
    result_dir: Path,
    result: dict[str, Any],
    runtime_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Full reproducibility block (legacy / reproduce temp runs)."""
    artifact_sha256, profile, primary = compute_artifact_sha256(
        technique, result_dir, result
    )
    spec_profile = reproducibility_spec(technique).get("profile")
    return {
        "runtime": runtime_manifest,
        "artifact_sha256": artifact_sha256,
        "determinism_profile": spec_profile or profile,
        "primary_artifact": primary,
        "technique": technique,
    }


def build_job_execution_receipt(
    *,
    technique: str,
    result: dict[str, Any],
    runtime_manifest: dict[str, Any],
    job_id: str | None = None,
    parameters: dict[str, Any] | None = None,
    input_evidence_sha256: str | None = None,
) -> dict[str, Any]:
    """Lightweight execution snapshot captured at job completion (preview tier)."""
    canonical = _strip_volatile_result(result)
    execution_digest = hashlib.sha256(
        hash_canonical_json(canonical).encode("utf-8")
    ).hexdigest()
    spec = reproducibility_spec(technique)
    profile = spec.get("profile", "numeric")
    return {
        "receipt_schema_version": JOB_RECEIPT_SCHEMA_VERSION,
        "kind": "job_execution_receipt",
        "technique": technique,
        "job_id": job_id,
        "execution_digest": execution_digest,
        "determinism_profile": profile,
        "runtime": runtime_manifest,
        "parameters": parameters or {},
        "input_evidence_sha256": input_evidence_sha256,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def compute_promoted_artifact_sha256(
    technique: str,
    artifact_path: Path,
    *,
    result_dir: Path | None = None,
    result: dict[str, Any] | None = None,
    artifact_filename: str | None = None,
) -> tuple[str, str, str | None]:
    """Hash the artifact actually promoted to derivatives."""
    spec = reproducibility_spec(technique)
    profile = spec.get("profile", "numeric")

    if artifact_path.is_file():
        return _sha256_file(artifact_path), profile, artifact_filename or artifact_path.name

    if result_dir is not None and result is not None:
        return compute_artifact_sha256(technique, result_dir, result)

    raise FileNotFoundError(f"Artefato promovido nao encontrado: {artifact_path}")


def build_promoted_reproducibility_record(
    *,
    technique: str,
    job_receipt: dict[str, Any],
    artifact_path: Path,
    artifact_filename: str,
    result_dir: Path | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full forensic reproducibility block when an artifact is saved as derivative."""
    artifact_sha256, profile, primary = compute_promoted_artifact_sha256(
        technique,
        artifact_path,
        result_dir=result_dir,
        result=result,
        artifact_filename=artifact_filename,
    )
    spec_profile = reproducibility_spec(technique).get("profile")
    return {
        "reproducibility_schema_version": PROMOTED_REPRO_SCHEMA_VERSION,
        "kind": "promoted_derivative",
        "technique": technique,
        "artifact_sha256": artifact_sha256,
        "promoted_artifact": artifact_filename or primary,
        "determinism_profile": spec_profile or profile or job_receipt.get("determinism_profile"),
        "runtime": job_receipt.get("runtime") or {},
        "job_execution_receipt": job_receipt,
        "execution_digest": job_receipt.get("execution_digest"),
    }


def load_job_execution_receipt(
    job_result: dict[str, Any],
    runtime_manifest: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve job receipt from result.json or legacy runtime_manifest."""
    receipt = job_result.get("job_receipt")
    if isinstance(receipt, dict) and receipt.get("kind") == "job_execution_receipt":
        return receipt
    if isinstance(runtime_manifest, dict) and runtime_manifest.get("kind") == "job_execution_receipt":
        return runtime_manifest
    if isinstance(runtime_manifest, dict) and runtime_manifest.get("runtime_schema_version"):
        return {
            "receipt_schema_version": JOB_RECEIPT_SCHEMA_VERSION,
            "kind": "job_execution_receipt",
            "technique": job_result.get("adapter") or job_result.get("technique"),
            "execution_digest": job_result.get("reproducibility", {}).get("artifact_sha256"),
            "determinism_profile": job_result.get("reproducibility", {}).get("determinism_profile"),
            "runtime": runtime_manifest,
            "parameters": {},
            "legacy_migration": True,
        }
    return None


def compare_execution_receipt(
    *,
    technique: str,
    original_receipt: dict[str, Any] | None,
    reproduced_receipt: dict[str, Any],
    current_runtime: dict[str, Any],
) -> dict[str, Any]:
    """Compare lightweight execution receipts after re-running a job."""
    profile = (
        (original_receipt or {}).get("determinism_profile")
        or reproducibility_spec(technique).get("profile", "numeric")
    )
    original_digest = (original_receipt or {}).get("execution_digest")
    reproduced_digest = reproduced_receipt.get("execution_digest")

    orig_rt = (original_receipt or {}).get("runtime") or {}
    orig_docker = orig_rt.get("docker_image_digest") or ""
    curr_docker = current_runtime.get("docker_image_digest") or ""
    runtime_match = bool(orig_docker and curr_docker and orig_docker == curr_docker)

    if not original_digest:
        status = "NO_BASELINE"
        message = "Job sem recibo de execucao (analise anterior a este modelo)."
    elif original_digest == reproduced_digest:
        status = "MATCH"
        message = "Recibo de execucao reproduzido com digest identico."
    elif profile in ("parallel", "gpu_ml"):
        status = "BEST_EFFORT_MISMATCH"
        message = (
            f"Digest de execucao diferente (perfil {profile}). "
            "Divergencia pode ser esperada em tecnicas paralelas ou GPU/ML."
        )
    else:
        status = "MISMATCH"
        message = "Digest de execucao difere do registrado originalmente."

    if original_digest and not runtime_match:
        if orig_docker and curr_docker:
            message += " Runtime Docker atual difere do original."
        elif not orig_docker:
            message += " Job original sem docker_image_digest registrado."

    return {
        "status": status,
        "artifact_match": original_digest == reproduced_digest,
        "runtime_digest_match": runtime_match,
        "determinism_profile": profile,
        "original_artifact_sha256": original_digest,
        "reproduced_artifact_sha256": reproduced_digest,
        "original_runtime": orig_rt,
        "current_runtime": current_runtime,
        "message": message,
        "comparison_mode": "execution_receipt",
    }
