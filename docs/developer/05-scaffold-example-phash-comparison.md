# Exemplo passo a passo: Similaridade por Perceptual Hash (aHash)

Tutorial completo do scaffold **comparison** — manifesto → dry-run → gerar →
implementar `pipeline.py` → testar na UI (referências globais por rótulo).

Pré-requisito: ler [`03-scaffold-technique.md`](03-scaffold-technique.md).

Exemplos irmãos:  
[`04` medium mediana](04-scaffold-example-median-denoise.md) ·  
[`06` ensemble](06-scaffold-example-ensemble.md).

Ambiente:

```bash
conda activate forensicauth
cd "/caminho/VA-Suite"
```

---

## Passo 1 — Manifesto YAML

Crie o arquivo:

`config/techniques/image_phash_similarity.yaml`

Conteúdo:

```yaml
id: image_phash_similarity
template: comparison
media: imagem
title: "Similaridade por Perceptual Hash (aHash)"
subtitle: "Matriz de similaridade entre imagens · hash médio 8×8"
description: >
  Calcula average hash (aHash) de cada imagem e monta a matriz de
  similaridade (1 − distância de Hamming / nbits) entre referências e
  questionadas, ou todas × todas. Exemplo didático do scaffold comparison.
citation: |
  ZAUNER, Christoph. Implementation and Benchmarking of Perceptual
  Image Hash Functions. Master's thesis, Upper Austria University of
  Applied Sciences, Hagenberg, 2010.
gpu: false
disabled: false
admin_only: false
card:
  mode: existing
  group_id: classicas-correlacao
comparison:
  modes: [with_reference, all_pairs]
  # Refs globais da aba Referências (por rótulo), filtradas por tipo imagem
  reference_source: case_references
  min_questioned: 1
  min_references: 1
parameters:
  - name: hash_size
    type: int
    widget: slider
    label: Tamanho do hash (lado)
    default: 8
    min: 4
    max: 16
    step: 2
    description: aHash em hash_size×hash_size (bits = lado²)
artifacts:
  - key: similarity_matrix_image_path
    filename: similarity_matrix.png
    role: plot_data
    label: Matriz de similaridade
    savable: true
  - key: similarity_json_path
    filename: similarity_matrices.json
    role: json
    label: JSON das matrizes
    savable: true
```

Notas:

- `template: comparison` → página `GenericComparisonAnalysis`.
- `reference_source: case_references` → usa **referências globais** do caso
  (`global_groups`), escolhidas por **rótulo** (ex.: Imagens-Rotulo1).  
  Não são refs de plugin específicas da técnica.
- `card.group_id: classicas-correlacao` → card em **Clássicas: Correlações entre pixels**.
- Cadastre as refs na aba **Referências** do caso *antes* de testar (se a lista
  estiver vazia, a UI avisa).

**Checkpoint:** arquivo salvo.

---

## Passo 2 — Dry-run do scaffold

```bash
python scripts/technique/scaffold_technique.py config/techniques/image_phash_similarity.yaml --dry-run
```

Esperado: exit 0 e linhas `DRY` para plugin, `pipeline.py`, teste e patches
`scaffolded*` + `scaffolded_artifact_mappings.py` (chaves novas da matriz).

**Checkpoint:** dry-run limpo.

---

## Passo 3 — Gerar de verdade

```bash
python scripts/technique/scaffold_technique.py config/techniques/image_phash_similarity.yaml
```

Esperado: `WRITE` / `PATCH` e a mensagem apontando para
`forensics/image_phash_similarity/pipeline.py`.

Confira em `scaffoldedTechniques.tsx`:

- `component: GenericComparisonAnalysis`
- `comparisonConfig.referenceSource: "case_references"`

Reinicie a API se já estiver rodando; F5 em **Análises** — o card deve aparecer
(pipeline ainda stub).

**Checkpoint:** scaffold ok.

---

## Passo 4 — Implementar `pipeline.py`

Abra **somente**:

`src/backend/forensics/image_phash_similarity/pipeline.py`

