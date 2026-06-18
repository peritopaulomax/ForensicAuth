# test-module-jobs.md - Especificacao de Testes: Jobs e Processamento

## Testes Unitarios

### TU-JOB-001: Submissao de job valido
- **Funcao**: `AnalysisService.submit_job(evidence_id, technique, parameters, user)`
- **Setup**: Evidencia existente, plugin registrado, parametros validos
- **Saida esperada**: AnalysisJob com status="pending"
- **Verificacoes**:
  - Job persistido no banco
  - Task Celery publicada no broker (mock)
  - CustodyRecord de analysis_started criado

### TU-JOB-002: Submissao com tecnica inexistente
- **Entrada**: technique="tecnica_falsa"
- **Saida esperada**: Lanca `ValueError`, HTTP 422
- **Verificacoes**: Mensagem = "Tecnica 'tecnica_falsa' nao encontrada"

### TU-JOB-003: Submissao com parametros invalidos
- **Setup**: Plugin que requer parametro "threshold" (float 0-1)
- **Entrada**: parameters={"threshold": 1.5}
- **Saida esperada**: HTTP 422 com detalhes do erro de validacao

### TU-JOB-004: Execucao de job com sucesso
- **Funcao**: `AnalysisWorker.run_forensic_analysis(job_id)`
- **Setup**: Job pending, plugin mock que retorna artefato fixo
- **Fluxo**:
  1. Worker executa
  2. Status muda para "running"
  3. Plugin.analyze chamado
  4. Artefatos salvos em disco
  5. Status muda para "completed"
  6. result_sha256 preenchido
- **Verificacoes**: Artefato existe no path esperado

### TU-JOB-005: Execucao de job com falha
- **Setup**: Plugin mock que lanca excecao
- **Fluxo**:
  1. Worker executa
  2. Status muda para "running"
  3. Plugin lanca excecao
  4. Retry 1 (max 3)
  5. Apos 3 falhas: status="failed"
  6. error_message preenchido

### TU-JOB-006: Serializacao GPU
- **Setup**: Dois jobs que requerem GPU submetidos
- **Fluxo**:
  1. Job_1 adquire lock GPU
  2. Job_2 tenta adquirir, fica em espera
  3. Job_1 libera lock
  4. Job_2 adquire e executa
- **Verificacoes**: Nunca houve dois jobs em running simultaneamente para tecnicas GPU

### TU-JOB-007: Timeout de job
- **Setup**: Plugin que dorme por 2 horas
- **Configuracao**: timeout GPU = 1h, timeout CPU = 10min
- **Saida esperada**: Job marcado como failed apos timeout

## Testes de Integracao

### TI-JOB-001: Fluxo completo de submissao e resultado
- **Fluxo**:
  1. POST /api/v1/analysis → recebe job_id
  2. GET /api/v1/analysis/{job_id} → status pending
  3. Worker processa (modo eager)
  4. GET /api/v1/analysis/{job_id} → status completed
  5. GET /api/v1/analysis/{job_id}/result → artefatos acessiveis

### TI-JOB-002: Consulta de tecnicas disponiveis
- **Endpoint**: GET /api/v1/analysis/techniques?file_type=imagem
- **Saida esperada**: Lista de tecnicas que suportam imagem
- **Verificacoes**: Cada item tem name, description, supported_types, parameters_schema

## Mocks/Stubs

- Mock Celery broker (memoria) para testes unitarios
- Mock plugins em `tests/mocks/plugins/`
- Mock GPU lock (semaforo em memoria)
