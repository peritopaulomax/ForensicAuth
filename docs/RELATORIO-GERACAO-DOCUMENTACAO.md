# Relatório — geração e integração da documentação humana

## Metadados

- Projeto: ForensicAuth / VA Suite
- Data: 2026-08-25
- Modo: integrar
- Idioma/público: PT-BR; iniciantes, contribuidores e operação
- Fontes: `brains/`, `summaries/`, `knowledge/`, specs, docs existentes e
  evidências no código/config

Nenhum documento foi movido ou apagado. O manual canônico existente foi
preservado e atualizado.

## Inventário de docs existentes

| Path | Classificação | Destino | Notas |
|------|---------------|---------|-------|
| `README.md` | manter-como-fonte | raiz | Entrada curta para o manual |
| `docs/README.md`, `docs/01`–`10` | manter-como-fonte | manual canônico | Atualizados nesta execução |
| `docs/specs/` | manter-como-fonte | contrato SDD | Não fundir com narrativa didática |
| `tests/specs/` | manter-como-fonte | aceite TDD textual | Não são testes executáveis |
| `docs/developer/` | manter-como-fonte | contribuidores | Guia profundo e scaffold |
| `docs/deploy/` | manter-como-fonte | operação/SRE | Runbooks detalhados |
| `docs/public/` | manter-como-fonte | peritos/auditores | Custódia, VCP e arquitetura |
| `docs/references/` | manter-como-fonte | científico | Papers e referências |
| `scripts/README.md` | manter-como-fonte | junto aos scripts | Fonte do inventário real |
| `tests/README.md`, `tests/CATALOG.md` | manter-como-fonte | junto aos testes | Execução e catálogo |
| `reference_data/README.md` | manter-como-fonte | junto aos dados | Lifecycle publicado |
| `docs/deploy/MIGRATION-GPU.md` | arquivar (proposta) | sem alteração | Histórico; requer aprovação para mover |
| `reference_data/INVENTORY_*.md` | arquivar (proposta) | sem alteração | Snapshot regenerável; requer aprovação |

## Checklist técnico

| Tema | Status | Path da seção |
|------|--------|----------------|
| Docker / containers | conteúdo | `07-operacao-e-setup.md` |
| PostgreSQL / migrações / backup | conteúdo | `06-dados-e-integracoes.md`, `07-operacao-e-setup.md` |
| Filas / Celery CPU-GPU | conteúdo | `04-backend.md`, `07-operacao-e-setup.md` |
| Redis / cache-broker | conteúdo | `06-dados-e-integracoes.md`, `07-operacao-e-setup.md` |
| ML / checkpoints | conteúdo | `09-ml-e-artefatos.md` |
| Vendor / forks | conteúdo | `09-ml-e-artefatos.md` |
| TDD / testes / CI | conteúdo | `10-testes-e-qualidade.md` |
| Scripts / automação | conteúdo | `07-operacao-e-setup.md`, `scripts/README.md` |
| Frontend | conteúdo | `05-frontend.md` |
| Primeira semana | conteúdo | `docs/README.md` |
| Glossário / riscos | conteúdo | `08-glossario-e-armadilhas.md` |

Cobertura: 100% dos itens obrigatórios possui conteúdo; nenhum item é N/A.

## Conflitos entre docs antigas e código

| Tema | Doc antiga | Evidência código | Resolução |
|------|------------|------------------|-----------|
| ACL de jobs | Manual assumia ACL geral | `analysis.py` usa `get_job` em rotas por UUID | Risco crítico explicitado nos capítulos 01, 02, 04 e 08 |
| Custódia PostgreSQL | RN dizia INSERT-only sem ressalva | trigger localizado somente para SQLite | Limite e teste de `UPDATE` negado documentados |
| Produção | exemplo de env parecia suficiente | Compose/config exigem variáveis adicionais | Gate de produção adicionado ao capítulo 07 |
| Execução de jobs | fluxo mostrava apenas SQLite vs Celery | falha de publicação também cai para thread | Diagramas e operação alinhados |
| `config/` | mapa citava diretório inexistente | scaffold vive em `scripts/technique/` | Árvore corrigida |
| Migrações | só revision inicial | três revisions + `ensure_*` no startup | Dual-path documentado |
| Frontend | rotas e E2E incompletos | `App.tsx` + 12 specs Playwright | Catálogo ampliado |
| PRNU | hint FE podia sugerir GPU | backend não inclui PRNU no conjunto GPU | Fonte de verdade e exceção documentadas |
| Vendor | política sem bootstrap | seis gitlinks e nenhum `.gitmodules` | Bloqueio operacional explicitado |
| Downloads | descrição genérica | só TruVIL/ViLocal têm scripts versionados | Procedimentos reais documentados |
| Testes | sem posição sobre CI | não há CI versionado | Gate local e risco residual explícitos |
| Offline | promessa absoluta | frontend solicita Google Fonts | Dívida e fallback documentados |

## Artefatos atualizados

- `docs/README.md`
- `docs/01-visao-e-negocio.md`
- `docs/02-arquitetura-e-decisoes.md`
- `docs/03-mapa-do-repositorio.md`
- `docs/04-backend.md`
- `docs/05-frontend.md`
- `docs/06-dados-e-integracoes.md`
- `docs/07-operacao-e-setup.md`
- `docs/08-glossario-e-armadilhas.md`
- `docs/09-ml-e-artefatos.md`
- `docs/10-testes-e-qualidade.md`
- este relatório

## Quality gates

- [x] Memória consumida na ordem executive summary → system brain/mental model
  → summaries → knowledge/evidência
- [x] Inventário anexado
- [x] Checklist técnico 100%
- [x] Capítulos canônicos presentes
- [x] README raiz aponta para `docs/README.md`
- [x] Frontend documentado
- [x] Roteiro da primeira semana presente
- [x] Nenhum move/delete ou duplicata nova não aprovada
- [x] Conteúdo crítico inclui detecção, recuperação e risco residual

## Pendências e risco residual

- Corrigir no produto a ACL de jobs e a imutabilidade PostgreSQL; documentar
  não elimina o risco.
- Completar o template versionado de produção e automatizar seu smoke.
- Criar manifesto reproduzível para gitlinks, vendors e pesos.
- Remover referências de runtime a scripts de download inexistentes.
- Implementar CI; até lá, qualidade depende dos gates locais.
- Arquivamentos sugeridos exigem aprovação explícita.

## Próximo passo sugerido

Executar `/detectar-divergencias`. Para preparar entrega de produção depois da
validação, usar `/sanear-projeto`.
