# ForensicAuth

Plataforma forense digital para analise de imagem, audio, video e PDF, com cadeia de custodia rastreavel, jobs assincronos e geracao de laudos.

## Ambiente de desenvolvimento

O projeto usa um ambiente **conda** dedicado:

```bash
conda env create -f environment.yml
conda activate forensicauth
```

Ou, se o ambiente ja existir:

```bash
conda activate forensicauth
pip install -r requirements.txt
```

Para analises com GPU (detecção de imagens sintéticas, deepfake, etc.), instale tambem `requirements-gpu.txt`.

### Stack dev completo (API + workers + Postgres/Redis)

Com uma GPU local, use o script unificado (warmup ML **somente** no log do `worker-gpu`; a API nao ocupa VRAM):

```bash
./scripts/dev-stack.sh setup   # conda va-suite, deps, postgres+redis dev
./scripts/dev-stack.sh start   # uvicorn + worker-cpu + worker-gpu + frontend
./scripts/dev-stack.sh status
./scripts/dev-stack.sh stop
```

Templates de `.env` por processo: `src/backend/.env.api.example`, `.env.worker-cpu.example`, `.env.worker-gpu.example`.

## Execucao local (desenvolvimento)

**Backend** (na pasta `src/backend`):

```bash
conda activate forensicauth
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend** (na pasta `src/frontend`):

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

## Producao

Para implantacao em servidor Linux com Docker, consulte [docs/public/INSTALACAO-PRODUCAO-LINUX.md](docs/public/INSTALACAO-PRODUCAO-LINUX.md).

Compose com GPU (`app` + `worker-cpu` + `worker-gpu`): use `docker-compose.gpu.yml` e `.env.production.example`.

Worker GPU remoto na LAN (futuro): [docs/deploy/WORKER-REMOTE.md](docs/deploy/WORKER-REMOTE.md).

## Documentacao

| Publico | Conteudo |
|---------|----------|
| Operadores / administradores | [docs/public/](docs/public/) — instalacao, arquitetura, VCP, cadeia de custodia |
| Desenvolvedores | [docs/developer/](docs/developer/) — visao geral, contribuicao, specs |
| Agentes / automacao | [AGENTS.md](AGENTS.md) — regras de execucao do projeto |

## Estrutura principal

```
ForensicAuth/
├── src/backend/     # API FastAPI, plugins forenses, servicos
├── src/frontend/    # Interface React + TypeScript
├── docs/            # Documentacao publica e de desenvolvimento
├── tests/           # Testes unitarios e de integracao
└── prompts/         # Prompts de execucao por modulo
```
