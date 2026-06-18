# 🚀 Kit de Migração — Ambiente Definitivo (Linux + RTX 3090)

> **Quando usar:** Chegou na máquina Linux com GPU? Só falar pro Kimi:
> *"Oi Kimi, estou no sistema definitivo, vamos adaptar o que está faltando"*
> 
> Ele vai ler este arquivo, rodar os diagnósticos, e saber EXATAMENTE o que perguntar.

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

> **Nota CUDA:** O comando de instalação do PyTorch depende da versão do CUDA. O Kimi vai perguntar: *"Qual a versão do CUDA instalada? (nvidia-smi)"* e gerar o comando correto, ex:
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

> **O Kimi vai perguntar:** *"Onde estão os arquivos de peso? Manda o caminho ou cola aqui a estrutura de pastas."*

### 3. Verificar GPU (Diagnóstico Automático)
```bash
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
```

> **O Kimi vai pedir:** Rode esse comando e me manda o output.

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

> **O Kimi vai perguntar:** *"Quer usar Docker com GPU ou rodar nativo?"*

---

## 🤖 Como o Kimi vai gerenciar isso

### Diagnóstico Automático (Script)
O Kimi vai rodar:
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
✅ GPU: NVIDIA RTX 3090
❌ torch não instalado
❌ insightface não instalado
❌ Pesos Detecção de imagens sintéticas não encontrados em ./models/sepael/
⚠️  GPU_AVAILABLE=false no .env
```

### Prompt de Migração (para você usar no futuro)
Copie e cole isso quando chegar no sistema definitivo:

```
Oi Kimi, estou no sistema definitivo (Linux, RTX 3090, CUDA X.X).
Rode o diagnose e vamos adaptar o ForensicAuth.

Output do nvidia-smi:
[PASTE AQUI]

Output do diagnose_gpu.py:
[PASTE AQUI]

Caminho dos pesos dos modelos:
[PASTE AQUI]

Quero rodar: [Docker nativo / Docker GPU / Nativo sem Docker]
```

Com isso, o Kimi vai saber EXATAMENTE:
- Qual comando de instalação do PyTorch usar
- Quais adapters precisam de ajuste
- Se os pesos estão no lugar certo
- Se o Celery worker GPU precisa de configuração extra

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

**No seu notebook Windows (agora):**
- Todos os adapters IA existem como código
- Se você tentar usar Detecção de imagens sintéticas/Deepfake, retorna erro educado
- Testes unitários passam (usam mock ou lite)

**No Linux GPU (depois):**
- `pip install -r requirements-gpu.txt`
- Copiar pesos para `./models/`
- Rodar `diagnose_gpu.py`
- Tudo funciona sem alterar código dos adapters
