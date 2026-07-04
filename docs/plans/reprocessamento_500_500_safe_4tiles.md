# Plano de Reprocessamento: 500/500 por Gerador + SAFE com 4 Tiles

> Status: **PRONTO PARA EXECUÇÃO**  
> Criado em: 2026-07-02  
> Quando quiser executar, diga: **"execute o plano de reprocessamento 500/500 com SAFE 4 tiles"**.

---

## 1. Contexto e Objetivo

As bases de referência LR foram ampliadas de **150 reais + 150 sintéticas** para **500 reais + 500 sintéticas** por gerador. Os manifests originais já refletem esse novo tamanho.

Além disso, o detector **SAFE**, que hoje usa apenas um crop central de 256×256, passará a usar **4 tiles** (sempre incluindo o tile central) com média dos logits.

O objetivo deste plano é:

1. Regenerar todas as augmentations a partir dos novos manifests (500/500).
2. Modificar o pipeline SAFE para 4 tiles + média de logits.
3. Recalcular todos os scores dos detectores sobre originais + augmentations.
4. Reconstruir o score matrix aumentado final.
5. Validar integridade e métricas.

---

## 2. Estado Atual (pré-execução)

- Manifests originais atualizados com ~51.000 imagens.
- Augmentations antigas (baseadas em 150/150) existem em `*_lr_sample_augmented/`.
- Score matrix aumentado antigo: `outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv` (~126.664 linhas).
- Scorer atual: `scripts/run_lr_score_matrix_batched_v2.py` (SAFE single crop).

---

## 3. Alterações de Código Necessárias

### 3.1. Implementar SAFE com 4 tiles

Criar/modificar função em `src/backend/core/legacy/safe/safe_pipeline.py`:

```python
def infer_safe_from_pil_tiled(
    image: Image.Image,
    device: torch.device,
    n_tiles: int = 4,
) -> float:
    """Run SAFE on N tiles and return average logit probability.

    Tile 0 is always the central 256x256 crop. Remaining tiles are
    extracted from quadrants to cover distinct image regions.
    """
    # 1. Determinar crop central 256x256 (tile 0).
    # 2. Extrair tiles adicionais de regiões diferentes (ex: cantos ou quadrantes).
    # 3. Para cada tile, chamar a rede SAFE existente e obter fake_prob.
    # 4. Converter cada fake_prob em logit.
    # 5. Retornar sigmoid(mean(logits)).
```

**Regras:**
- Não alterar a rede SAFE em si (camada de inferência permanece igual).
- Tile central sempre incluso.
- Tiles adicionais devem ser crops de 256×256 de regiões distintas.
- Se a imagem for menor que 256×256, usar apenas o tile disponível (fallback para single crop).

### 3.2. Atualizar o scorer para usar SAFE tiled

Em `scripts/run_lr_score_matrix_batched_v2.py`, substituir:

```python
prob = safe_pipeline.infer_safe_from_pil(image, device)
```

por:

```python
prob = safe_pipeline.infer_safe_from_pil_tiled(image, device, n_tiles=4)
```

### 3.3. Ajustar sample_multiplier (se necessário)

O `sample_multiplier` atual é 5 (1 original + 4 augmentations). Manter.

Caso se queira aumentar `SAMPLE_PER_CLASS` no futuro (ex: de 150 para 500), isso deve ser feito em `src/backend/core/synthetic_lr_reference.py` **antes** da execução, mas requer que as bases tenham 500/500 — o que agora é verdade.

> **Nota de decisão:** este plano assume `SAMPLE_PER_CLASS = 150` e `sample_multiplier = 5`. Se quiser aproveitar os 500/500 aumentando `SAMPLE_PER_CLASS`, adicione esse passo antes de iniciar.

---

## 4. Passo a Passo de Execução

### Passo 1 — Backup do score matrix antigo (opcional mas recomendado)

```bash
cp "outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv" \
   "outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented_pre_500_500.csv"
```

### Passo 2 — Implementar SAFE 4 tiles

Editar `src/backend/core/legacy/safe/safe_pipeline.py` e `scripts/run_lr_score_matrix_batched_v2.py` conforme seção 3.

Validar com teste rápido:

```bash
cd "/home/bfl-pcf/VA Suite"
python3 -c "
import sys; sys.path.insert(0, 'src/backend')
import torch
from PIL import Image
from core.legacy.safe import safe_pipeline
from core.gpu_inference import resolve_inference_device
img = Image.new('RGB', (512, 512), color='red')
device = resolve_inference_device()
print('single:', safe_pipeline.infer_safe_from_pil(img, device))
print('tiled4:', safe_pipeline.infer_safe_from_pil_tiled(img, device, n_tiles=4))
"
```

### Passo 3 — Limpar augmentations antigas

```bash
rm -rf /home/bfl-pcf/datasets/*_lr_sample_augmented
```

### Passo 4 — Gerar augmentations para todas as bases (paralelo)

Rodar em background, uma por base:

