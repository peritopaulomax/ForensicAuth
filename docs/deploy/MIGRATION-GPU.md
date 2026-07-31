# Kit de Migração — Ambiente Definitivo com GPU NVIDIA

> **Documento histórico / operacional.** Partes abaixo descrevem o estado de migração
> original; o stack GPU atual usa `requirements-gpu.txt`, `docker-compose.gpu.yml`,
> `Dockerfile.gpu` e [`WORKER-REMOTE.md`](WORKER-REMOTE.md). Ignore checklists de
> “prompt” e arquivos marcados como “a criar” se já existirem no repositório.

> **Quando usar:** Ao implantar o ForensicAuth em uma máquina Linux com GPU NVIDIA.

---

## ✅ O que JÁ ESTÁ PRONTO
| Item | Status | Arquivo(s) |
|------|--------|------------|
| Auth (login, JWT, bcrypt) | ✅ Completo | `services/auth_service.py` |
| Core (plugin registry, settings) | ✅ Completo | `core/plugin_registry.py`, `app/config.py` |
| Custody (cadeia SHA-256) | ✅ Completo | `services/custody_service.py` |
| Jobs (Celery, endpoints) | ✅ Completo | `services/job_service.py`, `tasks/analysis_tasks.py` |
| Image Lite (ELA, metadata, hash) | ✅ Completo | `core/plugins/ela_plugin.py`, `metadata_plugin.py`, `hash_plugin.py` |
| Mock plugin para testes | ✅ Completo | `core/plugins/mock_plugin.py` |
| Docker Compose (DB, Redis, App) | ✅ Completo | `docker-compose.yml` |

---

## 🔧 O que PRECISA SER ADAPTADO (checklist)

### 1. Instalar Dependências Pesadas
```bash
pip install -r requirements-gpu.txt
```
**Arquivo:** `requirements-gpu.txt` (já versionado na raiz do repositório)

**Dependências:** ver `requirements-gpu.txt` (torch/CUDA, transformers, open_clip,
xgboost, kornia/wavelets para SAFE, mmcv para MIML, decord/lightning para vídeo, etc.).
Pacotes de técnicas aposentadas (CAMO/`dlib`, InsightFace, rawpy, imagehash, openai CLIP
git) foram removidos da lista.

> **Nota CUDA:** O comando de instalação do PyTorch depende da versão do CUDA instalada. Verifique a versão com `nvidia-smi` e use o `index-url` correspondente, por exemplo:
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
> ```

### 2. Colocar os Pesos dos Modelos
**Diretório base:** `./models/` (configurável via `MODELS_DIR` no `.env`)

Estrutura esperada (resumo — o diagnóstico lista a cobertura completa):
```
./models/
├── sepael/                 # imagens sintéticas
├── bfree/ grip_clipd/ truebees_clip_d/ safire/
├── imdlbenco/              # TruFor, CAT-Net, …
├── prnu/ pad/ moe_ffd/
├── sls_spoofing/ wedefense_asv2025/
├── videofact/ stil/ lowres_fake_video/ truvil/ vilocal/
└── icpbrasil/              # âncoras PDF (não é peso ML)
```

> Certifique-se de que os arquivos de peso estejam no diretório configurado em `MODELS_DIR` (padrão: `./models/`).

### 3. Verificar GPU (Diagnóstico Automático)
```bash
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
```

> Execute o comando acima e verifique se a GPU é detectada.

### 4. Atualizar `.env` (se necessário)
Possíveis mudanças:
```bash
# GPU
GPU_AVAILABLE=true

# Modelos (se o caminho for diferente)
MODELS_DIR=/mnt/storage/forensicauth/models

# CUDA device
CUDA_VISIBLE_DEVICES=0
```

### 5. Subir com Docker GPU (opcional)
Se quiser usar Docker com GPU:
```bash
docker-compose -f docker-compose.gpu.yml up --build
```

> Escolha entre Docker com GPU ou execução nativa conforme a política de infraestrutura da instituição.

---

## Automação do Diagnóstico

### Diagnóstico Automático (Script)
Execute:
```bash
python scripts/diagnose_gpu.py
```

Esse script verifica:
1. Python / plataforma
2. `nvidia-smi` e `nvcc`
3. PyTorch + CUDA (device / VRAM)
4. Dependências de `requirements-gpu.txt` (incl. mmcv, kornia, open_clip, decord, …)
5. Subpastas de pesos em `MODELS_DIR` (IMDL, spoofing, vídeo, PAD, …)
6. Env (GPU_AVAILABLE, role worker-gpu, CUDA_VISIBLE_DEVICES) e ping Redis

Exit code `1` se houver falhas críticas (ex.: sem CUDA / sem torch).

Exemplo de trechos no relatório:
```
[PYTORCH]
OK  torch 2.x.x
    CUDA available: True
[HEAVY DEPENDENCIES]
FAIL mmcv                   ausente
[MODEL WEIGHTS]
WARN imdlbenco             ausente — IMDL-BenCo (TruFor, CAT-Net, …)
Resultado: NÃO pronto para GPU (corrija as falhas FAIL).
```
### Checklist de Migração

Ao chegar no sistema definitivo, colete as informações abaixo antes de prosseguir:

- Output do `nvidia-smi` (versão do CUDA e modelo da GPU).
- Output do `python scripts/diagnose_gpu.py`.
- Caminho dos pesos dos modelos no ambiente definitivo.
- Modo de execução desejado: Docker nativo, Docker GPU ou nativo sem Docker.

Com essas informações, determine:
- Qual comando de instalação do PyTorch usar.
- Quais adapters precisam de ajuste.
- Se os pesos estão no diretório configurado.
- Se o Celery worker GPU precisa de configuração extra.

---

## Arquivos do stack GPU (referência atual)

| Arquivo | Propósito |
|---------|-----------|
| `requirements-gpu.txt` | Dependências pesadas (CUDA / ML) |
| `docker-compose.gpu.yml` | Compose com worker GPU |
| `Dockerfile.gpu` | Imagem otimizada para GPU |
| `docs/deploy/MIGRATION-GPU.md` | Este documento |
| `docs/deploy/WORKER-REMOTE.md` | Worker GPU em host remoto |

Adapters forenses (`synthetic_image_detection`, deepfake, PRNU, etc.) vivem em `src/backend/core/plugins/`.

---

## Resultado esperado

**Desenvolvimento sem GPU:** adapters existem; técnicas ML retornam indisponível se pesos/CUDA faltarem; testes unitários usam mock ou lite.

**Linux com GPU:**
- `pip install -r requirements-gpu.txt` (ou imagem `Dockerfile.gpu`)
- Pesos em `./models/`
- Compose GPU ou worker remoto conforme `WORKER-REMOTE.md`
- Sem alterar a lógica dos algoritmos em `forensics/` / `vendor/`
