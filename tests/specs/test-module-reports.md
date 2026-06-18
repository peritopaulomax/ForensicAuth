# test-module-reports.md - Especificacao de Testes: Relatorios

## Testes Unitarios

### TU-REP-001: Validacao de jobs antes de gerar laudo
- **Funcao**: `ReportService.validate_jobs_for_report(case_id, job_ids)`
- **Setup**: Caso com 3 jobs (2 completed, 1 pending)
- **Entrada**: job_ids dos 3 jobs
- **Saida esperada**: Lanca `ValueError` — "Todos os jobs devem estar completados"

### TU-REP-002: Validacao com jobs de outro caso
- **Setup**: Job de outro caso
- **Entrada**: job_ids incluindo job de outro caso
- **Saida esperada**: Lanca `PermissionError` — "Job nao pertence ao caso"

### TU-REP-003: Geracao de HTML do laudo
- **Funcao**: `ReportService.render_html(report, case, jobs, custody_records)`
- **Setup**: Dados completos de caso, evidencias, jobs e custodia
- **Saida esperada**: String HTML valida
- **Verificacoes**:
  - HTML contem titulo do caso
  - HTML contem tabela de evidencias com SHA-256
  - HTML contem secao de cadeia de custodia
  - HTML contem secao para cada job com metricas
  - HTML contem espaco para assinatura

### TU-REP-004: Conversao HTML para PDF
- **Funcao**: `ReportService.html_to_pdf(html_string, output_path)`
- **Setup**: HTML valido
- **Saida esperada**: Arquivo PDF criado no path
- **Verificacoes**:
  - PDF existe e tamanho > 0
  - PDF contem pelo menos 2 paginas

### TU-REP-005: Hash do laudo
- **Funcao**: `ReportService.compute_pdf_hash(file_path)`
- **Setup**: PDF gerado
- **Saida esperada**: SHA-256 de 64 caracteres
- **Verificacoes**:
  - Hash identico se gerado novamente com mesmo HTML
  - Hash diferente se HTML muda

## Testes de Integracao

### TI-REP-001: Fluxo completo de geracao de laudo
- **Fluxo**:
  1. Cria caso, upload de evidencia, 2 jobs completados
  2. POST /api/v1/reports com case_id e job_ids
  3. Recebe report_id com status="pending"
  4. Worker processa (modo eager)
  5. GET /api/v1/reports/{id} → status="completed", sha256 preenchido
  6. GET /api/v1/reports/{id}/download → PDF binario valido
  7. Verifica: CustodyRecord de report_generated existe
  8. Verifica: Cadeia de custodia do caso e valida

### TI-REP-002: Laudo imutavel
- **Fluxo**:
  1. Gera laudo (report_1)
  2. Tenta "editar" o laudo (nao existe endpoint para isso)
  3. Verifica: Nao ha endpoint PUT/PATCH para reports
  4. Verifica: Tentativa de alterar registro no banco e bloqueada

### TI-REP-003: Template customizado
- **Fluxo**:
  1. Cria template HTML customizado em `templates/reports/custom.html`
  2. Gera laudo com template="custom"
  3. Verifica: Laudo usa o template customizado

## Mocks/Stubs

- Mock de WeasyPrint para testes unitarios (evita dependencia de sistema)
- Mock de jobs com resultados deterministicos
- Template HTML minimo para testes
