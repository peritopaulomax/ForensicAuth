# Feature Catalog — ForensicAuth

## Missão
Inventariar capacidades do sistema ForensicAuth.

## Tabela Principal

| Feature | Objetivo | Usuários | Componentes | APIs | Criticidade | Status |
|---|---|---|---|---|---|---|
| Autenticação JWT | Login seguro com controle de acesso | Todos | AuthService, auth endpoints, Zustand | `/auth/*` | Crítica | Ativa |
| Gestão de Usuários | CRUD de usuários e perfis | Admin | UserService, users endpoints | `/users/*` | Alta | Ativa |
| Gestão de Casos | Criar, editar, fechar e reabrir casos forenses | Perito, Admin | CaseLifecycleService, cases endpoints | `/cases/*` | Crítica | Ativa |
| Upload de Evidências | Receber arquivos com SHA-256 e tipo | Perito | EvidenceService, evidences endpoints | `/evidences/upload` | Crítica | Ativa |
| Download de Evidências | Recuperar arquivo original | Perito, Analista | EvidenceService | `/evidences/{id}/download` | Alta | Ativa |
| Cadeia de Custódia | Registrar e verificar integridade de evidências e jobs | Perito, Admin | CustodyService, CustodySigningService | `/audit/*` | Crítica | Ativa |
| Análise de Imagem | Aplicar técnicas forenses em imagens (CPU + GPU/ML), incl. PAD e MoE-FFD no hub facial | Perito, Admin | Plugins de imagem, JobService | `/analysis/*` | Crítica | Ativa |
| Análise de Áudio | Aplicar técnicas forenses em áudio, incluindo LR calibrado e tipicidade latente | Perito | Plugins de áudio, `AudioSpoofingAdapter` | `/analysis/*` | Alta | Ativa |
| Análise de Vídeo | Aplicar técnicas forenses em vídeo | Perito | Plugins de vídeo | `/analysis/*` | Alta | Ativa |
| Análise de PDF | Aplicar técnicas forenses em PDF | Perito | Plugins de PDF | `/analysis/*` | Alta | Ativa |
| Jobs Assíncronos | Enfileirar e executar análises pesadas | Sistema | Celery, Redis, JobRunner | `/analysis/*` | Crítica | Ativa |
| Reprodutibilidade | Reexecutar jobs e comparar resultados | Perito | Reproducibility, JobService | `/analysis/{id}/reproduce` | Alta | Ativa |
| Derivados | Promover artefatos a novas evidências | Perito | DerivativeService | `/evidences/derivatives` | Alta | Ativa |
| Laudos / Relatórios | Gerar PDF oficial com resultados | Perito | ReportService (modelo apenas) | `/reports/*` (não implementado) | Alta | Planejada |
| Compartilhamento de Casos | Viewer/editor de casos | Perito | CaseShareService | `/cases/{id}/shares` | Média | Ativa |
| Transferência VCP | Exportar/importar pacotes forenses | Perito | CaseTransferService | `/case-transfer/*` | Média | Ativa |
| Bridge Peritus | Integração com Peritus Desktop | Perito | PeritusBridgeService | `/peritus-transfer/*` | Média | Ativa |
| PRNU por Caso | Gerenciar fingerprints de câmera | Perito | PRNUFingerprintService | `/prnu/*` | Média | Ativa |
| Referências Técnicas | Catálogo de artigos técnicos | Todos | ReferencesService | `/references/*` | Baixa | Ativa |
| Verificação Forense | Verificar cadeia + arquivos + assinaturas | Perito, Admin | ForensicIntegrityService | `/audit/verify-case-forensic/*` | Crítica | Ativa |
| Dashboard | Visão geral de técnicas disponíveis | Perito, Admin | Frontend | `/dashboard` | Média | Ativa |
| Calibração LR de Spoofing de Áudio | Calibrar likelihood ratio sobre população de referência multi-detector | Perito | `audio_spoofing_lr_reference.py`, `AudioSpoofingAdapter` | `/analysis/audio-spoofing-reference-catalog`, `/analysis` | Alta | Ativa |
| Tipicidade Latente (k-NN) | Enriquecer LR com features de vizinhança em embeddings dos detectores | Perito | `core/latent_typicality/` | `/analysis` | Média | Experimental |
| População de Referência Aumentada de Áudio | Ampliar calibração LR com variantes de codec/ruído | Sistema | `scripts/audio_lr_*.py`, `audio_lr_augmentation.py` | — | Alta | Ativa |

## Classificação

### Core Features
- Autenticação e autorização
- Gestão de casos e evidências
- Cadeia de custódia
- Análise forense (imagem, áudio, vídeo, PDF)
- Jobs assíncronos
- Reprodutibilidade
- Verificação forense

