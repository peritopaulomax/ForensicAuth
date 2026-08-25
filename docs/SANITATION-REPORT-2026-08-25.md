# Relatório de saneamento — preparação para produção

## Resumo executivo

- Modo selecionado: **Preparar para Produção**
- Fase: inventário e plano; nenhuma limpeza executada
- Score estático de prontidão: **49/100 — não apto para produção**
- Código first-party inventariado para higiene: 688 arquivos
- Vendor protegido: aproximadamente 2.429 arquivos, propostos como exceção
- Dados runtime preservados: cerca de 1,1 GB em uploads e 404 MB em derivados
- Working tree já contém alterações; nenhuma delas foi descartada

Os bloqueadores não são apenas lixo técnico. Há falhas críticas de autorização,
imutabilidade PostgreSQL e configuração de produção. Limpar caches e órfãos não
torna o sistema seguro para dados reais.

## Gates A–M

| Gate | Estado | Evidência / ação necessária |
|------|--------|-----------------------------|
| A — Código morto | analisado | candidatos FE, path `ops/calibration` e mock mapeados |
| B — Órfãos | analisado | páginas/registries FE, diretório `uploads/`, docs stale |
| C — Dependências | falha | deps de teste/tooling no runtime; candidatos sem uso |
| D — Artefatos de teste | falha parcial | caches, `node_modules`, marker/path órfãos |
| E — Banco | falha produção | DB local populado; custódia PG sem enforcement |
| F — Storage | falha produção | dados ativos + permissões amplas; sem reset autorizado |
| G — Configurações | falha | template prod incompleto; bootstrap não reproduzível |
| H — Credenciais | falha | exemplos/defaults e `.env` locais com permissões 666 |
| I — Plano | concluído | ondas abaixo |
| J — Aprovação | pendente | nenhuma mutação antes da enquete |
| K — Comentários | falha | 10 arquivos first-party acionáveis; vendor requer exceção |
| L — Manual humano | passa | `docs/README.md` + capítulos 01–10 |
| M — Docs fora de `docs/` | classificado | READMEs co-localizados e memória do agente preservados |

`knowledge/`, `summaries/` e `brains/` não devem ser movidos para o manual:
conforme a arquitetura documental, são memória do agente, não documentação
humana. Permanecem separados.

## Código morto

| Item | Evidência | Classificação | Ação proposta | Risco |
|------|-----------|---------------|---------------|-------|
| `src/frontend/src/pages/Upload.tsx` | sem import/rota; upload real em `CaseDetail` | Seguro remover | excluir + build/E2E | Baixo |
| `ImdlBencoHub.tsx` | sem import/rota ativa | Provável remoção | excluir após build/Vitest | Baixo |
| registries FE antigos por mídia | sem imports; registry unificado ativo | Seguro remover | excluir 4 arquivos | Baixo |
| `components/TechniqueConfig.tsx` | sem imports | Seguro remover | excluir | Baixo |
| `analysis.ts::getJob` | sem consumidores | Seguro remover | excluir função | Baixo |
| `/analysis/jobs` em `submitJob` | endpoint backend inexistente | Corrigir | apontar ao contrato atual + teste | Médio |
| `wav_ima_adpcm.py` | sem imports | Revisão necessária | manter nesta rodada por Regra 8 | Baixo |
| `mock_technique` | auto-descoberto em produção | Corrigir | filtrar em production; preservar testes | Alto |

## Arquivos órfãos e configurações stale

| Item | Evidência | Ação proposta |
|------|-----------|---------------|
| `uploads/` raiz | vazio; runtime usa `data/uploads` | remover diretório vazio |
| `tests/conftest.py` → `ops/calibration` | diretório ausente | remover path fantasma |
| `docker-compose.dev.yml` → `dev-lan.sh` | script ausente | corrigir comentário |
| `docs/developer/*` → `config/techniques` | diretório inexistente | usar `scripts/technique/examples` |
| `tools/diag_custody.py` em docs | path real sob `src/backend` | corrigir comando |
| `MIGRATION-GPU.md` | declarado histórico e parcialmente stale | arquivar somente após aprovação |
| runtime cita downloads inexistentes | 16 nomes; só TruVIL/ViLocal existem | substituir por instrução canônica ou implementar |

## Dependências desnecessárias ou mal separadas

| Dependência | Uso observado | Ação | Risco |
|-------------|---------------|------|-------|
| pytest, pytest-asyncio, pytest-cov, httpx | testes; instalados pelo `Dockerfile.prod` | separar requirements dev/prod | Médio |
| `gdown` | scripts de download | mover para tooling | Baixo |
| `weasyprint`, `jinja2` | sem import first-party; provável resíduo de reports | remover só após smoke PDF/vendor | Médio |
| deps repetidas base/GPU | necessárias, mas sujeitas a drift | consolidar após smoke GPU | Médio |
| `lightning` + `pytorch-lightning` | stack de vídeo | manter até prova em hardware | Alto |
| OpenMMLab legado | MIML protegido | não remover | Alto |

## Artefatos de teste e desenvolvimento

| Item | Estado | Ação |
|------|--------|------|
| `.pytest_cache`, `__pycache__` | locais e ignorados | remover antes do pacote |
| `src/frontend/node_modules` | 213 MB, regenerável | remover somente se desejado; Docker já exclui |
| fixtures pytest | regressão forense | manter |
| contas fake | limitadas aos testes in-memory | manter testes; não copiar para prod |
| marker `e2e_sanitization` | registrado sem uso encontrado | remover ou implementar |
| `.dockerignore` | exclui data, caches, tests, vendor/models montados | manter |

