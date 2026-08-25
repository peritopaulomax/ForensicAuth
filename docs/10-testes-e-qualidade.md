# 10 — Testes e qualidade

## Pirâmide

| Camada | Onde | Ferramenta | No default? |
|--------|------|------------|-------------|
| Unit | `tests/unit/` | pytest | Sim |
| Integration | `tests/integration/` | pytest | Sim (filtrado) |
| Aceitação SDD | `tests/specs/*.md` | Manual / revisão | Não executa |
| FE unit | frontend | Vitest | À parte |
| E2E UI | `src/frontend/e2e/` | Playwright | À parte |

Markers em `pytest.ini`: `weights`, `gpu`, `slow`, `integration`, `e2e`.
Inventário em 2026-08-25: 88 arquivos pytest (80 unitários + 8 de
integração) e 12 specs Playwright. A contagem deve ser confirmada no tree; não
é métrica de cobertura.

## Comando canônico (sem pesos/GPU)

```bash
conda activate forensicauth
PYTHONPATH=src/backend pytest tests/unit tests/integration -m "not weights and not gpu" -q
```

Suite completa / pesos: [`developer/02-guia-contribuidor.md`](developer/02-guia-contribuidor.md) § testes.

## Frontend

```bash
cd src/frontend
npm install
npm run test
npm run build
npx playwright test
```

Não existe script `npm run test:e2e` no `package.json`; use diretamente
Playwright. Os E2E usam mocks extensos, portanto mantenha também um smoke com
backend real para login, upload e job.

## Política

Qualquer mudança em `src/backend/forensics/` ou `vendor/` exige:

1. Teste de regressão vs baseline  
2. Erro zero ou tolerância **aprovada**  
3. Aprovação explícita antes de merge  

Ver `AGENTS.md` Regra 8 e Regra 4 (testes verdes).

## TDD / SDD no projeto

1. Ler `docs/specs/00-overview.md` + módulo  
2. Ler `tests/specs/` correspondente  
3. Implementar  
4. Rodar pytest imediatamente  

Specs de módulo: `docs/specs/modules/02` … `15`.

## Como verificar qualidade local

| Check | Ação |
|-------|------|
| Unit+integration default | comando canônico acima |
| Plugin novo | testes do scaffold + smoke API |
| Custody | testes de cadeia / verify |
| FE | Vitest + Playwright smoke login |

## CI e gates

Não há pipeline CI versionado nem relatório de cobertura publicado. Metas de
cobertura em specs são objetivos, não evidência. Enquanto isso, o gate é local:

1. pytest default;
2. Vitest + build do frontend;
3. Playwright pertinente à mudança;
4. suites `weights/gpu` em hardware homologado quando a mudança toca ML;
5. comparação de baseline e aprovação explícita para algoritmos protegidos.

Falha em teste pesado não autoriza substituir silenciosamente modelo, vendor
ou algoritmo. Registre versão, hardware, hash dos pesos e motivo da falha.

## Índice

Voltar ao [mapa do manual](README.md).