### Supporting Features
- Compartilhamento de casos
- Transferência VCP
- Bridge Peritus
- PRNU por caso
- Referências técnicas
- Derivados
- Calibração LR de spoofing de áudio
- População de referência aumentada de áudio

### Administrative Features
- Gestão de usuários
- Auditoria
- Diagnóstico GPU

### Experimental Features
- Métodos IMDL-BenCo `ecosystem` (visíveis na UI, mas requerem pesos/pipelines adicionais)
- `deepfake_similarity` (adapter placeholder sem inferência real)
- Tipicidade latente (`latent_typicality`) — sistema D, k-NN, embeddings de detectores de áudio

## Feature: Análise de Imagem

- Objetivo: Detectar adulterações em imagens
- Usuários: Perito
- Fluxo Principal: selecionar evidência → escolher técnica → ajustar parâmetros → submeter job → visualizar resultado
- Componentes: `ImageAnalysisGroupPage`, plugins de imagem, `JobService`, `useForensicJob`
- Dependências: Modelos ML, OpenCV, NumPy, GPU opcional
- APIs: `/analysis/techniques`, `/analysis`, `/analysis/{id}`, `/analysis/{id}/result`
- Dados: Evidence, AnalysisJob, artefatos de resultado
- Riscos: Jobs GPU longos, modelos ausentes, não-determinismo

## Feature: Detecção de Imagens Sintéticas (`synthetic_image_detection` / `sepael`)

- Objetivo: Classificar imagem como real, sintética ou incerto usando ensemble de detectores
- Usuários: Perito
- Fluxo Principal: selecionar evidência → submeter `synthetic_image_detection` → executar na fila GPU → retornar scores individuais + visualizações
- Componentes: `SyntheticImageDetectionAdapter`, `synthetic_image_detection/pipeline.py`, `bfree_pipeline.py`, `clipd_pipeline.py`, `gpu_residency.py`
- Dependências: PyTorch, transformers, Pillow, modelos HuggingFace + B-Free + Corvi2023
- APIs: `/analysis/techniques`, `/analysis`, `/analysis/{id}/result`
- Dados: Evidence, AnalysisJob, artefatos (`model_scores.txt`, PNGs de resíduos/FFT)
- Riscos:
  - `torch.load(weights_only=False)` no carregamento do NPR legado
  - Pesos sem checksums SHA-256
  - Sem score ensemble consolidado
  - Thresholds hardcoded (`0.66/0.34`)
- Legados/testados não integrados: CLIDE, SAFE, Effort, XGBoost, NPR
- Status: Implementada (operacional), com dívidas técnicas documentadas

## Feature: Spoofing de Áudio (`audio_spoofing_detection`)

- Objetivo: Detectar áudio sintético/spoof com hub multi-detector
- Usuários: Perito
- Fluxo: selecionar evidência → marcar detectores (DF Arena, SLS, WeDefense) → job CPU → scores por detector + gráfico temporal; opcionalmente ativar LR calibrado sobre população de referência
- Componentes: `AudioSpoofingAdapter`, `audio_spoofing/pipeline.py`, `AudioSpoofingAnalysis.tsx`
- Detectores: `df_arena_1b`, `sls_xlsr`, `wedefense_wavlm_mhfa`
- APIs: `/analysis/audio-spoofing-detectors`, `/analysis/audio-spoofing-reference-catalog`, `/analysis`
- Dados: `detector_scores.txt`, `audio_spoofing_plot.json`, `audio_spoofing_details.json`
- Riscos: detectores discordam; limiar 65%; pesos locais obrigatórios; agregação por janelas
- Status: **Ativa** (jul/2026)
- Doc: `knowledge/audio_spoofing_pipeline.md`

## Feature: Calibração LR de Spoofing de Áudio (`audio_spoofing_lr_reference`)

