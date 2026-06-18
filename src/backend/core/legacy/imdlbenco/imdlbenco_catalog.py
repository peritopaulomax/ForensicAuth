"""Catalog of IMDL-BenCo hub methods (native + ecosystem)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MethodTier = Literal["native", "ecosystem"]
MethodStatus = Literal["ready", "weights_missing", "vendor_missing", "unavailable"]


@dataclass(frozen=True)
class ImdlBencoMethod:
    id: str
    name: str
    venue: str
    tier: MethodTier
    description: str
    repo_url: str
    stars: int | None = None
    accent: str = "#0369a1"
    image_size: int = 512
    use_padding: bool = False
    use_resizing: bool = True
    edge_width: int | None = 7


IMDLBENCO_METHODS: tuple[ImdlBencoMethod, ...] = (
    ImdlBencoMethod(
        id="trufor",
        name="TruFor",
        venue="CVPR'23",
        tier="native",
        description="TruFor oficial GRIP-UNINA: full-res, mapa de localizacao, confianca e score de integridade.",
        repo_url="https://github.com/grip-unina/TruFor",
        stars=120,
        accent="#0e7490",
        image_size=0,
        use_resizing=False,
        edge_width=7,
    ),
    ImdlBencoMethod(
        id="cat_net",
        name="CAT-Net",
        venue="IJCV'22",
        tier="native",
        description="CAT-Net oficial (jpegio DCT, resolucao completa, CAT_full_v2).",
        repo_url="https://github.com/mjkwon2021/CAT-Net",
        stars=180,
        accent="#b45309",
        image_size=512,
        use_resizing=True,
        edge_width=None,
    ),
    ImdlBencoMethod(
        id="objectformer",
        name="ObjectFormer",
        venue="CVPR'22",
        tier="native",
        description="Prototipos de objetos + traços de alta frequencia para localizacao IML.",
        repo_url="https://github.com/wdrink/Objectformer",
        stars=0,
        accent="#4f46e5",
        image_size=224,
        use_resizing=True,
        edge_width=7,
    ),
    ImdlBencoMethod(
        id="dinov3_iml",
        name="DINOv3-IML",
        venue="ArXiv'26",
        tier="ecosystem",
        description="ViT-L DINOv3 congelado + LoRA r=32 na QKV e cabeca conv 3x3 (protocolo CAT, ~9M params treinaveis).",
        repo_url="https://github.com/Irennnne/DINOv3-IML",
        stars=9,
        accent="#7c3aed",
        image_size=512,
        use_resizing=True,
        edge_width=None,
    ),
    ImdlBencoMethod(
        id="co_transformers",
        name="Co-Transformers",
        venue="AAAI'26",
        tier="ecosystem",
        description="Dual-Transformer com atencao forense multi-nivel.",
        repo_url="https://github.com/ProgrameThinking/Co-Transformers",
        stars=0,
        accent="#b45309",
        image_size=512,
        use_padding=False,
        use_resizing=True,
        edge_width=7,
    ),
    ImdlBencoMethod(
        id="nfa_vit",
        name="NFA-ViT",
        venue="AAAI'26",
        tier="ecosystem",
        description="Noise-guided forgery amplification (BR-Gen) — dual-branch SegFormer + DnCNN noiseprint.",
        repo_url="https://github.com/clpbc/BR-Gen",
        stars=29,
        accent="#be123c",
        image_size=512,
        use_padding=True,
        use_resizing=False,
        edge_width=7,
    ),
    ImdlBencoMethod(
        id="forensic_hub",
        name="ForensicHub",
        venue="NeurIPS'25",
        tier="ecosystem",
        description="Framework multi-dominio: IMDL, deepfake, AIGC e documentos.",
        repo_url="https://github.com/scu-zjz/ForensicHub",
        stars=208,
        accent="#0f766e",
        image_size=512,
        use_resizing=True,
        edge_width=None,
    ),
    ImdlBencoMethod(
        id="opensdi",
        name="OpenSDI",
        venue="CVPR'25",
        tier="ecosystem",
        description="Deteccao de imagens geradas por difusao em mundo aberto.",
        repo_url="https://github.com/iamwangyabin/OpenSDI",
        stars=45,
        accent="#1d4ed8",
        image_size=512,
        use_resizing=True,
        edge_width=None,
    ),
    ImdlBencoMethod(
        id="sparse_vit",
        name="Sparse-ViT",
        venue="AAAI'25",
        tier="native",
        description="Extrator nao-semantico via attention esparsa auto-supervisionada.",
        repo_url="https://github.com/scu-zjz/SparseViT",
        stars=106,
        accent="#059669",
        image_size=512,
        use_resizing=True,
        edge_width=None,
    ),
    ImdlBencoMethod(
        id="mesorch",
        name="Mesorch",
        venue="AAAI'25",
        tier="native",
        description="Mesorch oficial (512 resize, Mesorch/Mesorch-P, pesos AAAI 2025).",
        repo_url="https://github.com/scu-zjz/Mesorch",
        stars=100,
        accent="#c026d3",
        image_size=512,
        use_resizing=True,
        edge_width=None,
    ),
    ImdlBencoMethod(
        id="miml_apscnet",
        name="MIML APSC-Net",
        venue="MIML",
        tier="ecosystem",
        description="APSC-Net oficial do MIML para localizacao single-image de regioes manipuladas.",
        repo_url="https://github.com/qcf-568/MIML/tree/main/models%20for%20IML",
        stars=118,
        accent="#9333ea",
        image_size=512,
        use_resizing=True,
        edge_width=None,
    ),
)


def get_method(method_id: str) -> ImdlBencoMethod | None:
    for method in IMDLBENCO_METHODS:
        if method.id == method_id:
            return method
    return None