```bash
python3 "/home/bfl-pcf/VA Suite/scripts/augment_lr_dataset.py" \
  --manifest /home/bfl-pcf/datasets/defactify_lr_sample/manifest.csv \
  --out-dir /home/bfl-pcf/datasets/defactify_lr_sample_augmented --force

python3 "/home/bfl-pcf/VA Suite/scripts/augment_lr_dataset.py" \
  --manifest /home/bfl-pcf/datasets/genimage_lr_sample/manifest.csv \
  --out-dir /home/bfl-pcf/datasets/genimage_lr_sample_augmented --force

python3 "/home/bfl-pcf/VA Suite/scripts/augment_lr_dataset.py" \
  --manifest /home/bfl-pcf/datasets/aigcdetectbenchmark_lr_sample/manifest.csv \
  --out-dir /home/bfl-pcf/datasets/aigcdetectbenchmark_lr_sample_augmented --force

python3 "/home/bfl-pcf/VA Suite/scripts/augment_lr_dataset.py" \
  --manifest /home/bfl-pcf/datasets/opensdi_lr_sample/manifest.csv \
  --out-dir /home/bfl-pcf/datasets/opensdi_lr_sample_augmented --force

python3 "/home/bfl-pcf/VA Suite/scripts/augment_lr_dataset.py" \
  --manifest /home/bfl-pcf/datasets/aigibench_lr_sample/manifest.csv \
  --out-dir /home/bfl-pcf/datasets/aigibench_lr_sample_augmented --force

python3 "/home/bfl-pcf/VA Suite/scripts/augment_lr_dataset.py" \
  --manifest /home/bfl-pcf/datasets/aigibench_socialrf_lr_sample/manifest.csv \
  --out-dir /home/bfl-pcf/datasets/aigibench_socialrf_lr_sample_augmented --force

python3 "/home/bfl-pcf/VA Suite/scripts/augment_lr_dataset.py" \
  --manifest /home/bfl-pcf/datasets/synthbuster_lr_sample/manifest.csv \
  --out-dir /home/bfl-pcf/datasets/synthbuster_lr_sample_augmented --force

python3 "/home/bfl-pcf/VA Suite/scripts/augment_lr_dataset.py" \
  --manifest /home/bfl-pcf/datasets/bfree_extended_lr_sample/manifest.csv \
  --out-dir /home/bfl-pcf/datasets/bfree_extended_lr_sample_augmented --force
```

**Total esperado:** ~51.000 originais → 204.000 variações.

### Passo 5 — Calcular scores (sequencial na GPU)

Usar o script mestre:

```bash
cd "/home/bfl-pcf/VA Suite"
python3 scripts/score_all_augmented_datasets.py --batch-size 16
```

Esse script:
- Roda `run_lr_score_matrix_batched_v2.py` para cada base aumentada.
- Faz merge de todos os scores no score matrix aumentado final.

### Passo 6 — Validar

```bash
cd "/home/bfl-pcf/VA Suite"
python3 - << 'PYEOF'
import pandas as pd
df = pd.read_csv("outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv", low_memory=False)
print("Total rows:", len(df))
print("Augmentation distribution:")
print(df["augmentation"].fillna("(original)").value_counts().to_dict())
print("Datasets:")
print(df["dataset"].value_counts().to_dict())
PYEOF
```

Esperado:
- Total rows: ~255.000
- Cada augmentation (`jpeg_85`, `webp_80`, `crop_upscale`, `resize_down_50`): ~51.000
- Originais: ~51.000

### Passo 7 — Testes unitários

```bash
cd "/home/bfl-pcf/VA Suite"
python3 -m pytest tests/unit/test_synthetic_image_detection.py -v
```

### Passo 8 — Validar LR calibrada

```bash
cd "/home/bfl-pcf/VA Suite"
python3 scripts/evaluate_augmentation_impact.py \
  --reference outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv \
  --augmented outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv \
  --out-dir outputs/lr_calibration/augmentation_impact_500_500_safe4tiles
```

---

## 5. Tempo Estimado

| Etapa | Tempo estimado |
|---|---|
| Implementar SAFE 4 tiles | 15–30 min |
| Gerar augmentations (paralelo) | ~75–90 min |
| Calcular scores (sequencial GPU) | ~7–8h (SAFE 4 tiles aumenta o scoring) |
| Merge + validações | ~15 min |
| **Total** | **~8,5–10h** |

> Nota: o scoring será mais lento que a rodada anterior (~5h) porque o SAFE agora processa 4 tiles por imagem.

---

## 6. Critérios de Aceitação

- [ ] `infer_safe_from_pil_tiled` existe e retorna probabilidade entre 0 e 1.
- [ ] Score matrix aumentado final tem ~255.000 linhas.
- [ ] Distribuição de augmentations está balanceada (~51.000 de cada tipo).
- [ ] Todos os testes unitários passam.
- [ ] `compute_reference_lr` com augmentation ativa funciona e retorna `sample_rows` maior que sem augmentation.
- [ ] Cache LR continua funcionando (chamadas subsequentes rápidas).

---

## 7. Riscos e Mitigações

| Risco | Mitigação |
|---|---|
| SAFE tiled muda comportamento do detector | Manter tile central e validar CLLr/EER/AUC no piloto. |
| Scoring muito longo | Rodar em background; usar `--resume` em caso de interrupção. |
| OOM na GPU | Manter scoring sequencial (uma base por vez), batch 16. |
| Manifests inconsistentes | Verificar contagem de linhas por base antes do merge. |

---

## 8. Decisões Pendentes

Antes de executar, confirmar:

1. **Manter `SAMPLE_PER_CLASS = 150`?**  
   Se quiser aproveitar os 500/500 e aumentar para 500, informe. Caso contrário, mantemos 150.

2. **Estratégia dos 4 tiles do SAFE:**  
   - Opção A: central + 3 cantos.  
   - Opção B: grid 2×2 com overlap.  
   - Opção C: central + 3 tiles em quadrantes fixos.  
   Recomendo **Opção C** (central + quadrantes) por cobertura mais uniforme.

3. **Agregação:**  
   - Média aritmética dos logits (recomendada).  
   - Alternativa: média das probabilidades.