Substitua o conteúdo inteiro por:

```python
"""Pipeline forense — técnica ``image_phash_similarity`` (aHash)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

ProgressCb = Callable[[int, str], None] | None


def _ahash(path: str, hash_size: int) -> np.ndarray | None:
    """Average hash: bits = pixels > média (após resize gray hash_size×hash_size)."""
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    small = cv2.resize(img, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    mean = float(np.mean(small))
    return (small > mean).astype(np.uint8).reshape(-1)


def _similarity(a: np.ndarray, b: np.ndarray) -> float:
    nbits = a.size
    if nbits == 0:
        return 0.0
    dist = int(np.count_nonzero(a != b))
    return 1.0 - (dist / nbits)


def _matrix_png(
    matrix: np.ndarray,
    row_labels: list[str],
    col_labels: list[str],
    out_path: Path,
) -> None:
    """Heatmap simples (OpenCV) da matriz de similaridade [0,1]."""
    h, w = matrix.shape
    cell = 48
    left = 140
    top = 100
    canvas = np.ones((top + h * cell + 20, left + w * cell + 20, 3), dtype=np.uint8) * 255
    heat = (np.clip(matrix, 0, 1) * 255).astype(np.uint8)
    colored = cv2.applyColorMap(heat, cv2.COLORMAP_VIRIDIS)
    for i in range(h):
        for j in range(w):
            y0, x0 = top + i * cell, left + j * cell
            canvas[y0 : y0 + cell, x0 : x0 + cell] = colored[i, j]
            txt = f"{matrix[i, j]:.2f}"
            cv2.putText(
                canvas,
                txt,
                (x0 + 8, y0 + cell // 2 + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
    for i, lab in enumerate(row_labels):
        cv2.putText(
            canvas,
            lab[:18],
            (8, top + i * cell + cell // 2 + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (30, 30, 30),
            1,
            cv2.LINE_AA,
        )
    for j, lab in enumerate(col_labels):
        cv2.putText(
            canvas,
            lab[:12],
            (left + j * cell + 4, top - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (30, 30, 30),
            1,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(out_path), canvas)


def run(
    evidence_path: str,
    parameters: dict[str, Any],
    out_dir: Path,
    *,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def progress(pct: int, msg: str) -> None:
        if on_progress:
            on_progress(pct, msg)

    mode = str(parameters.get("mode") or "with_reference")
    hash_size = int(parameters.get("hash_size", 8))
    hash_size = max(4, min(16, hash_size))

    # Após resolve do JobService (x-forensic-role no plugin gerado):
    q_paths = [str(p) for p in (parameters.get("questioned_paths") or [])]
    q_labels = [str(x) for x in (parameters.get("questioned_labels") or [])]
    r_paths = [str(p) for p in (parameters.get("reference_paths") or [])]
    r_labels = [str(x) for x in (parameters.get("reference_labels") or [])]

    if not q_paths and evidence_path:
        q_paths = [evidence_path]
        q_labels = [Path(evidence_path).name]

    while len(q_labels) < len(q_paths):
        q_labels.append(Path(q_paths[len(q_labels)]).name)
    while len(r_labels) < len(r_paths):
        r_labels.append(Path(r_paths[len(r_labels)]).name)

    progress(10, "Preparando listas")

    if mode == "all_pairs":
        if len(q_paths) < 2:
            return {
                "success": False,
                "error": "all_pairs exige ao menos 2 questionados",
                "adapter": "image_phash_similarity",
            }
        row_paths, row_labels = q_paths, q_labels
        col_paths, col_labels = q_paths, q_labels
    else:
        if not r_paths or not q_paths:
            return {
                "success": False,
                "error": "with_reference exige reference_paths e questioned_paths",
                "adapter": "image_phash_similarity",
            }
        row_paths, row_labels = r_paths, r_labels
        col_paths, col_labels = q_paths, q_labels

    progress(30, "Calculando aHash")
    row_hashes: list[np.ndarray | None] = [_ahash(p, hash_size) for p in row_paths]
    col_hashes: list[np.ndarray | None] = (
        row_hashes if mode == "all_pairs" else [_ahash(p, hash_size) for p in col_paths]
    )

    if any(h is None for h in row_hashes) or any(h is None for h in col_hashes):
        return {
            "success": False,
            "error": "Falha ao carregar uma ou mais imagens para aHash",
            "adapter": "image_phash_similarity",
        }

    progress(60, "Montando matriz")
    matrix = np.zeros((len(row_hashes), len(col_hashes)), dtype=np.float64)
    for i, ha in enumerate(row_hashes):
        assert ha is not None
        for j, hb in enumerate(col_hashes):
            assert hb is not None
            matrix[i, j] = _similarity(ha, hb)

    png_path = out_dir / "similarity_matrix.png"
    json_path = out_dir / "similarity_matrices.json"

    progress(80, "Gravando artefatos")
    _matrix_png(matrix, row_labels, col_labels, png_path)

    payload = {
        "mode": mode,
        "hash_size": hash_size,
        "nbits": hash_size * hash_size,
        "metrics": {
            "ahash": {
                "matrix": matrix.tolist(),
                "row_labels": row_labels,
                "col_labels": col_labels,
            }
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    progress(100, "Concluído")
    return {
        "success": True,
        "adapter": "image_phash_similarity",
        "mode": mode,
        "reference_count": 0 if mode == "all_pairs" else len(r_paths),
        "questioned_count": len(q_paths),
        "similarity_matrix_image_path": str(png_path),
        "similarity_json_path": str(json_path),
        "metrics": payload["metrics"],
    }
```

