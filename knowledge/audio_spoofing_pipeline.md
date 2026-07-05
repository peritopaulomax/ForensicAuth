# Audio Spoofing Pipeline — ForensicAuth

## Missão
Documentar o hub multi-detector de spoofing de áudio (jul/2026).

## Confiança
**Alta** — evidência direta em código e testes.

## Arquitetura

```text
AudioSpoofingAdapter
  → audio_spoofing/pipeline.py (orquestração)
      → df_arena/infer_df_arena_windows
      → sls_spoofing/infer_sls_windows
      → wedefense_spoofing/infer_wedefense_windows
  → artefatos: detector_scores.txt, plot JSON, details JSON
```

## Detectores

| ID | Modelo | Pesos | Convenção logits | Janela |
|---|---|---|---|---|
| `df_arena_1b` | DF Arena 1B (HF antispoofing) | `Legados/audio/DF_ARENA_1B/` ou Hub | idx0=spoof, idx1=bonafide | 4 s @ 16 kHz, pad 64600 |
| `sls_xlsr` | XLS-R 300M + SLS classifier | `models/sls_spoofing/` | idx0=spoof, idx1=bonafide (log-softmax) | 4 s, pad 64600 |
| `wedefense_wavlm_mhfa` | WavLM Base podado + MHFA | `models/wedefense_asv2025/` | idx0=bonafide, idx1=spoof | 4 s @ 16 kHz |

## Agregação VA Suite

- Janelas deslizantes de 4 s (stride = janela).
- Agregação por **média de logits** → softmax → probabilidades.
- Decisão por detector: spoof/bonafide se prob > **65%**, senão **uncerto**.
- **Diverge** dos autores em áudios longos (autores usam clipe único ~64600 amostras).

## Paridade com autores (jul/2026)

| Detector | Paridade em clipe ≤4 s | Notas |
|---|---|---|
| DF Arena | **Exata** | Mesmo pipeline HF + feature extractor |
| SLS | **Exata** | Mesmo pad/tile e índices |
| WeDefense | **Exata** | Frontend podado + avg_model.pt (sem frontend.*) |

Detectores **discordam entre si** no mesmo áudio — comportamento esperado, não bug de implementação.

## APIs

- `GET /api/v1/analysis/audio-spoofing-detectors` — catálogo + runtime status
- `POST /api/v1/analysis` com `technique: audio_spoofing_detection`, `selected_analyses: [...]`

## Frontend

- Página: `AudioSpoofingAnalysis.tsx`
- Rota: `/cases/:caseId/analysis/audio_spoofing`
- Checkboxes por detector; gráfico por janela via `plot_by_detector`

## Pesos (não versionados no Git)

| Asset | Local | Download |
|---|---|---|
| DF Arena 4.3 GB | `Legados/audio/DF_ARENA_1B/pytorch_model.bin` | HuggingFace `Speech-Arena-2025/DF_Arena_1B_V_1` |
| XLS-R | `models/sls_spoofing/xlsr2_300m.pt` | `scripts/download_sls_spoofing_assets.py` |
| SLS head | `models/sls_spoofing/weights/MMpaper_model.pth` | idem |
| WeDefense | `models/wedefense_asv2025/` | `scripts/download_wedefense_assets.py` |

## Riscos

| Risco | Severidade |
|---|---|
| GitHub rejeita pesos >100 MB / LFS >2 GB | Alto (operacional) |
| Áudio longo: agregação ≠ protocolo original | Médio |
| Limiar 65% gera muitos "incertos" | Médio (UX) |
| SLS exige `chdir` no vendor fairseq | Baixo |
| WeDefense: avg_model.pt vs frontend podado separados | Médio (manutenção) |

## Evidências

- `src/backend/core/legacy/audio_spoofing/`
- `src/backend/core/plugins/audio_spoofing_adapter.py`
- `tests/integration/test_audio_spoofing_multi.py`
- `src/frontend/e2e/audio-spoofing-detectors.spec.ts`
