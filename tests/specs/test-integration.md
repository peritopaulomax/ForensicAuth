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
3. Verifica: **nenhum** CustodyRecord novo por causa do job (preview exploratorio)
4. Verifica: Artefatos salvos em disco em `{RESULTS_DIR}/{case_id}/{evidence_id}/{job_id}/`
5. Verifica: result_sha256 preenchido no AnalysisJob

### Estados
- Antes: N registros de custodia (ex.: so o upload)
- Depois: 1 job completed, artefatos em disco, **mesma** contagem de CustodyRecord (sem elo de job)

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

## Teste INT-004: Promocao de Derivado + Custodia

### Setup
- Caso com 1 evidencia e 1 job completed com artefato em disco

### Passos
1. POST derivados (promove artefato do job)
2. Verifica: Evidence derivada criada
3. Verifica: CustodyRecord tipo `derivative_saved`
4. Verifica: arquivo em `DERIVATIVES_DIR`
5. Verifica: cadeia do caso ainda valida

### Estados
- Antes: job completed sem derivado
- Depois: evidencia derivada + elo `derivative_saved`

## Teste INT-005: Reprodutibilidade de Analise

### Setup
- Job completado com artefatos e hash registrado no AnalysisJob
- (Opcional) derivado salvo se o fluxo de reproducao exigir custody

### Passos
1. Chama endpoint/utilitario de reproducao do job (`reproduce` / `recompute_job_hash` conforme API vigente)
2. Verifica: novo resultado tem mesmo hash que o original (`result_sha256` / artefato)
3. Verifica: `reproducible=true` (ou equivalente na resposta)

### Estados
- Resultado original e reexecutado devem ser identicos
