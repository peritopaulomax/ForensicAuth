# Exemplo passo a passo: Ensemble calibrado (detectores + população + LR)

Tutorial do scaffold **ensemble** (Wave 2) — manifesto → dry-run → gerar →
contrato do `pipeline.py` → UI (`GenericEnsembleAnalysis`).

Pré-requisito: ler [`03-scaffold-technique.md`](03-scaffold-technique.md)
(especialmente §5 cards, §9 ensemble e o apêndice de campos YAML).

Exemplos irmãos:

| Template | Doc |
|----------|-----|
| `medium` | [`04-scaffold-example-median-denoise.md`](04-scaffold-example-median-denoise.md) |
| `comparison` | [`05-scaffold-example-phash-comparison.md`](05-scaffold-example-phash-comparison.md) |

YAML de referência no repo: `scripts/technique/examples/ensemble.yaml`.

Ambiente:

```bash
conda activate forensicauth
cd "/caminho/VA-Suite"
```

> **Escopo:** este tutorial ensina o **contrato** do automatizador e da UI.  
> Features de população (`reference_data/<domain>/`) são publicadas **offline**  
> (não pelo scaffold). O motor LR completo (LogReg + bigaussian) fica no  
> `pipeline.py` da sua técnica — o scaffold só gera stub + página genérica.

---

## Passo 1 — Manifesto em `config/techniques/`

Copie o exemplo (ou crie o arquivo):

```bash
cp scripts/technique/examples/ensemble.yaml \
   config/techniques/demo_ensemble_scores.yaml
```

Conteúdo canônico (igual ao exemplo; ajuste `id` / `card` / detectores à vontade):

```yaml
id: demo_ensemble_scores
template: ensemble
media: imagem
title: "Demo Ensemble Calibrado (scaffold)"
subtitle: "Detectores + gestão de bases + contrato LR (Wave 2)"
description: >
  Técnica de demonstração do scaffold ensemble calibrado.
  A UI espelha áudio spoofing (picker de população, tipicidade, aug).
  Após o scaffold, implemente a lógica em forensics/<id>/pipeline.py.
citation: ""
gpu: false
disabled: true          # card visível mas desabilitado (útil em demo)
admin_only: true
card:
  mode: existing
  group_id: classicas-compressao   # ver §5 do guia 03 — IDs dos grupos
ensemble:
  detectors:
    - id: detector_a
      label: "Detector A (demo)"
    - id: detector_b
      label: "Detector B (demo)"
  result_headers:
    - Modelo
    - Score AI
    - Score Real
    - Razão (Log)
    - Classificação
    - Dispositivo
  selected_param: selected_analyses
  score_display:
    positive_key: score_positive
    negative_key: score_negative
    label_key: label
  reference_lr:
    enabled: true
    mode: calibrated                 # ou result_only
    domain: demo_ensemble_lr
    scores_path: features/scores/scores.csv
    embeddings_path: features/embeddings/
    feature_map:
      detector_a: score_a
      detector_b: score_b
    embedding_map:
      detector_a: emb_a
      detector_b: emb_b
    allow_augmented: true
    allow_typicality: true
    allow_meta_classifier: true
    enable_split_roles: true
    default_meta_classifier: logistic
    population_unit_label: imagens
    lr_positive_label: real
    subgroup_unit_label: subgrupos
    hypothesis_hint: >
      Defina subgrupos para treino/calibração e para teste.
      LR positiva favorece H1 = real/autêntico.
      Meta-classificador: logistic | xgboost.
    macros:
      demo_toy:
        label: Demo toy
        year_range: "2026"
        description: Bases de exemplo (substitua pelas suas).
        items:
          - base_group: ToyBase
            subgroup: gen_alpha
          - base_group: ToyBase
            subgroup: gen_beta
    default_reference_items:
      - base_group: ToyBase
        subgroup: gen_alpha
parameters:
  - name: threshold
    type: float
    widget: slider
    label: Limiar
    default: 0.5
    min: 0.0
    max: 1.0
    step: 0.05
artifacts:
  - key: model_scores_txt_path
    filename: model_scores.txt
    role: txt
    label: Scores (TXT)
    savable: true
```

### Notas importantes

