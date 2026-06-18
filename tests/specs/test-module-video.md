# test-module-video.md - Especificacao de Testes: Video

## Dados de Teste

- `tests/fixtures/video/`
  - `original.mp4` — MP4 nativo, estrutura ISO BMFF padrao
  - `edited_stts.mp4` — MP4 com edicao na timeline (STTS/ELST manipulados)
  - `reference_set/` — Pasta com 3 MP4s padrao do mesmo encoder

## Testes Unitarios

### TU-VID-001: ISO BMFF Parser - Extracao de estrutura
- **Adapter**: `ISOMediaParserAdapter`
- **Entrada**: `tests/fixtures/video/original.mp4`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Grafo JSON gerado com nos e arestas
  - Boxes principais presentes: ftyp, moov, trak, mdat
  - Metadados extraidos: timescale, duration, creation_time
  - Tree.txt com hierarquia indentada

### TU-VID-002: ISO BMFF Parser - Box de tamanho estendido
- **Entrada**: MP4 com box de 64 bits (tamanho=1, extended size presente)
- **Verificacoes**:
  - Parser le tamanho estendido corretamente
  - Box incluido no grafo com tamanho correto

### TU-VID-003: ISO BMFF Compare - Match exato
- **Adapter**: `ISOMediaCompareAdapter`
- **Entrada**: `tests/fixtures/video/original.mp4`
- **Parametros**: reference_paths=[`reference_set/ref1.mp4`]
- **Setup**: ref1.mp4 tem estrutura identica
- **Saida esperada**: success=true
- **Verificacoes**:
  - Similaridade = 1.0
  - Classificado como "exato"

### TU-VID-004: ISO BMFF Compare - Diferenca estrutural
- **Entrada**: `tests/fixtures/video/edited_stts.mp4`
- **Parametros**: reference_paths=[`reference_set/ref1.mp4`]
- **Saida esperada**: success=true
- **Verificacoes**:
  - Similaridade < 1.0
  - Diferencas listadas (ex: box X ausente, relacao Y diferente)

### TU-VID-005: STTS Analysis - Deteccao de edicao
- **Adapter**: `STTSAnalysisAdapter`
- **Entrada**: `tests/fixtures/video/edited_stts.mp4`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Anomalias detectadas (delta=0, gaps, edicoes na ELST)
  - Classificacao de gravidade >= MEDIA
  - Relatorio com explicacao da anomalia

### TU-VID-006: STTS Analysis - Arquivo integro
- **Entrada**: `tests/fixtures/video/original.mp4`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Sem anomalias criticas
  - Classificacao de gravidade = INFO ou BAIXA
  - Trilha de audio com deltas constantes (CBR)

## Testes de Integracao

### TI-VID-001: Pipeline de video completo
- **Fluxo**:
  1. Upload de video MP4
  2. Submissao de 2 jobs: ISOMedia Parser + STTS Analysis
  3. Ambos completam
  4. Resultados estruturais e temporais correlacionaveis

## Mocks/Stubs

- Arquivos MP4 de teste devem ser pequenos (< 5MB, poucos segundos de video)
- Gerar via ffmpeg se necessario: `ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=30 -pix_fmt yuv420p test.mp4`
