#!/usr/bin/env python3
"""Diagnóstico do ambiente GPU / deps pesadas do ForensicAuth.

Uso (na raiz do repositório, com o conda do projeto ativo):
    python scripts/diagnose_gpu.py

Verifica: Python, NVIDIA/CUDA, PyTorch, pacotes de requirements-gpu.txt,
subpastas em MODELS_DIR, e variáveis de ambiente relevantes ao worker GPU.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Pacotes críticos alinhados a requirements-gpu.txt (módulo importável → rótulo).
HEAVY_DEPS: list[tuple[str, str]] = [
    ("torch", "torch"),
    ("torchvision", "torchvision"),
    ("transformers", "transformers"),
    ("accelerate", "accelerate"),
    ("peft", "peft"),
    ("timm", "timm"),
    ("open_clip", "open_clip_torch"),
    ("mmcv", "mmcv"),
    ("xgboost", "xgboost"),
    ("kornia", "kornia"),
    ("pytorch_wavelets", "pytorch_wavelets"),
    ("pywt", "PyWavelets"),
    ("numba", "numba"),
    ("jpegio", "jpegio"),
    ("skimage", "scikit-image"),
    ("librosa", "librosa"),
    ("soundfile", "soundfile"),
    ("decord", "decord"),
    ("imageio_ffmpeg", "imageio-ffmpeg"),
    ("pytorch_lightning", "pytorch-lightning"),
    ("lightning", "lightning"),
]

# Subpastas esperadas sob MODELS_DIR (técnicas GPU / ML ativas).
EXPECTED_MODEL_DIRS: list[tuple[str, str]] = [
    ("sepael", "Detecção imagens sintéticas (XGBoost / SID)"),
    ("bfree", "B-Free / Bias-free"),
    ("grip_clipd", "GRIP CLIP-based"),
    ("truebees_clip_d", "TrueBees CLIP-D / Corvi"),
    ("safire", "SAFIRE"),
    ("imdlbenco", "IMDL-BenCo (TruFor, CAT-Net, …)"),
    ("prnu", "PRNU"),
    ("pad", "Presentation Attack Detection"),
    ("moe_ffd", "MoE-FFD"),
    ("sls_spoofing", "SLS áudio spoofing"),
    ("wedefense_asv2025", "WeDefense ASV"),
    ("videofact", "VideoFact"),
    ("stil", "STIL vídeo"),
    ("lowres_fake_video", "LowRes fake video"),
    ("truvil", "TruVIL"),
    ("vilocal", "ViLocal"),
]

OPTIONAL_MODEL_DIRS: list[tuple[str, str]] = [
    ("icpbrasil", "Âncoras ICP-Brasil (PDF signatures — não é peso ML)"),
]


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return True, (result.stdout or "").strip()
        return False, (result.stderr or result.stdout or "").strip()
    except FileNotFoundError:
        return False, "comando não encontrado"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def try_import(module: str) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(module)
        version = getattr(mod, "__version__", None)
        return True, str(version or "ok")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc).split("\n")[0][:120]


def count_files(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for p in path.rglob("*") if p.is_file())


def main() -> int:
    missing_critical = 0
    warnings = 0
    recommendations: list[str] = []

    print("=" * 64)
    print("FORENSICAUTH — GPU / HEAVY DEPS DIAGNOSTIC")
    print("=" * 64)

    # --- System ---
    print("\n[SYSTEM]")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Platform: {sys.platform}")
    print(f"Repo root: {ROOT}")
    if sys.version_info < (3, 11):
        warnings += 1
        recommendations.append("Use Python 3.11+ (conda env forensicauth).")

    # --- CUDA / GPU ---
    print("\n[CUDA / GPU]")
    ok, out = run_cmd(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ]
    )
    if ok:
        print(f"OK  nvidia-smi: {out}")
    else:
        missing_critical += 1
        print(f"FAIL nvidia-smi: {out}")
        recommendations.append("Instale driver NVIDIA e confira nvidia-smi no host.")

    ok, out = run_cmd(["nvcc", "--version"])
    if ok:
        line = next((ln for ln in out.splitlines() if "release" in ln.lower()), out.splitlines()[-1])
        print(f"OK  nvcc: {line.strip()}")
    else:
        warnings += 1
        print("WARN nvcc ausente (ok se usar wheels pip/conda com CUDA embutida)")

    # --- PyTorch ---
    print("\n[PYTORCH]")
    torch_ok, torch_ver = try_import("torch")
    if not torch_ok:
        missing_critical += 1
        print("FAIL torch NÃO instalado")
        recommendations.append(
            "Instale PyTorch com CUDA, ex.: "
            "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124"
        )
    else:
        import torch

        print(f"OK  torch {torch.__version__}")
        cuda_ok = torch.cuda.is_available()
        print(f"    CUDA available: {cuda_ok}")
        print(f"    torch.version.cuda: {torch.version.cuda}")
        if cuda_ok:
            print(f"    Device: {torch.cuda.get_device_name(0)}")
            props = torch.cuda.get_device_properties(0)
            print(f"    VRAM: {props.total_memory / 1e9:.1f} GB")
        else:
            missing_critical += 1
            print("FAIL PyTorch sem CUDA")
            recommendations.append(
                "Reinstale torch com índice CUDA (cu124/cu121) compatível com o driver."
            )

    # --- Heavy deps ---
    print("\n[HEAVY DEPENDENCIES] (requirements-gpu.txt)")
    for module, label in HEAVY_DEPS:
        if module == "torch":
            continue  # já coberto
        ok, detail = try_import(module)
        if ok:
            print(f"OK   {label:22s} {detail}")
        else:
            # open_clip/mmcv/decord/peft são frequentes de faltar em hosts parciais
            soft = module in {"open_clip", "mmcv", "decord", "peft"}
            if soft:
                warnings += 1
                print(f"WARN {label:22s} ausente ({detail})")
            else:
                missing_critical += 1
                print(f"FAIL {label:22s} ausente")
            recommendations.append(f"Instale deps GPU: pip install -r requirements-gpu.txt ({label})")

    # --- Model weights ---
    print("\n[MODEL WEIGHTS]")
    models_dir = Path(os.environ.get("MODELS_DIR", ROOT / "models"))
    if not models_dir.is_absolute():
        models_dir = (ROOT / models_dir).resolve()
    else:
        models_dir = models_dir.resolve()

    if not models_dir.is_dir():
        missing_critical += 1
        print(f"FAIL MODELS_DIR inexistente: {models_dir}")
        recommendations.append(f"Crie {models_dir} e baixe/pesos conforme docs/deploy/MIGRATION-GPU.md")
    else:
        print(f"OK  MODELS_DIR: {models_dir}")
        present = 0
        for dirname, desc in EXPECTED_MODEL_DIRS:
            path = models_dir / dirname
            n = count_files(path)
            if n > 0:
                present += 1
                print(f"OK   {dirname:22s} {n:5d} arquivos — {desc}")
            elif path.is_dir():
                warnings += 1
                print(f"WARN {dirname:22s} pasta vazia — {desc}")
                recommendations.append(f"Preencha pesos em {path}")
            else:
                warnings += 1
                print(f"WARN {dirname:22s} ausente — {desc}")
                recommendations.append(f"Adicione pasta/pesos: {path} ({desc})")
        print(f"     Cobertura ML esperada: {present}/{len(EXPECTED_MODEL_DIRS)} pastas com arquivos")
        if present == 0:
            missing_critical += 1
            recommendations.append("Nenhum peso ML encontrado — técnicas GPU vão falhar.")

        for dirname, desc in OPTIONAL_MODEL_DIRS:
            path = models_dir / dirname
            n = count_files(path)
            if n > 0:
                print(f"OK   {dirname:22s} {n:5d} arquivos — {desc}")
            else:
                print(f"info {dirname:22s} opcional ausente — {desc}")

        # Pastas extras não listadas (informativo)
        known = {d for d, _ in EXPECTED_MODEL_DIRS} | {d for d, _ in OPTIONAL_MODEL_DIRS}
        extras = sorted(p.name for p in models_dir.iterdir() if p.is_dir() and p.name not in known)
        if extras:
            print(f"info pastas extras em MODELS_DIR: {', '.join(extras)}")

    # --- Environment ---
    print("\n[ENVIRONMENT]")
    for key in (
        "GPU_AVAILABLE",
        "MODELS_DIR",
        "CUDA_VISIBLE_DEVICES",
        "FORENSICAUTH_PROCESS_ROLE",
        "FORENSICAUTH_WORKER_QUEUE",
        "REDIS_URL",
        "CELERY_BROKER_URL",
    ):
        val = os.environ.get(key)
        print(f"  {key}={val if val is not None else '(não definido no ambiente)'}")

    env_file = ROOT / ".env"
    if env_file.is_file():
        print(f"OK  .env presente: {env_file}")
        text = env_file.read_text(encoding="utf-8", errors="replace")
        if "GPU_AVAILABLE=false" in text.replace(" ", ""):
            warnings += 1
            print("WARN .env contém GPU_AVAILABLE=false")
            recommendations.append("Para worker GPU, use GPU_AVAILABLE=true no .env.")
        elif "GPU_AVAILABLE=true" in text.replace(" ", ""):
            print("OK  .env: GPU_AVAILABLE=true")
        if "FORENSICAUTH_PROCESS_ROLE=worker-gpu" in text.replace(" ", ""):
            print("OK  .env: FORENSICAUTH_PROCESS_ROLE=worker-gpu")
    else:
        warnings += 1
        print("WARN .env não encontrado na raiz (ok se só Compose injeta env)")

    # --- Redis (opcional, broker) ---
    print("\n[REDIS / BROKER]")
    broker = os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/0"
    print(f"  broker alvo: {broker}")
    try:
        import redis  # type: ignore

        client = redis.from_url(broker, socket_connect_timeout=1)
        client.ping()
        print("OK  Redis ping")
    except ImportError:
        warnings += 1
        print("WARN pacote redis não instalado — não foi possível pingar o broker")
    except Exception as exc:  # noqa: BLE001
        warnings += 1
        print(f"WARN Redis indisponível: {exc}")
        recommendations.append("Suba Redis (Compose) antes do worker Celery GPU.")

    # --- Summary ---
    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"Falhas críticas: {missing_critical}")
    print(f"Avisos:          {warnings}")

    # Dedup recommendations preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for rec in recommendations:
        if rec not in seen:
            seen.add(rec)
            uniq.append(rec)

    if uniq:
        print("\nRECOMMENDATIONS")
        for i, rec in enumerate(uniq[:20], 1):
            print(f"{i}. {rec}")
        if len(uniq) > 20:
            print(f"... e mais {len(uniq) - 20}")
    else:
        print("\nNenhuma recomendação pendente neste host.")

    if missing_critical:
        print("\nResultado: NÃO pronto para GPU (corrija as falhas FAIL).")
        code = 1
    elif warnings:
        print("\nResultado: parcial — GPU básica ok, mas há WARN (deps/pesos/env).")
        code = 0
    else:
        print("\nResultado: checks críticos OK para operação GPU.")
        code = 0

    print("=" * 64)
    return code


if __name__ == "__main__":
    sys.exit(main())
