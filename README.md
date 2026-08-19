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

Roteiro operacional completo e testado (máquina principal + workers GPU/CPU na LAN, incluindo multi-GPU por máquina):
**[docs/deploy/INSTALACAO-PROD-WORKERS.md](docs/deploy/INSTALACAO-PROD-WORKERS.md)**

Cobre: Docker/NVIDIA, segredos, compose de produção, workers GPU via systemd, NFS para workers remotos, proxy corporativo, downloads de modelos HuggingFace, ingestão da população de referência e problemas comuns.

## Modelos pré-treinados (download obrigatório — não vão no Git)

Os pesos em `models/` (**dezenas de GB**) precisam ser **baixados da fonte oficial e colocados na pasta correspondente**. Sem eles as técnicas ficam indisponíveis. Fontes por pasta:

| Pasta `models/` | Técnica | Fonte oficial |
|---|---|---|
| `imdlbenco/` | TruFor (CVPR 2023) | [github.com/grip-unina/TruFor](https://github.com/grip-unina/TruFor) |
| `imdlbenco/` | CAT-Net (IJCV 2022) | [github.com/mjkwon2021/CAT-Net](https://github.com/mjkwon2021/CAT-Net) |
| `imdlbenco/` | MIML APSC-Net (CVPR 2024) | [github.com/qcf-568/MIML](https://github.com/qcf-568/MIML) |
| `imdlbenco/` | Mesorch (AAAI 2025) | [github.com/scu-zjz/Mesorch](https://github.com/scu-zjz/Mesorch) |
| `imdlbenco/` | Co-Transformers (AAAI 2026) | [github.com/ProgrameThinking/Co-Transformers](https://github.com/ProgrameThinking/Co-Transformers) |
| `imdlbenco/` | DINOv3-IML (2026) | [github.com/Irennnne/DINOv3-IML](https://github.com/Irennnne/DINOv3-IML) |
| `bfree/` | B-Free (CVPR 2025) | [github.com/grip-unina/B-Free](https://github.com/grip-unina/B-Free) |
| `grip_clipd/` | GRIP CLIP-D / Corvi2023 | [github.com/grip-unina/ClipBased-SyntheticImageDetection](https://github.com/grip-unina/ClipBased-SyntheticImageDetection) |
| `safire/` | SAFIRE (AAAI 2025) | [github.com/mjkwon2021/SAFIRE](https://github.com/mjkwon2021/SAFIRE) (+ SAM ViT-B: [dl.fbaipublicfiles.com](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth)) |
| `synthetic_image_detection/huggingface/` | Ensemble SID | HF: [`haywoodsloan/ai-image-detector-deploy`](https://huggingface.co/haywoodsloan/ai-image-detector-deploy) · `cmckinle/sdxl-flux-detector_v1.1` (**repo privado** — copiar de quem tem) |
| `sepael/` | Ensemble SID (scores XGBoost + NPR) | NPR: [github.com/chuangchuangtan/NPR-DeepfakeDetection](https://github.com/chuangchuangtan/NPR-DeepfakeDetection) |
| `truebees_clip_d/` | TrueBees deepfake | [github.com/truebees-ai/Image-Deepfake-Detectors-Public-Library](https://github.com/truebees-ai/Image-Deepfake-Detectors-Public-Library) |
| `moe_ffd/` | MoE-FFD (IEEE TDSC 2025) | [github.com/LoveSiameseCat/MoE-FFD](https://github.com/LoveSiameseCat/MoE-FFD) · pesos HF [`luobo91/MoE-FFD`](https://huggingface.co/luobo91/MoE-FFD) |
| `pad/` | Face anti-spoofing (MiniFASNet) | [github.com/minivision-ai/Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing) |
| `prnu/` | PRNU | implementação própria — fingerprints gerados internamente |
| `videofact/` | VideoFACT (WACV 2024) | [github.com/ductai199x/videofact-wacv-2024](https://github.com/ductai199x/videofact-wacv-2024) (pesos no Dropbox do repo) |
| `stil/` | STIL deepfake vídeo (ACM MM 2021) | [github.com/wizyoung/STIL-DeepFake-Video-Detection](https://github.com/wizyoung/STIL-DeepFake-Video-Detection) |
| `lowres_fake_video/` | Low-Res Fake Video (TUM) | [github.com/lukasHoel/fake-video-detection](https://github.com/lukasHoel/fake-video-detection) |
| `truvil/` | TruVIL (IEEE TDSC 2025) | [github.com/multimediaFor/TruVIL](https://github.com/multimediaFor/TruVil) — use `scripts/download_truvil_weights.py` |
| `vilocal/` | ViLocal (IEEE SPL 2025) | [github.com/multimediaFor/ViLocal](https://github.com/multimediaFor/ViLocal) — use `scripts/download_vilocal_weights.py` |
| `sls_spoofing/` | SLS ASVspoof (ACM MM 2024) | [github.com/QiShanZhang/SLSforASVspoof-2021-DF](https://github.com/QiShanZhang/SLSforASVspoof-2021-DF) (+ XLS-R 300M: [fairseq](https://dl.fbaipublicfiles.com/fairseq/wav2vec/xlsr2_300m.pt)) |
| `wedefense_asv2025/` | WeDefense WavLM+MHFA (ASVspoof 2025) | [github.com/zlin0/wedefense](https://github.com/zlin0/wedefense) · pesos HF [`JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning`](https://huggingface.co/JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning) |
| áudio DF Arena 1B (cache HF) | Speech DF Arena | HF [`Speech-Arena-2025/DF_Arena_1B_V_1`](https://huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1) + backbone [`facebook/wav2vec2-xls-r-1b`](https://huggingface.co/facebook/wav2vec2-xls-r-1b) |
| `icpbrasil/` | Âncoras ICP-Brasil (assinaturas PDF) | Certificados raiz oficiais do [ITI](https://www.gov.br/iti) |

A forma mais rápida é copiar `models/` de uma máquina que já tenha tudo (ver roteiro de produção, seção 4).

## Vendor (código de terceiros — baixar e colar na pasta correspondente)

A pasta `vendor/` traz código-fonte de terceiros exigido em runtime pelas técnicas. Se faltar pasta no clone, baixe do repositório oficial e coloque em `vendor/<nome>`:

| Pasta `vendor/` | Projeto | Repositório oficial |
|---|---|---|
| `grip-unina-trufor/` | TruFor | [github.com/grip-unina/TruFor](https://github.com/grip-unina/TruFor) |
| `CAT-Net-main/` | CAT-Net | [github.com/mjkwon2021/CAT-Net](https://github.com/mjkwon2021/CAT-Net) |
| `MIML/` | MIML APSC-Net | [github.com/qcf-568/MIML](https://github.com/qcf-568/MIML) |
| `Mesorch/` | Mesorch | [github.com/scu-zjz/Mesorch](https://github.com/scu-zjz/Mesorch) |
| `Co-Transformers-main/` | Co-Transformers | [github.com/ProgrameThinking/Co-Transformers](https://github.com/ProgrameThinking/Co-Transformers) |
| `DINOv3-IML/` | DINOv3-IML | [github.com/Irennnne/DINOv3-IML](https://github.com/Irennnne/DINOv3-IML) |
| `dinov3/` | DINOv3 (Meta) | [github.com/facebookresearch/dinov3](https://github.com/facebookresearch/dinov3) |
| `BR-Gen-main/` | BR-Gen / NFA-ViT | [github.com/clpbc/BR-Gen](https://github.com/clpbc/BR-Gen) |
| `bfree/` | B-Free | [github.com/grip-unina/B-Free](https://github.com/grip-unina/B-Free) |
| `grip_clipbased_synthetic/` | CLIP-D synthetic | [github.com/grip-unina/ClipBased-SyntheticImageDetection](https://github.com/grip-unina/ClipBased-SyntheticImageDetection) |
| `dmimage_detection/` | DMimageDetection (Corvi2023) | [github.com/grip-unina/DMimageDetection](https://github.com/grip-unina/DMimageDetection) |
| `SAFE/` | SAFE (KDD 2025) | [github.com/Ouxiang-Li/SAFE](https://github.com/Ouxiang-Li/SAFE) |
| `SAFIRE-main/` | SAFIRE | [github.com/mjkwon2021/SAFIRE](https://github.com/mjkwon2021/SAFIRE) |
| `MoE-FFD/` | MoE-FFD | [github.com/LoveSiameseCat/MoE-FFD](https://github.com/LoveSiameseCat/MoE-FFD) |
| `truebees_deepfake_detectors/` | TrueBees | [github.com/truebees-ai/Image-Deepfake-Detectors-Public-Library](https://github.com/truebees-ai/Image-Deepfake-Detectors-Public-Library) |
| `deepfakebench/` | DeepfakeBench | [github.com/SCLBD/DeepfakeBench](https://github.com/SCLBD/DeepfakeBench) |
| `sidbench/` | SIDBench | [github.com/mever-team/sidbench](https://github.com/mever-team/sidbench) |
| `fake-video-detection/` | Low-Res Fake Video | [github.com/lukasHoel/fake-video-detection](https://github.com/lukasHoel/fake-video-detection) |
| `videofact-wacv-2024/` | VideoFACT | [github.com/ductai199x/videofact-wacv-2024](https://github.com/ductai199x/videofact-wacv-2024) |
| `truvil/` | TruVIL | [github.com/multimediaFor/TruVIL](https://github.com/multimediaFor/TruVIL) |
| `vilocal/` | ViLocal | [github.com/multimediaFor/ViLocal](https://github.com/multimediaFor/ViLocal) |
| `sls_asvspoof/` | SLS ASVspoof (inclui fairseq) | [github.com/QiShanZhang/SLSforASVspoof-2021-DF](https://github.com/QiShanZhang/SLSforASVspoof-2021-DF) |
| `wedefense/` | WeDefense | [github.com/zlin0/wedefense](https://github.com/zlin0/wedefense) |
| `tfcl/` | TFCL (áudio spoofing) | [github.com/JunXue-tech/TFCL](https://github.com/JunXue-tech/TFCL) |
| `df_arena_1b/` | DF Arena 1B (model card + código) | [huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1](https://huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1) |
| `bitmind-subnet/` | BitMind SN34 | [github.com/BitMind-AI/bitmind-subnet](https://github.com/BitMind-AI/bitmind-subnet) |

## Testes

```bash
conda activate forensicauth
PYTHONPATH=src/backend pytest tests/unit tests/integration -m "not weights and not gpu" -q
```

## Documentação por público

| Público | Onde |
|---------|------|
| Manual didático | [docs/](docs/) (capítulos 01–10) |
| **Instalação produção + workers (roteiro)** | **[docs/deploy/INSTALACAO-PROD-WORKERS.md](docs/deploy/INSTALACAO-PROD-WORKERS.md)** |
| Instalação / custódia / VCP | [docs/public/](docs/public/) |
| Deploy / worker remoto | [docs/deploy/](docs/deploy/) |
| Contribuidores / scaffold | [docs/developer/](docs/developer/) |
| Specs SDD | [docs/specs/](docs/specs/) |
| Agentes | [AGENTS.md](AGENTS.md) |

## Estrutura

```text
src/backend · src/frontend · vendor · models · reference_data · data · docs · tests
```

Ambiente conda: **`forensicauth`**. Não versionar `.env` nem evidências em `data/`.
