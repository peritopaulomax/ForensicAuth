# ML/Forensic Summary — ForensicAuth

**Atualizado:** 2026-07-08

## Contrato

`ForensicPlugin` em `core/forensic_plugin.py`

## Imagem sintética (GPU)

**Ensemble ativo:** ai-image-detector-deploy, sdxl-flux-detector v1.1, B-Free, Corvi2023 (tiles 1024), SAFE (tiles)

**LR opcional:** `synthetic_lr_reference.py` — bi-Gauss, matriz local em `outputs/lr_calibration/`

**Infra sem ensemble:** DeeCLIP, CLIDE (parcial), DistilDIRE/FakeVLM (STANDBY)

## Spoofing áudio (CPU)

| Detector | Backend | Pesos |
|---|---|---|
| DF Arena 1B | HF pipeline | `Legados/audio/DF_ARENA_1B/` ou Hub |
| SLS XLS-R | fairseq + SLS | `models/sls_spoofing/` |
| WeDefense | WavLM podado + MHFA | `models/wedefense_asv2025/` |

Paridade com autores em clipes ≤4s; agregação por janelas em áudios longos.

### Calibração LR de referência

Implementada em `core/audio_spoofing_lr_reference.py` (espelha `synthetic_lr_reference.py`):

- **Hipóteses:** LR > 1 favorece H1 = bonafide/autêntico; LR < 1 favorece H0 = spoof/sintético.
- **População de referência:** seleção de subgrupos `base_group/generator` (datasets: ASVspoof 2019/2021/5, CodecFake, ADD 2022/23, DFADD, SONAR, In-The-Wild, Fake-or-Real, LibriSeVoc).
- **Split:** treino 250 / calibração bi-Gaussiana 125 / teste 125 amostras por classe por subgrupo.
- **Meta-classificador:** `logistic` (default), compartilhado com `synthetic_lr_reference.py`; gera z-score usado na calibração.
- **Calibração:** bi-Gaussiana variant EER (`mu_real`, `mu_fake`, `sigma`, `eer`).
- **Cache:** modelo + calibração + scored teste em `.joblib` sob `outputs/lr_calibration/cache/`.

### Tipicidade latente

Módulo `core/latent_typicality/` (sistema D default):

- **k-NN:** `k=5`, distância `cosine`, sobre embeddings dos três detectores.
- **Features por detector:**
  - `S_*`: logit bonafide bruto;
  - `T_R_*`, `T_S_*`: typicalidade real vs. sintética (1 − CDF do raio k-ésimo);
  - `OOD_*`: out-of-distribution (`1 − max(T_R, T_S)`);
  - `Delta_r_*`: diferença de raios (`r_R − r_S`);
  - `rho_*`: log-ratio dos raios.
- **Sistemas A/B/C/D:** A apenas logits; B + T_R/T_S; C + OOD; D + Delta_r/rho.
- **Anti-leak:** bancos k-NN construídos apenas no split `train_logreg`; materialização em lotes (`VA_LR_TYPICALITY_BATCH=512`) e paralela (`VA_LR_TYPICALITY_JOBS`).
- **Matriz de representações:** `outputs/lr_calibration/audio_spoofing/representations/representations.csv` com scores + caminhos para embeddings `.npy`.

### População de referência aumentada

Augmentações forenses controladas (`scripts/audio_lr_augmentation.py`):

- `mp3_128k` — recompressão MP3 LAME 128 kbps;
- `opus_32k` — Opus 32 kbps modo voip;
- `noise_snr_20` — ruído pink a 20 dB SNR;
- `noise_snr_15` — ruído pink a 15 dB SNR.

Usadas para expandir a referência quando `use_augmented_reference=true`; exigem score matrix aumentado ou matriz de representações completa.

### Endpoint e catálogo

- `GET /analysis/audio-spoofing-reference-catalog` — retorna macro-categorias (`asv_classic`, `codec_conditions`, `deepfake_challenges`, `in_the_wild`), bases, geradores e EER por detector.
- `GET /analysis/audio-spoofing-detectors` — catálogo dos detectores com disponibilidade runtime.

### Artefatos LR

Gerados no diretório do job:

- `lr_reference_report.json` — métricas (CLLR, minCLLR, EER, AUC), pesos, LR questionada;
- `lr_reference_summary.txt` — relatório textual;
- `lr_reference_tippett.png`;
- `lr_reference_distribution.png`;
- `lr_reference_identity.png`;
- `lr_reference_model.joblib`;
- `lr_reference_test_scored.csv`.

### Frontend

`src/frontend/src/pages/AudioSpoofingAnalysis.tsx`:

- Seleção de detectores com catálogo e indisponibilidade;
- Seletor de população de referência com splits treino/calibração vs. teste (`enableSplitRoles`);
- Controles: meta-classificador, população aumentada, tipicidade latente (k-NN);
- Painel `ReferenceLrPanel` com Tippett, distribuição, identidade e salvamento de derivados na cadeia de custodia.

### Scripts de pipeline

- `scripts/audio_lr_augmentation.py` — gera variações aumentadas;
- `scripts/audio_lr_disk_verify.py` — verifica completude de WAV, embeddings 3/3 e scores no disco;
- `scripts/audio_lr_completion_gate.py` — gate de integridade da matriz e das representações (zero NaN, zero duplicatas, zero grupos órfãos).

## Outros ML

- PAD (MiniFASNet), MoE-FFD (ViT-MoE face forgery), SAFIRE, Noiseprint, IMDL-BenCo, VideoFACT, STIL, LFV

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
| Matriz de representações típicas | Grande e gerada offline; sem ela tipicidade latente fica indisponível |

## Testes ML

Unit: synthetic, safire, audio_plugins, deeclip_runtime, sls paths
Integration: audio_spoofing_multi, deeclip, camo, safe, iapl
