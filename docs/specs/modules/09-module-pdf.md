# 09-module-pdf.md - Modulo de Analise Forense de PDF

## Responsabilidade Unica

Implementar adaptadores forenses para analise estrutural de documentos PDF, deteccao de manipulacoes e geracao de overlays visuais, encapsulando PyMuPDF, pdfminer e tokenizadores customizados sob a interface `ForensicPlugin`.

## Tecnicas Implementadas

| Nome | Tecnica Legada | Biblioteca Sensivel | Usa GPU |
|------|---------------|---------------------|---------|
| `pdf_structure` | estrutura_pdf_metricas.ipynb | pypdf + pdfminer.six + networkx | Nao |
| `pdf_font_overlay` | pdf_font_color_overlay.py | PyMuPDF (fitz) | Nao |
| `pdf_touchup_scan` | pdf_forensic_scanner.py | PyMuPDF + tokenizador customizado | Nao |

## Interfaces Publicas

```python
class PDFStructureAdapter(ForensicPlugin):
    name = "pdf_structure"
    supported_types = ["pdf"]
    
    def validate_parameters(self, params: dict) -> tuple[bool, str]:
        # Sem parametros obrigatorios
        return True, ""
        
    def analyze(self, evidence_path: str, parameters: dict) -> dict:
        # 1. Parseia arvore de objetos indiretos do PDF
        # 2. Constroi grafo dirigido (trailer, dicionarios, streams, referencias)
        # 3. Calcula similaridade de Jaccard e kernel Weisfeiler-Lehman se houver PDFs de referencia
        # 4. Gera visualizacao do grafo (Graphviz ou PyVis)
        # Retorna: success, artifacts=[graph.json, similarity_matrix.png, report.txt], metrics={object_count, xref_count}
        pass
```

```python
class PDFFontOverlayAdapter(ForensicPlugin):
    name = "pdf_font_overlay"
    supported_types = ["pdf"]
    
    def validate_parameters(self, params: dict) -> tuple[bool, str]:
        # opcional: mode ("by_subset" default, "by_family")
        return True, ""
        
    def analyze(self, evidence_path: str, parameters: dict) -> dict:
        # 1. Abre PDF com PyMuPDF
        # 2. Itera paginas e content streams (incluindo Form XObjects)
        # 3. Mapeia cada span de texto ao seu /BaseFont
        # 4. Diferencia subsets (tags de 6 chars) de embeddings completos
        # 5. Gera paleta de cores distinta por fonte (Okabe-Ito + HSV)
        # 6. Adiciona retangulos semi-transparentes sobre cada span (blend Multiply)
        # 7. Insere numeros de legenda no canto superior-esquerdo
        # 8. Exporta legenda TXT com: nome da fonte, RGB/HEX, embedding, tipo, tag subset
        # Retorna: success, artifacts=[overlayed_pdf.pdf, legend.txt], metrics={font_count, embedded_count}
        pass
```

```python
class PDFTouchUpAdapter(ForensicPlugin):
    name = "pdf_touchup_scan"
    supported_types = ["pdf"]
    
    def validate_parameters(self, params: dict) -> tuple[bool, str]:
        return True, ""
        
    def analyze(self, evidence_path: str, parameters: dict) -> dict:
        # 1. Abre PDF com PyMuPDF
        # 2. Tokeniza content streams: strings (...), hex <...>, arrays, names, numbers, operators, inline images BI..EI
        # 3. Simula estado grafico: pilha q/Q, matrizes cm, CTM
        # 4. Simula objetos de texto: BT/ET, Tm, Td, Tj, TJ
        # 5. Detecta marked content: MP, BDC, BMC, EMC
        # 6. Identifica blocos TouchUp_TextEdit
        # 7. Calcula bounding boxes aproximadas dos glifos
        # 8. Refina geometria com page.search_for em janela expandida
        # 9. Detecta texto invisivel (Tr=3)
        # 10. Gera PDF com highlights amarelos
        # 11. Gera relatorio TXT com: pagina, tipo, coordenadas, texto
        # Retorna: success, artifacts=[highlighted_pdf.pdf, forensic_report.txt], metrics={touchup_count, invisible_text_count}
        pass
```

## Dependencias de Outros Modulos

- **Core**: `ForensicPlugin` interface
- **Jobs**: Executado via Celery task
- **Custody**: Registra inicio/fim de cada analise

## Fluxo Interno (Exemplo: PDF TouchUp Scan)

1. Worker Celery chama `PDFTouchUpAdapter.analyze(evidence_path, params)`
2. Abre PDF com `fitz.open(evidence_path)`
3. Para cada pagina:
   - Obtem content stream bruto (`page.read_contents()`)
   - Tokeniza sequencia de bytes em tokens PDF validos
   - Interpretador `ContentInterpreter` simula:
     - Pilha de graficos (`q` push, `Q` pop)
     - Matriz CTM (`cm`)
     - Texto: `BT`/`ET`, `Tm` (text matrix), `Td` (translate), `Tj`/`TJ` (show text)
     - Fonte: `/Font` resource, Widths, DW, CID
     - Marked content: `BDC`/`BMC` ... `EMC`, propriedade `TouchUp_TextEdit`
   - Para cada bloco TouchUp encontrado:
     - Calcula bbox aproximada somando avancos de glifos
     - Refina com `page.search_for(texto)` numa janela expandida (+10 pts)
     - Agrupa retangulos por linha (baseline clustering) quando area extensa
   - Detecta texto invisivel: modo de renderizacao `Tr=3`
4. Gera copia do PDF com anotacoes de highlight amarelo nas regioes detectadas
5. Gera relatorio TXT formatado
6. Retorna dict com metrics e artifacts

## Regras de Negocio Especificas

- **RN-PDF-01**: O tokenizador customizado de content streams NAO pode ser substituido por parser generico que nao expoe operadores PDF individuais.
- **RN-PDF-02**: O overlay de fontes deve usar blend mode `Multiply` e opacidade configuravel (default 0.3).
- **RN-PDF-03**: A deteccao de TouchUp_TextEdit deve incluir agrupamento por baseline para areas extensas de texto editado.
- **RN-PDF-04**: O relatorio forense deve incluir coordenadas em user space e texto extraido de cada regiao detectada.

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| PDF corrompido ou protegido por senha | Retorna `success=false`, log do erro |
| Content stream malformado | Loga warning, continua processamento da pagina |
| Fonte sem metrics disponiveis | Usa estimativa de largura (0.5 * font_size) |
| Sem TouchUp_TextEdit encontrado | Retorna `success=true`, metrics={touchup_count: 0} |

## Dados de Entrada/Saida

- Entrada: arquivo PDF, parametros JSON
- Saida: JSON com metrics + artefatos (PDF, TXT, JSON, PNG)
- Artefatos sao salvos em disco e seus paths retornados no dict
