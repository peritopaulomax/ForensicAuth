# Kit de Migração — Ambiente Definitivo com GPU NVIDIA

> **Quando usar:** Este guia deve ser seguido ao implantar o ForensicAuth em uma máquina Linux definitiva com GPU NVIDIA.

---

## ✅ O que JÁ ESTÁ PRONTO (não precisa mexer)

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
**Arquivo:** `requirements-gpu.txt` (será criado neste prompt)

**Dependências:**
- [ ] `torch>=2.0.0` (com suporte CUDA — ver nota abaixo)
- [ ] `torchvision>=0.15.0`
- [ ] `transformers>=4.35.0`
- [ ] `xgboost>=2.0.0`
- [ ] `insightface>=0.7.0`
- [ ] `numba>=0.58.0`
- [ ] `jpegio>=0.2.0` (biblioteca legada forense)
- [ ] `rawpy>=0.18.0`
- [ ] `imagehash>=4.3.0`
- [ ] `scikit-image>=0.21.0`

> **Nota CUDA:** O comando de instalação do PyTorch depende da versão do CUDA instalada. Verifique a versão com `nvidia-smi` e use o `index-url` correspondente, por exemplo:
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
> ```

### 2. Colocar os Pesos dos Modelos
**Diretório base:** `./models/` (configurável via `MODELS_DIR` no `.env`)

Estrutura esperada:
```
./models/
├── sepael/
│   ├── model_1_xgboost.pkl
│   ├── model_2_ensemble.pkl
│   ├── huggingface_model/
│   └── npr_resnet50.pth
├── deepfake/
│   └── insightface_model/
└── prnu/
    └── fingerprints/
        └── camera_xyz.prnu
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
1. Python version
2. CUDA version
3. GPU detectada
4. Quais deps pesadas estão instaladas
5. Quais arquivos de peso estão presentes
6. Qual versão do PyTorch precisa

E gera um relatório tipo:
```
[DIAGNÓSTICO GPU]
✅ Python 3.11.6
✅ CUDA 12.4
✅ GPU: <MODELO_GPU>
❌ torch não instalado
❌ insightface não instalado
❌ Pesos Detecção de imagens sintéticas não encontrados em ./models/sepael/
⚠️  GPU_AVAILABLE=false no .env
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

## 📦 Arquivos que serão criados neste prompt (Prompt 08)

| Arquivo | Propósito |
|---------|-----------|
| `requirements-gpu.txt` | Lista completa de deps pesadas |
| `scripts/diagnose_gpu.py` | Script de diagnóstico automático |
| `core/plugins/synthetic_image_detection_adapter.py` | Adapter Detecção de imagens sintéticas com fallback |
| `core/plugins/deepfake_adapter.py` | Adapter Deepfake com fallback |
| `core/plugins/prnu_adapter.py` | Adapter PRNU com fallback |
| `docker-compose.gpu.yml` | Docker Compose com suporte a GPU |
| `Dockerfile.gpu` | Dockerfile otimizado para GPU |
| `docs/MIGRATION-GPU.md` | Este documento |

---

## 🎯 Resultado Esperado

**No ambiente de desenvolvimento atual:**
- Todos os adapters IA existem como código
- Se você tentar usar Detecção de imagens sintéticas/Deepfake, retorna erro educado
- Testes unitários passam (usam mock ou lite)

**No Linux GPU (depois):**
- `pip install -r requirements-gpu.txt`
- Copiar pesos para `./models/`
- Rodar `diagnose_gpu.py`
- Tudo funciona sem alterar código dos adapters
