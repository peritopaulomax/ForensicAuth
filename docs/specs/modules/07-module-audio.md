# 07-module-audio.md - Modulo de Analise Forense de Audio

## Responsabilidade Unica

Implementar adaptadores forenses para todas as tecnicas de analise de audio dos legados, encapsulando parsers binarios customizados e analises espectrais sob a interface `ForensicPlugin`.

## Tecnicas Implementadas

| Nome | Tecnica Legada | Biblioteca Sensivel | Usa GPU |
|------|---------------|---------------------|---------|
| `mp3_parser` | Analise MP3.ipynb | Parser binario puro (struct) | Nao |
| `opus_parser` | Analise_Opus.ipynb | Parser binario puro (struct) | Nao |
| `wav_ima_adpcm` | Analise de Consistencia Indice WAV IMA ADPCM.ipynb | numpy + struct | Nao |
| `audio_enf` | interface_gradio_Paulo.ipynb (aba ENF) | scipy (FIR, Hilbert) | Nao |
| `audio_quantization` | interface_gradio_Paulo.ipynb (aba Quantizacao) | numpy + matplotlib | Nao |
| `audio_dc_local` | interface_gradio_Paulo.ipynb (aba DC Local) | numpy | Nao |
| `audio_spectrogram` | interface_gradio_Paulo.ipynb (aba Espectrograma) | `scipy.signal.spectrogram` | Nao |
| `audio_ltas` | interface_gradio_Paulo.ipynb (aba LTAS) | scipy.signal (Welch) | Nao |
| `audio_stereo_residual` | interface_gradio_Paulo.ipynb (Residuo Estereo) | numpy | Nao |

## Interfaces Publicas

Cada tecnica implementa `ForensicPlugin`:

```python
class MP3ParserAdapter(ForensicPlugin):
    name = "mp3_parser"
    supported_types = ["audio"]
    
    def validate_parameters(self, params: dict) -> tuple[bool, str]:
        # Sem parametros obrigatorios
        return True, ""
        
    def analyze(self, evidence_path: str, parameters: dict) -> dict:
        # 1. Abre arquivo MP3 em modo binario
        # 2. Parseia tags ID3v2 e ID3v1
        # 3. Itera frames MP3, decodifica headers (bitrate, sample rate, canal)
        # 4. Detecta headers VBR (Xing/Info/VBRI) e encoder signature
        # 5. Verifica consistencia de parametros entre frames
        # Retorna: success, artifacts=[relatorio.txt, grafico_frames.png], metrics={frame_count, inconsistencies, encoder}
        pass
```

```python
class ENFAdapter(ForensicPlugin):
    name = "audio_enf"
    supported_types = ["audio"]
    
    def validate_parameters(self, params: dict) -> tuple[bool, str]:
        # opcional: target_freq (50 ou 60, default 60 para BR), band_width (0.5 Hz)
        pass
        
    def analyze(self, evidence_path: str, parameters: dict) -> dict:
        # 1. Le audio via scipy.io.wavfile ou soundfile
        # 2. Aplica filtro FIR passa-banda em torno de target_freq
        # 3. Transformada de Hilbert para envelope
        # 4. Calcula frequencia instantanea ao longo do tempo
        # 5. Gera grafico de desvio de frequencia
        # Retorna: success, artifacts=[enf_plot.png, enf_data.csv], metrics={mean_deviation, max_deviation}
        pass
```

## Dependencias de Outros Modulos

- **Core**: `ForensicPlugin` interface, `Settings`
- **Jobs**: Executado via Celery task
- **Custody**: Registra inicio/fim de cada analise

## Fluxo Interno (Exemplo: Opus Parser)

1. Worker Celery chama `OpusParserAdapter.analyze(evidence_path, params)`
2. Abre arquivo em modo binario
3. Busca por paginas Ogg (`OggS` magic bytes)
4. Para cada pagina: valida flags (BOS, EOS, CONT), serial number, granule position
5. Extrai headers Opus: `OpusHead` (canais, pre-skip, input sample rate) e `OpusTags` (vendor string)
6. Identifica plataforma por assinaturas:
   - vendor string contendo "whatsapp", "telegram", "discord", "ffmpeg"
   - pre-skip: 104 = WhatsApp Android; 312 = libopus padrao
   - serial number: 0x00000000 = WhatsApp Android; 0x00000064 = WhatsApp iOS
7. Analisa TOC bytes dos pacotes de audio para verificar modo (SILK/Hybrid/CELT)
8. Valida estrutura conforme RFC 7845
9. Gera relatorio textual com assinaturas identificadas e nivel de confianca
10. Retorna dict com metrics e artifacts

## Fluxo Interno (Exemplo: WAV IMA ADPCM)

1. Worker Celery chama `WAVIMAADPCMAdapter.analyze(evidence_path, params)`
2. Le cabecalho WAV, valida formato IMA ADPCM (0x0011)
3. Extrai blocos de dados
4. Para cada bloco:
   - Le valor inicial do preditor e step_index do cabecalho
   - Processa nibbles (4 bits) simulando decodificacao
   - Atualiza step_index via tabela IndexTab
   - Compara step_index calculado ao final do bloco com o step_index armazenado no proximo bloco
5. Registra inconsistencias: bloco, sample, timestamp, indices calculado vs. header, diferenca
6. Gera grafico de flags de inconsistencia por canal
7. Exporta CSV com detalhes
8. Retorna dict com metrics (total_inconsistencies, percentage) e artifacts (plot.png, data.csv)

## Regras de Negocio Especificas

- **RN-AUD-01**: Parsers binarios de MP3 e Opus NAO podem ser substituidos por bibliotecas de alto nivel (ex: mutagen, pydub) que ocultariam frames, metadados ou assinaturas.
- **RN-AUD-02**: A analise ENF deve suportar frequencias de rede de 50 Hz e 60 Hz, com default 60 Hz (Brasil).
- **RN-AUD-03**: A analise de IMA ADPCM deve gerar CSV com todos os detalhes das inconsistencias para auditoria.
- **RN-AUD-04**: O espectrograma deve suportar controle de pontos FFT, tipo de janela (Hamming, Hanning, Blackman, Blackman-Harris, Kaiser) e reamostragem.

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| Arquivo de audio corrompido | Retorna `success=false`, log do erro |
| Formato nao suportado pela tecnica | Retorna 422 na validacao do job |
| Amostra de audio muito curta para ENF | Retorna `success=false`, "Audio muito curto" |
| WAV nao e IMA ADPCM | Retorna `success=false`, "Formato WAV nao suportado para esta tecnica" |

## Dados de Entrada/Saida

- Entrada: arquivo de audio (MP3, OGG/Opus, WAV), parametros JSON
- Saida: JSON com metrics + artefatos (PNG, CSV, TXT)
- Artefatos sao salvos em disco e seus paths retornados no dict
