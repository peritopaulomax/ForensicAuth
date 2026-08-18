# Scaffold de técnicas forenses — guia completo (didático)

Este guia explica **tudo** que o automatizador entende hoje: templates, manifesto YAML,
parâmetros, artefatos e — o mais importante — o **vocabulário de `role`**, porque cada
`role` **liga direto a um pedaço da interface**.

> Regra de ouro: **só declare no YAML um `role` que a UI já sabe desenhar.**  
> O scaffold **rejeita** roles desconhecidos. Inventar string sem renderização = erro.

---

## 1. O que o automatizador faz (em uma frase)

Você escreve um **manifesto YAML** → o script gera plugin, stub de pipeline, testes e
liga a técnica a uma **página genérica** (sem React manual) → você só implementa
`forensics/<id>/pipeline.py`.

**Templates com scaffold ativo:** `simple` · `medium` · `comparison` · `ensemble`  
**Roadmap / manual:** `complex` · `hub`

### Tutoriais passo a passo

| Exemplo | Template | Doc |
|---------|----------|-----|
| Resíduo de mediana | `medium` | [`04-scaffold-example-median-denoise.md`](04-scaffold-example-median-denoise.md) |
| Similaridade aHash | `comparison` | [`05-scaffold-example-phash-comparison.md`](05-scaffold-example-phash-comparison.md) |
| Ensemble calibrado | `ensemble` | [`06-scaffold-example-ensemble.md`](06-scaffold-example-ensemble.md) |

