# tests/ — suite ForensicAuth

## Layout

```text
tests/
  unit/           # suite DEFAULT
  integration/    # poucos fluxos HTTP/DB
  fixtures/       # imagens/native/prnu + video/inpainting (demos TruVIL/ViLocal)
  specs/          # aceite SDD (Markdown; não pytest) — ver specs/README.md
  conftest.py
```

## Como rodar

```bash
conda activate forensicauth
# Default (sem pesos/GPU) — hábito diário
PYTHONPATH=src/backend pytest tests/unit tests/integration -m "not weights and not gpu" -q

# Completo
PYTHONPATH=src/backend pytest tests/unit tests/integration -q

# Só pesos/GPU
PYTHONPATH=src/backend pytest tests/unit tests/integration -m "weights or gpu" -q
```

Markers: `weights`, `gpu`, `slow` (`pytest.ini` + `conftest.py`).

## Regras rápidas

1. Inferência real com checkpoint → `@pytest.mark.weights` (e/ou `gpu`).
3. Runtime LR = **publish** (`reference_data/`), não BUILD/samples.
4. Specs de aceite: `tests/specs/` ↔ produto em `docs/specs/`.

## OPTIONAL (fora do default)

| Área | Marker |
|---|---|
| Embeddings / smoke FSD·UFD | `weights` (+ `gpu` no smoke) |
| PAD / SLS / WeDefense / LFV checkpoint / ObjectFormer / ensemble SDXL | `weights` nos cases reais |
| Peritus C++ / golden pesado | `slow` |

Mocks e contratos “pesos ausentes” ficam no default.





## Contagem aproximada

~72 módulos `test_*.py` em `unit/`+`integration/` · specs Markdown à parte.

Lista arquivo → propósito: [`CATALOG.md`](./CATALOG.md).
