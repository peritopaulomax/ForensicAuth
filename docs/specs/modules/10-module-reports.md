# 10-module-reports.md - Modulo de Geracao de Relatorios (Laudos)

## Responsabilidade Unica

Gerar laudos periciais em PDF com template institucional, consolidando resultados de analises forenses, evidencias, hashes e cadeia de custodia em um documento imutavel e assinavel.

## Interfaces Publicas

### API Endpoints

- `POST /api/v1/reports`
  - Entrada: `{case_id: UUID, title: str, job_ids: list[UUID], template: str (default: "padrao_institucional")}`
  - Saida: `{report_id: UUID, status: "pending", message: "Laudo em geracao"}`
  - Erros: 404 (case nao existe), 403 (sem permissao no caso), 422 (job_ids invalidos)

- `GET /api/v1/reports/{report_id}`
  - Entrada: `report_id: UUID`
  - Saida: `{id: UUID, case_id: UUID, title: str, status: str, file_path: str | null, sha256: str | null, generated_by: UUID, created_at: datetime}`

- `GET /api/v1/reports/{report_id}/download`
  - Entrada: `report_id: UUID`
  - Saida: PDF binario (Content-Type: application/pdf)
  - Erros: 409 (laudo ainda nao gerado)

### Servico Interno (ReportService)

```python
class ReportService:
    def generate_report(self, report_id: UUID) -> None:
        """
        Gera o PDF do laudo. Executado como Celery task.
        """
        pass
```

## Dependencias de Outros Modulos

- **Core**: `Settings` (paths, templates)
- **Database**: Models `Report`, `Case`, `Evidence`, `AnalysisJob`, `CustodyRecord`
- **Custody**: `CustodyService` para registrar geracao do laudo
- **Jobs**: Celery task para geracao assincrona

## Fluxo Interno

### Submissao de Laudo
1. Recebe requisicao POST com case_id, title, job_ids
2. Valida se case existe e usuario tem permissao
3. Valida se todos os job_ids pertencem ao caso
4. Valida se todos os jobs estao com status "completed"
5. Cria `Report` no banco (status=pending)
6. Publica Celery task `generate_report.delay(report_id)`
7. Retorna report_id

### Geracao do PDF (Celery Worker)
1. Worker recebe task `generate_report`
2. Busca `Report`, `Case`, `Evidence` relacionada, `AnalysisJob`s selecionados
3. Busca `CustodyRecord`s do caso para cadeia de custodia
4. Renderiza template HTML (Jinja2) com:
   - Capa: titulo, numero do caso, data, nome do perito
   - Secao 1: Informacoes do Caso (protocolo, descricao, data de abertura)
   - Secao 2: Evidencias (lista com filename, tipo, tamanho, SHA-256)
   - Secao 3: Cadeia de Custodia (tabela com timestamp, acao, usuario, hashes)
   - Secao 4: Analises Realizadas (uma subsecao por job)
     - Nome da tecnica, parametros aplicados
     - Resultados (metricas em tabela)
     - Screenshots/artefatos incorporados ao PDF
     - Hash SHA-256 do resultado
   - Secao 5: Conclusoes (espaco livre para o perito preencher manualmente)
   - Secao 6: Assinatura (espaco para assinatura digital/manual)
5. Converte HTML para PDF usando WeasyPrint
6. Calcula SHA-256 do PDF gerado
7. Atualiza `Report`:
   - status = completed
   - file_path = caminho do PDF
   - sha256 = hash do PDF
8. Registra `CustodyRecord` (report_generated)
9. Notifica frontend (via SSE ou polling)

## Template HTML

O template deve usar CSS puro com:
- Cabecalho institucional (logo, endereco, telefone)
- Numero de pagina no rodape
- Fonte Times New Roman ou Arial 12pt para corpo
- Tabelas com bordas finas para dados tabulares
- Imagens centralizadas com legenda
- Quebra de pagina entre secoes principais (`page-break-after: always`)

## Regras de Negocio Especificas

- **RN-REP-01**: Um laudo so pode ser gerado se todos os jobs selecionados estiverem com status "completed".
- **RN-REP-02**: O laudo deve incluir o hash SHA-256 de cada evidencia e de cada resultado analisado.
- **RN-REP-03**: O laudo e imutavel apos geracao. Se o perito precisar alterar, deve gerar um novo laudo (novo report_id).
- **RN-REP-04**: O template HTML deve ser configuravel via pasta `templates/reports/`.
- **RN-REP-05**: O PDF deve ser acessivel para leitura de tela (tags semanticas HTML5).

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| Job nao completado | Retorna 422: "Todos os jobs devem estar completados antes de gerar o laudo" |
| Template nao encontrado | Usa template padrao "padrao_institucional" e loga warning |
| WeasyPrint falha | Retry 1x, depois marca como failed |
| Artefato de job ausente no disco | Inclui mensagem "Artefato nao disponivel" no laudo |

## Dados de Entrada/Saida

- Entrada: case_id, title, job_ids[], template_name
- Saida: PDF do laudo + registro no banco
- Hash: SHA-256 do PDF registrado em `Report.sha256` e `CustodyRecord`
