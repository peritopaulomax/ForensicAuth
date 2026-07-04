#!/usr/bin/env python3
"""Diagnostic script for GPU/Heavy-dependency environment.

Run this on the definitive system to check what's installed and what's missing.
Share the output with the engineering team if anything is missing.

Usage:
    python scripts/diagnose_gpu.py
"""

import os
import subprocess
import sys
from pathlib import Path


def check(section: str, cmd: list, shell=False) -> tuple[bool, str]:
    """Run a command and return (success, output_or_error)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, shell=shell, timeout=30
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 60)
    print("FORENSICAUTH — GPU ENVIRONMENT DIAGNOSTIC")
    print("=" * 60)

    # 1. System
    print("\n[SYSTEM]")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")

    # 2. CUDA
    print("\n[CUDA / GPU]")
    ok, out = check("nvidia-smi", ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"])
    if ok:
        print(f"✅ GPU detected: {out}")
    else:
        print(f"❌ nvidia-smi failed: {out}")

    ok, out = check("nvcc", ["nvcc", "--version"])
    if ok:
        print(f"✅ nvcc found:\n{out}")
    else:
        print(f"⚠️  nvcc not found (not critical if using conda/pip wheels)")

    # 3. PyTorch + CUDA
    print("\n[PYTORCH]")
    try:
        import torch
        print(f"✅ torch {torch.__version__}")
        print(f"   CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"   CUDA version: {torch.version.cuda}")
            print(f"   Device: {torch.cuda.get_device_name(0)}")
            print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
        else:
            print("   ⚠️  PyTorch installed but CUDA NOT available")
    except ImportError:
        print("❌ torch NOT installed")

    # 4. Other heavy deps
    print("\n[HEAVY DEPENDENCIES]")
    deps = [
        ("torchvision", "torchvision"),
        ("transformers", "transformers"),
        ("xgboost", "xgboost"),
        ("insightface", "insightface"),
        ("onnxruntime", "onnxruntime"),
        ("numba", "numba"),
        ("jpegio", "jpegio"),
        ("rawpy", "rawpy"),
        ("imagehash", "imagehash"),
        ("skimage", "skimage"),
        ("librosa", "librosa"),
        ("soundfile", "soundfile"),
        ("av", "av"),
    ]
    for name, module in deps:
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "unknown")
            print(f"✅ {name:20s} {version}")
        except ImportError:
            print(f"❌ {name:20s} NOT installed")

    # 5. Model weights
    print("\n[MODEL WEIGHTS]")
    models_dir = Path(os.environ.get("MODELS_DIR", "./models"))
    if not models_dir.exists():
        print(f"❌ MODELS_DIR not found: {models_dir}")
    else:
        print(f"✅ MODELS_DIR: {models_dir.resolve()}")
        for subdir in ["synthetic_image_detection", "deepfake", "prnu"]:
            path = models_dir / subdir
            if path.exists():
                files = list(path.rglob("*"))
                files = [f for f in files if f.is_file()]
                print(f"   ✅ {subdir:10s} ({len(files)} files)")
                for f in files[:5]:
                    print(f"      - {f.relative_to(models_dir)}")
                if len(files) > 5:
                    print(f"      ... and {len(files)-5} more")
            else:
                print(f"   ❌ {subdir:10s} directory missing")

    # 6. Settings / .env
    print("\n[ENVIRONMENT]")
    gpu_avail = os.environ.get("GPU_AVAILABLE", "not set")
    print(f"GPU_AVAILABLE env: {gpu_avail}")
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file exists")
        content = env_file.read_text()
        if "GPU_AVAILABLE=true" in content:
            print("   GPU_AVAILABLE=true configured")
        elif "GPU_AVAILABLE=false" in content:
            print("   ⚠️  GPU_AVAILABLE=false — set to true for GPU")
    else:
        print("❌ .env file not found")

    # 7. Recommendations
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)

    recommendations = []
    try:
        import torch
        if not torch.cuda.is_available():
            recommendations.append("PyTorch installed without CUDA. Reinstall with: pip install torch --index-url https://download.pytorch.org/whl/cu124")
    except ImportError:
        recommendations.append("Install PyTorch with CUDA support first.")

    sid_dir = models_dir / "synthetic_image_detection"
    if not sid_dir.exists() and not (models_dir / "sepael").exists():
        recommendations.append(
            f"Create {sid_dir}/ and place synthetic image detection model weights there."
        )
    if not (models_dir / "deepfake").exists():
        recommendations.append(f"Create {models_dir}/deepfake/ and place model weights there.")

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")
    else:
        print("🎉 Everything looks good! Ready to run forensic analysis with GPU.")

    print("\n" + "=" * 60)
    print("Diagnostic complete. Share the output above if support is needed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
