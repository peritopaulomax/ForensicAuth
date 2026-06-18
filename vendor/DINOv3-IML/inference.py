"""
Standalone inference for DINOv3-IML models.

No IMDLBenCo required — only torch, peft, and Pillow.

Usage:
    python inference.py \
        --image path/to/image.jpg \
        --checkpoint checkpoints/vitl_lora_r32_cat.pth \
        --dinov3_repo path/to/dinov3 \
        --dinov3_weights path/to/dinov3_vitl16_pretrain.pth \
        --model_type dinov3_vitl16 \
        --lora_rank 32 \
        --output mask.png

Or from Python:
    from inference import predict
    mask = predict("image.jpg", "checkpoint.pth", dinov3_repo="...", dinov3_weights="...")
    mask.save("mask.png")
"""

import argparse
from pathlib import Path

import numpy as np
import torch
from PIL import Image

# ImageNet normalization (used by DINOv3)
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _load_and_preprocess(image_path: str, image_size: int = 512) -> torch.Tensor:
    """Load image, resize to image_size×image_size, normalize. Returns (1, 3, H, W)."""
    img = Image.open(image_path).convert("RGB").resize(
        (image_size, image_size), Image.BILINEAR
    )
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = ((arr - _MEAN) / _STD).astype(np.float32)  # (H, W, 3)
    tensor = torch.from_numpy(arr).permute(2, 0, 1)  # (3, H, W)
    return tensor.unsqueeze(0)                        # (1, 3, H, W)


def _save_mask(prob: torch.Tensor, output_path: str, threshold: float = 0.5):
    """Save binary mask and heatmap.

    Saves two files:
      <output_path>          — binary mask (white=tampered)
      <stem>_heatmap<suffix> — probability heatmap (jet colormap)
    """
    prob_np = prob.squeeze().cpu().numpy()  # (H, W), values in [0, 1]

    # Binary mask
    binary = (prob_np > threshold).astype(np.uint8) * 255
    Image.fromarray(binary, mode="L").save(output_path)

    # Heatmap (jet colormap via matplotlib)
    try:
        import matplotlib.pyplot as plt
        p = Path(output_path)
        heatmap_path = str(p.parent / (p.stem + "_heatmap" + p.suffix))
        plt.imsave(heatmap_path, prob_np, cmap="jet", vmin=0, vmax=1)
        print(f"Heatmap saved → {heatmap_path}")
    except ImportError:
        pass  # matplotlib optional


def predict(
    image_path: str,
    checkpoint_path: str,
    dinov3_repo: str,
    dinov3_weights: str,
    model_type: str = "dinov3_vitl16",
    lora_rank: int = 32,
    lora_alpha: float = 64.0,
    image_size: int = 512,
    device: str = "cuda" if torch.cuda.is_available() else "cpu",
    model_variant: str = "lora",  # "lora" | "frozen" | "fullft"
) -> Image.Image:
    """Run inference on a single image and return the probability mask as a PIL Image.

    Args:
        image_path: Path to input image.
        checkpoint_path: Path to .pth checkpoint (from this repo or IMDLBenCo training).
        dinov3_repo: Path to local DINOv3 repository.
        dinov3_weights: Path to DINOv3 pretrained backbone weights (.pth).
        model_type: Backbone size — dinov3_vits16 / dinov3_vitb16 / dinov3_vitl16.
        lora_rank: LoRA rank (ignored for frozen/fullft variants).
        lora_alpha: LoRA alpha (ignored for frozen/fullft variants).
        image_size: Resize input to this size before inference (default 512).
        device: 'cuda' or 'cpu'.
        model_variant: Which model class to use ('lora', 'frozen', or 'fullft').

    Returns:
        PIL Image (mode 'L') — probability map scaled to [0, 255].
    """
    # Import model class
    if model_variant == "lora":
        from models.dinov3_forensics_lora import DINOv3ForensicsLoRA as ModelCls
        model = ModelCls.from_pretrained(
            checkpoint_path,
            dinov3_repo_path=dinov3_repo,
            dinov3_weights_path=dinov3_weights,
            dinov3_model_type=model_type,
            image_size=image_size,
            lora_rank=lora_rank,
            lora_alpha=lora_alpha,
        )
    elif model_variant == "frozen":
        from models.dinov3_forensics import DINOv3Forensics as ModelCls
        model = ModelCls.from_pretrained(
            checkpoint_path,
            dinov3_repo_path=dinov3_repo,
            dinov3_weights_path=dinov3_weights,
            dinov3_model_type=model_type,
            image_size=image_size,
        )
    elif model_variant == "fullft":
        from models.dinov3_forensics_full_ft import DINOv3ForensicsFullFT as ModelCls
        model = ModelCls.from_pretrained(
            checkpoint_path,
            dinov3_repo_path=dinov3_repo,
            dinov3_weights_path=dinov3_weights,
            dinov3_model_type=model_type,
            image_size=image_size,
        )
    else:
        raise ValueError(f"Unknown model_variant: {model_variant!r}. Use 'lora', 'frozen', or 'fullft'.")

    model = model.to(device)
    model.eval()

    # Preprocess
    image_tensor = _load_and_preprocess(image_path, image_size).to(device)

    # Inference
    prob = model.predict(image_tensor)  # (1, 1, H, W), values in [0, 1]

    # Convert to PIL
    prob_np = (prob.squeeze().cpu().numpy() * 255).astype(np.uint8)
    return Image.fromarray(prob_np, mode="L")


def main():
    parser = argparse.ArgumentParser(description="DINOv3-IML inference")
    parser.add_argument("--image",           required=True,  help="Input image path")
    parser.add_argument("--checkpoint",      required=True,  help="Model checkpoint (.pth)")
    parser.add_argument("--dinov3_repo",     required=True,  help="Path to local DINOv3 repo")
    parser.add_argument("--dinov3_weights",  required=True,  help="Path to DINOv3 backbone weights (.pth)")
    parser.add_argument("--model_type",      default="dinov3_vitl16",
                        choices=["dinov3_vits16", "dinov3_vitb16", "dinov3_vitl16"])
    parser.add_argument("--variant",         default="lora",
                        choices=["lora", "frozen", "fullft"])
    parser.add_argument("--lora_rank",       type=int,   default=32)
    parser.add_argument("--lora_alpha",      type=float, default=64.0)
    parser.add_argument("--image_size",      type=int,   default=512)
    parser.add_argument("--threshold",       type=float, default=0.5)
    parser.add_argument("--output",          default="mask.png", help="Output mask path")
    parser.add_argument("--device",          default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    print(f"Running inference on: {args.image}")
    print(f"Model: {args.variant} / {args.model_type} / rank={args.lora_rank}")

    prob_img = predict(
        image_path=args.image,
        checkpoint_path=args.checkpoint,
        dinov3_repo=args.dinov3_repo,
        dinov3_weights=args.dinov3_weights,
        model_type=args.model_type,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
        image_size=args.image_size,
        device=args.device,
        model_variant=args.variant,
    )

    _save_mask(
        torch.from_numpy(np.array(prob_img, dtype=np.float32) / 255.0).unsqueeze(0).unsqueeze(0),
        args.output,
        threshold=args.threshold,
    )
    print(f"Mask saved → {args.output}")


if __name__ == "__main__":
    main()
