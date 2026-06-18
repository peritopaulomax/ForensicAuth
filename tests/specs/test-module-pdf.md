# test-module-pdf.md - Especificacao de Testes: PDF

## Dados de Teste

- `tests/fixtures/pdf/`
  - `original.pdf` — PDF nativo sem manipulacao
  - `edited_touchup.pdf` — PDF editado no Adobe Acrobat (TouchUp_TextEdit presente)
  - `multi_font.pdf` — PDF com multiplas fontes embutidas e referenciadas
  - `reference_set/` — Pasta com 2 PDFs padrao da mesma origem

## Testes Unitarios

### TU-PDF-001: PDF Structure - Grafico de objetos
- **Adapter**: `PDFStructureAdapter`
- **Entrada**: `tests/fixtures/pdf/original.pdf`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Grafo JSON gerado com nos (objetos) e arestas (referencias)
  - Trailer, Root, Catalog, Pages presentes
  - object_count > 0

### TU-PDF-002: PDF Structure - Similaridade entre PDFs
- **Entrada**: `tests/fixtures/pdf/original.pdf`
- **Parametros**: reference_paths=[`reference_set/ref1.pdf`]
- **Saida esperada**: success=true
- **Verificacoes**:
  - Similaridade de Jaccard calculada
  - Kernel Weisfeiler-Lehman normalizado calculado
  - Heatmap gerado

### TU-PDF-003: PDF Font Overlay - Mapeamento de fontes
- **Adapter**: `PDFFontOverlayAdapter`
- **Entrada**: `tests/fixtures/pdf/multi_font.pdf`
- **Saida esperada**: success=true
- **Verificacoes**:
  - PDF overlay gerado
  - Cada fonte recebeu cor distinta
  - Legenda TXT gerada com nome, RGB, embedding, tipo, tag subset
  - Fontes subset detectadas (tag de 6 chars + nome)

### TU-PDF-004: PDF Font Overlay - Modo by_family
- **Parametros**: mode="by_family"
- **Verificacoes**:
  - Fontes do mesmo family compartilham cor
  - Diferente de modo "by_subset" (default)

### TU-PDF-005: PDF TouchUp Scan - Deteccao de edicao
- **Adapter**: `PDFTouchUpAdapter`
- **Entrada**: `tests/fixtures/pdf/edited_touchup.pdf`
- **Saida esperada**: success=true
- **Verificacoes**:
  - touchup_count > 0
  - Regioes de edicao detectadas com coordenadas
  - PDF com highlights amarelos gerado
  - Relatorio TXT com pagina, tipo, coordenadas, texto

### TU-PDF-006: PDF TouchUp Scan - PDF sem edicao
- **Entrada**: `tests/fixtures/pdf/original.pdf`
- **Saida esperada**: success=true
- **Verificacoes**:
  - touchup_count = 0
  - PDF de saida identico ao original (ou sem highlights)

### TU-PDF-007: PDF TouchUp Scan - Texto invisivel
- **Entrada**: PDF com texto invisivel (Tr=3)
- **Verificacoes**:
  - invisible_text_count > 0
  - Texto invisivel reportado no relatorio

## Testes de Integracao

### TI-PDF-001: Pipeline de PDF completo
- **Fluxo**:
  1. Upload de PDF
  2. Submissao de 3 jobs: Structure, Font Overlay, TouchUp Scan
  3. Todos completam
  4. Resultados correlacionaveis (ex: se TouchUp encontrou edicao, Structure pode mostrar anomalias)

## Mocks/Stubs

- PDFs de teste devem ser pequenos (< 1MB, poucas paginas)
- Criar PDFs de teste programaticamente com reportlab ou PyMuPDF se necessario
