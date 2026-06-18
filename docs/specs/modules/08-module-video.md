# 08-module-video.md - Modulo de Analise Forense de Video

## Responsabilidade Unica

Implementar adaptadores forenses para analise estrutural de containers de video (ISO BMFF) e metadados temporais, encapsulando parsers binarios customizados sob a interface `ForensicPlugin`.

## Tecnicas Implementadas

| Nome | Tecnica Legada | Biblioteca Sensivel | Usa GPU |
|------|---------------|---------------------|---------|
| `isomedia_parser` | Analise Estrutura de Arquivo - Video - Parser Isom.ipynb | Parser binario puro (struct) + networkx | Nao |
| `isomedia_compare` | isom_compare_sepael.py + isom_similarity_matrix_sepael.py | networkx + numpy | Nao |
| `stts_analysis` | Analise STTS MP4.ipynb | struct puro (big-endian) | Nao |

## Interfaces Publicas

```python
class ISOMediaParserAdapter(ForensicPlugin):
    name = "isomedia_parser"
    supported_types = ["video"]
    
    def validate_parameters(self, params: dict) -> tuple[bool, str]:
        # Sem parametros obrigatorios
        return True, ""
        
    def analyze(self, evidence_path: str, parameters: dict) -> dict:
        # 1. Abre arquivo MP4/MOV/M4V em modo binario
        # 2. Parseia recursivamente boxes ISO BMFF (ftyp, moov, trak, mdat, etc.)
        # 3. Constroi grafo dirigido da hierarquia (networkx.DiGraph)
        # 4. Extrai metadados forenses: timestamps, timescale, duration, handler, language
        # 5. Salva representacao do grafo e metadados
        # Retorna: success, artifacts=[structure_graph.json, metadata.txt, tree.txt], metrics={box_count, depth}
        pass
```

```python
class STTSAnalysisAdapter(ForensicPlugin):
    name = "stts_analysis"
    supported_types = ["video"]
    
    def validate_parameters(self, params: dict) -> tuple[bool, str]:
        # Sem parametros obrigatorios
        return True, ""
        
    def analyze(self, evidence_path: str, parameters: dict) -> dict:
        # 1. Parseia boxes ate encontrar moov -> trak -> mdia -> minf -> stbl
        # 2. Extrai stts (Time-to-Sample): sample_count e delta por entrada
        # 3. Extrai elst (Edit List): segment_duration, media_time, media_rate
        # 4. Classifica trilha como audio/video/metadados pelo handler type
        # 5. Heuristica de analise:
        #    - Deteccao de drift correction (delta anomalo com count=1)
        #    - Deteccao de VBR em audio (alta diversidade de deltas)
        #    - Deteccao de delta=0, gaps temporais (delta > 3x padrao)
        #    - Analise de Edit List: padding de encoder, skips, edicoes complexas
        # 6. Gera relatorio forense com classificacao de gravidade (INFO, BAIXA, MEDIA, ALTA)
        # Retorna: success, artifacts=[report.txt, timeline_plot.png], metrics={anomaly_count, severity}
        pass
```

## Dependencias de Outros Modulos

- **Core**: `ForensicPlugin` interface
- **Jobs**: Executado via Celery task
- **Custody**: Registra inicio/fim de cada analise

## Fluxo Interno (Exemplo: ISOMedia Parser)

1. Worker Celery chama `ISOMediaParserAdapter.analyze(evidence_path, params)`
2. Abre arquivo em modo binario
3. Le recursivamente boxes:
   - Cada box: le 4 bytes de tamanho (ou 8 se extended), 4 bytes de tipo
   - Boxes container (moov, trak, mdia, minf, stbl) sao parseados recursivamente
   - Trata boxes especiais: `wide`, `free`, boxes de tamanho 0 (ate EOF), tamanho 1 (extended 64-bit)
4. Para boxes forenses (mvhd, tkhd, mdhd, hdlr): extrai campos especificos
5. Constroi grafo `nx.DiGraph` com nós = boxes (atributos: tipo, offset, tamanho, conteudo) e arestas = relacao pai-filho
6. Gera representacao textual da arvore com indentacao
7. Salva grafo em JSON (node_link_data)
8. Retorna dict com metrics e artifacts

## Fluxo Interno (Exemplo: ISOMedia Compare)

1. Worker Celery chama `ISOMediaCompareAdapter.analyze(evidence_path, params)`
2. Requer parametro `reference_paths: list[str]` (caminhos de arquivos padrao)
3. Para cada arquivo padrao:
   - Parseia estrutura em grafo
   - Calcula similaridade estrutural: intersecao / uniao de (tipos de boxes + relacoes pai-filho)
   - Lista diferencas especificas (ex: "Box 'stss': 1 vs 0")
4. Classifica correspondencias: exatas (similaridade=1.0) e parciais (threshold=0.9)
5. Gera matriz de similaridade (heatmap)
6. Retorna dict com matches, similaridades e artifacts

## Regras de Negocio Especificas

- **RN-VID-01**: O parser ISO BMFF deve suportar tamanhos de box de 32 e 64 bits (extended size).
- **RN-VID-02**: A analise STTS deve ser mais rigorosa para trilhas de audio (CBR esperado) e mais tolerante para video (VFR aceitavel).
- **RN-VID-03**: A comparacao estrutural deve considerar nao apenas presenca/ausencia de boxes, mas tambem as relacoes hierarquicas pai-filho.
- **RN-VID-04**: Relatorios de STTS devem usar classificacao de gravidade: INFO, BAIXA, MEDIA, ALTA.

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| Arquivo nao e ISO BMFF valido | Retorna `success=false`, "Formato nao suportado" |
| Box com tamanho invalido | Loga warning, pula box, continua parseamento |
| Nao encontrado moov box | Retorna `success=false`, "Arquivo sem metadados de container" |
| Referencias para comparacao nao encontradas | Retorna 422 na validacao |

## Dados de Entrada/Saida

- Entrada: arquivo de video (MP4, MOV, M4V, 3GP), parametros JSON
- Saida: JSON com metrics + artefatos (JSON, PNG, TXT)
- Artefatos sao salvos em disco e seus paths retornados no dict
