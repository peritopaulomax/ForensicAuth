# 14-module-derivation-lineage.md - Grafo de Derivacao e Proveniencia

## Responsabilidade

Expor a cadeia de insumos → operacao forense → artefato derivado promovido, para auditoria e reproducao.

## API

### `GET /api/v1/evidences/{evidence_id}/lineage`

Retorna grafo DAG com:

| Campo | Descricao |
|-------|-----------|
| `nodes[]` | Evidencias (upload/derivadas) e nos sinteticos (`is_synthetic`) |
| `edges[]` | Relacoes insumo → derivado com `technique`, `procedure_summary`, `source_job_id` |
| `operations[]` | Operacoes merge (>=2 insumos) |
| `phases[]` | Camadas do DAG |
| `derivation_groups[]` | Irmaos promovidos do mesmo `derivation_group_id` / `source_job_id` |
| `legacy_notes[]` | Avisos de metadados legados (PRNU antigo, sem `parent_inputs`) |

### `GET /api/v1/analysis/provenance-contract`

Matriz estatica por tecnica: `parent_roles`, `min_parameters`, `savable_artifacts`, `conceptual_inputs`.

## Nos sinteticos

Populacao LR em deteccao sintetica nao e arquivo fisico. O grafo inclui no sintetico:

- `synthetic_kind: lr_reference_population`
- `sha256` = hash canonico da selecao (`reference_population_hash`)
- aresta com role `lr_reference_population`

## Metadados ao salvar derivado

Todo derivado novo deve incluir em `extra_metadata`:

- `derivation_group_id` (= `source_job_id` do job de origem)
- `parent_inputs[]` com `sha256` e `role`
- `provenance` v1 + `reproducibility`
- `derivation_outputs` com metricas da tecnica

## UI

- Apos salvar na pagina de analise: banner com link ao grafo e aba Derivados (`DerivativeSaveNotifier`).
- Aba Derivados: lista, pacotes multi-artefato, modal de grafo.
- Aba Custodia: botao "Ver grafo de derivacao" em registros `derivative_saved`.

## Regras

- **RN-LIN-01**: Grafos sao montados apenas a partir de metadados persistidos (sem inferencia oculta), exceto fallbacks documentados para PRNU legado.
- **RN-LIN-02**: Nos sinteticos nunca entram na custodia como evidencia fisica.
- **RN-LIN-03**: `derivation_group_id` agrupa artefatos promovidos do mesmo job (ex.: resampling multiplos PNGs).
