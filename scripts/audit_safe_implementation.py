"""Compare our SAFE inference against the official vendor eval transform."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.transforms import InterpolationMode

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.legacy.safe.safe_pipeline import _load_model, _load_safe_resnet50, resolve_checkpoint
from core.gpu_inference import resolve_inference_device


def official_transform(size: int = 256):
    return transforms.Compose([
        transforms.CenterCrop([size, size]),
        transforms.ToTensor(),
    ])


def our_old_transform(size: int = 256):
    return transforms.Compose([
        transforms.Resize((size, size), interpolation=InterpolationMode.BILINEAR),
        transforms.ToTensor(),
    ])


def our_new_transform(size: int = 256):
    from core.legacy.safe.safe_pipeline import _SafeEvalTransform
    return _SafeEvalTransform()


def infer_with_transform(image: Image.Image, model: torch.nn.Module, device: torch.device, tfm):
    tensor = tfm(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        logits = model(tensor)
        prob_fake = F.softmax(logits, dim=1)[0, 1].item()
    return prob_fake


def main():
    device = resolve_inference_device()
    print(f"Device: {device}")

    resnet50 = _load_safe_resnet50()
    model = resnet50(num_classes=2)
    ckpt = resolve_checkpoint()
    obj = torch.load(str(ckpt), map_location="cpu", weights_only=False)
    state = obj.get("model", obj) if isinstance(obj, dict) else obj
    if isinstance(state, dict):
        state = {k.replace("module.", ""): v for k, v in state.items()}
    model.load_state_dict(state, strict=True)
    model = model.to(device)
    model.eval()

    df = pd.read_csv(
        "outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv",
        low_memory=False,
    )
    # Sample real and fake images from different generators/datasets
    samples = []
    grouped = df[df["error"].fillna("").eq("")].groupby(["dataset", "generator", "y_fake"])
    for (dataset, generator, y_fake), group in grouped:
        if len(samples) >= 60:
            break
        samples.append(group.iloc[len(group) // 2])

    print(f"\nComparing {len(samples)} sample images")
    print("-" * 120)
    print(f"{'dataset':<25} {'generator':<25} {'y_fake':<8} {'old_resize':<12} {'new_safe':<12} {'official_crop':<14} {'delta_old':<10} {'delta_new':<10} path")
    print("-" * 120)

    for row in samples:
        path = row["image_path"]
        try:
            image = Image.open(path).convert("RGB")
        except Exception as exc:
            print(f"Cannot open {path}: {exc}")
            continue

        old_prob = infer_with_transform(image, model, device, our_old_transform())
        new_prob = infer_with_transform(image, model, device, our_new_transform())
        try:
            official_prob = infer_with_transform(image, model, device, official_transform())
        except Exception as exc:
            official_prob = f"ERR:{exc}"

        delta_old = "-"
        delta_new = "-"
        official_str = str(official_prob)
        if isinstance(official_prob, float):
            delta_old = f"{old_prob - official_prob:+.4f}"
            delta_new = f"{new_prob - official_prob:+.4f}"
            official_str = f"{official_prob:.4f}"

        print(
            f"{row['dataset']:<25} {row['generator']:<25} {row['y_fake']:<8} "
            f"{old_prob:<12.4f} {new_prob:<12.4f} {official_str:<14} "
            f"{delta_old:<10} {delta_new:<10} {path}"
        )


if __name__ == "__main__":
    main()