| Campo | Significado |
|-------|-------------|
| `template: ensemble` | Página `GenericEnsembleAnalysis` |
| `card.group_id` | Grupo **existente** na aba Imagem (lista no guia 03 §5) |
| `reference_lr.mode: calibrated` | Picker de população estilo áudio + params de job |
| `macros` **ou** `catalog_endpoint` | Catálogo inline **ou** API GET |
| `role: txt` | Só **Salvar em derivados** (sem download direto do job) |

**Checkpoint:** YAML em `config/techniques/<id>.yaml`.

---

## Passo 2 — Dry-run

```bash
python scripts/technique/scaffold_technique.py \
  config/techniques/demo_ensemble_scores.yaml --dry-run
```

Ou, sem copiar:

```bash
python scripts/technique/scaffold_technique.py --example ensemble --dry-run
```

**Checkpoint:** exit 0, linhas `DRY` (plugin, pipeline, patches `scaffolded*`).

---

## Passo 3 — Gerar

```bash
python scripts/technique/scaffold_technique.py \
  config/techniques/demo_ensemble_scores.yaml
```

Use `--force` só se for **regenerar** plugin/teste/`pipeline.py` (apaga implementação).

**Checkpoint:** existem

- `src/backend/core/plugins/<id>_plugin.py`
- `src/backend/forensics/<id>/pipeline.py` (stub)
- entradas em `scaffoldedTechniques.tsx` (etc.)

---

## Passo 4 — Contrato do `pipeline.run`

Arquivo: `src/backend/forensics/<id>/pipeline.py`.

### Entrada (calibrated)

```python
parameters["selected_analyses"]          # list[str]
parameters["reference_lr_enabled"]       # bool
parameters["reference_population"]       # {fit_items, test_items} ou {items}
parameters["meta_classifier"]            # opcional
parameters["use_augmented_reference"]    # opcional
parameters["use_latent_typicality"]      # opcional
parameters["reference_lr_domain"]        # opcional (eco do YAML)
# + seus parameters do manifesto (ex.: threshold)
```

### Saída mínima útil

| Chave | Uso na UI |
|-------|-----------|
| `success` | Job ok/erro |
| `individual_results` | Tabela (linhas; tipicamente 6 colunas) |
| `score_positive` / `score_negative` / `label` | Badges se `score_display` no YAML |
| `reference_lr` | Objeto do `ReferenceLrPanel` (métricas, `questioned`, `test_metrics`…) |
| `lr_reference_{tippett,distribution,identity}.png` | Plots (via `fetchImage`) |
| `*_path` dos artifacts | Ex.: `model_scores_txt_path` → **Salvar** derivado |

Features da população: ler de  
`reference_data/<domain>/<scores_path>` (já publicadas).  
O pipeline **não** extrai a base inteira no job do questionado.

Calibração esperada (espelho áudio): LogReg (train) → logits (val) →
bigaussianização → Tippett / Cllr / EER (test) + LR do questionado.

**Checkpoint:** stub substituído; job devolve `success: true` + tabela (+ LR se calibrated).

---

## Passo 5 — UI

1. Stack frontend/backend ativos; login (admin se `admin_only: true`).  
2. Caso com evidência do tipo `media`.  
3. Grupo do `card.group_id` (ou grupo novo se `mode: new`).  
4. Se `disabled: true`, o card aparece off — mude para `false` e re-rode o scaffold (ou edite o patch) para testar.  
5. Selecione detectores + população (fit/test) → Processar.

Artefatos: use **Salvar em derivados** (custódia). Não há “Baixar” direto do job.

---

## Passo 6 — Limpeza (se for só exercício)

Remova técnica gerada + patches `scaffold-entry:<id>` + YAML em `config/techniques/`  
+ dados em `reference_data/<domain>/` se tiver criado.  
**Não** apague `scripts/technique/examples/ensemble.yaml` nem a infra Wave 2.

---

## Riscos

| Risco | Nível | Mitigação |
|-------|-------|-----------|
| `calibrated` sem CSV publicado | Alto | Publique `reference_data/<domain>/` antes do job |
| Nomes `base_group`/`subgroup` ≠ macros | Alto | Mesmos ids no CSV e no YAML |
| Confundir com sintético/spoofing de produção | Médio | IDs/demo + `disabled`/`admin_only` |
| `--force` apaga `pipeline.py` | Médio | Commit antes |

---

## Onde aprofundar

- Campos YAML completos e **IDs dos cards**: [`03-scaffold-technique.md`](03-scaffold-technique.md)  
- Exemplo mínimo: `scripts/technique/examples/ensemble.yaml`
