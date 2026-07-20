# Audio Spoofing Pipeline — ForensicAuth

## Missão

Documentar o hub multi-detector de spoofing de áudio e a calibração LR baseada em população de referência (jul/2026).

## Confiança

**Alta** — evidência direta em código e testes.

## Arquitetura

```text
AudioSpoofingAdapter
  → audio_spoofing/pipeline.py (orquestração)
      → df_arena/infer_df_arena_windows
      → sls_spoofing/infer_sls_windows
      → wedefense_spoofing/infer_wedefense_windows
  → audio_spoofing_lr_reference.py (calibração LR por população de referência)
      → meta-classificador → calibração bi-Gaussiana (EER)
      → latent_typicality/ (k-NN sobre embeddings, sistema D)
  → artefatos: detector_scores.txt, plot JSON, details JSON, relatório LR, plots Tippett/distribuição/identidade
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
- Quando `use_latent_typicality=true`, o pipeline retorna também os **embeddings** dos detectores para alimentar a tipicidade latente.

## Paridade com autores (jul/2026)

| Detector | Paridade em clipe ≤4 s | Notas |
|---|---|---|
| DF Arena | **Exata** | Mesmo pipeline HF + feature extractor |
| SLS | **Exata** | Mesmo pad/tile e índices |
| WeDefense | **Exata** | Frontend podado + avg_model.pt (sem frontend.*) |

Detectores **discordam entre si** no mesmo áudio — comportamento esperado, não bug de implementação.

## Calibração LR de spoofing de áudio

A calibração é implementada em `core.audio_spoofing_lr_reference.compute_reference_lr`, espelhando `synthetic_lr_reference.py` para os três detectores ativos.

| Aspecto | Valor/Comportamento |
|---|---|
| Hipótese positiva (H1) | `bonafide_authentic` (LR > 1 favorece áudio autêntico) |
| Hipótese negativa (H0) | `spoof_synthetic` |
| Features base | Logit bonafide de cada detector (`{detector}_bonafide_logit`) |
| Features tipicidade | Sistema D: `S_*`, `T_R_*`, `T_S_*`, `OOD_*`, `Delta_r_*`, `rho_*` |
| Meta-classificadores | `logistic` (default), `logistic_poly2`, `xgboost`, `gradient_boosting`, `random_forest`, `extra_trees`, `svm_rbf`, `mlp`, `kde_naive_bayes` |
| Splits | `train_logreg` (250/classe/subgrupo) → `calibration_bigauss` (125/classe) → `test_bigauss` (125/classe) |
| Calibração | Bi-Gaussiana ajustada no EER: `mu_real`, `mu_fake`, `sigma`, `eer` |
| Amostragem | 500 amostras por classe por subgrupo; semente padrão `20260704`; amostragem estratificada por augmentação quando disponível |
| Cache | SHA-256 do experimento → `.joblib` em `outputs/lr_calibration/cache/`; reutiliza modelo, calibração e scored test |

### População de referência

- Catálogo hierárquico definido em `audio_spoofing_lr_reference.py`:
  - `asv_classic`: ASVspoof 2019 LA, ASVspoof 2021 LA eval, ASVspoof 5
  - `codec_conditions`: CodecFake C1–C7
  - `deepfake_challenges`: ADD2022, ADD2023, DFADD, SONAR
  - `in_the_wild`: In-The-Wild, Fake-or-Real, LibriSeVoc
- População default (`DEFAULT_VOICE_CLONE_REFERENCE`): clonagem comercial + ASVspoof 5 + In-The-Wild.
- Seleção suporta:
  - itens individuais (`base_group/subgroup`)
  - macros (`macro:<id>`)
  - grupos inteiros (todos os geradores de uma base)
  - splits separados: `fit_items` (treino+calibração) e `test_items` (métricas held-out)

### População de referência aumentada

- Ativada via `use_augmented_reference=true` ou `sample_multiplier > 1`.
- Augmentações aplicadas off-line: `mp3_128k`, `opus_32k`, `noise_snr_20`, `noise_snr_15`.
- Multiplicador padrão: `1 + len(AUGMENTATION_NAMES) = 5`.
- Requer matriz de representações (`representations.csv`) ou score matrix aumentado (`lr_scores_balanced_full_augmented.csv`).
- Implementação forense em `scripts/audio_lr_augmentation.py`: MP3 via `libmp3lame`, Opus via `libopus`, ruído pink com semente estável por amostra.

## Tipicidade latente

Implementada em `core.latent_typicality/`.

| Aspecto | Valor |
|---|---|
| Sistema default | `D` |
| Métrica de distância | `cosine` |
| `k` | 5 |
| `eps` | 1e-8 |

### Bancos k-NN

- Um `TypicalityReference` por detector, construído apenas no split `train_logreg` para evitar leak.
- Dois bancos: embeddings `real` (bonafide) e `synthetic` (spoof).
- Raio de referência = distância do k-ésimo vizinho mais próximo dentro de cada classe.

### Features por detector

| Feature | Descrição |
|---|---|
| `S_<det>` | Logit bonafide bruto do detector |
| `T_R_<det>` | Tipicidade no banco real: `1 − CDF(r_real)` |
| `T_S_<det>` | Tipicidade no banco spoof: `1 − CDF(r_spoof)` |
| `OOD_<det>` | Out-of-distribution: `1 − max(T_R, T_S)` |
| `Delta_r_<det>` | Diferença de raios: `r_real − r_spoof` |
| `rho_<det>` | Razão logarítmica de raios |

### Sistemas A/B/C/D

| Sistema | Features |
|---|---|
| A | `S_*` |
| B | `S_*`, `T_R_*`, `T_S_*` |
| C | `S_*`, `T_R_*`, `T_S_*`, `OOD_*` |
| D | `S_*`, `T_R_*`, `T_S_*`, `OOD_*`, `Delta_r_*`, `rho_*` |

### Performance e memória

- Carregamento de embeddings em batches controlados por `VA_LR_TYPICALITY_BATCH` (default 512) para evitar OOM.
- Paralelismo controlado por `VA_LR_TYPICALITY_JOBS` (default 8, cap 12).
- Exclude-self aplicado apenas às linhas do split de treino.

## APIs

- `GET /api/v1/analysis/audio-spoofing-detectors` — catálogo + runtime status dos detectores
- `GET /api/v1/analysis/audio-spoofing-reference-catalog` — catálogo hierárquico de população de referência + EER por detector + população default
- `POST /api/v1/analysis` com `technique: audio_spoofing_detection`, `selected_analyses: [...]`

Parâmetros de análise suportados:

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `selected_analyses` | `list[str]` | Detectores a executar |
| `reference_lr_enabled` | `bool` | Ativa calibração LR |
| `reference_population` | `dict` | Seleção de população (`fit_items`/`test_items` ou itens legados) |
| `meta_classifier` | `str` | `logistic` (default), `logistic_poly2`, `xgboost`, `gradient_boosting`, `random_forest`, `extra_trees`, `svm_rbf`, `mlp`, `kde_naive_bayes` |
| `use_augmented_reference` | `bool` | Usa população aumentada (MP3/Opus/ruído) |
| `use_latent_typicality` | `bool` | Usa sistema D de tipicidade latente |
| `window_seconds` | `float` | 1–60 s (default 4 s) |
| `max_duration_seconds` | `float` | 10–300 s (default 90 s) |

## Frontend

- Página: `AudioSpoofingAnalysis.tsx`
- Rota: `/cases/:caseId/analysis/audio_spoofing`
- Checkboxes por detector; gráfico temporal por janela via `plot_by_detector`.
- Painel de população de referência (`ReferencePopulationSelector`):
  - seleção hierárquica por macro-categoria/base/subgrupo
  - split de papéis `fit`/`test`
  - exibe EER por detector quando disponível
- Seletor de meta-classificador (`MetaClassifierSelect`).
- Controles:
  - **Usar população de referência aumentada** (MP3 128 kbps, Opus 32 kbps, ruído 20/15 dB SNR)
  - **Tipicidade latente (k-NN)** — sistema D, cosine, k=5
- Resultado LR exibido via `ReferenceLrPanel` com log10(LR), LR, CLLR, minCLLR, EER, AUC, pesos dos detectores.
- Botões para salvar derivados: escores TXT, plot JSON, details JSON, resumo LR TXT, relatório LR JSON, Tippett plot, distribuição LR, função identidade.

## Novos artefatos (LR + tipicidade)

| Artefato | Arquivo | Conteúdo |
|---|---|---|
| Relatório LR JSON | `lr_reference_report.json` | Métricas de teste, população selecionada, LR questionada, pesos, configuração de tipicidade |
| Resumo LR TXT | `lr_reference_summary.txt` | Texto legível com LR, CLLR, EER, população, pesos |
| Tippett plot | `lr_reference_tippett.png` | Plot Tippett da população de referência |
| Distribuição LR | `lr_reference_distribution.png` | Histograma/densidade com posição da evidência questionada |
| Função identidade | `lr_reference_identity.png` | Calibração empírica vs. teórica (com MSE) |
| Modelo serializado | `lr_reference_model.joblib` | Modelo, feature cols, calibração, detectores selecionados |
| Teste scored CSV | `lr_reference_test_scored.csv` | Linhas do split `test_bigauss` com scores e LRs |

## Scripts de preparação de dados

| Script | Função |
|---|---|
| `scripts/audio_lr_augmentation.py` | Gera variações MP3/Opus/ruído com sementes estáveis |
| `scripts/audio_lr_dataset_utils.py` | Helpers de configuração, pools de bonafide/spoof, splits, manifestos |
| `scripts/audio_lr_disk_verify.py` | Auditoria de completude de WAVs, embeddings e scores no disco |
| `scripts/audio_lr_completion_gate.py` | Gate de conclusão: verifica matriz limpa, representations sem NaN/orfãos e progresso por gerador |

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
| Calibração LR: dependência de score matrix e representations gerados off-line | Médio (operação) |
| Tipicidade latente: alto custo de memória/CPU na primeira calibração | Médio (infra) |
| População aumentada: 5× amostras → tempos de calibração maiores | Baixo/Médio |

## Evidências

- `src/backend/core/legacy/audio_spoofing/`
- `src/backend/core/plugins/audio_spoofing_adapter.py`
- `src/backend/core/audio_spoofing_lr_reference.py`
- `src/backend/core/latent_typicality/`
- `src/backend/api/v1/endpoints/analysis.py`
- `src/frontend/src/pages/AudioSpoofingAnalysis.tsx`
- `scripts/audio_lr_*.py`
- `tests/integration/test_audio_spoofing_multi.py`
- `src/frontend/e2e/audio-spoofing-detectors.spec.ts`
