# ForensicAuth

Plataforma forense digital (local) para análise de imagem, áudio, vídeo e PDF, com cadeia de custódia, jobs assíncronos (CPU/GPU), artefatos por técnica e transferência VCP.

## Começar aqui

Manual pedagógico completo: **[docs/README.md](docs/README.md)**  
(ordem de leitura, primeira semana, capítulos 01–10).

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

## Testes

```bash
conda activate forensicauth
PYTHONPATH=src/backend pytest tests/unit tests/integration -m "not weights and not gpu" -q
```

## Documentação por público

| Público | Onde |
|---------|------|
| Manual didático | [docs/](docs/) (capítulos 01–10) |
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
