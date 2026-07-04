# Dependency Graph — ForensicAuth

## Missão
Mapear dependências reais do sistema.

## Visão Geral
O ForensicAuth depende de um stack Python/FastAPI no backend, React no frontend, PostgreSQL/Redis como infraestrutura de dados e fila, e dezenas de bibliotecas científicas e de ML para processamento forense. O storage é filesystem local.

## Dependências Internas

| Componente | Depende de |
|---|---|
| API FastAPI | Services, Core, Models, Config, Database |
| Services | Models, Database, Core, Config, outros Services |
| Core/Plugins | Core/Legacy, Models (weights), Config |
| Celery Workers | Services, Core, Models |
| Frontend React | Backend API REST |

## Dependências Externas

| Dependência | Tipo | Criticidade | Uso |
|---|---|---|---|
| Python 3.11+ | Runtime | Tier 0 | Backend e workers |
| FastAPI >= 0.104 | Framework | Tier 0 | API HTTP |
| Uvicorn | Servidor | Tier 0 | ASGI server |
| SQLAlchemy >= 2.0 | ORM | Tier 0 | Persistência |
| Alembic | Migration | Tier 2 | Instalado mas não usado como motor principal |
| psycopg2-binary | Driver | Tier 0 | PostgreSQL |
| Pydantic v2 | Validação | Tier 0 | Schemas e config |
| python-jose | Auth | Tier 0 | JWT |
| passlib[bcrypt] | Auth | Tier 0 | Hash de senhas |
| Celery >= 5.3 | Fila | Tier 0 | Jobs assíncronos |
| Redis >= 5.0 | Cache/Fila | Tier 0 | Broker e backend Celery, lock GPU |
| PyTorch | ML | Tier 1 | Inferência GPU/CPU |
| torchvision | ML | Tier 1 | Visão computacional |
| transformers | ML | Tier 1 | Modelos HuggingFace |
| onnxruntime | ML | Tier 1 | Inferência ONNX |
| OpenCV (headless) | Imagem | Tier 1 | Processamento de imagem |
| NumPy / SciPy | Computação | Tier 1 | Arrays e sinais |
| Pillow | Imagem | Tier 1 | Manipulação de imagens |
| scikit-learn / scikit-image | ML/Imagem | Tier 1 | Algoritmos clássicos |
| PyMuPDF (fitz) | PDF | Tier 1 | Parsing PDF |
| pdfminer.six | PDF | Tier 1 | Extração de texto PDF |
| jpegio | Forense | Tier 1 | Coeficientes DCT JPEG |
| librosa / soundfile | Áudio | Tier 1 | Processamento de áudio |
| IMDL-BenCo | ML | Tier 1 | Localização de manipulação |
| timm / einops / fvcore | ML | Tier 2 | Modelos de visão |
| WeasyPrint | PDF | Tier 2 | Geração de laudos |
| Jinja2 | Templating | Tier 2 | Templates de relatório |
| networkx / pydot / pyvis | Grafos | Tier 2 | Visualização de estruturas |
| numba | Performance | Tier 2 | Aceleração NumPy |
| huggingface_hub | ML | Tier 2 | Download de modelos |
| gdown | ML | Tier 2 | Download de pesos |

## Bancos

| Banco | Tecnologia | Uso | Criticidade |
|---|---|---|---|
| PostgreSQL | 15+ | Produção | Tier 0 |
| SQLite | nativo | Dev/testes | Tier 1 |

## Caches

| Cache | Tecnologia | Uso |
|---|---|---|
| Redis | 7+ | Broker Celery, backend resultados, lock GPU, visibilidade de fila |

## Filas

| Fila | Tecnologia | Uso |
|---|---|---|
| `celery` | Celery + Redis | Jobs CPU e gerais |
| `gpu` | Celery + Redis | Jobs ML/GPU serializados |

## Storage

| Storage | Tecnologia | Objetos |
|---|---|---|
| Filesystem local | Volumes Docker/bind mounts | uploads, results, derivatives, models, peritus_cases |

## APIs Externas

Nenhuma API externa obrigatória. O sistema opera 100% local/offline (RNF-01). Downloads de pesos são feitos via scripts manuais (gdown, huggingface_hub, wget) e não em runtime.

## Modelos de IA

| Modelo/Técnica | Origem | Local |
|---|---|---|
| Ensemble sintético | HF + XGBoost | `models/` + `src/backend/core/legacy/synthetic_image_detection/` |
| CAMO | BitMind/UCF | `vendor/`, `models/camo/` |
| CLIDE | CLIP + whitening | `vendor/clide/`, `models/clide/` |
| DeeCLIP | DeeCLIP oficial | `vendor/deeclip/` |
| EFFORT/SAFE/IAPL | Detectores sintéticos | `vendor/`, `models/` |
| IMDL-BenCo | TruFor, CAT-Net, etc. | `vendor/`, `models/imdlbenco/` |
| SAFIRE | SAM + SAFIRE | `vendor/`, `models/safire/` |
| Noiseprint | GRIP-UNINA | `vendor/`, `models/noiseprint/` |
| DistilDire | ICML 2024 | `vendor/distildire/`, `models/distildire/` |
| VideoFACT/STIL/LFV | Detecção de fake em vídeo | `vendor/`, `models/` |
| PAD | Presentation Attack | `vendor/`, `models/pad/` |
| PRNU / Copy-Move / PatchMatch | Clássicas | `src/backend/core/legacy/`, `tools/` |

## Grafo Resumido

```text
Usuario
↓
React SPA (nginx)
↓ /api/v1
FastAPI
↓
Services → Models (SQLAlchemy)
↓
PostgreSQL / SQLite
↓
Custody Records (imutáveis)

FastAPI / Celery Workers
↓
Redis (broker + lock GPU)
↓
Plugins Forenses
↓
Legacy / Vendor / Models (PyTorch/ONNX)
↓
CPU / GPU

Filesystem
↓
uploads / results / derivatives / models
```

## Falhas em Cascata

| Falha | Impacto |
|---|---|
| PostgreSQL indisponível | Todo o sistema paralisa (login, casos, jobs) |
| Redis indisponível | Sem fila de jobs, sem lock GPU, sem resultados assíncronos |
| Storage indisponível | Upload, download e resultados falham |
| GPU indisponível | Jobs GPU caem para CPU (muito lentos) ou falham |
| Worker GPU único falha | Fila GPU acumula, throughput zero |
| PyTorch/CUDA incompatível | Técnicas GPU falham ou usam CPU |

## SPOFs

1. Banco PostgreSQL único
2. Redis único
3. Filesystem local compartilhado
4. Worker GPU singleton (apenas um job GPU por vez)
5. GPU única (não há suporte a múltiplas GPUs no código atual)

## Evidências

- `requirements.txt`
- `requirements-gpu.txt`
- `docker-compose.yml`
- `docker-compose.gpu.yml`
- `src/backend/app/config.py`
- `src/backend/core/gpu_inference.py`
- `src/backend/core/job_dispatch.py`
