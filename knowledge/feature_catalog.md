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
| Análise de Imagem | Aplicar técnicas forenses em imagens (CPU + GPU/ML) | Perito | Plugins de imagem, JobService | `/analysis/*` | Crítica | Ativa |
| Análise de Áudio | Aplicar técnicas forenses em áudio | Perito | Plugins de áudio | `/analysis/*` | Alta | Ativa |
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

### Administrative Features
- Gestão de usuários
- Auditoria
- Diagnóstico GPU

### Experimental Features
- Métodos IMDL-BenCo `ecosystem` (visíveis na UI, mas requerem pesos/pipelines adicionais)
- `deepfake_similarity` (adapter placeholder sem inferência real)

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
- Fluxo: selecionar evidência → marcar detectores (DF Arena, SLS, WeDefense) → job CPU → scores por detector + gráfico temporal
- Componentes: `AudioSpoofingAdapter`, `audio_spoofing/pipeline.py`, `AudioSpoofingAnalysis.tsx`
- Detectores: `df_arena_1b`, `sls_xlsr`, `wedefense_wavlm_mhfa`
- APIs: `/analysis/audio-spoofing-detectors`, `/analysis`
- Dados: `detector_scores.txt`, `audio_spoofing_plot.json`, `audio_spoofing_details.json`
- Riscos: detectores discordam; limiar 65%; pesos locais obrigatórios; agregação por janelas
- Status: **Ativa** (jul/2026)
- Doc: `knowledge/audio_spoofing_pipeline.md`

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
