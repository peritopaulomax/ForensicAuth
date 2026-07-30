"""Helpers to capture penultimate-layer embeddings from spoofing detectors."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch


def aggregate_embeddings(window_embeddings: list[np.ndarray]) -> np.ndarray:
    if not window_embeddings:
        raise RuntimeError("Nenhum embedding de janela disponível")
    stacked = np.stack([np.asarray(item, dtype=np.float32).reshape(-1) for item in window_embeddings], axis=0)
    return np.mean(stacked, axis=0).astype(np.float32)


def capture_fc_input(module: Any, inputs: tuple[Any, ...], store: list[np.ndarray]) -> None:
    if inputs and inputs[0] is not None:
        store.append(inputs[0].detach().cpu().numpy()[0].astype(np.float32))


def register_df_arena_embedding_hook(backbone: Any) -> Any:
    store: list[np.ndarray] = []

    def _hook(_module: Any, inputs: tuple[Any, ...], _output: Any) -> None:
        capture_fc_input(_module, inputs, store)

    handle = backbone.conformer.fc5.register_forward_hook(_hook)
    return handle, store


def register_sls_embedding_hook(model: Any) -> Any:
    store: list[np.ndarray] = []

    def _hook(_module: Any, inputs: tuple[Any, ...], _output: Any) -> None:
        capture_fc_input(_module, inputs, store)

    handle = model.fc3.register_forward_hook(_hook)
    return handle, store
