# tests/specs — contratos de aceite (SDD), não pytest

Decisão **Fase 6 (poda 2026-07):** estes Markdown **permanecem** em `tests/specs/`.
Não foram movidos para `docs/specs/acceptance/`.

| Camada | Onde | Papel |
|---|---|---|
| Spec de produto / arquitetura | `docs/specs/` | O que o sistema deve fazer |
| Spec de teste (aceite TDD) | **`tests/specs/`** (aqui) | O que os testes devem cobrir (IDs TU-*) |
| Testes executáveis | `tests/unit/`, `tests/integration/` | pytest |

## O que isto **não** é

- Não é coletado pelo pytest (só `.py` com `test_*`).
- Não substitui `docs/specs/modules/*.md`.
- Não entra na contagem de “módulos no suite default”.

## Índice

| Arquivo | Spec de produto relacionada |
|---|---|
| `test-overview.md` | `docs/specs/00-overview.md` |
| `test-integration.md` | fluxos cross-módulo |
| `test-module-auth.md` | `docs/specs/modules/` auth |
| `test-module-core.md` | core / plugins |
| `test-module-custody.md` | custody |
| `test-module-jobs.md` | jobs |
| `test-module-image.md` | image |
| `test-module-audio.md` | audio |
| `test-module-video.md` | video |
| `test-module-pdf.md` | pdf |
| `test-module-case-sharing.md` | case sharing |
| `test-module-case-transfer.md` | case transfer / VCP |
| `test-module-pad.md` | PAD (`13-module-pad`) |
| `test-module-moe-ffd.md` | MoE-FFD (`15-module-moe-ffd`) |

## Como usar (agente / contribuídor)

1. Ler `docs/specs/00-overview.md` + módulo em `docs/specs/modules/`.
2. Ler o `test-module-*.md` correspondente **antes** de implementar (AGENTS.md regra 5).
3. Implementar/ajustar `tests/unit` ou `tests/integration`.
4. Rodar o suite default:

```bash
conda activate forensicauth
PYTHONPATH=src/backend pytest tests/unit tests/integration -m "not weights and not gpu" -q
```

Ver também: [`tests/README.md`](../README.md).