- Objetivo: Produzir likelihood ratio (LR) calibrado para evidência de áudio a partir de uma população de referência multi-detector. LR > 1 favorece H1 = bonafide/autêntico; LR < 1 favorece H0 = spoof/sintético.
- Usuários: Perito
- Fluxo Principal: selecionar evidência → escolher detectores → definir população de referência (treino/calibração/teste) → opcionalmente ativar tipicidade latente e/ou população aumentada → submeter job → receber `log10(LR)`, métricas da população de referência e artefatos gráficos
- Componentes: `audio_spoofing_lr_reference.py`, `AudioSpoofingAdapter`, `ReferencePopulationSelector`, `ReferenceLrPanel`, `MetaClassifierSelect`
- Detectores LR: `df_arena_1b`, `sls_xlsr`, `wedefense_wavlm_mhfa`
- População de referência: macro-categorias (`asv_classic`, `codec_conditions`, `deepfake_challenges`, `in_the_wild`) com bases (`ASVspoof2019_LA`, `ASVspoof2021_LA_eval`, `ASVspoof5`, `CodecFake`, `ADD2022`, `ADD2023`, `DFADD`, `SONAR`, `In-The-Wild`, `Fake-or-Real`, `LibriSeVoc`) e geradores/subgrupos. População padrão: DFADD/StyleTTS2, NaturalSpeech2; SONAR/xTTS, PromptTTS2, VoiceBox; ASVspoof5/flac_E_eval; In-The-Wild/In-The-Wild.
- Splits: cada subgrupo amostrado em 500 amostras/classe, divididas em `train_logreg` (250), `calibration_bigauss` (125) e `test_bigauss` (125).
- Meta-classificadores: importados de `synthetic_lr_reference.py` (`META_CLASSIFIERS`); padrão `logistic`.
- Calibração: bi-Gaussiana ajustada no EER (`_fit_bigauss`), com parâmetros `mu_real`, `mu_fake`, `sigma`, `eer`.
- Cache: SHA-256 da seleção + matriz + classificador + semente (mais `system`, `k` e `distance` quando tipicidade latente está ativa) em `_cache_dir()/*.joblib`; reutilização automática para seleções idênticas.
- APIs: `/analysis/audio-spoofing-reference-catalog` (catálogo hierárquico e EER por detector), `/analysis` (submissão com `reference_lr_enabled: true`)
- Dados/Artefatos:
  - `lr_reference_report.json` — relatório completo
  - `lr_reference_summary.txt` — resumo textual
  - `lr_reference_model.joblib` — modelo serializado
  - `lr_reference_test_scored.csv` — conjunto de teste com LRs
  - `lr_reference_tippett.png` — Tippett plot
  - `lr_reference_distribution.png` — distribuição das LRs
  - `lr_reference_identity.png` — função identidade
- Métricas: CLLR, minCLLR, EER (%), AUC, identity MSE, pesos/importância dos detectores, intercepto logístico.
- Riscos: matrizes de referência (`outputs/lr_calibration/audio_spoofing/`) não versionadas; requer pré-computação offline; primeiro uso de seleção nova pode levar vários minutos; seleção sem `fit_items` e `test_items` inválida.
- Status: **Ativa** (jul/2026)

## Feature: Tipicidade Latente (`latent_typicality`)

- Objetivo: Enriquecer o vetor de features do meta-classificador LR com medidas de tipicidade baseadas em k-NN sobre embeddings dos detectores de áudio, capturando similaridade da evidência com distribuições bonafide e spoof.
- Usuários: Perito (via `audio_spoofing_detection` com `use_latent_typicality: true`)
- Fluxo Principal: durante o job, os detectores retornam embeddings junto aos logits → constrói bancos k-NN nos embeddings do split `train_logreg` → materializa features de tipicidade para treino, calibração, teste e evidência questionada → meta-classificador treinado sobre features estendidas.
- Componentes: `core/latent_typicality/config.py`, `typicality.py`, `features.py`, `representations_utils.py`, `audio_spoofing_lr_reference.py`
- Configuração padrão: sistema "D", distância `cosine`, k=5, eps=1e-8.
- Sistemas de features:
  - A: apenas scores `S_<detector>` (logit bonafide)
  - B: scores + tipicidade real/sintética `T_R_<detector>`, `T_S_<detector>`
  - C: + out-of-distribution `OOD_<detector>`
  - D: + diferenças de raio `Delta_r_<detector>` e `rho_<detector>`
- Features computadas por detector:
  - `T_R`: tipicidade em relação à população bonafide (1 - CDF do k-ésimo vizinho)
  - `T_S`: tipicidade em relação à população spoof
  - `OOD`: 1 - max(T_R, T_S)
  - `Delta_r`: r_real - r_spoof
  - `rho`: log(r_real / r_spoof)
  - `r_R`, `r_S`: distâncias ao k-ésimo vizinho
- Matriz de representações: `outputs/lr_calibration/audio_spoofing/representations/representations.csv`, com colunas de logits e caminhos para embeddings `.npy` (`<sample_id>__<detector>.npy`).
- APIs: `/analysis` (parâmetro `use_latent_typicality` no job)
- Dados: embeddings `.npy`, `representations.csv`, referências k-NN cacheadas no `.joblib`.
- Riscos: requer matriz de representações previamente materializada; alto consumo de RAM/I/O na carga batch de embeddings (`VA_LR_TYPICALITY_BATCH`, `VA_LR_TYPICALITY_JOBS` configuráveis via ambiente); experimental — sistema D POC.
- Status: **Experimental** (jul/2026)

