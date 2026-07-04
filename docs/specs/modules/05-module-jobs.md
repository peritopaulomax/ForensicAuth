# 05-module-jobs.md - Modulo de Filas e Processamento de Jobs

## Responsabilidade Unica

Orquestrar a execucao assincrona de tarefas forenses usando Celery, com gerenciamento de GPU/VRAM e serializacao de jobs que consomem recursos da placa de video.

## Interfaces Publicas

### API Endpoints

- `POST /api/v1/analysis`
  - Entrada: `{evidence_id: UUID, technique: str, parameters: dict}`
  - Saida: `{job_id: UUID, status: str, message: str}`
  - Erros: 404 (evidencia nao existe), 422 (tecnica invalida ou parametros invalidos)

- `GET /api/v1/analysis/{job_id}`
  - Entrada: `job_id: UUID`
  - Saida: `{id: UUID, evidence_id: UUID, technique: str, status: str, parameters: dict, result: dict | null, error_message: str | null, started_at: datetime | null, completed_at: datetime | null}`
  - Erros: 404 (job nao existe)

- `GET /api/v1/analysis/{job_id}/result`
  - Entrada: `job_id: UUID`
  - Saida: JSON/imagens conforme tecnica
  - Erros: 409 (job ainda nao completado)

- `GET /api/v1/analysis/techniques`
  - Entrada: Query `file_type` (opcional: imagem, audio, video, pdf)
  - Saida: `List[{name: str, description: str, supported_types: list[str], parameters_schema: dict}]`

### Celery Tasks

```python
@app.task(bind=True, max_retries=3)
def run_forensic_analysis(self, job_id: str):
    """
    Task Celery que executa uma analise forense.
    
    Args:
        job_id: UUID do AnalysisJob
        
    Returns:
        dict com status e paths dos artefatos gerados
    """
    pass
```

## Dependencias de Outros Modulos

- **Core**: `ForensicPlugin`, `PLUGINS` registry, `Settings`
- **Custody**: Jobs sao execucoes exploratorias (preview) e NAO geram `CustodyRecord`; a cadeia e registrada apenas em upload, derivados salvos e fechamento/laudos.
- **Database**: Models `AnalysisJob`, `Evidence`, sessao SQLAlchemy
- **Adapters**: Implementacoes concretas de `ForensicPlugin`

## Fluxo Interno

### Submissao de Job
1. Recebe requisicao POST com evidence_id, technique, parameters
2. Valida se evidence_id existe e usuario tem permissao no caso
3. Valida se tecnica existe no registry `PLUGINS`
4. Chama `plugin.validate_parameters(parameters)`
5. Se invalido: retorna 422 com mensagem
6. Cria `AnalysisJob` no banco (status=pending)
7. Publica task Celery `run_forensic_analysis.delay(job_id)`
8. Retorna job_id ao cliente

> Nota: jobs sao previews exploratorios e, portanto, nao geram `CustodyRecord` neste estagio. A cadeia de custodia e atualizada apenas quando um artefato e promovido a derivado ou incluido em um laudo.

### Execucao do Worker
1. Worker Celery recebe task `run_forensic_analysis`
2. Busca `AnalysisJob` no banco
3. Atualiza status para `running`, registra `started_at`
4. Identifica plugin pelo nome da tecnica
5. Se tecnica usa GPU:
   - Adquire lock/semaforo de GPU (Redis-based)
   - Executa analise
   - Libera lock
6. Se tecnica nao usa GPU: executa diretamente
7. Plugin retorna resultado (artefatos, metricas, logs)
8. Salva artefatos em disco (`RESULTS_DIR/{case_id}/{evidence_id}/{job_id}/`)
9. Calcula SHA-256 de cada artefato
10. Atualiza `AnalysisJob`:
    - status = completed (ou failed)
    - result_path = diretorio dos artefatos
    - result_sha256 = hash do resultado principal (ou dict de hashes)
    - artifact_sha256 = hash do artefato canônico, quando aplicável
    - completed_at = now()
    - error_message = null (ou mensagem se falhou)
11. Retorna resultado para Celery backend

> Nota: a conclusao do job tambem nao gera `CustodyRecord`. O registro na cadeia ocorre apenas na promocao do artefato a derivado.

### Consulta de Resultado
1. Cliente faz GET /analysis/{job_id}/result
2. Se status != completed: retorna 409
3. Le artefatos do disco
4. Retorna JSON com dados e URLs/paths dos artefatos

## Regras de Negocio Especificas

- **RN-JOB-01**: Jobs com tecnicas que usam GPU (synthetic_image_detection, safire, noiseprint, imdlbenco, videofact, stil_video_detection, lowres_fake_video, distildire, presentation_attack_detection, fakevlm, clipbased_synthetic) DEVEM ser serializados via semaforo Redis.
- **RN-JOB-02**: Cada job tem maximo de 3 retries automaticos em caso de falha (exceto falhas de validacao).
- **RN-JOB-03**: Artefatos de resultado DEVEM ser armazenados em subdiretorio exclusivo por job, seguindo o padrao `{RESULTS_DIR}/{case_id}/{evidence_id}/{job_id}/`.
- **RN-JOB-05**: Jobs pendentes por mais de 24 horas sem worker disponivel devem ser marcados como failed.

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| Evidencia nao encontrada | HTTP 404 |
| Tecnica nao existe | HTTP 422 |
| Parametros invalidos | HTTP 422 com detalhes da validacao |
| GPU OOM | Retry com delay exponencial (max 3x), depois failed |
| Worker crash | Celery redelivery automatica (acks_late=true) |
| Timeout (> 1h para GPU, > 10min para CPU) | Marca como failed |

## Dados de Entrada/Saida

- Entrada: evidence_id (UUID), technique (str), parameters (JSON)
- Saida: job metadata + artefatos em disco
- Artefatos: imagens (PNG/JPG), JSON, CSV, PDF (relatorios internos de tecnica)
