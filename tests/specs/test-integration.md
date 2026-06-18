# test-integration.md - Testes de Integracao

## Escopo

Testar a comunicacao entre modulos, banco de dados, fila Celery e sistema de arquivos.

## Teste INT-001: Upload de Evidencia + Cadeia de Custodia

### Setup
- Banco limpo, Redis vazio, diretorio de uploads temporario
- Usuario perito autenticado

### Passos
1. POST /api/v1/cases (cria caso)
2. POST /api/v1/evidence (upload de arquivo de teste)
3. Verifica: HTTP 201, Evidence criada no banco
4. Verifica: SHA-256 calculado automaticamente
5. Verifica: Arquivo salvo em disco no path correto
6. Verifica: CustodyRecord criado com tipo `evidence_upload`
7. Verifica: Cadeia de custodia verificavel (verify_chain retorna valid=true)

### Estados
- Antes: 0 evidencias, 0 registros de custodia
- Depois: 1 evidencia, 1 registro de custodia, arquivo em disco

## Teste INT-002: Submissao e Execucao de Job de Analise

### Setup
- Caso e evidencia de imagem JPEG criados
- Plugin `jpeg_ghosts` registrado
- Worker Celery em modo sincrono (CELERY_TASK_ALWAYS_EAGER=true)

### Passos
1. POST /api/v1/analysis com evidence_id e technique="jpeg_ghosts"
2. Verifica: HTTP 201, AnalysisJob criado com status="completed" (modo eager)
3. Verifica: CustodyRecord de `analysis_started` e `analysis_completed` criados
4. Verifica: Artefatos salvos em disco em `{RESULTS_DIR}/{case_id}/{evidence_id}/{job_id}/`
5. Verifica: result_sha256 preenchido no AnalysisJob

### Estados
- Antes: 0 jobs, 0 artefatos
- Depois: 1 job completed, artefatos em disco, 2 registros de custodia

## Teste INT-003: Serializacao de Jobs GPU

### Setup
- Redis limpo, semaforo de GPU livre
- Dois jobs Detecção de imagens sintéticas submetidos simultaneamente

### Passos
1. Submete job_1 (Detecção de imagens sintéticas) para evidencia A
2. Submete job_2 (Detecção de imagens sintéticas) para evidencia B
3. Verifica: job_1 entra em status "running" rapidamente
4. Verifica: job_2 fica em status "pending" ate job_1 completar
5. Verifica: job_2 muda para "running" apos job_1 completar
6. Verifica: Nenhum OOM ocorre

### Estados
- job_1: pending → running → completed
- job_2: pending → running (depois do 1) → completed

## Teste INT-004: Geracao de Laudo Completo

### Setup
- Caso com 1 evidencia e 2 jobs completados
- Template de relatorio padrao disponivel

### Passos
1. POST /api/v1/reports com case_id e job_ids
2. Worker gera PDF
3. Verifica: Report criado com status="completed"
4. Verifica: PDF existe em disco
5. Verifica: SHA-256 do PDF calculado
6. Verifica: CustodyRecord do tipo `report_generated` criado
7. GET /api/v1/reports/{id}/download retorna PDF valido

### Estados
- Antes: 0 reports
- Depois: 1 report completed, PDF em disco, hash registrado

## Teste INT-005: Reprodutibilidade de Analise

### Setup
- Job completado com artefatos e hash registrado

### Passos
1. GET /api/v1/audit/verify/{record_id} para o registro de analysis_completed
2. Chama `recompute_job_hash(job_id)`
3. Verifica: novo resultado tem mesmo hash que o original
4. Verifica: `reproducible=true`

### Estados
- Resultado original e reexecutado devem ser identicos
