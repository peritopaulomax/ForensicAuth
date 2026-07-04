# test-module-pad.md — Especificação de Testes do Módulo PAD

## 1. Filosofia

Aplicar TDD + SDD: testes são escritos antes ou junto com a implementação, cobrindo backend, worker, frontend e cadeia de custódia. O objetivo é garantir que o fluxo fim a fim de detecção de ataques de apresentação funcione e esteja integrado ao ForensicAuth.

## 2. Pirâmide de Testes

| Nível | % Alvo | Ferramenta | Escopo |
|---|---|---|---|
| Unitário | 50% | pytest | Plugin, adapter, funções auxiliares |
| Integração | 30% | pytest + Celery + TestClient | JobService, worker, API, banco |
| E2E | 20% | Playwright | Fluxo completo no navegador |

## 3. Organização

```
tests/
├── unit/
│   ├── test_presentation_attack_detection_plugin.py
│   └── test_presentation_attack_detection_adapter.py
├── integration/
│   ├── test_presentation_attack_detection_job.py
│   └── test_presentation_attack_detection_worker.py
├── e2e/
│   └── test_presentation_attack_detection_e2e.py
└── fixtures/
    ├── face_real.jpg
    ├── face_printed.jpg
    └── face_mask.jpg
```

## 4. Plano de Testes por Funcionalidade

### 4.1 Registro do Plugin

| Teste | Descrição | Tipo |
|---|---|---|
| `test_pad_plugin_registered` | Verifica que `presentation_attack_detection` aparece no `PluginRegistry` para tipo `imagem`. | Unit |
| `test_pad_supported_types` | Verifica que o plugin suporta apenas `imagem`. | Unit |

### 4.2 Validação de Parâmetros

| Teste | Descrição | Tipo |
|---|---|---|
| `test_pad_validate_parameters_empty` | Parâmetros vazios são válidos (threshold padrão). | Unit |
| `test_pad_validate_parameters_custom_threshold` | Threshold customizado entre 0 e 1 é aceito. | Unit |
| `test_pad_validate_parameters_invalid_threshold` | Threshold < 0 ou > 1 rejeitado. | Unit |

### 4.3 Inferência

| Teste | Descrição | Tipo |
|---|---|---|
| `test_pad_detects_face_and_classifies_real` | Imagem com rosto real retorna `label=real`, score > threshold. | Integration |
| `test_pad_detects_face_and_classifies_fake` | Imagem com ataque (print/máscara) retorna `label=fake`, score < threshold. | Integration |
| `test_pad_no_face_returns_error` | Imagem sem rosto retorna erro `NO_FACE_DETECTED`. | Integration |
| `test_pad_inference_device_reported` | Resultado indica `cuda` ou `cpu`. | Unit/Integration |

### 4.4 Job e Worker

| Teste | Descrição | Tipo |
|---|---|---|
| `test_pad_job_submission_creates_analysis_job` | POST `/analysis` cria `AnalysisJob` pending. | Integration |
| `test_pad_worker_executes_job` | Worker Celery executa job e atualiza para completed. | Integration |
| `test_pad_worker_updates_failed_on_error` | Worker atualiza para failed quando não detecta face. | Integration |
| `test_pad_job_uses_gpu_queue` | Job é roteado para fila `gpu`. | Unit |

### 4.5 Cadeia de Custódia

| Teste | Descrição | Tipo |
|---|---|---|
| `test_pad_custody_record_created` | Ao completar job, cria `CustodyRecord` com hashes. | Integration |
| `test_pad_custody_chain_verifiable` | Cadeia de custódia do caso pode ser verificada. | Integration |

### 4.6 E2E Frontend

| Teste | Descrição | Tipo |
|---|---|---|
| `test_pad_dashboard_navigation` | Playwright navega para aba Imagens → Detecção de Ataques de Apresentação. | E2E |
| `test_pad_select_evidence_and_submit` | Seleciona evidência, submete job e aguarda resultado. | E2E |
| `test_pad_result_display` | Verifica que label, score e imagem com bbox são exibidos. | E2E |
| `test_pad_no_face_error_display` | Verifica mensagem de erro quando não há face. | E2E |

### 4.7 Regressão Forense

| Teste | Descrição | Tipo |
|---|---|---|
| `test_pad_regression_vs_original_repo` | Compara saída do adapter com saída do `test.py` original do Silent-Face-Anti-Spoofing (Regra Máxima 8). | Integration |

## 5. Fixtures

- `face_real.jpg`: imagem de rosto real.
- `face_printed.jpg`: foto de rosto impressa (ataque).
- `face_mask.jpg`: máscara de rosto (ataque, opcional).
- `sample_evidence_pad`: fixture que cria `Evidence` a partir de `face_real.jpg`.
- `pad_job`: fixture que cria `AnalysisJob` para `presentation_attack_detection`.

## 6. Gate E2E

O gate E2E do protótipo v0 é executado por:

```bash
pytest tests/e2e/test_presentation_attack_detection_e2e.py -v
```

Critério: todos os testes E2E passam, incluindo navegação frontend, submissão de job, execução worker, exibição de resultado e verificação de cadeia de custódia.

## 7. Definition of Done

- [ ] Todos os testes unitários passam.
- [ ] Todos os testes de integração passam.
- [ ] Todos os testes E2E passam.
- [ ] Teste de regressão forense passa (comparação com repo original).
- [ ] Código segue estilo do projeto.
- [ ] Documentação de setup de pesos está clara.

## 8. Comandos de Verificação

```bash
# Unit + integration
pytest tests/unit/test_presentation_attack_detection_*.py tests/integration/test_presentation_attack_detection_*.py -v

# E2E
pytest tests/e2e/test_presentation_attack_detection_e2e.py -v

# Frontend
npm run test -- src/frontend/src/pages/PresentationAttackDetectionAnalysis.test.tsx
```
