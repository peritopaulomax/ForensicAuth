#!/usr/bin/env python3
"""Baixa pesos IMDL-BenCo e integrações de ecossistema."""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "imdlbenco"

HF_REPO = "suncore147/imdl-benco"
HF_FILES = {
    "trufor/trufor_casiav2.pth": "Trufor/checkpoint-0.pth",
    "trufor/noiseprint.pth": "NPR/NPR.pth",
    "trufor/mit_b2.pth": "RTM/mit_b2_20220624-66e8bf70.pth",
    "cat_net/cat_net_cat_net.pth": "Cat_Net/checkpoint-0.pth",
}

UNIFORMER_URL = (
    "https://huggingface.co/Sense-X/uniformer_image/resolve/main/uniformer_base_in1k.pth"
)
MESORCH_DRIVE_FOLDER = "1jwYv-S3HAZqzz0YxM9bJynBiPv-O9-6x"
MESORCH_CHECKPOINTS = ("mesorch-98.pth", "mesorch_p-118.pth")
MIT_B3_URL = (
    "https://github.com/qubvel/segmentation_models.pytorch/releases/download/v0.0.2/mit_b3.pth"
)
SPARSE_CKPT_DRIVE_ID = "104BPPvLXkxuPu_NHaxjesdcdZ-ln92-G"
BAIDU_CKPT_HINT = "https://pan.baidu.com/s/1DtkOwLCTunvI3d_GAAj2Dg (codigo: bchm)"
IMDLBENCO_CKPT_DRIVE_FOLDER = "1DCqc016-N4YvoMKKA87bFtrCdPVIDxAp"

MIML_DRIVE_FILES = {
    "miml/apsc/APSC-Net.pth": "1fTFUnn1mCO9w-YG3wa9Xqqkdn2PsSwmZ",
}


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _download_url(url: str, dest: Path, min_size: int = 100_000) -> bool:
    if dest.is_file() and dest.stat().st_size >= min_size:
        print(f"OK  {dest.name}")
        return True
    print(f"Baixando {dest.name} ...")
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as exc:
        print(f"FALHA  {dest.name}: {exc}")
        return False
    ok = dest.is_file() and dest.stat().st_size >= min_size
    print(f"{'OK' if ok else 'FALHA'}  {dest}")
    return ok


