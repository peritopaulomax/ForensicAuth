#!/usr/bin/env python3
"""Gera processed_model_weights.pth para ObjectFormer (IMDL-BenCo issue #41)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional

import torch
import torch.nn.functional as F
import timm

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "models" / "imdlbenco" / "objectformer" / "processed_model_weights.pth"


def resample_abs_pos_embed(
    posemb,
    new_size: List[int],
    old_size: Optional[List[int]] = None,
    num_prefix_tokens: int = 1,
    interpolation: str = "bicubic",
    antialias: bool = True,
):
    num_pos_tokens = posemb.shape[1]
    num_new_tokens = new_size[0] * new_size[1] + num_prefix_tokens
    if num_new_tokens == num_pos_tokens and new_size[0] == new_size[1]:
        return posemb

    if old_size is None:
        hw = int(math.sqrt(num_pos_tokens - num_prefix_tokens))
        old_size = hw, hw

    if num_prefix_tokens:
        posemb_prefix, posemb = posemb[:, :num_prefix_tokens], posemb[:, num_prefix_tokens:]
    else:
        posemb_prefix, posemb = None, posemb

    embed_dim = posemb.shape[-1]
    orig_dtype = posemb.dtype
    posemb = posemb.float()
    posemb = posemb.reshape(1, old_size[0], old_size[1], -1).permute(0, 3, 1, 2)
    posemb = F.interpolate(posemb, size=new_size, mode=interpolation, antialias=antialias)
    posemb = posemb.permute(0, 2, 3, 1).reshape(1, -1, embed_dim)
    posemb = posemb.to(orig_dtype)

    if posemb_prefix is not None:
        posemb = torch.cat([posemb_prefix, posemb], dim=1)
    return posemb


def build_processed_weights(out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model = timm.create_model("vit_base_patch16_224", pretrained=True)
    processed_state_dict: dict[str, torch.Tensor] = {}

    pos_embed = model.state_dict()["pos_embed"][0][1::].unsqueeze(0)
    pos_embed = resample_abs_pos_embed(pos_embed, [14, 28], num_prefix_tokens=0)
    processed_state_dict["pos_embed"] = pos_embed

    processed_state_dict["patch_embed.proj.weight"] = model.state_dict()["patch_embed.proj.weight"]
    processed_state_dict["patch_embed.proj.bias"] = model.state_dict()["patch_embed.proj.bias"]

    for i in range(8):
        block_prefix = f"blocks.{i}."
        processed_state_dict[f"{block_prefix}norm1.weight"] = model.state_dict()[f"{block_prefix}norm1.weight"]
        processed_state_dict[f"{block_prefix}norm1.bias"] = model.state_dict()[f"{block_prefix}norm1.bias"]

        qkv_weight = model.state_dict()[f"{block_prefix}attn.qkv.weight"]
        qkv_bias = model.state_dict()[f"{block_prefix}attn.qkv.bias"]
        dim = qkv_weight.shape[0] // 3
        processed_state_dict[f"{block_prefix}attn.q.weight"] = qkv_weight[:dim]
        processed_state_dict[f"{block_prefix}attn.k.weight"] = qkv_weight[dim : 2 * dim]
        processed_state_dict[f"{block_prefix}attn.v.weight"] = qkv_weight[2 * dim :]
        processed_state_dict[f"{block_prefix}attn.q.bias"] = qkv_bias[:dim]
        processed_state_dict[f"{block_prefix}attn.k.bias"] = qkv_bias[dim : 2 * dim]
        processed_state_dict[f"{block_prefix}attn.v.bias"] = qkv_bias[2 * dim :]

        processed_state_dict[f"{block_prefix}attn.proj.weight"] = model.state_dict()[f"{block_prefix}attn.proj.weight"]
        processed_state_dict[f"{block_prefix}attn.proj.bias"] = model.state_dict()[f"{block_prefix}attn.proj.bias"]

        processed_state_dict[f"{block_prefix}norm2.weight"] = model.state_dict()[f"{block_prefix}norm2.weight"]
        processed_state_dict[f"{block_prefix}norm2.bias"] = model.state_dict()[f"{block_prefix}norm2.bias"]
        processed_state_dict[f"{block_prefix}mlp.fc1.weight"] = model.state_dict()[f"{block_prefix}mlp.fc1.weight"]
        processed_state_dict[f"{block_prefix}mlp.fc1.bias"] = model.state_dict()[f"{block_prefix}mlp.fc1.bias"]
        processed_state_dict[f"{block_prefix}mlp.fc2.weight"] = model.state_dict()[f"{block_prefix}mlp.fc2.weight"]
        processed_state_dict[f"{block_prefix}mlp.fc2.bias"] = model.state_dict()[f"{block_prefix}mlp.fc2.bias"]

    torch.save(processed_state_dict, out_path)
    return out_path


def main() -> None:
    import os

    out = Path(os.environ.get("OBJECTFORMER_INIT_OUT", DEFAULT_OUT)).resolve()
    path = build_processed_weights(out)
    print(f"OK  {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
