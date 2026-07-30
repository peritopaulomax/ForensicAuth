# Exemplo passo a passo: Resíduo de Denoising (Filtro de Mediana)

Tutorial completo usando o scaffold de técnicas (`simple` / `medium`).  
Reproduz o exercício feito na receita de bolo: manifesto → dry-run → gerar → implementar `pipeline.py` → testar na UI.

Pré-requisito: ler [`03-scaffold-technique.md`](03-scaffold-technique.md).

Exemplos irmãos:  
[`05` comparison aHash](05-scaffold-example-phash-comparison.md) ·  
[`06` ensemble](06-scaffold-example-ensemble.md).

Ambiente:

```bash
conda activate forensicauth
cd "/caminho/VA-Suite"
```

---

## Passo 1 — Manifesto YAML

Crie o arquivo:

`config/techniques/median_denoise_residual.yaml`

Conteúdo:

```yaml
id: median_denoise_residual
template: medium
media: imagem
title: "Resíduo de Denoising (Filtro de Mediana)"
subtitle: "Imagem − mediana · mapa de resíduo"
description: >
  Aplica filtro de mediana à evidência e calcula o resíduo
  (original − filtrada), útil para evidenciar texturas e ruído local.
citation: |
  GONZALEZ, Rafael C.; WOODS, Richard E. Digital Image Processing.
  4. ed. New York: Pearson, 2018. Cap. 5 — Image Restoration and Reconstruction.
paper:
  title: "Digital Image Processing — Median filtering / residual (referência didática)"
  venue: "Pearson 2018"
  sources:
    - "https://www.pearson.com"
  local_file: "median_denoise_residual/median_denoise_residual_paper.pdf"
gpu: false
disabled: false
admin_only: false
card:
  mode: existing
  group_id: classicas-correlacao
parameters:
  - name: kernel_size
    type: int
    widget: slider          # number | slider (int/float); radio | select (enum)
    label: Tamanho do filtro (px)
    default: 5
    min: 3
    max: 31
    step: 2
    description: Deve ser ímpar (3, 5, 7, …)
artifacts:
  - key: original_crop_path
    filename: original.png
    role: original
    label: Original
    savable: false
  - key: heatmap_path
    filename: heatmap.png
    role: heatmap
    label: Resíduo (mediana)
    savable: true
  - key: overlay_image_path
    filename: overlay.png
    role: overlay
    label: Overlay
    savable: true
```

Notas:

