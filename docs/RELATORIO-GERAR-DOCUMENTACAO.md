# Relatório — gerar documentação humana

## Metadados

- Projeto: ForensicAuth / VA Suite
- Data: 2026-07-30
- Modo: **integrar** (validação + atualização mínima do manual existente)
- Política: sem novos históricos/versões; só corrigir drift necessário

## Inventário de docs existentes

| Path | Classificação | Destino | Notas |
|------|---------------|---------|-------|
| `docs/README.md` + `01`–`10` | manter-como-fonte | Manual canônico | Já completo; patches pontuais nesta passagem |
| `docs/public/*` | manter-como-fonte | Caps. 06–07–08 | Instalação, custódia, VCP |
| `docs/deploy/*` | manter-como-fonte | Cap. 07 | Env, worker remoto, migration GPU |
| `docs/developer/*` | manter-como-fonte | Contribuição / scaffold | Áudio hub já alinhado em `03-scaffold` |
| `docs/specs/*` | manter-como-fonte | SDD | Não substituído |
| `docs/references/*` | manter-como-fonte | Cap. 09 | Papers IMDL |
| `README.md` (raiz) | manter | → `docs/README.md` | OK |
| `AGENTS.md` | manter-como-fonte | Caps. 04, 08, 10 | Existe no disco; tracking git é pendência A1 (fora deste comando) |
| `vendor/*/docs` | arquivar (não mexer) | — | Terceiros |
| `docs/RELATORIO-*.md` | manter | Auditorias | Não duplicar; este arquivo é o relatório vigente do comando |

**Nenhum arquivo antigo foi apagado ou movido.**

## Checklist técnico

| Tema | Status | Path da seção |
|------|--------|---------------|
| Docker / containers | conteúdo | `docs/07-operacao-e-setup.md` |
| Banco (Postgres) | conteúdo | `docs/06-dados-e-integracoes.md`, `07` |
| Filas / Celery CPU-GPU | conteúdo | `docs/04-backend.md`, `07` |
| Redis / cache-broker | conteúdo | `docs/07-operacao-e-setup.md` |
| ML / checkpoints | conteúdo | `docs/09-ml-e-artefatos.md` |
| Vendor / forks | conteúdo | `docs/09-ml-e-artefatos.md` |
| TDD / testes | conteúdo | `docs/10-testes-e-qualidade.md` |
| Scripts / automação | conteúdo (parcial) | `docs/07` — `scripts/technique/` |

## Conflitos user-doc vs código (resolvidos nesta passagem)

| Tema | Doc antiga | Evidência código | Resolução |
|------|------------|------------------|-----------|
| VCP → `peritus_cases` | Cap. 06 ciclo de vida | VCP = `case_transfer_service`; Peritus = `PERITUS_CASES_DIR` | Ciclo de vida e tabela de integrações corrigidos |
| Cards áudio duplicados | Cap. 05 omitia hub | `mediaAnalysisGroups.ts` (`audio-forense`) | Subseção hub + Peritus picker |
| Glossário VCP/Peritus | Cap. 08 incompleto | Bridge vs VCP | Termos + armadilhas |
| Diagrama FS | Cap. 02 sem `peritus_cases` | Compose / config | Caixa FS atualizada |

## Artefatos atualizados

- `docs/02-arquitetura-e-decisoes.md`
- `docs/05-frontend.md`
- `docs/06-dados-e-integracoes.md`
- `docs/08-glossario-e-armadilhas.md`
- `docs/RELATORIO-GERAR-DOCUMENTACAO.md` (este arquivo)

Capítulos `01`, `03`, `04`, `07`, `09`, `10`, `README` raiz/`docs/README`: **sem mudança** (já alinhados).

## Pendências / aprovação necessária

- Nenhuma deleção pendente.
- Fora do escopo deste comando: restaurar `AGENTS.md` no git (divergência A1).

## Gates (`human-docs-gates`)

- [x] Memória do agente consumida (`knowledge/` + `summaries/` + `brains/`)
- [x] Inventário no relatório
- [x] Checklist 100% (conteúdo ou parcial documentado)
- [x] Capítulos canônicos 01–10 + índice
- [x] README raiz curto → `docs/README.md`
- [x] Frontend documentado (cap. 05)
- [x] Roteiro primeira semana
- [x] Sem delete/move sem aprovação
- [x] Escrita em Agent mode

## Próximo passo sugerido

- `/detectar-divergencias` (opcional) ou restaurar tracking de `AGENTS.md` se for a prioridade operacional
