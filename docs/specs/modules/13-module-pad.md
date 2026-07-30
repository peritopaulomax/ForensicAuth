# 13-module-pad.md — Detecção de Ataques de Apresentação (Presentation Attack Detection)

## 1. Propósito

Este módulo integra ao ForensicAuth uma técnica forense de **detecção de ataques de apresentação facial (PAD)** que utiliza o modelo open source [Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing). O objetivo é permitir que o perito submeta uma imagem de face e obtenha uma análise indicando se o rosto é real ou falso (foto impressa, tela de dispositivo, máscara, imagem 3D etc.).

## 2. Escopo

### Dentro do escopo (v0)

- Técnica `presentation_attack_detection` registrada no `PluginRegistry`.
- Plugin backend que executa o modelo MiniFASNetV2 + RetinaFace.
- Suporte a imagens de evidência do tipo `imagem`.
- Detecção da face principal (maior bounding box) na imagem.
- Retorno de: label (`real` / `fake`), score de confiança (0..1), bounding box da face.
- Dashboard no frontend na aba "Imagens" chamado "Detecção de Ataques de Apresentação".
- Integração completa com o fluxo de jobs, hashes no `AnalysisJob` e reproducibilidade; custódia oficial nos eventos de lifecycle (upload / derivado / share / close / VCP), não por job.

### Fora do escopo (v0)

- Suporte a múltiplas faces (v1).
- Fine-tuning do modelo para dados forenses (v1).
- Geração de PDF institucional dedicado de PAD (fora de escopo do produto).
- Suporte a vídeo/streaming.

## 3. Atores

- **Perito**: submete imagem de face e interpreta resultado.
- **Sistema**: executa o modelo e registra o job (`AnalysisJob` + artefatos/hashes).

## 4. Requisitos Funcionais

| ID | Requisito |
|---|---|
| PAD-RF-01 | O plugin deve ser registrado com nome técnico `presentation_attack_detection` e tipo suportado `imagem`. |
| PAD-RF-02 | O plugin deve detectar a face principal usando RetinaFace. |
| PAD-RF-03 | O plugin deve classificar a face como `real` ou `fake` usando MiniFASNetV2. |
| PAD-RF-04 | O plugin deve retornar `score` (float 0..1), `label` ("real" \| "fake") e `bbox` (x, y, w, h). |
| PAD-RF-05 | Se nenhuma face for detectada, o plugin deve retornar erro controlado com mensagem clara. |
| PAD-RF-06 | O plugin deve suportar execução GPU com fallback para CPU. |
| PAD-RF-07 | O frontend deve disponibilizar página/dashboard na aba "Imagens" para execução da técnica. |
| PAD-RF-08 | O frontend deve exibir o resultado com label, score e bounding box sobreposto na imagem. |
| PAD-RF-09 | O job deve persistir hashes de entrada/saída no `AnalysisJob` (e artefatos no filesystem). Elo de custódia só na promoção a derivado ou em eventos de lifecycle. |

## 5. Requisitos Não-Funcionais

| ID | Requisito |
|---|---|
| PAD-RNF-01 | Tempo de inferência < 5s por imagem em GPU (modelo leve, ~20-90ms; overhead de I/O é tolerado). |
| PAD-RNF-02 | O modelo deve operar 100% local (sem chamadas externas). |
| PAD-RNF-03 | Reprodutibilidade best-effort: usar perfil `gpu_ml` nos hashes/artefatos do job (reexecução). |
| PAD-RNF-04 | O código do modelo original deve ser preservado via adapter (Regra Máxima 8). |
| PAD-RNF-05 | Threshold padrão de classificação deve ser configurável (`PAD_DEFAULT_THRESHOLD=0.5`). |

## 6. Componentes/Módulos

```text
src/backend/core/plugins/presentation_attack_detection_adapter.py   # adapter
src/backend/forensics/pad/                                        # código do modelo vendored
src/frontend/src/pages/PresentationAttackDetectionAnalysis.tsx      # página/dashboard
src/frontend/src/config/imageAnalysisGroups.ts                      # registro da técnica
```

## 7. Stack e Decisões

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI + SQLAlchemy + Celery + Redis |
| ML inference | PyTorch + OpenCV + RetinaFace + MiniFASNetV2 |
| Frontend | React 18 + TypeScript + Vite |
| Testes | pytest + Vitest + Playwright |

