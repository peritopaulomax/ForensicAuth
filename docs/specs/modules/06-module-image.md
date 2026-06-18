# 06-module-image.md - Modulo de Analise Forense de Imagem

## Responsabilidade Unica

Implementar adaptadores forenses para todas as tecnicas de analise de imagem dos legados, encapsulando bibliotecas especificas (jpegio, libzero, opencv, insightface, etc.) sob a interface `ForensicPlugin`.

## Tecnicas Implementadas

| Nome | Tecnica Legada | Biblioteca Sensivel | Usa GPU |
|------|---------------|---------------------|---------|
| `prnu` | PRNU.ipynb + src/ | Pipeline wavelet customizado | Nao |
| `prnu_localizado` | PRNU Localizado.ipynb | Pipeline wavelet customizado | Nao |
| `dct_artifacts` | Inconsistencias_Artefatos_Blocos_DCT.ipynb | `jpegio` + estimativaq.py | Nao |
| `jpeg_ghosts` | JPEG_Ghosts.ipynb | OpenCV + DCT manual | Nao |
| `bag_extraction` | ExtraçãoBAG.ipynb | OpenCV + scipy | Nao |
| `zero_grid` | ZERO.ipynb | `iio`, `cffi`, `libzero.so_` | Nao |
| `double_compression` | Deteccao_Dupla_Compressao.ipynb | `jpegio` + FFT | Nao |
| `quantization_estimation` | Estimativa_M_Quantizacao.ipynb | scipy.fftpack.dct + FFT | Nao |
| `resampling` | Reamostragem_Versao2.ipynb | skimage (Radon) + scipy | Nao |
| `patchmatch` | patchmatch.py + postprocessing.py | Numba + Zernike customizado | Nao |
| `copy_move_pca` | Peritus/copy-move-forgery-detection-pca | Numba + OpenCV PCA | Nao |
| `deepfake_similarity` | Sepaelv1_Deepfake_detection_prediction_example.ipynb | `insightface`, OpenCV | Sim |
| `synthetic_image_detection` | app_Gradio_Sepael_Models_Noise_FFT_V4.py | PyTorch, Transformers, XGBoost | Sim |

## Interfaces Publicas

Cada tecnica implementa `ForensicPlugin`:

```python
class PRNUAdapter(ForensicPlugin):
    name = "prnu"
    supported_types = ["imagem"]
    
    def validate_parameters(self, params: dict) -> tuple[bool, str]:
        # requer: fingerprint_path (str) ou camera_id (UUID)
        # opcional: mode ("full", "cropped", "scaled"), block_size (int)
        pass
        
    def analyze(self, evidence_path: str, parameters: dict) -> dict:
        # 1. Carrega fingerprint .prnu do banco ou path
        # 2. Extrai residuo de ruido da imagem questionada via NoiseExtractFromImage
        # 3. Calcula correlacao cruzada e PCE via maindir.py
        # 4. Gera mapa de correlacao e metricas
        # Retorna: success, artifacts=[heatmap.png, correlation_3d.png], metrics={pce, p_value, p_fa}
        pass
```

## Dependencias de Outros Modulos

- **Core**: `ForensicPlugin` interface, `PLUGINS` registry
- **Jobs**: Executado via Celery task
- **Custody**: Registra inicio/fim de cada analise

## Fluxo Interno (Exemplo: PRNU)

1. Worker Celery chama `PRNUAdapter.analyze(evidence_path, params)`
2. Adapter carrega a imagem via OpenCV (cv2.imread)
3. Extrai residuo de ruido usando `NoiseExtractFromImage` (src/Filter.py)
4. Carrega fingerprint PRNU (arquivo .prnu previamente calculado)
5. Calcula correlacao cruzada via `crosscorr` (src/Functions.py)
6. Calcula PCE via `PCE` (src/maindir.py)
7. Se modo localizado: divide em blocos e calcula mapa de correlacao
8. Salva artefatos: heatmap de correlacao, plot 3D da superficie
9. Retorna dict com metrics e artifacts

## Fluxo Interno (Exemplo: Detecção de imagens sintéticas)

1. Worker Celery chama `Detecção de imagens sintéticasAdapter.analyze(evidence_path, params)`
2. Verifica disponibilidade de GPU (se indisponivel, retorna erro)
3. Preprocessa imagem (resize, normalizacao)
4. Extrai resíduos de ruido: mediana, NLM, NPR
5. Aplica FFT aos residuos
6. Extrai features GLCM do espectro FFT
7. Executa modelos: huggingface model, sdxl-flux-detector, modelo NPR ResNet-50
8. Executa Modelo 1 (XGBoost) e Modelo 2 (ensemble ponderado log-odds)
9. Gera visualizacoes: residuos, espectros FFT, ELA
10. Retorna dict com scores de cada modelo, score agregado, classificacao final, artifacts

## Regras de Negocio Especificas

- **RN-IMG-01**: `jpegio` NAO pode ser substituido. O adapter deve chama-lo diretamente para ler coeficientes DCT quantizados.
- **RN-IMG-02**: `libzero.so_` e `cffi` devem ser carregados corretamente pelo adapter ZERO.
- **RN-IMG-03**: Modelos de IA (Detecção de imagens sintéticas, Deepfake) devem ser carregados uma unica vez no startup do worker para evitar overhead de VRAM.
- **RN-IMG-04**: O path dos modelos pre-treinados deve ser configuravel via `Settings` (MODELS_DIR).
- **RN-IMG-05**: Resultados de PRNU devem incluir PCE, p-value e P_FA para decisao estatistica.

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| Imagem corrompida | Retorna `success=false`, log do erro |
| Fingerprint nao encontrado | Retorna 422 na submissao do job |
| Modelo IA nao carregado | Retorna `success=false`, "Modelo indisponivel" |
| GPU OOM no Detecção de imagens sintéticas/Deepfake | Retry apos liberacao de VRAM, max 3x |
| jpegio falha ao ler JPEG | Retorna `success=false`, log detalhado |

## Dados de Entrada/Saida

- Entrada: arquivo de imagem (JPG, PNG, BMP, TIFF), parametros JSON
- Saida: JSON com metrics + artefatos (PNG, JSON, CSV, MAT)
- Artefatos sao salvos em disco e seus paths retornados no dict