def _try_gdown(file_id: str, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 100_000:
        print(f"OK  {dest.name}")
        return True
    try:
        import gdown
    except ImportError:
        return False
    try:
        try:
            gdown.download(id=file_id, output=str(dest), quiet=False)
        except TypeError:
            gdown.download(f"https://drive.google.com/uc?id={file_id}", str(dest), quiet=False)
        return dest.is_file() and dest.stat().st_size > 100_000
    except Exception as exc:
        print(f"gdown falhou ({dest.name}): {exc}")
        return False


def _copy_from_folder(tmp: Path, fname: str, dest: Path) -> bool:
    if dest.is_file() and dest.stat().st_size > 100_000:
        print(f"OK  {dest.name}")
        return True
    found = list(tmp.rglob(fname))
    if not found:
        return False
    shutil.copy2(found[0], dest)
    print(f"OK  {dest.name}")
    return True


def _download_drive_folder(folder_id: str, tmp: Path) -> bool:
    try:
        import gdown
    except ImportError:
        return False
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        gdown.download_folder(
            id=folder_id,
            output=str(tmp),
            quiet=False,
            use_cookies=False,
        )
        return tmp.is_dir()
    except Exception as exc:
        print(f"gdown pasta falhou ({folder_id}): {exc}")
        return False


def _download_hf(dest_rel: str, hf_file: str, base: Path) -> bool:
    dest = base / dest_rel
    if dest.is_file() and dest.stat().st_size > 100_000:
        print(f"OK  {dest.name}")
        return True
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("FALHA  huggingface_hub ausente. pip install huggingface_hub")
        return False
    try:
        cached = hf_hub_download(repo_id=HF_REPO, filename=hf_file)
        _ensure_dir(dest.parent)
        shutil.copy2(cached, dest)
        print(f"OK  {dest.name} (HF:{hf_file})")
        return True
    except Exception as exc:
        print(f"FALHA  {dest.name}: {exc}")
        return False


def _download_mesorch_checkpoints(mesorch_dir: Path) -> None:
    targets = {fname: mesorch_dir / fname for fname in MESORCH_CHECKPOINTS}
    if all(p.is_file() and p.stat().st_size > 100_000 for p in targets.values()):
        for p in targets.values():
            print(f"OK  {p.name}")
        return

    tmp = mesorch_dir / "_drive_tmp"
    if _download_drive_folder(MESORCH_DRIVE_FOLDER, tmp):
        for fname, dest in targets.items():
            _copy_from_folder(tmp, fname, dest)
        shutil.rmtree(tmp, ignore_errors=True)

    drive_url = f"https://drive.google.com/drive/folders/{MESORCH_DRIVE_FOLDER}"
    for fname, dest in targets.items():
        if dest.is_file() and dest.stat().st_size > 100_000:
            continue
        print(f"PENDENTE  {fname}: copie para {dest}")
        print(f"  {drive_url}")


def _download_objectformer(base: Path) -> None:
    obj_dir = _ensure_dir(base / "objectformer")
    init_path = obj_dir / "processed_model_weights.pth"
    ckpt_path = obj_dir / "object_former_casiav2.pth"

    if not init_path.is_file() or init_path.stat().st_size < 100_000:
        print("Gerando processed_model_weights.pth (timm ViT-B/16) ...")
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "build_objectformer_init",
                ROOT / "scripts" / "build_objectformer_init.py",
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("nao foi possivel carregar build_objectformer_init.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.build_processed_weights(init_path)
            print(f"OK  {init_path.name}")
        except Exception as exc:
            print(f"FALHA  gerar init ObjectFormer: {exc}")

    if ckpt_path.is_file() and ckpt_path.stat().st_size > 100_000:
        print(f"OK  {ckpt_path.name}")
        return

    staging = obj_dir / "_gdrive"
    if _download_drive_folder(IMDLBENCO_CKPT_DRIVE_FOLDER, staging):
        if _copy_from_folder(staging, "objectformer_casiav2.pth", ckpt_path):
            return

    print(f"PENDENTE  object_former_casiav2.pth: copie para {ckpt_path}")
    print("  Google Drive: https://drive.google.com/drive/folders/1DCqc016-N4YvoMKKA87bFtrCdPVIDxAp")
    print(f"  Baidu IMDLBenCo_ckpt: {BAIDU_CKPT_HINT}")
    print("  Ou: python scripts/download_objectformer_weights.py")


def _download_miml(base: Path) -> None:
    print("--- MIML / APSC-Net ---")
    for rel, file_id in MIML_DRIVE_FILES.items():
        dest = base / rel
        _ensure_dir(dest.parent)
        if _try_gdown(file_id, dest):
            print(f"OK  {dest.name}")
            continue
        print(f"PENDENTE  {dest.name}: copie para {dest}")
        print(f"  https://drive.google.com/file/d/{file_id}/view")


def main() -> None:
    base = Path(os.environ.get("IMDLBENCO_MODELS_DIR", TARGET)).resolve()
    print(f"Destino: {base}")

    print("--- HuggingFace mirror (suncore147/imdl-benco) ---")
    for dest_rel, hf_file in HF_FILES.items():
        _download_hf(dest_rel, hf_file, base)

    _download_objectformer(base)

    mesorch_dir = _ensure_dir(base / "mesorch")
    sparse_dir = _ensure_dir(base / "sparse_vit")

    print("--- Mesorch ---")
    _download_mesorch_checkpoints(mesorch_dir)
    mit_b3 = mesorch_dir / "mit_b3.pth"
    _download_url(MIT_B3_URL, mit_b3, min_size=1_000_000)

    print("--- Sparse-ViT ---")
    uniformer = sparse_dir / "uniformer_base_in1k.pth"
    _download_url(UNIFORMER_URL, uniformer)

    sparse_ckpt = sparse_dir / "sparse_vit.pth"
    if not _try_gdown(SPARSE_CKPT_DRIVE_ID, sparse_ckpt):
        print(f"PENDENTE  Sparse-ViT: baixe para {sparse_ckpt}")
        print("  https://drive.google.com/file/d/104BPPvLXkxuPu_NHaxjesdcdZ-ln92-G/view")

    _download_miml(base)

    print("Download IMDL-BenCo concluido (verifique itens PENDENTE).")
    print("\n--- NFA-ViT (BR-Gen) ---")
    print("Execute: python scripts/download_nfa_vit_weights.py")
    print("Execute: python scripts/download_dinov3_iml_weights.py")
    print("Execute: python scripts/download_co_transformers_weights.py")
    print("Execute: python scripts/download_objectformer_weights.py")


if __name__ == "__main__":
    main()
