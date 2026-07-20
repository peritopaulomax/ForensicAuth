# System Brain — ForensicAuth

**Atualizado:** 2026-07-13

## Arquitetura em 60 Segundos

```text
Perito/Admin → React SPA → FastAPI → Services → PostgreSQL/Redis/FS
                                    ↓
                           Celery Workers → Plugins → Legacy/Vendor/Models
```

## Componentes Críticos

| Componente | Tier | Função |
|---|---|---|
| FastAPI App | 0 | API, lifespan, routers |
| PostgreSQL | 0 | Estado e cadeia de custódia |
| Redis | 0 | Fila Celery, backend, lock GPU |
| Filesystem | 0 | uploads, results, derivatives, models (local) |
| CustodyService | 0 | Cadeia SHA-256 + Ed25519 |
| JobService | 0 | Jobs e reproducibilidade |
| PluginRegistry | 1 | ~35+ adapters ativos (incl. `moe_ffd`) |
| GPUInference | 1 | Filas CPU/GPU, serialização |
| synthetic_lr_reference | 1 | Meta-LR calibrado (imagens sintéticas) |
| audio_spoofing_lr_reference | 1 | Meta-LR calibrado (spoofing de áudio, 3 detectores) |
| latent_typicality | 1 | Features k-NN sobre embeddings dos detectores de áudio |
| audio_spoofing pipeline | 1 | Hub DF Arena + SLS + WeDefense |
| moe_ffd pipeline | 1 | Hub facial: MoE-FFD (exige best.pkl; HF tar mid-training rejeitado) + PAD |
| React SPA | 1 | Hubs image-group (`dl-facial-spoofing`), áudio, PDF, vídeo |
| LrReferencePanels | 1 | Seletor de população de referência + painel LR (imagem + áudio) |

## Fluxos Críticos

1. **Upload** → SHA-256 → `Evidence` + `CustodyRecord`
2. **Análise imagem sintética** → ensemble GPU → scores + LR opcional
3. **Análise spoofing áudio** → 3 detectores CPU → scores independentes
4. **Calibração LR áudio** → detectores retornam logits (e embeddings se tipicidade) → amostra da população de referência (train/calib/test) → meta-classificador → bi-Gaussiana EER → LR + Tippett + distribuição + identidade
5. **Derivado** → `Evidence` derivada + provenance + `CustodyRecord`
6. **Verificação forense** → cadeia + arquivos + assinaturas
7. **Login** → JWT HS256

## Dependências Críticas

PostgreSQL 15, Redis 7, PyTorch/CUDA 12.4, filesystem local, jpegio, PyMuPDF, librosa, fairseq (SLS), transformers (DF Arena), scikit-learn, XGBoost, joblib.

## Dados Críticos

| Dado | Onde | Risco |
|---|---|---|
| CustodyRecord | PostgreSQL | Imutabilidade PG pendente |
| Evidence | PostgreSQL + FS | Perda de FS = perda de evidência |
| Modelos | `models/` (gitignored) | ~43+ GB, download manual |
| LR reference matrix (imagem) | `outputs/` (gitignored) | Não clonável sem recompute |
| LR score matrix áudio | `outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv` | Não clonável |
| LR score matrix áudio aumentada | `outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full_augmented.csv` | Requer pipeline offline de augmentação |
| Representações LR áudio | `outputs/lr_calibration/audio_spoofing/representations/representations.csv` | Necessária para tipicidade latente; contém scores + embeddings |
| Cache LR calibrado | `outputs/lr_calibration/cache/*.joblib` | Pode ser grande (modelo + typicality refs) |
| AnalysisJob | PostgreSQL | Não gera custódia |

## Top 10 Riscos (jul/2026)

1. Commit acidental de pesos/outputs (>100 MB / >2 GB LFS)
2. GPU singleton / lock distribuído
3. `torch.load(weights_only=False)` em pipelines legados
4. PostgreSQL único
5. Credenciais padrão docker-compose
6. Modelos não versionados com checksum
7. Imutabilidade cadeia (trigger SQLite vs PG)
8. JWT em localStorage
9. Discordância entre detectores ML (não é bug)
10. Observabilidade ausente

## Top 10 Dívidas (jul/2026)

1. Laudos PDF não implementados
2. Testes regressão forense / golden parity
3. DeeCLIP fora do ensemble sintético
4. Modo "compatível autores" para spoofing áudio
5. Frontend páginas grandes + rotas legadas
6. Observabilidade ausente
7. Submódulos vendor com LFS frágil
8. Cobertura frontend baixa
9. Migrations ad-hoc + Alembic
10. Validações domínio (caso fechado, media type)

## Calibração LR de Spoofing de Áudio

Mirror de `synthetic_lr_reference.py` para os três detectores ativos de spoofing de áudio:

