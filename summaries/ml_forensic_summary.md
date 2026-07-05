# ML/Forensic Summary — ForensicAuth

**Atualizado:** 2026-07-04

## Contrato

`ForensicPlugin` em `core/forensic_plugin.py`

## Imagem sintética (GPU)

**Ensemble ativo:** ai-image-detector-deploy, sdxl-flux-detector v1.1, B-Free, Corvi2023 (tiles 1024), SAFE (tiles)

**LR opcional:** `synthetic_lr_reference.py` — bi-Gauss, matriz local em `outputs/lr_calibration/`

**Infra sem ensemble:** DeeCLIP, CLIDE (parcial), DistilDIRE/FakeVLM (STANDBY)

## Spoofing áudio (CPU) — **NOVO**

| Detector | Backend | Pesos |
|---|---|---|
| DF Arena 1B | HF pipeline | `Legados/audio/DF_ARENA_1B/` ou Hub |
| SLS XLS-R | fairseq + SLS | `models/sls_spoofing/` |
| WeDefense | WavLM podado + MHFA | `models/wedefense_asv2025/` |

Paridade com autores em clipes ≤4s; agregação por janelas em áudios longos.

## Outros ML

- PAD (MiniFASNet), SAFIRE, Noiseprint, IMDL-BenCo, VideoFACT, STIL, LFV

## GPU

Lock Redis + `ml_gpu_job_slot`; cache LRU residente; warmup GPU worker (Effort, SAFE, CAMO, IAPL)

## Modelos

~20+ famílias em `models/` (**gitignored**); download via `scripts/download_*.py`

## Reproducibilidade

`REPRODUCIBILITY_REGISTRY`, runtime manifests, perfis strict/gpu_ml/canonical

## Riscos ML

| Risco | Nota |
|---|---|
| Pesos fora do Git | Obrigatório; GitHub max 100MB/2GB LFS |
| torch.load inseguro | ~22 pipelines legados |
| Multi-detector discordância | Spoofing + sintético |
| LR matrix local | Não clonável |
| DeeCLIP não integrado | Dívida |

## Testes ML

Unit: synthetic, safire, audio_plugins, deeclip_runtime, sls paths
Integration: audio_spoofing_multi, deeclip, camo, safe, iapl
