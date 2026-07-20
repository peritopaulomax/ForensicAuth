# Backend Summary — ForensicAuth

**Atualizado:** 2026-07-08

## Stack

FastAPI + SQLAlchemy + Pydantic + Celery + Redis + PostgreSQL (prod) / SQLite (dev)

## Camadas

| Camada | Path | Papel |
|---|---|---|
| App | `app/main.py`, `config.py`, `celery_app.py` | Bootstrap, settings, workers |
| API | `api/v1/endpoints/` | REST (~15 routers) |
| Services | `services/` | Domínio (jobs, custody, evidence, derivative, GPU queue) |
| Core | `core/` | Plugins, ML pipelines, reproducibility, GPU |
| Plugins | `core/plugins/` | ~35 adapters ativos |
| Legacy | `core/legacy/` | Algoritmos forenses + runtime |
| Tasks | `tasks/analysis_tasks.py` | Celery CPU/GPU |

## Técnicas canônicas (`technique_ids.py`)

- `synthetic_image_detection` (alias `sepael`)
- `presentation_attack_detection`
- `audio_spoofing_detection`

## Jobs

```text
POST /analysis → JobService → JobRunner
  → Celery (Postgres) ou thread (SQLite)
  → queue: gpu | celery
```

GPU: synthetic, safire, noiseprint, imdlbenco, videofact, stil, lfv, pad

CPU: clássicas, PDF, áudio espectral, **audio_spoofing_detection**

## Novidades jul/2026

| Módulo | Função |
|---|---|
| `audio_spoofing/` | Orquestra DF Arena, SLS, WeDefense |
| `audio_spoofing_lr_reference.py` | LR calibrado multi-detector para áudio (população de referência, meta-classificador, bi-Gaussiana, splits train/calib/test) |
| `latent_typicality/` | Tipicidade latente k-NN sobre embeddings dos detectores de áudio (sistemas A/B/C/D) |
| `synthetic_lr_reference.py` | LR calibrado multi-detector imagem |
| `deeclip/` | Pipeline DeeCLIP (infra; não no ensemble) |
| `wedefense_spoofing/`, `sls_spoofing/` | Detectores áudio |

## APIs novas

- `GET /analysis/audio-spoofing-detectors`
- `GET /analysis/audio-spoofing-reference-catalog` — catálogo hierárquico de populações de referência (macro-categorias, bases, geradores, EERs por detector)
- `GET /analysis/synthetic-reference-catalog`

## Calibração LR de spoofing de áudio

`core/audio_spoofing_lr_reference.py` implementa LR de referência para os três detectores ativos:

- `df_arena_1b` — DF Arena 1B
- `sls_xlsr` — SLS XLS-R
- `wedefense_wavlm_mhfa` — WeDefense WavLM + MHFA

LR positiva favorece `H1 = bonafide` (autêntico). O pipeline:

1. Amostra 500 amostras/classe de cada subgrupo selecionado.
2. Divide em `train_logreg` (250), `calibration_bigauss` (125) e `test_bigauss` (125).
3. Treina meta-classificador sobre logits bonafide (`_bonafide_logit`) reutilizando `META_CLASSIFIERS` de `synthetic_lr_reference.py`.
4. Calibra bi-Gaussiana (variante EER) no split de calibração.
5. Reporta CLLR, minCLLR, EER, AUC no split de teste.

Seleção de referência suporta `fit_items` / `test_items` separados, itens explícitos, seleção por macro-categoria (`macro:<id>`) ou por dataset/generator. Catálogo hierárquico cobre `asv_classic`, `codec_conditions`, `deepfake_challenges` e `in_the_wild`. A população padrão `DEFAULT_VOICE_CLONE_REFERENCE` tem 7 subgrupos (DFADD, SONAR, ASVspoof5, In-The-Wild).

## Tipicidade latente

`core/latent_typicality/` enriquece a calibração LR com features k-NN sobre embeddings dos detectores:

| Arquivo | Papel |
|---|---|
| `config.py` | Defaults: sistema D, distância cosine, k=5, eps=1e-8 |
| `typicality.py` | `TypicalityReference`, k-NN real/spoof, CDF empírica dos raios |
| `features.py` | Builders dos sistemas A/B/C/D e colunas de features |
| `representations_utils.py` | `sample_id`, I/O de embeddings, disponibilidade da matriz |

Features geradas por detector: `T_R_*` (tipicidade real), `T_S_*` (tipicidade spoof), `OOD_*` (out-of-distribution), `Delta_r_*`, `rho_*`, `r_R_*`, `r_S_*`. Sistema D concatena score `S_*` + todas as features de tipicidade. Treino dos k-NN usa apenas o split `train_logreg` para evitar leak.

## População de referência aumentada

Aumentações forenses aplicáveis à calibração LR (`scripts/audio_lr_augmentation.py`):

- `mp3_128k` — recompressão MP3 128 kbps
- `opus_32k` — Opus 32 kbps (proxy de mensageiro/voz)
- `noise_snr_20` — ruído pink a 20 dB SNR
- `noise_snr_15` — ruído pink a 15 dB SNR

Quando ativada, o multiplicador é 5× (original + 4 augmentações). A matriz de referência aumentada reside em `outputs/lr_calibration/audio_spoofing/representations/representations.csv` (scores + embeddings). Scripts auxiliares:

- `audio_lr_dataset_utils.py` — amostragem balanceada, splits, manifestos
- `audio_lr_disk_verify.py` — auditoria de WAVs, embeddings e scores no disco
- `audio_lr_completion_gate.py` — gate de integridade da matriz e das representações

## Artefatos LR

`compute_reference_lr` e o adapter `AudioSpoofingAdapter` geram no diretório do job:

- `lr_reference_report.json` — métricas, subgrupos, config, LR da evidência
- `lr_reference_summary.txt` — relatório textual
- `lr_reference_model.joblib` — modelo + calibração serializados
- `lr_reference_test_scored.csv` — split de teste com LRs
- `lr_reference_tippett.png` — Tippett plot
- `lr_reference_distribution.png` — distribuição das LRs
- `lr_reference_identity.png` — função identidade

Cache SHA-256 em `outputs/lr_calibration/cache/` (arquivos `.joblib`); repetições de mesma seleção reusam modelo.

## Frontend

`src/frontend/src/pages/AudioSpoofingAnalysis.tsx` consome:

- `GET /analysis/audio-spoofing-detectors` — catálogo com disponibilidade
- `GET /analysis/audio-spoofing-reference-catalog` — populações de referência e EERs

Controles adicionados:

- Seletor de população de referência com papéis separados (treino/calibração vs. teste)
- Seletor de meta-classificador
- Checkbox "Usar população de referência aumentada"
- Checkbox "Tipicidade latente (k-NN)" — usa sistema D
- Painel `ReferenceLrPanel` exibindo log10(LR), LR, métricas e botões para salvar artefatos LR na cadeia de custódia

## Config crítica

`DATABASE_URL`, `REDIS_URL`, `FORENSICAUTH_PROCESS_ROLE`, `MODELS_DIR`, `GPU_*`, `DF_ARENA_MODEL`

## Testes

~487 unit + ~55 integration + 14 e2e backend (`tests/`)

## Riscos backend

GPU lock, torch.load inseguro, pesos locais, audio spoofing na fila CPU sob carga; calibração LR com tipicidade latente pode levar vários minutos na primeira execução de uma nova seleção.
