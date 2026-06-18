# test-module-audio.md - Especificacao de Testes: Audio

## Dados de Teste

- `tests/fixtures/audio/`
  - `original.mp3` — MP3 com tags ID3 e header VBR LAME
  - `whatsapp.opus` — Opus gerado pelo WhatsApp (assinatura conhecida)
  - `normal.wav` — WAV PCM padrao
  - `ima_adpcm.wav` — WAV com codec IMA ADPCM (integro)
  - `ima_adpcm_corrupt.wav` — WAV IMA ADPCM com inconsistencias no step_index
  - `sample_60hz_enf.wav` — Audio com sinal de rede eletrica 60 Hz embutido

## Testes Unitarios

### TU-AUD-001: MP3 Parser - Extracao de metadados
- **Adapter**: `MP3ParserAdapter`
- **Entrada**: `tests/fixtures/audio/original.mp3`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Encoder detectado (ex: "LAME3.99")
  - Tags ID3 extraidas corretamente
  - Frame count > 0
  - Bitrate/sample rate consistentes

### TU-AUD-002: MP3 Parser - Inconsistencia de frames
- **Entrada**: MP3 com frames de bitrates diferentes (simulado ou arquivo real)
- **Verificacoes**:
  - Inconsistencias detectadas e reportadas
  - Alerta no relatorio

### TU-AUD-003: Opus Parser - Identificacao WhatsApp
- **Adapter**: `OpusParserAdapter`
- **Entrada**: `tests/fixtures/audio/whatsapp.opus`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Vendor string contem "whatsapp"
  - pre-skip = 104 (Android) ou 312 (padrao)
  - serial number conhecido
  - Plataforma identificada com confianca Alta

### TU-AUD-004: Opus Parser - Validacao estrutural
- **Verificacoes**:
  - Paginas Ogg em sequencia correta
  - BOS unico no inicio, EOS unico no final
  - granule_position crescente
  - Sem gaps na sequencia de paginas

### TU-AUD-005: WAV IMA ADPCM - Integridade total
- **Adapter**: `WAVIMAADPCMAdapter`
- **Entrada**: `tests/fixtures/audio/ima_adpcm.wav` (integro)
- **Saida esperada**: success=true
- **Verificacoes**:
  - Inconsistencias = 0
  - Percentual de inconsistencias = 0%

### TU-AUD-006: WAV IMA ADPCM - Deteccao de corrupcao
- **Entrada**: `tests/fixtures/audio/ima_adpcm_corrupt.wav`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Inconsistencias > 0
  - CSV gerado com detalhes das inconsistencias
  - Grafico de flags gerado

### TU-AUD-007: ENF - Deteccao de 60 Hz
- **Adapter**: `ENFAdapter`
- **Entrada**: `tests/fixtures/audio/sample_60hz_enf.wav`
- **Parametros**: target_freq=60
- **Saida esperada**: success=true
- **Verificacoes**:
  - Frequencia dominante proxima a 60 Hz
  - Desvio calculado ao longo do tempo
  - Grafico ENF gerado

### TU-AUD-008: Espectrograma - Geracao de imagem
- **Adapter**: `SpectrogramAdapter`
- **Entrada**: `tests/fixtures/audio/original.mp3` (convertido para WAV)
- **Parametros**: n_fft=2048, window="hamming"
- **Saida esperada**: success=true
- **Verificacoes**:
  - Artefato PNG gerado
  - Dimensoes coerentes com parametros

### TU-AUD-009: LTAS - Espectro medio
- **Adapter**: `LTASAdapter`
- **Entrada**: `tests/fixtures/audio/original.mp3`
- **Saida esperada**: success=true
- **Verificacoes**:
  - 4 vistas geradas: normal, compensada, ordenada, derivada
  - Artefatos PNG para cada vista

## Testes de Integracao

### TI-AUD-001: Pipeline de audio completo
- **Fluxo**:
  1. Upload de audio Opus
  2. Submissao de 2 jobs: Opus Parser + ENF
  3. Ambos completam
  4. Resultados consistentes e acessiveis

## Mocks/Stubs

- Nenhuma dependencia externa critica (tudo local)
- Parser binarios nao precisam de mock — usam arquivos reais de teste