- `widget: slider` gera um controle deslizante na UI (em vez da caixa `number`). Para `enum`, use `radio` ou `select` — ver [`03-scaffold-technique.md`](03-scaffold-technique.md#parâmetros-e-widgets).
- `card.group_id: classicas-correlacao` coloca o card no grupo **Clássicas: Correlações entre pixels**.
- A citação ABNT aparece na página mesmo sem o PDF.
- O botão de download do PDF só funciona depois que existir o arquivo em  
  `docs/references/papers/imdl/median_denoise_residual/median_denoise_residual_paper.pdf` (>1 KB).

**Checkpoint:** arquivo salvo.

---

## Passo 2 — Dry-run do scaffold

```bash
python scripts/technique/scaffold_technique.py config/techniques/median_denoise_residual.yaml --dry-run
```

Esperado: exit 0 e linhas `DRY` para, entre outros:

- `src/backend/core/plugins/median_denoise_residual_plugin.py`
- `src/backend/forensics/median_denoise_residual/pipeline.py`
- `tests/unit/test_median_denoise_residual_plugin.py`
- patches em `scaffoldedTechniqueMeta.ts`, `scaffoldedTechniques.tsx`, `scaffoldedRouteMeta.ts`, `scaffoldedMediaGroups.ts`
- `scaffoldedTechniquePapers.ts`
- `docs/references/papers/imdl/scaffolded_manifest.json`

Nenhum arquivo deve ser criado/alterado de verdade.

**Checkpoint:** dry-run ok.

---

## Passo 3 — Gerar de verdade

```bash
python scripts/technique/scaffold_technique.py config/techniques/median_denoise_residual.yaml
```

Esperado: linhas `WRITE` / `PATCH` e a mensagem:

```text
Próximo passo: edite src/backend/forensics/median_denoise_residual/pipeline.py (função run).
```

Depois:

1. Reinicie a API se já estiver rodando.
2. F5 na aba **Análises** — não deve aparecer “Erro ao carregar técnicas”.
3. No grupo **Clássicas: Correlações entre pixels**, o card da técnica deve aparecer (pipeline ainda stub até o Passo 4).
4. Na página, a **citação** deve aparecer.

**Checkpoint:** scaffold ok + Análises carrega.

---

## Passo 4 — Implementar `pipeline.py`

Abra **somente**:

`src/backend/forensics/median_denoise_residual/pipeline.py`

Substitua o conteúdo inteiro por:

```python
"""Pipeline forense — técnica ``median_denoise_residual``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

ProgressCb = Callable[[int, str], None] | None


def _odd_kernel(size: int) -> int:
    """Garante kernel ímpar >= 3 (OpenCV medianBlur exige ímpar)."""
    k = int(size)
    if k < 3:
        k = 3
    if k % 2 == 0:
        k += 1
    return k


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

    progress(5, "Carregando evidência")
    image = cv2.imread(evidence_path, cv2.IMREAD_COLOR)
    if image is None:
        return {
            "success": False,
            "error": "Falha ao carregar imagem",
            "adapter": "median_denoise_residual",
        }

    kernel_size = _odd_kernel(int(parameters.get("kernel_size", 5)))

    progress(30, f"Filtro de mediana ({kernel_size}×{kernel_size})")
    filtered = cv2.medianBlur(image, kernel_size)

    # Resíduo absoluto por canal; mapa visual em escala de cinza amplificada
    progress(60, "Calculando resíduo")
    residual = cv2.absdiff(image, filtered)
    residual_gray = cv2.cvtColor(residual, cv2.COLOR_BGR2GRAY)
    residual_vis = cv2.normalize(residual_gray, None, 0, 255, cv2.NORM_MINMAX)
    residual_bgr = cv2.cvtColor(residual_vis, cv2.COLOR_GRAY2BGR)

    # Overlay: original com resíduo em vermelho (simples)
    overlay = image.copy()
    overlay[:, :, 2] = np.clip(
        overlay[:, :, 2].astype(np.int16) + residual_vis.astype(np.int16),
        0,
        255,
    ).astype(np.uint8)

    original_path = out_dir / "original.png"
    heatmap_path = out_dir / "heatmap.png"
    overlay_path = out_dir / "overlay.png"

    progress(85, "Gravando artefatos")
    cv2.imwrite(str(original_path), image)
    cv2.imwrite(str(heatmap_path), residual_bgr)
    cv2.imwrite(str(overlay_path), overlay)

    mean_residual = float(np.mean(residual_gray))
    max_residual = float(np.max(residual_gray))

    progress(100, "Concluído")
    return {
        "success": True,
        "adapter": "median_denoise_residual",
        "kernel_size": kernel_size,
        "mean_residual": mean_residual,
        "max_residual": max_residual,
        "original_crop_path": str(original_path),
        "heatmap_path": str(heatmap_path),
        "overlay_image_path": str(overlay_path),
    }
```

Smoke opcional:

```bash
PYTHONPATH=src/backend python -c "
from forensics.median_denoise_residual.pipeline import run
print('import ok')
"
```

**Checkpoint:** arquivo salvo; import ok.

---

## Passo 5 — Testar na UI

1. Reinicie API/frontend se necessário.
2. Caso → **Análises** → **Imagem** → grupo **Clássicas: Correlações entre pixels**.
3. Abra **Resíduo de Denoising (Filtro de Mediana)**.
4. Confira a citação no topo.
5. Selecione uma imagem → ajuste `kernel_size` se quiser → **Processar**.
6. Verifique:
   - abas **Resíduo (mediana)** e **Overlay** alternam e permanecem na aba escolhida;
   - zoom / pan no par de imagens;
   - **Salvar** não faz o viewer desaparecer.

PDF opcional:

```text
docs/references/papers/imdl/median_denoise_residual/median_denoise_residual_paper.pdf
```

**Checkpoint:** processamento e UI ok.

---

## O que o scaffold gera (resumo)

| Artefato | Papel |
|----------|--------|
| `core/plugins/median_denoise_residual_plugin.py` | Adapter `ForensicPlugin` (não editar a lógica aqui) |
| `forensics/median_denoise_residual/pipeline.py` | **Único lugar** da lógica forense |
| `scaffoldedTechniques.tsx` | Página `GenericTechniqueAnalysis` |
| `scaffoldedTechniqueMeta.ts` | Título, citação, detalhe |
| `scaffoldedMediaGroups.ts` | Card no grupo (qualquer mídia) |
| `scaffoldedRouteMeta.ts` | Rota `/analysis/median_denoise_residual` |
| `scaffoldedTechniquePapers.ts` + `scaffolded_manifest.json` | Botão de PDF |

---

## Como desfazer o exemplo

Remova os arquivos gerados e limpe as entradas `scaffold-entry:median_denoise_residual` nos arquivos `scaffolded*`, ou peça ao agente para reverter o exemplo. A infra do scaffold (`scripts/technique/`, página genérica) permanece.

---

## Referências

- Scaffold genérico: [`03-scaffold-technique.md`](03-scaffold-technique.md)
- Guia do contribuidor: [`02-guia-contribuidor.md`](02-guia-contribuidor.md)
