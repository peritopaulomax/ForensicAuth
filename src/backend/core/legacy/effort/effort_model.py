"""Effort detector (CLIP ViT-L/14 + SVD residual) — inference-only port."""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import CLIPVisionModel


class SVDResidualLinear(nn.Module):
    def __init__(self, in_features, out_features, r, bias=True, init_weight=None):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.r = r

        self.weight_main = nn.Parameter(torch.Tensor(out_features, in_features), requires_grad=False)
        if init_weight is not None:
            self.weight_main.data.copy_(init_weight)
        else:
            nn.init.kaiming_uniform_(self.weight_main, a=math.sqrt(5))

        if bias:
            self.bias = nn.Parameter(torch.Tensor(out_features))
            nn.init.zeros_(self.bias)
        else:
            self.register_parameter("bias", None)

    def forward(self, x):
        if hasattr(self, "U_residual") and hasattr(self, "V_residual") and self.S_residual is not None:
            residual_weight = self.U_residual @ torch.diag(self.S_residual) @ self.V_residual
            weight = self.weight_main + residual_weight
        else:
            weight = self.weight_main
        return F.linear(x, weight, self.bias)


def replace_with_svd_residual(module: nn.Module, r: int) -> nn.Module:
    if not isinstance(module, nn.Linear):
        return module

    in_features = module.in_features
    out_features = module.out_features
    bias = module.bias is not None
    new_module = SVDResidualLinear(
        in_features,
        out_features,
        r,
        bias=bias,
        init_weight=module.weight.data.clone(),
    )
    if bias and module.bias is not None:
        new_module.bias.data.copy_(module.bias.data)

    new_module.weight_original_fnorm = torch.norm(module.weight.data, p="fro")

    u, s, vh = torch.linalg.svd(module.weight.data, full_matrices=False)
    r = min(r, len(s))

    u_r = u[:, :r]
    s_r = s[:r]
    vh_r = vh[:r, :]
    weight_main = u_r @ torch.diag(s_r) @ vh_r
    new_module.weight_main_fnorm = torch.norm(weight_main.data, p="fro")
    new_module.weight_main.data.copy_(weight_main)

    u_residual = u[:, r:]
    s_residual = s[r:]
    vh_residual = vh[r:, :]

    if len(s_residual) > 0:
        new_module.S_residual = nn.Parameter(s_residual.clone())
        new_module.U_residual = nn.Parameter(u_residual.clone())
        new_module.V_residual = nn.Parameter(vh_residual.clone())
        new_module.S_r = nn.Parameter(s_r.clone(), requires_grad=False)
        new_module.U_r = nn.Parameter(u_r.clone(), requires_grad=False)
        new_module.V_r = nn.Parameter(vh_r.clone(), requires_grad=False)
    else:
        new_module.S_residual = None
        new_module.U_residual = None
        new_module.V_residual = None
        new_module.S_r = None
        new_module.U_r = None
        new_module.V_r = None

    return new_module


def apply_svd_residual_to_self_attn(model: nn.Module, r: int) -> nn.Module:
    for name, module in model.named_children():
        if "self_attn" in name:
            for sub_name, sub_module in module.named_modules():
                if isinstance(sub_module, nn.Linear):
                    parent_module = module
                    sub_module_names = sub_name.split(".")
                    for module_name in sub_module_names[:-1]:
                        parent_module = getattr(parent_module, module_name)
                    setattr(parent_module, sub_module_names[-1], replace_with_svd_residual(sub_module, r))
        else:
            apply_svd_residual_to_self_attn(module, r)

    for param_name, param in model.named_parameters():
        if any(x in param_name for x in ("S_residual", "U_residual", "V_residual")):
            param.requires_grad = True
        else:
            param.requires_grad = False
    return model


class EffortDetector(nn.Module):
    """CLIP-L/14 + orthogonal subspace (Effort) — fake probability via softmax[:, 1]."""

    def __init__(self, clip_model_path: str):
        super().__init__()
        clip_vision = CLIPVisionModel.from_pretrained(clip_model_path)
        self.backbone = apply_svd_residual_to_self_attn(clip_vision, r=1023)
        self.head = nn.Linear(1024, 2)

    def forward(self, data_dict: dict, inference: bool = False) -> dict:
        del inference
        features = self.backbone(data_dict["image"])["pooler_output"]
        pred = self.head(features)
        prob = torch.softmax(pred, dim=1)[:, 1]
        return {"cls": pred, "prob": prob, "feat": features}