Smoke opcional:

```bash
PYTHONPATH=src/backend python -c "
from forensics.image_phash_similarity.pipeline import run
print('import ok')
"
```

**Checkpoint:** arquivo salvo; import ok.

---

## Passo 5 — Testar na UI

1. Reinicie API/frontend se necessário.
2. Abra um caso que tenha:
   - evidências de imagem (questionadas);
   - referências **globais** na aba **Referências** (ex.: grupo Imagens-Rotulo1).  
     A badge `Referencias (N)` deve incluir as globais.
3. **Análises** → **Imagem** → **Clássicas: Correlações entre pixels** →
   **Similaridade por Perceptual Hash (aHash)**.
4. Aba **Com referência**:
   - escolha o **rótulo** global;
   - confirme os arquivos de referência;
   - selecione questionadas;
   - ajuste `hash_size` se quiser → **Processar**.
5. Verifique heatmap PNG + tabela numérica (`metrics.ahash`) e **Salvar em derivados**.
6. Opcional: aba **Todas × todas** com ≥ 2 questionadas.

**Checkpoint:** processamento e UI ok.

---

## O que o scaffold gera (resumo)

| Artefato | Papel |
|----------|--------|
| `core/plugins/image_phash_similarity_plugin.py` | Adapter com `x-forensic-role` (não editar a lógica aqui) |
| `forensics/image_phash_similarity/pipeline.py` | **Único lugar** da lógica forense |
| `scaffoldedTechniques.tsx` | Página `GenericComparisonAnalysis` + `comparisonConfig` |
| `scaffoldedTechniqueMeta.ts` | Título, citação, detalhe |
| `scaffoldedMediaGroups.ts` | Card no grupo (qualquer mídia) |
| `scaffoldedRouteMeta.ts` | Rota |
| `scaffolded_artifact_mappings.py` | Mapeia `similarity_matrix_image_path` etc. |

---

## Como desfazer o exemplo

Remova os arquivos gerados e limpe as entradas `scaffold-entry:image_phash_similarity`
nos `scaffolded*`, ou peça ao agente para reverter. A infra do scaffold permanece.

---

## Referências

- Guia completo do manifesto: [`03-scaffold-technique.md`](03-scaffold-technique.md)
- Exemplo medium: [`04-scaffold-example-median-denoise.md`](04-scaffold-example-median-denoise.md)
- Guia do contribuidor: [`02-guia-contribuidor.md`](02-guia-contribuidor.md)
