# Documentação humana — ForensicAuth (VA Suite)

Manual pedagógico do sistema. Público: quem está começando no projeto e quem vai contribuir código ou operar a stack.

> Memória de agentes (`knowledge/`, `summaries/`, `brains/`) **não** substitui este manual.
> Specs SDD (`docs/specs/`) descrevem contratos; este manual explica *como pensar e operar*.

## Ordem de leitura sugerida

1. [01 — Visão e negócio](01-visao-e-negocio.md) — o que o produto faz  
2. [02 — Arquitetura e decisões](02-arquitetura-e-decisoes.md) — como as peças se encaixam  
3. [03 — Mapa do repositório](03-mapa-do-repositorio.md) — onde está cada coisa  
4. [04 — Backend](04-backend.md) — API, serviços, plugins, jobs  
5. [05 — Frontend](05-frontend.md) — UI, rotas, chamadas à API  
6. [06 — Dados e integrações](06-dados-e-integracoes.md) — DB, FS, VCP, Peritus  
7. [07 — Operação e setup](07-operacao-e-setup.md) — instalar, Docker, workers  
8. [09 — ML e artefatos](09-ml-e-artefatos.md) — pesos, vendor, LR  
9. [10 — Testes e qualidade](10-testes-e-qualidade.md)  
10. [08 — Glossário e armadilhas](08-glossario-e-armadilhas.md) — consultar sob demanda  

## Roteiro — primeira semana

| Dia | Objetivo | Como verificar |
|-----|----------|----------------|
| 1 | Subir API + FE (ou Compose) e fazer login | `GET /health`; tela `/login` |
| 2 | Criar caso e upload de imagem de teste | Evidência com `sha256` no detalhe do caso |
| 3 | Rodar uma técnica **CPU** (ex.: metadata / ELA) | Job `completed` + artefato em `data/results/` |
| 4 | Entender plugins: ler `ForensicPlugin` + um adapter | Código em `core/forensic_plugin.py` |
| 5 | Ver custódia e verify | Aba custódia / `audit/verify-case-forensic` |
| 6 | (Opcional GPU) subir `worker-gpu` e uma técnica ML | `/api/v1/analysis/gpu-queue` |
| 7 | Rodar testes default + ler AGENTS.md Regra 8 | `pytest … -m "not weights and not gpu"` |

## O que o repositório usa

| Tema | Presente? | Onde aprofundar |
|------|-----------|-----------------|
| Docker / Compose | Sim | [07](07-operacao-e-setup.md), `docker-compose*.yml` |
| PostgreSQL | Sim | [06](06-dados-e-integracoes.md), [07](07-operacao-e-setup.md) |
| Celery CPU / GPU | Sim | [04](04-backend.md), [07](07-operacao-e-setup.md) |
| Redis (broker + lock) | Sim | [07](07-operacao-e-setup.md) |
| ML / checkpoints | Sim | [09](09-ml-e-artefatos.md), `models/` |
| Vendor / forks | Sim | [09](09-ml-e-artefatos.md), `vendor/` |
| TDD / testes | Sim | [10](10-testes-e-qualidade.md) |
| Scripts / automação | Parcial | [07](07-operacao-e-setup.md) — `scripts/technique/` |

## Outras pastas em `docs/` (já existentes — mantidas)

| Pasta | Público | Conteúdo |
|-------|---------|----------|
| [`public/`](public/) | Ops / peritos | Instalação Linux, custódia, VCP |
| [`deploy/`](deploy/) | SRE | Env produção, worker GPU remoto, migração GPU |
| [`developer/`](developer/) | Contribuidores | Visão, guia, scaffold de técnicas |
| [`specs/`](specs/) | Devs / SDD | Overview e módulos |
| [`references/`](references/) | Científico | Papers IMDL etc. |

Lab local não versionado: `DOCS_DEV_NOGIT/` na raiz do clone.