## Dados e storage

| Path | Estado | Decisão segura |
|------|--------|----------------|
| `data/uploads` | ~1,1 GB; evidências | **não remover** |
| `data/derivatives` | ~404 MB; derivados custodiados | **não remover** |
| `data/results` | ~76 KB; previews/cache | limpar só após conferir política |
| `data/db` | ~187 MB; banco e backups locais | **não resetar sem backup explícito** |
| `data/peritus_cases` | workspaces presentes | preservar |
| `uploads/` raiz | vazio | remover |

Permissões observadas: `.env` e `src/backend/.env` em `666`; `data/` em `777`;
SQLite em `666`. Para produção, usar volumes novos e permissões restritivas,
sem destruir o ambiente de desenvolvimento atual.

## Bloqueadores de produção

### P0 — críticos

| Bloqueador | O que pode falhar | Detecção | Recuperação | Residual |
|------------|-------------------|----------|------------|----------|
| ACL por `job_id` ausente em várias rotas | IDOR de metadata e artefatos | teste com dois peritos | `get_accessible_job` em toda rota + regressão | UUID nunca substitui ACL |
| custódia PostgreSQL sem trigger/REVOKE | UPDATE/DELETE da cadeia | tentativa com role da app | migração PG + teste | superuser continua trust boundary |
| template prod incompleto | startup inseguro ou falho | `compose config` + validator | env fechado, secrets e smoke | erro operacional |
| dados dev em volumes locais | vazamento/perda ao “resetar” | inventário DB+FS | volumes novos ou backup validado | classificação humana dos dados |

### P1 — altos

- seis gitlinks sem `.gitmodules`;
- pesos/vendor/referências não reproduzíveis apenas pelo Git;
- ausência de CI;
- Dockerfiles dev/GPU com layouts diferentes do prod;
- OpenAPI exposto por default;
- Google Fonts incompatível com air-gap estrito;
- backup/restore DB+FS não automatizado;
- workers GPU dependem de provisionamento externo.

## Varredura de comentários

Foram encontrados 10 arquivos first-party acionáveis:

- termos “hack” no pipeline VideoFACT;
- autoria pessoal em dois comentários PAD;
- “Temporarily” em bootstrap IML-ViT/SAFIRE;
- paths locais nos scripts de ingestão;
- “Legacy dispatcher” em task compatível.

Não foram encontrados rastros first-party de ChatGPT, Copilot, Claude ou
“generated by AI”. Placeholders `TODO` do scaffold são intencionais e devem
permanecer.

Alterações em `src/backend/forensics/` serão apenas textuais, mas ainda exigem
aprovação explícita e testes por Regra 8. `vendor/` permanece intocado e deve
ser registrado como exceção aprovada do Gate K.

## Documentação fora de `docs/`

| Grupo | Classificação |
|-------|---------------|
| `README.md`, `AGENTS.md` | manter na raiz |
| `scripts/README.md`, `tests/*.md`, `reference_data/README.md` | manter co-localizados |
| READMEs de modelos/fixtures | manter junto ao ativo |
| `tests/specs/` | manter como contrato TDD |
| `knowledge/`, `summaries/`, `brains/` | manter separados como memória do agente |
| `pdfsig_forense_README.md` | candidato a mover/fundir em docs de referência |
| inventário datado de reference data | candidato a arquivar |

## Plano de execução

### Onda 1 — segura e reversível

1. limpar caches e diretório `uploads/` vazio;
2. corrigir paths/comentários stale;
3. remover órfãos FE comprovados;
4. corrigir chamada `/analysis/jobs`;
5. esconder `mock_technique` em produção;
6. executar build/Vitest/pytest pertinente.

### Onda 2 — bloqueadores P0

1. aplicar ACL em todas as rotas de job + teste IDOR;
2. criar enforcement PostgreSQL da custódia + teste de integração;
3. fechar `.env.production.example` e forçar modo production no Compose;
4. restringir docs OpenAPI em produção;
5. criar volumes/diretórios limpos de produção sem apagar dados dev.

### Onda 3 — empacotamento e supply chain

1. separar dependências dev/prod e regenerar constraints;
2. alinhar Dockerfiles/Compose;
3. resolver manifesto dos gitlinks e hashes dos pesos;
4. criar CI default e smoke;
5. self-host de fontes.

### Onda 4 — higiene completa

1. corrigir os 10 comentários first-party;
2. registrar `vendor/` como exceção;
3. arquivar/mover docs aprovadas;
4. reexecutar gates A–M.

## Score de limpeza

| Domínio | Nota |
|---------|-----:|
| Estrutura e lixo técnico | 72 |
| Dependências | 52 |
| Configuração/segredos | 38 |
| Segurança/ACL | 32 |
| Dados/custódia | 42 |
| Documentação | 94 |
| CI/automação | 28 |
| **Prontidão produção ponderada** | **49/100** |

## Aprovação necessária

Nenhuma onda foi executada. A aprovação deve definir:

1. escopo de código/config;
2. política para dados existentes;
3. exceção de `vendor/` e comentários em algoritmos protegidos.

