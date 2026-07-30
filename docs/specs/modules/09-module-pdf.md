# 09-module-pdf.md - Modulo de Analise Forense de PDF

## Responsabilidade Unica

Implementar adaptadores forenses para analise estrutural de documentos PDF, deteccao de manipulacoes e geracao de overlays visuais, encapsulando PyMuPDF, pdfminer e tokenizadores customizados sob a interface `ForensicPlugin`.

## Tecnicas Implementadas

| Nome | Motor / pipeline | Biblioteca Sensivel | Usa GPU |
|------|------------------|---------------------|---------|
| `pdf_structure_metrics` / `pdf_structure_similarity` | Metricas e grafo estrutural | pypdf + pdfminer.six + networkx | Nao |
| `pdf_font_color_overlay` | Overlay por fonte/cor | PyMuPDF (fitz) | Nao |
| `pdf_forensic_extract` | Extracao forense incremental (incl. deteccao TouchUp no scanner) | PyMuPDF + pypdf + pyHanko | Nao |

`pdf_forensic_extract` extrai imagens embutidas, metadados (/Info + XMP), versoes incrementais (`%%EOF`) e assinaturas digitais via motor **pdfsig_forense** (PAdES/CAdES, enfase ICP-Brasil): digest/ByteRange, cadeia matematica (inclusive orfaos), DSS/VRI/LCR/OCSP, carimbos TSA, revisoes incrementais, nivel PAdES e relatório Markdown humanizado. Artefatos: `signatures_report.txt` (relatório), `signatures.json`, PEMs em `signatures/certs/`. Ancora recomendada: raiz oficial do ITI em `models/icpbrasil/` ou `PDF_SIG_TRUST_ANCHORS`; sem isso usa raiz do arquivo e marca circularidade. Nao substitui `validar.iti.gov.br`.

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

## Dependencias de Outros Modulos

- **Core**: `ForensicPlugin` interface
- **Jobs**: Executado via Celery task
- **Custody**: Registra inicio/fim de cada analise

## Fluxo Interno (Exemplo: extracao forense + TouchUp no scanner)

1. Worker Celery chama o plugin ativo (ex.: `pdf_forensic_extract`).
2. O motor `pdf_forensic_scanner` abre o PDF e percorre content streams.
3. Quando aplicavel, o interpretador detecta marked content `TouchUp_TextEdit`,
   refina geometria e registra regioes no relatorio da extracao.
4. Artefatos e metricas voltam pelo contrato `ForensicPlugin` (sem plugin
   dedicado `pdf_touchup` na superficie atual).

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