YAMLs mínimos: `scripts/technique/examples/{simple,medium,comparison,ensemble}.yaml`.  
**Referência completa de campos YAML:** §4–§10 e [apêndice A](#apêndice-a--referência-completa-do-manifesto-yaml).

---

## 2. Como rodar

```bash
conda activate forensicauth
cd /caminho/VA-Suite

python scripts/technique/scaffold_technique.py path/to/manifest.yaml --dry-run
python scripts/technique/scaffold_technique.py path/to/manifest.yaml
python scripts/technique/scaffold_technique.py --example comparison --dry-run
python scripts/technique/scaffold_technique.py --example ensemble --dry-run
python scripts/technique/scaffold_technique.py path/to/manifest.yaml --force
```

| Flag | Significado |
|------|-------------|
| `--dry-run` | Só mostra o que faria |
| `--force` | Pode sobrescrever plugin/teste/`pipeline.py` |
| `--example …` | Usa YAML de `scripts/technique/examples/` |

Depois: edite **somente** `src/backend/forensics/<id>/pipeline.py`.

---

## 3. Escolha o template (qual página genérica)

| Template | Quando usar | Página |
|----------|-------------|--------|
| `simple` | Resultado = métricas e/ou HTML | `GenericTechniqueAnalysis` |
| `medium` | Resultado = mapas na imagem (heatmap, overlay, máscara…) | `GenericTechniqueAnalysis` |
| `comparison` | Compara 2+ evidências (refs × questionadas ou todas×todas) | `GenericComparisonAnalysis` |
| `ensemble` | Vários detectores + scores (+ LR calibrada / população) | `GenericEnsembleAnalysis` |
| `complex` / `hub` | Relatório multi-etapa / hub — **sem** scaffold genérico | páginas dedicadas |

`complex` ≠ `ensemble`: relatório/multi-etapa vs. vários detectores + scores/LR.  
Produção (`synthetic_image_detection`, `audio_spoofing_detection`) ainda usa páginas dedicadas; o scaffold serve a **novas** técnicas ensemble (Wave 2 alinha o contrato à UI de áudio).

---

## 4. Manifesto YAML — campos de topo

Tabela resumida. **Lista exaustiva (todos os campos aninhados):** [apêndice A](#apêndice-a--referência-completa-do-manifesto-yaml).

| Campo | Obrigatório? | Valores / tipo | O que faz |
|-------|--------------|----------------|-----------|
| `id` | **sim** | snake_case | Nome do plugin, pasta e rota |
| `template` | **sim** | `simple` \| `medium` \| `comparison` \| `ensemble` | Qual UI genérica |
| `media` | **sim** | `imagem` \| `audio` \| `video` \| `pdf` | Tipo de evidência |
| `title` | **sim** | texto | Título na UI |
| `subtitle` | não | texto | Subtítulo do card da técnica |
| `description` | não | texto (pode usar `>`) | Detalhe / intro |
| `citation` | não | texto (`\|` multilinha) | Bibliografia ABNT |
| `license` | não | texto | Mostrado no intro |
| `repo_url` | não | URL | Também aceita alias `repo` |
| `gpu` | não | bool (default false) | Marca GPU |
| `disabled` | não | bool | Card da técnica visível mas off |
| `admin_only` | não | bool | Só admin |
| `card` | recomendado | objeto | **Grupo** onde a técnica aparece (§5) |
| `parameters` | não | lista | Controles do formulário |
| `artifacts` | recomendado | lista | Arquivos + **roles** de UI |
| `comparison` | se comparison | objeto | Modos e fonte de refs |
| `ensemble` | se ensemble | objeto | Detectores, headers, LR |
| `paper` | não | objeto | PDF de referência |

---

## 5. Bloco `card` (onde o card aparece na aba da mídia)

Vale para **todas** as mídias: `imagem` \| `audio` \| `video` \| `pdf`.

O scaffold grava um hook em `src/frontend/src/config/scaffoldedMediaGroups.ts`
(`media` + `groupId` + `entry`), aplicado sobre:

| `media` | Catálogo base |
|---------|----------------|
| `imagem` | `imageAnalysisGroups.ts` |
| `audio` / `video` / `pdf` | `mediaAnalysisGroups.ts` |

Na UI do caso, a aba da mídia mostra **cards de grupo** (não a lista plana de plugins).

- **Imagem:** `/analysis/image-group/:groupId` — evidência compartilhada + **abas** por técnica (embed).
- **Áudio / vídeo / PDF:** `/analysis/media-group/:media/:groupId` — **mesmo padrão** (evidência + abas; `?tab=<technique_id>`).

O scaffold (`card.mode` existing|new) adiciona a técnica ao grupo; ela aparece como **nova aba** em qualquer mídia.

| Campo | Quando | Descrição |
|-------|--------|-----------|
| `mode` | default `existing` | `existing` \| `new` \| `none` |
| `group_id` | `existing` (obrigatório) ou `new` (opcional) | Id do **grupo** (não o título na tela). Deve existir no catálogo da **mesma** `media` |
| `title` | `mode=new` | Título do **novo** grupo |
| `description` | `mode=new` | Texto descritivo do novo grupo |

| `mode` | Efeito |
|--------|--------|
| `existing` | Insere a técnica num grupo **já listado** abaixo para aquela mídia (`group_id` obrigatório e validado) |
| `new` | Cria um grupo novo + coloca a técnica nele (`title` + `description` obrigatórios). Se omitir `group_id`, o scaffold usa `scaffold-<id_da_tecnica>` |
| `none` | Só registry/rota — **sem** card na grade de grupos |

### 5.1 Onde estão os IDs dos grupos (cards)?

Cada objeto de grupo tem:

- `id` → o que você coloca em `card.group_id`
- `title` → texto do card na UI
- `description` → subtítulo do grupo
- `techniques[]` → plugins (e IMDL, só em imagem) já no grupo

```bash
# Imagem
rg -n 'id: "' src/frontend/src/config/imageAnalysisGroups.ts | head -40
# Áudio / vídeo / PDF
rg -n 'id: "' src/frontend/src/config/mediaAnalysisGroups.ts | head -40
```

### 5.2 Catálogo de `group_id` — imagem (`media: imagem`)

Fonte: `imageAnalysisGroups.ts`.

| `group_id` (YAML) | Título na UI |
|-------------------|--------------|
| `estrutura-arquivo` | Estrutura de arquivo |
| `classicas-compressao` | Clássicas: Artefatos de compressão |
| `classicas-correlacao` | Clássicas: Correlações entre pixels |
| `classicas-aquisicao` | Clássicas: Características de aquisição |
| `dl-manipulacao` | Deep Learning: Detecção e Localização de Manipulações em Imagens |
| `dl-sintetico` | Deep Learning: Detecção de Imagens Sintéticas |
| `dl-facial-spoofing` | Deep Learning: Manipulação e Spoofing Facial |

Aliases de URL (compatibilidade): ver `IMAGE_GROUP_ID_ALIASES` (ex.: `biometria-facial` → `dl-facial-spoofing`).
**No manifesto use o id canônico.**

### 5.3 Catálogo de `group_id` — áudio (`media: audio`)

Fonte: `mediaAnalysisGroups.ts`.

| `group_id` (YAML) | Título na UI |
|-------------------|--------------|
| `audio-forense` | Análise forense de áudio (hub: espectral + níveis/DC) |
| `audio-estrutura` | Metadados e parsers de container |
| `audio-spoofing` | Deep Learning: Spoofing / deepfake de áudio |

Aliases de URL (redirecionam para `audio-forense`): `audio-espectral`, `audio-niveis`.

### 5.4 Catálogo de `group_id` — vídeo (`media: video`)

| `group_id` (YAML) | Título na UI |
|-------------------|--------------|
| `video-estrutura` | Estrutura de container |
| `video-manipulacao` | Deep Learning: Manipulação e deepfake de vídeo |

### 5.5 Catálogo de `group_id` — PDF (`media: pdf`)

| `group_id` (YAML) | Título na UI |
|-------------------|--------------|
| `pdf-estrutura` | Estrutura e similaridade |
| `pdf-conteudo` | Conteúdo e extração forense |

### 5.6 Exemplos

**Imagem — grupo existente:**

```yaml
media: imagem
card:
  mode: existing
  group_id: classicas-correlacao
```

**Áudio — grupo existente:**

```yaml
media: audio
card:
  mode: existing
  group_id: audio-spoofing
```

**Vídeo — grupo novo:**

```yaml
media: video
card:
  mode: new
  group_id: video-lab-experimental
  title: "Lab experimental de vídeo"
  description: "Técnicas em avaliação do laboratório."
```

**Só rota, sem card:**

```yaml
card:
  mode: none
```

---


## 6. Bloco `parameters` (formulário)

Cada item vira um controle na página e uma chave em `parameters` do `run`.

| Campo | Obrig.? | Descrição |
|-------|---------|-----------|
| `name` | sim | Nome da chave no pipeline |
| `type` | sim | `int` \| `float` \| `boolean` \| `string` \| `enum` |
| `widget` | não | Como desenhar o controle (ver tabela) |
| `label` | não | Texto na UI |
| `default` | recomendado | Valor inicial |
| `min` / `max` / `step` | numéricos / slider | Limites |
| `options` | se enum | Lista de strings |
| `description` | não | Tooltip |

### Widgets (o que aparece na tela)

| `type` | Default se omitir `widget` | Outras opções |
|--------|----------------------------|---------------|
| `int` / `float` | `number` (caixa) | `slider` (**exige** `min` e `max`) |
| `enum` | `select` (dropdown) | `radio` |
| `boolean` | `checkbox` | — |
| `string` | `text` | — |

Valores válidos de `widget`: `number` · `slider` · `select` · `radio` · `checkbox` · `text`.

---

## 7. Artefatos e `role` — o coração da UI genérica

Cada item de `artifacts[]`:

| Campo | Obrig.? | Descrição |
|-------|---------|-----------|
| `key` | **sim** | Chave no dict de resultado (ex.: `heatmap_path`) — **quase livre** |
| `filename` | **sim** | Nome do arquivo em `out_dir` / job |
| `role` | **sim na prática** | Diz **como** a UI mostra o arquivo |
| `label` | não | Texto da aba / botão |
| `savable` | não | default true — pode salvar em derivados |

### 7.1 Ideia central: `key` ≠ `role`

- **`key`**: contrato com o JobService (“grave este path no resultado”).  
- **`role`**: contrato com a interface (“mostre como heatmap / HTML / download…”).

Você pode inventar `key: meu_residuo_path` desde que o filename bata e o mapping exista
(o scaffold registra keys novas automaticamente).  
Você **não** pode inventar `role: meu_widget_legal` — a UI não sabe desenhar.

### 7.2 Vocabulário completo de `role` (com renderização)

Código-fonte: `src/frontend/src/config/artifactRoles.ts`.  
Viewers: `TechniqueArtifactViewer` (simple/medium) e `GenericComparisonAnalysis`.

#### A — Imagem espacial (par sincronizado)

Usado em **simple/medium** (e plots em comparison).

| `role` | O que a UI faz |
|--------|----------------|
| `original` | Painel **esquerdo** |
| `input` | Alias de original (painel esquerdo) |
| `heatmap` | Aba **direita** |
| `overlay` | Aba direita |
| `mask` | Aba direita |
| `score_map` | Aba direita (mapa de score) |
| `confidence` | Aba direita (mapa de confiança) |
| `detection` | Aba direita (detecção/máscara) |
| `other` | Se for **imagem**, também vira aba direita |

Vários roles “direita” → várias abas; zoom/pan compartilhados; botões **Salvar**.

#### B — Relatório HTML

| `role` | O que a UI faz |
|--------|----------------|
| `interactive` | iframe / PlotlyHtmlFrame |
| `report` | Idem (alias) |

Vários HTML → abas de relatório.

#### C — Comparison (matriz / plot)

| `role` | O que a UI faz |
|--------|----------------|
| `plot_data` | Mostra a **imagem** da matriz/plot |
| `plot` | Alias de `plot_data` |
| `matrix` | Alias de `plot_data` |

Além disso, se o JSON de resultado tiver `metrics.<nome>.matrix` (com
`row_labels` / `col_labels`), a UI desenha uma **tabela numérica**.

#### D — Arquivos (derivados — sem download direto do job)

| `role` | O que a UI faz |
|--------|----------------|
| `json` | Painel **Salvar em derivados** |
| `txt` | Idem |
| `download` | Idem (qualquer binário/anexo) |

`other` que **não** é imagem/HTML também entra nesse painel.  
**Não** há botão “Baixar” a partir do job: o fluxo forense é salvar o derivado (cadeia de custódia) e baixar depois pela aba Derivados.

### 7.3 Exemplo medium (vários mapas + HTML + JSON)

```yaml
artifacts:
  - key: original_crop_path
    filename: original.png
    role: original
    label: Original
    savable: false
  - key: heatmap_path
    filename: heatmap.png
    role: heatmap
    label: Resíduo
  - key: confidence_image_path
    filename: confidence_map.png
    role: confidence
    label: Confiança
  - key: interactive_html_path
    filename: interactive.html
    role: interactive
    label: Relatório
  - key: scores_json_path
    filename: scores.json
    role: json
    label: Scores
```

Isso gera automaticamente: par Original↔abas Resíduo/Confiança + iframe Relatório +
botão Salvar Scores (derivado) — **sem página React dedicada**.

### 7.4 Exemplo comparison (matriz + JSON)

```yaml
artifacts:
  - key: similarity_matrix_image_path
    filename: similarity_matrix.png
    role: plot_data   # ou plot | matrix
    label: Matriz
  - key: similarity_json_path
    filename: similarity_matrices.json
    role: json
    label: JSON das matrizes
```

### 7.5 Sobre “chaves conhecidas” do JobService

O backend tem uma lista longa de `key → filename` históricos (`job_artifacts.py`).
O scaffold **não** exige que você use só essas chaves: se a combinação for nova,
ele registra em `scaffolded_artifact_mappings.py`.

Convenção sugerida: sufixo `_path` para paths; nomes de arquivo estáveis e curtos.

---

## 8. Bloco `comparison` (só `template: comparison`)

| Campo | Default | Descrição |
|-------|---------|-----------|
| `modes` | ambos | `with_reference` e/ou `all_pairs` |
| `reference_source` | `case_evidences` | De onde vêm as referências |
| `min_questioned` | 1 | Mínimo de questionadas |
| `min_references` | 1 | Mínimo de refs (modo com referência) |

### `reference_source` (importante)

| Valor | Comportamento |
|-------|----------------|
| `case_evidences` | Multi-select nas **evidências** do caso (mesmo tipo de mídia) |
| `case_references` | Refs **globais** da aba Referências (`global_groups`), por **rótulo**, filtradas pelo tipo (`imagem`, etc.) |

A badge `Referencias (N)` do caso soma refs de plugin **+** globais.

A UI envia:

```ts
{ mode, case_id, questioned_evidence_ids, reference_evidence_ids?, ...params }
```

O JobService resolve IDs → `questioned_paths` / `reference_paths` (+ labels) via
`x-forensic-role` no plugin gerado.

---

## 9. Bloco `ensemble` (só `template: ensemble`)

Há dois modos de LR:

| `reference_lr.mode` | Comportamento |
|---------------------|---------------|
| `result_only` (default) | Detectores + tabela; painel LR só se o pipeline devolver `reference_lr` / PNGs |
| `calibrated` (Wave 2) | UI no padrão **áudio spoofing**: picker de população (fit/test), tipicidade, aug, meta-classificador |

### Campos gerais

| Campo | Default | Descrição |
|-------|---------|-----------|
| `detectors` | **obrigatório** | Lista `{id, label}` → checkboxes |
| `result_headers` | 6 cols padrão | Cabeçalhos de `individual_results` |
| `selected_param` | `selected_analyses` | Nome do parâmetro no job |
| `score_display` | opcional | Badges: `positive_key` / `negative_key` / `label_key` |

### `reference_lr` — Wave 2 (`mode: calibrated`)

| Campo | Obrig.? | Descrição |
|-------|---------|-----------|
| `enabled` | não | default true |
| `mode` | sim* | `calibrated` |
| `domain` | **sim** | Pasta `reference_data/<domain>/` |
| `scores_path` | **sim** | CSV de scores **já publicados** (relativo ao domain) |
| `feature_map` | **sim** | `detector_id` → coluna de score |
| `macros` **ou** `catalog_endpoint` | **sim** | Catálogo inline **ou** GET API `{ categories }` |
| `embeddings_path` | não | Path de embeddings (tipicidade) |
| `embedding_map` | não | `detector_id` → id/coluna de embedding |
| `allow_augmented` | não | Checkbox “população aumentada” |
| `allow_typicality` | não | Checkbox tipicidade k-NN |
| `allow_meta_classifier` | não | Select meta-classificador (default on em calibrated) |
| `enable_split_roles` | não | fit vs test (default true em calibrated) |
| `default_meta_classifier` | não | `logistic` ou `xgboost` (default `logistic`; alias `logistic_regression`) |
| `default_reference_items` | não | Pré-seleção `{base_group, subgroup}` |
| `population_unit_label` / `lr_positive_label` | não | Textos do painel |
| `subgroup_unit_label` / `hypothesis_hint` | não | Textos do picker |

\* Sem `mode`, o scaffold trata como `result_only` (compatível com manifests antigos).

**Importante:** o scaffold **não** extrai features das bases. Publicar scores/embeddings (com splits train/val/test e rótulos) é pipeline offline; os ativos publicados ficam em `reference_data/<domain>/`.

```yaml
ensemble:
  detectors:
    - id: detector_a
      label: "Detector A"
  reference_lr:
    enabled: true
    mode: calibrated
    domain: demo_ensemble_lr
    scores_path: features/scores/scores.csv
    feature_map:
      detector_a: score_a
    allow_augmented: true
    allow_typicality: true
    macros:
      demo_toy:
        label: Demo
        description: Bases fictícias
        items:
          - base_group: ToyBase
            subgroup: gen_alpha
    default_reference_items:
      - base_group: ToyBase
        subgroup: gen_alpha
```

Exemplo completo: `scripts/technique/examples/ensemble.yaml`.

### Payload do job (calibrated)

```ts
{
  selected_analyses: string[],
  reference_lr_enabled: true,
  reference_population: { fit_items?, test_items?, items? },
  reference_lr_domain?: string,
  meta_classifier?: string,
  use_augmented_reference?: boolean,
  use_latent_typicality?: boolean,
  ...params
}
```

### Contrato do resultado (pipeline)

| Chave | Obrig.? | Formato |
|-------|---------|---------|
| `individual_results` | recomendado | `list[list]` — linhas da tabela |
| `reference_lr` | se LR | objeto de `ReferenceLrPanel` (métricas Cllr/EER etc.; inclua `feature_weights` / `feature_values` para o menu colapsado de coeficientes ou importâncias XGBoost) |
| PNGs LR | se LR | `lr_reference_{tippett,distribution,identity}.png` |
| scores agregados | se `score_display` | chaves do manifesto |

Calibração esperada no pipeline (espelho áudio/imagem; **implementada por você** no `pipeline.py`, não pelo scaffold):  
meta via `core.synthetic_lr_reference.train_meta_classifier` (logistic = **z-score/`StandardScaler`** + LogReg; xgboost sem scaler) → logits (val) → bigaussianização → Tippett/Cllr/EER (test) + LR do questionado.  
**Proibido** treinar `LogisticRegression` direto nos logits brutos dos detectores — escalas diferentes enviesam o ensemble.

---

## 10. Bloco `paper` (PDF opcional)

```yaml
citation: |
  AUTOR. Título. Venue, ano.

paper:
  title: "Título"
  venue: "Venue 2020"
  sources: ["https://doi.org/..."]
  local_file: "meu_id/meu_id_paper.pdf"
```

Gera entrada de download; coloque o PDF em `docs/references/papers/imdl/<local_file>` (>1 KB).

---

## 11. O que o script gera

| Artefato | Função |
|----------|--------|
| `core/plugins/<id>_plugin.py` | Adapter (comparison: roles forenses; ensemble: `selected_analyses`) |
| `forensics/<id>/pipeline.py` | **Sua** lógica |
| `tests/unit/test_<id>_plugin.py` | Smoke |
| `config/techniques/<id>.yaml` | Cópia do manifesto |
| patches `scaffolded*` | Meta, registry, rota, grupo, papers, mappings |

---

## 12. Contrato do `pipeline.run`

```python
def run(evidence_path, parameters, out_dir, *, on_progress=None) -> dict:
    ...
```

1. Grave arquivos em `out_dir` com os `filename` do manifesto.  
2. Devolva `success` + as chaves `key` apontando para esses paths.  
3. Em comparison, use `questioned_paths` / `reference_paths` (não só o âncora).  
4. Em ensemble, leia `selected_analyses` e devolva `individual_results`.  
   Se `reference_lr.mode=calibrated`, leia também `reference_population` / tipicidade / aug  
   e carregue features de `reference_data/<domain>/` (já publicadas).  
5. Opcional: `metrics.<nome>.matrix` para tabela na UI (comparison/medium).  
6. `on_progress(0..100, "msg")` para a barra de progresso.

---

## 13. Limites atuais (honestidade)

Ainda **fora** do genérico / roadmap:

- Templates `complex`, `hub`
- **Orquestração LR genérica por domínio** (ainda nos adapters áudio/sintético) — o scaffold só declara contrato + UI; o **treino do meta** já é compartilhado (`train_meta_classifier` com z-score no logistic)
- Publicação automática de features das bases (continua offline)
- Escalas de cor TruFor / UI IMDL “gorda”
- Upload de refs globais **dentro** da página comparison (use a aba Referências)
- Matriz JPEG posicional clássica

---

## 14. Riscos

| Risco | Mitigação |
|-------|-----------|
| Role sem UI | Scaffold rejeita role inválido |
| Editar `scaffolded*` à mão | Re-rode o scaffold |
| Sobrescrever `pipeline.py` | Só com `--force` |
| Refs globais vazias | Cadastre na aba Referências do caso |
| Ensemble sem `individual_results` | Tabela vazia / MessageBox na UI |
| `calibrated` sem CSV publicado | Job falha no pipeline — validar `reference_data/<domain>/` antes |
| Catálogo vazio | Exija `macros` ou `catalog_endpoint` no manifesto |
| Meta logistic sem z-score | Detector de maior escala de logit domina — use só `train_meta_classifier` |

Reversibilidade das entradas scaffold: **Fácil**.

---

## 15. Robustez

Plugins cujo import falha são **ignorados** com warning — um adapter quebrado não
derruba `GET /analysis/techniques`.

---

## Apêndice A — Referência completa do manifesto YAML

Checklist de **todos** os campos que o automatizador lê hoje.  
Obrigatórios marcados com **\***. Valores omitidos usam o default indicado.

### A.1 Topo

| Campo | Obr. | Tipo / valores | Default / notas |
|-------|------|----------------|-----------------|
| `id` | **\*** | `[a-z][a-z0-9_]{1,63}` | Plugin, pasta `forensics/`, rota |
| `template` | **\*** | `simple` \| `medium` \| `comparison` \| `ensemble` | — |
| `media` | **\*** | `imagem` \| `audio` \| `video` \| `pdf` | — |
| `title` | **\*** | string | Título UI / meta |
| `subtitle` | | string | `cardSubtitle` |
| `description` | | string (`>` ok) | Normalizado a uma linha no plugin |
| `citation` | | string (`\|` ok) | Bibliografia |
| `license` | | string | Meta |
| `repo_url` | | URL | Alias: `repo` |
| `gpu` | | bool | `false` |
| `disabled` | | bool | `false` — card off |
| `admin_only` | | bool | `false` |
| `card` | rec. | objeto | Ver A.2 / §5 |
| `parameters` | | lista | Ver A.3 / §6 |
| `artifacts` | rec. | lista | Ver A.4 / §7 |
| `comparison` | se comparison | objeto | Ver A.5 / §8 |
| `ensemble` | se ensemble | objeto | Ver A.6 / §9 |
| `paper` | | objeto | Ver A.7 / §10 |

### A.2 `card`

| Campo | Obr. | Valores | Notas |
|-------|------|---------|-------|
| `mode` | | `existing` \| `new` \| `none` | default `existing` |
| `group_id` | se `existing` | id da §5.2–5.5 **da mesma** `media` | Validado pelo scaffold |
| `title` | se `new` | string | Título do **grupo** novo (qualquer mídia) |
| `description` | se `new` | string | Descrição do grupo novo |

### A.3 `parameters[]` (cada item)

| Campo | Obr. | Valores | Notas |
|-------|------|---------|-------|
| `name` | **\*** | snake_case | Chave em `parameters` do `run` |
| `type` | **\*** | `int` \| `float` \| `boolean` \| `string` \| `enum` | — |
| `widget` | | `number` \| `slider` \| `select` \| `radio` \| `checkbox` \| `text` | Defaults por type (§6) |
| `label` | | string | UI |
| `default` | rec. | conforme type | — |
| `min` / `max` | slider / limites | number | **slider exige min e max** |
| `step` | | number | — |
| `options` | se enum | lista string | **obrigatório** se `type: enum` |
| `description` | | string | Tooltip |

### A.4 `artifacts[]` (cada item)

| Campo | Obr. | Valores | Notas |
|-------|------|---------|-------|
| `key` | **\*** | string | Chave no result (`*_path` sugerido) |
| `filename` | **\*** | string | Arquivo em `out_dir` |
| `role` | rec. | ver §7.2 | Desconhecido → erro no scaffold |
| `label` | | string | Aba / botão Salvar |
| `savable` | | bool | default `true` |

Roles permitidos:  
`original` `input` `heatmap` `overlay` `mask` `score_map` `confidence` `detection`  
`interactive` `report` `plot_data` `plot` `matrix` `json` `txt` `download` `other`.

`json` / `txt` / `download` → **Salvar em derivados** (sem Baixar do job).

### A.5 `comparison` (só `template: comparison`)

| Campo | Default | Valores |
|-------|---------|---------|
| `modes` | ambos | lista: `with_reference`, `all_pairs` |
| `reference_source` | `case_evidences` | `case_evidences` \| `case_references` |
| `min_questioned` | `1` | int |
| `min_references` | `1` | int |

### A.6 `ensemble` (só `template: ensemble`)

| Campo | Obr. | Notas |
|-------|------|-------|
| `detectors` | **\*** | lista `{id, label}` |
| `result_headers` | | lista string (cols da tabela) |
| `selected_param` | | default `selected_analyses` |
| `score_display.positive_key` | | chave no result → badge |
| `score_display.negative_key` | | idem |
| `score_display.label_key` | | idem |
| `reference_lr` | | objeto abaixo |

#### `ensemble.reference_lr`

| Campo | Obr. | Default / notas |
|-------|------|-----------------|
| `enabled` | | `true` |
| `mode` | | `result_only` \| `calibrated` |
| `domain` | se calibrated | `reference_data/<domain>/` |
| `scores_path` | se calibrated | relativo ao domain |
| `feature_map` | se calibrated | `detector_id` → coluna CSV |
| `macros` **ou** `catalog_endpoint` | se calibrated | catálogo UI |
| `embeddings_path` | | tipicidade |
| `embedding_map` | | `detector_id` → id embedding |
| `allow_augmented` | | `false` |
| `allow_typicality` | | `false` |
| `allow_meta_classifier` | | `true` se calibrated |
| `enable_split_roles` | | `true` se calibrated |
| `default_meta_classifier` | | `logistic` (ou `xgboost`) |
| `population_unit_label` | | `amostras` |
| `lr_positive_label` | | `real` |
| `subgroup_unit_label` | | — |
| `hypothesis_hint` | | texto do picker |
| `default_reference_items` | | `[{base_group, subgroup}, …]` |

Formato `macros` (dict estilo catálogo):

```yaml
macros:
  meu_macro:
    label: "Rótulo"
    year_range: "2020–2024"
    description: "…"
    items:
      - base_group: BaseX
        subgroup: gen_y
```

### A.7 `paper`

| Campo | Notas |
|-------|-------|
| `title` | Título do paper |
| `venue` | Venue / ano |
| `sources` | lista de URLs |
| `local_file` | path sob `docs/references/papers/imdl/` |
| `repo` | opcional |

### A.8 Esqueleto máximo (comentários)

```yaml
id: minha_tecnica                 # *
template: ensemble                # * simple|medium|comparison|ensemble
media: imagem                     # *
title: "Título"                   # *
subtitle: "…"
description: >
  …
citation: |
  …
license: "…"
repo_url: "https://…"
gpu: false
disabled: false
admin_only: false
card:
  mode: existing                  # existing|new|none
  group_id: classicas-correlacao  # ver §5.2–5.5 (mesma media)
  # mode: new → title + description (+ group_id opcional)
parameters:
  - name: k
    type: int
    widget: slider
    label: "K"
    default: 5
    min: 1
    max: 31
    step: 2
    description: "…"
artifacts:
  - key: heatmap_path
    filename: heatmap.png
    role: heatmap
    label: "Mapa"
    savable: true
# comparison: { … }               # se template comparison
# ensemble: { detectors: […], reference_lr: { … } }
# paper: { title, venue, sources, local_file }
```