## Feature: População de Referência Aumentada de Áudio

- Objetivo: Ampliar a diversidade da população de referência LR com variantes sintéticas que simulam condições pós-captura/distro (codec e ruído), reduzindo overfit a condições de treino.
- Usuários: Perito (via checkbox no frontend), Sistema (scripts de ingestão)
- Augmentações: `mp3_128k`, `opus_32k`, `noise_snr_20`, `noise_snr_15`.
  - `mp3_128k`: roundtrip WAV→MP3 128 kbps (libmp3lame)→WAV 16 kHz mono via ffmpeg
  - `opus_32k`: roundtrip WAV→Opus 32 kbps (`-application voip`)→WAV via ffmpeg
  - `noise_snr_20`: ruído rosa misturado a 20 dB SNR
  - `noise_snr_15`: ruído rosa misturado a 15 dB SNR
- Componentes: `scripts/audio_lr_augmentation.py`, `scripts/audio_lr_disk_verify.py`, `scripts/audio_lr_completion_gate.py`, `scripts/audio_lr_dataset_utils.py`
- Ingestão: a partir de protocolo CSV, gera manifesto, copia/amostra áudios, aplica augmentações forensicamente rastreáveis (`source_sha256`, `augmentation_params`, `parent_source_id`) e gera score matrix aumentada + matriz de representações.
- Controle de qualidade: `audio_lr_completion_gate.py` verifica completude de 500+500 originais e 4×500+4×500 augmentações por gerador elegível, além de integridade da score matrix (sem NaN/duplicatas/erros) e da representations matrix (sem NaN nem grupos órfãos).
- Uso em runtime: quando `use_augmented_reference: true`, o `AudioSpoofingAdapter` escolhe a matriz aumentada (`DEFAULT_AUGMENTED_SCORE_MATRIX`) ou a matriz de representações (`DEFAULT_REPRESENTATIONS_MATRIX`) se tipicidade latente também estiver ativa; `sample_multiplier` passa a ser `AUGMENTATION_MULTIPLIER = 5`.
- Dados: `outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full_augmented.csv`, `outputs/lr_calibration/audio_spoofing/representations/representations.csv`, amostras em `outputs/lr_calibration/audio_spoofing/samples/augmented/reference_population/`.
- Riscos: depende de ffmpeg/ffprobe; alto volume de disco; requer pipeline offline completo antes de ficar disponível no frontend.
- Status: **Ativa** (jul/2026)

## Feature: Calibração LR Sintética (`reference_lr_enabled`)

- Objetivo: Likelihood ratio calibrado sobre população de referência multi-detector
- Usuários: Perito (via `synthetic_image_detection`)
- Componentes: `synthetic_lr_reference.py`, matrizes em `outputs/lr_calibration/` (local)
- Detectores LR: ai-image-detector, sdxl-flux, bfree, corvi2023, safe
- APIs: `/analysis/synthetic-reference-catalog`
- Riscos: matriz de referência não versionada; recomputação manual
- Status: **Ativa** (opcional por parâmetro)

## Feature: Cadeia de Custódia

- Objetivo: Garantir integridade e rastreabilidade de evidências
- Usuários: Perito, Admin
- Fluxo Principal: upload/job/derivado → registro assinado → encadeamento por hash
- Componentes: `CustodyService`, `CustodySigningService`, `ForensicIntegrityService`
- Dependências: PostgreSQL, Ed25519, filesystem
- APIs: `/audit/*`, `/audit/verify-case-forensic/*`
- Dados: CustodyRecord
- Riscos: Chave dev efêmera, lock local, imutabilidade dependente de trigger SQLite

## Feature: Jobs Assíncronos

- Objetivo: Executar análises forenses pesadas fora da requisição HTTP
- Usuários: Sistema
- Fluxo Principal: submeter → enfileirar → executar → persistir resultado
- Componentes: `JobService`, `JobRunner`, `Celery`, `Redis`, `GPUInference`
- Dependências: Redis, Celery, workers CPU/GPU
- APIs: `/analysis/*`
- Dados: AnalysisJob
- Riscos: Lock GPU, fallback CPU, fila única

## Gate

O sistema entrega: plataforma forense digital completa para gestão de casos, análises técnicas de mídia, cadeia de custódia rastreável e laudos.

## Evidências

- `docs/specs/00-overview.md`
- `src/backend/api/v1/endpoints/*.py`
- `src/frontend/src/pages/*.tsx`
- `src/backend/core/plugins/*.py`
- `src/backend/core/audio_spoofing_lr_reference.py`
- `src/backend/core/latent_typicality/*.py`
- `src/backend/core/legacy/audio_spoofing/pipeline.py`
- `scripts/audio_lr_*.py`