**ADR-PAD-001**: Usar MiniFASNetV2 como default — melhor trade-off entre acurácia e custo computacional.  
**ADR-PAD-002**: Apenas face principal no v0 — simplifica UI e testes; múltiplas faces em v1.  
**ADR-PAD-003**: Execução na fila GPU com fallback CPU — reutiliza infraestrutura existente e lock de GPU.

## 8. Fluxo de Dados

```text
Frontend (dashboard PAD)
  → POST /api/v1/analysis {evidence_id, technique: "presentation_attack_detection"}
  → JobService.submit_job
  → Celery (fila gpu)
  → Worker GPU → PresentationAttackDetectionAdapter
      → RetinaFace detecta face
      → MiniFASNetV2 classifica
      → retorna {label, score, bbox}
  → AnalysisJob atualizado (status, result_path, result_sha256, parameters)
  → Frontend consulta resultado e exibe
  → (Opcional) perito promove artefato → CustodyRecord `derivative_saved`
```

## 9. Interface do Plugin

### Entrada

```json
{
  "evidence_path": "/uploads/{uuid}.jpg",
  "parameters": {
    "threshold": 0.5
  }
}
```

### Saída

```json
{
  "success": true,
  "adapter": "presentation_attack_detection",
  "label": "fake",
  "score": 0.87,
  "bbox": {"x": 120, "y": 80, "w": 200, "h": 200},
  "inference_device": "cuda"
}
```

### Erro

```json
{
  "success": false,
  "adapter": "presentation_attack_detection",
  "error": "NO_FACE_DETECTED",
  "message": "Nenhuma face detectada na imagem."
}
```

## 10. Regras de Negócio

| ID | Regra |
|---|---|
| PAD-RN-01 | Apenas evidências do tipo `imagem` podem ser submetidas. |
| PAD-RN-02 | Se nenhuma face for detectada, o job deve falhar com status controlado. |
| PAD-RN-03 | O threshold padrão é 0.5; score > threshold → `real`, senão → `fake`. |
| PAD-RN-04 | O bounding box deve ser relativo às dimensões originais da imagem. |
| PAD-RN-05 | Todo processamento deve persistir hashes no `AnalysisJob`; não criar `CustodyRecord` só por concluir o job. |

## 11. Critérios de Aceite

- [ ] Plugin registrado e listado em `/analysis/techniques` para imagens.
- [ ] Submissão de job retorna `AnalysisJob` com status `pending`.
- [ ] Worker executa o job e retorna label/score/bbox.
- [ ] Frontend exibe dashboard e resultado corretamente.
- [ ] Hashes do job gravados no `AnalysisJob` (sem `CustodyRecord` automático ao completar).
- [ ] Testes E2E backend, frontend e worker passam; custódia coberta nos eventos de lifecycle/derivado.

## 12. Testabilidade (TDD)

Testes a serem criados:

- `test_pad_plugin_registered` — plugin aparece no registry para imagens.
- `test_pad_validate_parameters` — aceita threshold opcional.
- `test_pad_detects_face_and_classifies` — integração com modelo (fixture real).
- `test_pad_no_face_returns_error` — erro controlado quando não há face.
- `test_pad_job_submission` — endpoint `/analysis` cria job.
- `test_pad_worker_execution` — Celery executa job e retorna resultado.
- `test_pad_job_persists_hashes` — job completed com `result_sha256` / params hash (sem CustodyRecord por job).
- `test_pad_frontend_dashboard` — Playwright navega e submete análise.
- `test_pad_regression_vs_original` — saída do adapter vs. `test.py` original.

## 13. Rastreabilidade

| Regra/RF | Spec | Teste |
|---|---|---|
| PAD-RF-01 | 13-module-pad.md | test_pad_plugin_registered |
| PAD-RF-02 | 13-module-pad.md | test_pad_detects_face_and_classifies |
| PAD-RF-03 | 13-module-pad.md | test_pad_detects_face_and_classifies |
| PAD-RF-04 | 13-module-pad.md | test_pad_detects_face_and_classifies |
| PAD-RF-05 | 13-module-pad.md | test_pad_no_face_returns_error |
| PAD-RF-06 | 13-module-pad.md | test_pad_worker_execution |
| PAD-RF-07 | 13-module-pad.md | test_pad_frontend_dashboard |
| PAD-RF-08 | 13-module-pad.md | test_pad_frontend_dashboard |
| PAD-RF-09 | 13-module-pad.md | test_pad_custody_record_created |