- **Detectores:** DF Arena 1B, SLS XLS-R, WeDefense WavLM + MHFA.
- **Features base:** `bonafide_logit` de cada detector selecionado.
- **Hipótese positiva (LR > 1):** H1 = bonafide/autêntico.
- **População de referência:** subgrupos selecionáveis `(base_group, subgroup)` cobrindo ASVspoof 2019/2021/5, CodecFake, ADD 2022/2023, DFADD, SONAR, In-The-Wild, Fake-or-Real e LibriSeVoc.
- **Default voice-clone:** DFADD (StyleTTS2, NaturalSpeech2), SONAR (xTTS, PromptTTS2, VoiceBox), ASVspoof5 flac_E_eval, In-The-Wild.
- **Splits por subgrupo/classe:** train_logreg 250, calibration_bigauss 125, test_bigauss 125 (`SAMPLE_PER_CLASS=500`).
- **Meta-classificadores:** logistic (default), logistic_poly2, xgboost, gradient_boosting, random_forest, extra_trees, svm_rbf, mlp, kde_naive_bayes.
- **Calibração:** bi-Gaussiana EER-based (computa `mu_fake`, `mu_real`, `sigma` no split de calibração).
- **Cache:** chave SHA-256 canônica em `outputs/lr_calibration/cache/*.joblib`; reutiliza modelo + typicality refs quando disponível.
- **Artefatos de job:** `lr_reference_report.json`, `lr_reference_summary.txt`, `lr_reference_model.joblib`, `lr_reference_test_scored.csv`, `lr_reference_tippett.png`, `lr_reference_distribution.png`, `lr_reference_identity.png`.

## Tipicidade Latente

Implementação em `core/latent_typicality/`:

- **Sistemas A/B/C/D:**
  - A: logits dos detectores (`S_*`).
  - B: + typicalidades real e spoof (`T_R_*`, `T_S_*`).
  - C: + out-of-distribution (`OOD_*`).
  - D: + diferenças de raio e log-ratio (`Delta_r_*`, `rho_*`).
- **Default:** sistema D, distância cosine, k=5 (`DEFAULT_SYSTEM`, `DEFAULT_DISTANCE`, `DEFAULT_K`).
- **Features por detector:**
  - `S_detector` — logit bonafide.
  - `T_R_detector` — typicalidade da classe real (1 − CDF do k-ésimo vizinho real).
  - `T_S_detector` — typicalidade da classe spoof.
  - `OOD_detector` — `1 − max(T_R, T_S)`.
  - `Delta_r_detector` — `r_real − r_spoof`.
  - `rho_detector` — `log(r_real / r_spoof)`.
- **Anti-leak:** bancos k-NN (`sklearn.neighbors.NearestNeighbors`) são fit apenas no split `train_logreg`; materialização das features é feita em batches (tamanho controlado por `VA_LR_TYPICALITY_BATCH`) com paralelismo controlado por `VA_LR_TYPICALITY_JOBS`.
- **Pré-requisito:** `representations.csv` com colunas `{detector}_embedding_path` para os 3 detectores; linhas sem os 3 embeddings no disco são descartadas.

## População de Referência Aumentada

Conjunto de augmentações forenses para aumentar a robustez da calibração LR:

- **Augmentações:** `mp3_128k`, `opus_32k`, `noise_snr_20`, `noise_snr_15`.
- **Multiplicador:** 5× (original + 4 augmentações).
- **Pipeline offline:** scripts `audio_lr_augmentation.py`, `audio_lr_dataset_utils.py`, `audio_lr_disk_verify.py`, `audio_lr_completion_gate.py`.
- **Gate de completude:** verifica WAV + embeddings 3/3 + scores por gerador; alvo 500/classe originais + 500×4 aumentadas.
- **Ativação:** parâmetro `use_augmented_reference` no adapter/frontend. Com tipicidade latente usa `representations.csv`; sem tipicidade exige o score matrix aumentado.

## Endpoint e Frontend

- **Novo endpoint:** `GET /analysis/audio-spoofing-reference-catalog` retorna categorias macro, EER por detector e `default_reference_items`.
- **AudioSpoofingAnalysis.tsx:**
  - Seleção multipla dos 3 detectores.
  - Seletor de população de referência com roles separáveis `fit` (treino+calib, splits 1–2) e `test` (split 3).
  - Escolha de meta-classificador.
  - Checkbox "Usar população de referência aumentada".
  - Checkbox "Tipicidade latente (k-NN)".
  - Renderização dos gráficos Tippett, distribuição e identidade via `ReferenceLrPanel`.
- **Componentes compartilhados:** `ReferencePopulationSelector`, `ReferenceLrPanel`, `MetaClassifierSelect` em `LrReferencePanels.tsx` (usados também pela análise de imagem sintética).

## Decisões Chave

- Monólito modular; plugins preservam legados forenses.
- Pesos e experimentos **fora do Git** (scripts download + `.gitignore`).
- Jobs = previews; custódia em upload/derivado/fechamento.
- Multi-detector sem meta-fusão ainda (spoofing e sintético parcial).
- Calibração LR de áudio replica o padrão da imagem sintética, estendido com tipicidade latente e população aumentada.

## Roadmap Imediato

1. Push limpo (só código) — `.gitignore` reforçado
2. Golden parity áudio (ASVspoof)
3. Integrar DeeCLIP ou marcar experimental
4. Laudos PDF
5. Observabilidade + checksums de modelos
