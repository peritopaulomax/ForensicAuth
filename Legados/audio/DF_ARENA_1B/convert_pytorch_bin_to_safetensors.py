#!/usr/bin/env python3
"""Converte pytorch_model.bin -> model.safetensors na mesma pasta.

O transformers recente exige PyTorch >= 2.6 para carregar .bin (CVE-2025-32434).
Com model.safetensors na pasta, o detector.py carrega sem esse requisito.

Uso:
  pip install safetensors
  python convert_pytorch_bin_to_safetensors.py
"""
import os
import sys


def _pick_state_dict(obj):
    if isinstance(obj, dict):
        if "state_dict" in obj and isinstance(obj["state_dict"], dict):
            return obj["state_dict"]
        if "model" in obj and isinstance(obj["model"], dict):
            return obj["model"]
        return obj
    return None


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    bin_path = os.path.join(root, "pytorch_model.bin")
    out_path = os.path.join(root, "model.safetensors")
    if not os.path.isfile(bin_path):
        print(f"Não encontrado: {bin_path}", file=sys.stderr)
        sys.exit(1)
    if os.path.isfile(out_path):
        print(f"Já existe: {out_path}\nApague ou renomeie se quiser reconverter.", file=sys.stderr)
        sys.exit(1)
    try:
        from safetensors.torch import save_file
    except ImportError:
        print("Instale: pip install safetensors", file=sys.stderr)
        sys.exit(1)
    import torch

    print("Carregando pytorch_model.bin (demora e usa bastante RAM)...")
    try:
        raw = torch.load(bin_path, map_location="cpu", weights_only=True)
    except TypeError:
        raw = torch.load(bin_path, map_location="cpu")

    state = _pick_state_dict(raw)
    if state is None:
        print("Formato do .bin não reconhecido (esperado dict / state_dict).", file=sys.stderr)
        sys.exit(1)

    tensors = {k: v for k, v in state.items() if isinstance(v, torch.Tensor)}
    if not tensors:
        print("Nenhum tensor encontrado no checkpoint.", file=sys.stderr)
        sys.exit(1)

    save_file(tensors, out_path)
    print(f"OK: {out_path}\nAgora: python detector.py")


if __name__ == "__main__":
    main()
