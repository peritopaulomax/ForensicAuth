# ForensicAuth

Plataforma forense digital (local) para análise de imagem, áudio, vídeo e PDF, com cadeia de custódia, jobs assíncronos (CPU/GPU), artefatos por técnica e transferência VCP.

## Começar aqui

Manual pedagógico completo: **[docs/README.md](docs/README.md)**  


## Setup rápido (dev)

```bash
conda env create -f environment.yml
conda activate forensicauth
pip install -r requirements.txt          # + requirements-gpu.txt se for usar ML/GPU

# API
cd src/backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (outra shell)
cd src/frontend && npm install && npm run dev -- --host 0.0.0.0 --port 3000
```

Infra Postgres/Redis: `docker compose -f docker-compose.dev.yml up -d`  
Stack completa: `docker compose up -d` · GPU: `docker-compose.gpu.yml`.

## Instalação em produção (1 ou mais máquinas, workers CPU/GPU)

Roteiro operacional completo (máquina principal + workers GPU/CPU na LAN, incluindo multi-GPU por máquina):
**[docs/deploy/INSTALACAO-PROD-WORKERS.md](docs/deploy/INSTALACAO-PROD-WORKERS.md)**

Cobre: Docker/NVIDIA, segredos, compose de produção, workers GPU via systemd, NFS para workers remotos, proxy corporativo, modelos, ingestão da população de referência e problemas comuns.

## Modelos pré-treinados (download obrigatório — não vão no Git)

Os pesos em `models/` (**dezenas de GB**) precisam ser **baixados da fonte oficial e colocados na pasta correspondente**. Sem eles as técnicas ficam indisponíveis. Fontes por pasta:

| Pasta `models/` | Técnica | Fonte oficial |
|---|---|---|
| `imdlbenco/` | TruFor (CVPR 2023) | [github.com/grip-unina/TruFor](https://github.com/grip-unina/TruFor) |
| `imdlbenco/` | CAT-Net (IJCV 2022) | [github.com/mjkwon2021/CAT-Net](https://github.com/mjkwon2021/CAT-Net) |
| `imdlbenco/` | MIML APSC-Net (CVPR 2024) | [github.com/qcf-568/MIML](https://github.com/qcf-568/MIML) |
| `bfree/` | B-Free (CVPR 2025) | [github.com/grip-unina/B-Free](https://github.com/grip-unina/B-Free) |
| `grip_clipd/` | GRIP CLIP-D / Corvi2023 | [github.com/grip-unina/ClipBased-SyntheticImageDetection](https://github.com/grip-unina/ClipBased-SyntheticImageDetection) |
| `synthetic_image_detection/huggingface/` | Ensemble SID | HF: [`haywoodsloan/ai-image-detector-deploy`](https://huggingface.co/haywoodsloan/ai-image-detector-deploy) · (https://huggingface.co/cmckinle/sdxl-flux-detector_v1.1) |
| `wedefense_asv2025/` | WeDefense WavLM+MHFA (ASVspoof 2025) | [github.com/zlin0/wedefense](https://github.com/zlin0/wedefense) · pesos HF [`JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning`](https://huggingface.co/JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning) |
| áudio DF Arena 1B (cache HF) | Speech DF Arena | HF [`Speech-Arena-2025/DF_Arena_1B_V_1`](https://huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1) + backbone [`facebook/wav2vec2-xls-r-1b`](https://huggingface.co/facebook/wav2vec2-xls-r-1b) |



## Vendor (código de terceiros — baixar e colar na pasta correspondente)

A pasta `vendor/` traz código-fonte de terceiros exigido em runtime pelas técnicas. Se faltar pasta no clone, baixe do repositório oficial e coloque em `vendor/<nome>`:

| Pasta `vendor/` | Projeto | Repositório oficial |
|---|---|---|
| `grip-unina-trufor/` | TruFor | [github.com/grip-unina/TruFor](https://github.com/grip-unina/TruFor) |
| `CAT-Net-main/` | CAT-Net | [github.com/mjkwon2021/CAT-Net](https://github.com/mjkwon2021/CAT-Net) |
| `MIML/` | MIML APSC-Net | [github.com/qcf-568/MIML](https://github.com/qcf-568/MIML) |
| `bfree/` | B-Free | [github.com/grip-unina/B-Free](https://github.com/grip-unina/B-Free) |
| `dmimage_detection/` | DMimageDetection (Corvi2023) | [github.com/grip-unina/DMimageDetection](https://github.com/grip-unina/DMimageDetection) |
| `SAFE/` | SAFE (KDD 2025) | [github.com/Ouxiang-Li/SAFE](https://github.com/Ouxiang-Li/SAFE) |
| `deepfakebench/` | DeepfakeBench | [github.com/SCLBD/DeepfakeBench](https://github.com/SCLBD/DeepfakeBench) |
| `wedefense/` | WeDefense | [github.com/zlin0/wedefense](https://github.com/zlin0/wedefense) |
| `df_arena_1b/` | DF Arena 1B (model card + código) | [huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1](https://huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1) |

## Testes

```bash
conda activate forensicauth
PYTHONPATH=src/backend pytest tests/unit tests/integration -m "not weights and not gpu" -q
```

## Documentação por público

| Público | Onde |
|---------|------|
| Manual didático | [docs/](docs/) (capítulos 01–10) |
| Instalação produção + workers (roteiro) | [docs/deploy/INSTALACAO-PROD-WORKERS.md](docs/deploy/INSTALACAO-PROD-WORKERS.md) |
| Instalação / custódia / VCP | [docs/public/](docs/public/) |
| Deploy / worker remoto | [docs/deploy/](docs/deploy/) |
| Contribuidores / scaffold | [docs/developer/](docs/developer/) |
| Specs SDD | [docs/specs/](docs/specs/) |

## Estrutura

```text
src/backend · src/frontend · vendor · models · reference_data · data · docs · tests
```
