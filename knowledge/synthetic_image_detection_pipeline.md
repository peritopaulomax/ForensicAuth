# Pipeline de Detecção de Imagens Sintéticas — ForensicAuth

**Técnica canônica:** `synthetic_image_detection`  
**Alias legado:** `sepael`  
**Categoria:** Imagem — GPU/ML  
**Última atualização:** 2026-06-29 (alinhado com o código real)

---

## 1. Visão Geral

A detecção de imagens sintéticas do ForensicAuth é um **ensemble ativo** composto por quatro detectores:

1. `haywoodsloan/ai-image-detector-deploy` (HuggingFace)
2. `cmckinle/sdxl-flux-detector_v1.1` (HuggingFace)
3. **B-Free** (`vendor/bfree`, GRIP-UNINA)
4. **Corvi2023 / CLIP-D** (`vendor/grip_clipbased_synthetic`, GRIP-UNINA)

O ensemble é orquestrado por `src/backend/core/legacy/synthetic_image_detection/pipeline.py` e exposto ao sistema via `SyntheticImageDetectionAdapter` (`src/backend/core/plugins/synthetic_image_detection_adapter.py`).

> **Escopo real do código:** modelos previamente testados como CLIDE, SAFE, Effort, XGBoost, NPR e técnicas standby (`fakevlm`, `clipbased_synthetic`, `distildire`) **não fazem parte do ensemble ativo**. Eles permanecem em `models/`, `vendor/` ou `STANDBY_PLUGIN_NAMES` por compatibilidade/registro histórico, mas não são executados pelo pipeline `synthetic_image_detection`.

> **Observação importante:** a técnica **não possui um score final consolidado** no output padrão. O resultado é uma tabela de scores individuais, e cada detector emite sua própria classificação com thresholds fixos (`>0.66` = AI, `<0.34` = REAL, entre = Incerto).

---

## 2. Arquitetura do Pipeline

```text
Frontend / API
    │
    ▼
POST /api/v1/analysis  { evidence_id, technique: "synthetic_image_detection", parameters }
    │
    ▼
JobService.submit_job
    ├── resolve_technique_id("sepael") → "synthetic_image_detection"
    ├── valida tipo de mídia ("imagem")
    ├── validate_parameters()
    └── cria AnalysisJob (pending)
    │
    ▼
run_job_in_background → Celery fila "gpu" (ou thread local com ml_gpu_job_slot)
    │
    ▼
Celery worker GPU
    │
    ▼
JobService.run_job
    │
    ▼
SyntheticImageDetectionAdapter.analyze(evidence_path, parameters)
    │
    ├── _as_rgb(image) → PIL RGB
    ├── runtime_status() → dependências/pesos OK?
    └── run_synthetic_image_detection_analysis(image, ...)
            │
            ├── _ensure_models_loaded()          (lazy load HF, se selecionado)
            ├── predict_ensemble(image)
            │       ├── ai-image-detector-deploy → fake/real scores
            │       ├── sdxl-flux-detector_v1.1  → fake/real scores
            │       ├── B-Free (opcional)        → fake/real scores
            │       └── Corvi2023 (opcional)     → fake/real scores
            ├── FFT da imagem original
            └── Visualizações (NLM, mediana, FFT, ELA) se generate_visuals=True
    │
    ▼
Artefatos em job_artifact_dir
    ├── model_scores.txt
    ├── input_image_*.png
    ├── input_fft_*.png
    ├── nlm_residue_*.png / median_residue_*.png
    └── result.json
    │
    ▼
JobService.run_job persiste hashes SHA-256 + runtime_manifest
```

---

## 3. Arquivos Principais

| Caminho | Papel |
|---|---|
| `src/backend/core/plugins/synthetic_image_detection_adapter.py` | Adapter ForensicPlugin, validação de parâmetros, persistência de artefatos |
| `src/backend/core/legacy/synthetic_image_detection/pipeline.py` | Ensemble e inferência |
| `src/backend/core/legacy/synthetic_image_detection/runtime.py` | Resolução de paths, status de runtime, cache HuggingFace |
| `src/backend/core/legacy/bfree/bfree_pipeline.py` | Inferência B-Free |
| `src/backend/core/legacy/bfree/bfree_runtime.py` | Paths e runtime B-Free |
| `src/backend/core/legacy/truebees_clip_d/clipd_pipeline.py` | Inferência CLIP-D / Corvi2023 |
| `src/backend/core/legacy/truebees_clip_d/clipd_runtime.py` | Paths e runtime CLIP-D |
| `src/backend/core/technique_ids.py` | IDs canônicos e aliases |
| `src/backend/core/plugin_registry.py` | Descoberta e registro de plugins |
| `src/backend/core/gpu_inference.py` | Device, OOM fallback, purge de caches |
| `src/backend/core/gpu_residency.py` | Política de residência VRAM |
| `src/backend/services/job_service.py` | Submissão, execução e persistência de jobs |
| `src/backend/services/gpu_queue_service.py` | Fila de jobs GPU |
| `src/backend/api/v1/endpoints/analysis.py` | Endpoint `/analysis` |
| `src/backend/app/worker_bootstrap.py` | Warmup de modelos ML no worker-gpu |
| `src/backend/app/config.py` | Configurações de GPU e residência |
| `tests/unit/test_synthetic_image_detection.py` | Testes unitários do ensemble |
| `tests/integration/test_synthetic_new_detectors_smoke.py` | Smoke tests de FSD/UFD/CLIP-D |
| `scripts/download_bfree_assets.py` | Download B-Free |
| `scripts/download_truebees_clipd_assets.py` | Download CLIP-D/Corvi2023 |

---

## 4. Modelos e Pesos

### 4.1. Ativamente utilizados no ensemble

| Detector | Origem | Formato | Localização | Tamanho |
|---|---|---|---|---|
| `ai-image-detector-deploy` | HuggingFace | `model.safetensors` | `models/sepael/huggingface/models--haywoodsloan--ai-image-detector-deploy/...` | ~745 MB |
| `sdxl-flux-detector_v1.1` | HuggingFace | `model.safetensors` | `models/sepael/huggingface/models--cmckinle--sdxl-flux-detector_v1.1/...` | ~332 MB |
| B-Free `BFREE_dino2reg4` | `vendor/bfree` | `.pth` + `config.yaml` | `models/bfree/weights/BFREE_dino2reg4/` | ~331 MB |
| Corvi2023 + CLIP-D head | `vendor/grip_clipbased_synthetic` | `.pth` + `config.yaml` | `models/grip_clipd/weights/Corvi2023/` + `clipdet_latent10k_plus/` | ~270 MB |

### 4.2. Modelos legados/testados, mas não utilizados pelo ensemble ativo

| Modelo | Origem | Formato | Localização | Observação |
|---|---|---|---|---|
| `model1_xgboost_1p_20250809_213811.json` | Projeto | XGBoost | `models/sepael/` | Carregado em memória, **não integrado** ao output atual |
| `model2_xgboost_1p_20250809_213811.json` | Projeto | XGBoost | `models/sepael/` | Declarado em runtime, **não usado** |
| `model_epoch_last_3090.pth` | Projeto | PyTorch ResNet50 (NPR) | `models/sepael/` | Carregado via `torch.load` sem `weights_only=True`, **não usado** no fluxo principal |
| CLIDE | `vendor/clide` | PyTorch | `models/clide/` | Técnica standby, não integrada ao ensemble |
| SAFE | `vendor/SAFE` | PyTorch | `models/safe/` | Técnica standby, não integrada ao ensemble |
| Effort | `vendor/Effort-main` | PyTorch | `models/effort/` | Técnica standby, não integrada ao ensemble |
| NPR | `models/sepael/model_epoch_last_3090.pth` | PyTorch | `models/sepael/` | Legado/testado, não integrado ao ensemble |

> Esses modelos podem ser removidos do diretório `models/sepael/` se não forem mais necessários para reproducibilidade histórica, **desde que** a equivalência forense seja validada caso algum deles volte a ser usado (Regra Máxima 8 do `AGENTS.md`).

### 4.3. Técnicas relacionadas (não integradas)

| Técnica | Status | Observação |
|---|---|---|
| `fakevlm` | Standby | LLaVA 7B multimodal |
| `clipbased_synthetic` | Standby | CLIP-D como técnica isolada |
| `distildire` | Standby | DIRE leve |
| `safire` | Ativa separada | Localização de falsificação |
| `imdlbenco` | Ativa separada | Hub IMDL (TruFor etc.) |
| `fsd`, `ufd` | Modelos presentes | Não integrados ao ensemble |

---

## 5. Parâmetros da Técnica

| Parâmetro | Tipo | Default | Descrição |
|---|---|---|---|
| `mode` | `str` | `"full"` | `"full"` ou `"fast"`. Fast desativa visualizações |
| `generate_visuals` | `bool` | `true` | Gera PNGs de resíduos e FFT |
| `selected_analyses` | `list[str]` | todas | Subconjunto de `["ai_image_detector_deploy", "sdxl_flux_detector_v1_1", "bfree", "corvi2023"]` |
| `reference_lr_enabled` | `bool` | `false` | Ativa calibração de LogisticRegression com população de referência |
| `reference_population` | `str` | `null` | Identificador da população de referência |

---

## 6. Ensemble e Decisão

### 6.1. Como funciona

1. Cada detector selecionado é executado independentemente.
2. Cada detector retorna `fake_prob`, `real_prob`, `decision`, `device`.
3. O output JSON contém:
   - `individual_results`: lista tabulada (para exibição).
   - `detector_scores`: mapa com scores por detector.
4. **Não há score ensemble consolidado** no output padrão.
5. Opcionalmente, `reference_lr_enabled=true` aplica uma LogisticRegression treinada on-the-fly sobre os scores dos detectores **selecionados** (pode ser subconjunto dos 4), usando uma população de referência.

### 6.2. Thresholds

```python
if score_ai > 0.66:
    decision = "AI"
elif score_ai < 0.34:
    decision = "REAL"
else:
    decision = "Incerto"
```

> Os thresholds são **hardcoded** e não são configuráveis por parâmetro.

---

## 7. Serving e Integração

### 7.1. Registro

- Nome canônico: `synthetic_image_detection`
- Alias: `sepael`
- Tipos suportados: `["imagem"]`
- Categoria: ML/GPU
- Registro automático via `PluginRegistry.discover_and_register("src/backend/core/plugins")`

### 7.2. Warmup e Lazy Load

- **Não há warmup específico** para `synthetic_image_detection` em `worker_bootstrap.py` (o warmup atual cobre Effort/SAFE/CAMO/IAPL).
- Carregamento é **lazy** na primeira requisição.
- Configuração `SYNTHETIC_KEEP_RESIDENT` (default `true`) mantém modelos em VRAM entre jobs.

### 7.3. GPU Lock e Residência

- Jobs GPU são serializados por `ml_gpu_job_slot(technique)` (lock in-process).
- `gpu_residency.py` gerencia:
  - Residência por técnica.
  - Evicção de caches estrangeiros quando VRAM está sob pressão.
  - Fallback GPU → CPU em OOM (`gpu_inference.py`).

### 7.4. Filas e Escalabilidade

- Fila Celery dedicada: `gpu`.
- `gpu_queue_service.py` expõe posição na fila e contagem de pendentes.
- Jobs pendentes por mais de 24h são automaticamente marcados como `failed`.

### 7.5. Gargalos de Performance

| Gargalo | Impacto |
|---|---|
| Lazy load na primeira requisição | Latência inicial alta |
| Dois modelos HF ~1.1 GB | Uso alto de VRAM |
| B-Free + Corvi2023 adicionais | Podem estourar VRAM em GPUs modestas |
| Lock por técnica GPU | Apenas um job por worker por vez |
| Corvi2023 em tiles | Imagens >1024px geram múltiplas inferências |
| Resíduos NLM/mediana | Limitado a `SYNTHETIC_RESIDUE_MAX_SIDE=2048` |

---

## 8. Calibração LR (Opcional)

Quando `reference_lr_enabled=true`:

1. Seleciona população de referência (bases + geradores).
2. Treina LogisticRegression multivariada sobre os **detectores selecionados** (pode ser 1 a 4 detectores).
3. Aplica calibração bi-Gaussian baseada no EER.
4. Calcula LR da evidência questionada.
5. Gera artefatos:
   - `lr_reference_report.json` — métricas, coeficientes, população, LR
   - `lr_reference_summary.txt` — relatório textual consolidado
   - `lr_reference_tippett.png` — Tippett plot
   - `lr_reference_distribution.png` — distribuição das LRs com linha vermelha tracejada na LR do caso
   - `lr_reference_identity.png` — função identidade por KDE

Todos os artefatos LR podem ser salvos como derivados pela UI.

---

## 9. Riscos e Dívidas Técnicas

### 8.1. Segurança

| Risco | Evidência | Severidade |
|---|---|---|
| `torch.load(weights_only=False)` no NPR | `pipeline.py:298` | Crítica |
| Ausência de checksums/assinaturas para pesos | nenhum `manifest.json` em `models/` | Alta |
| Desserialização insegura potencial em vendors B-Free/CLIP-D | `load_weights` interno dos vendors | Média |

### 8.2. Ensemble

| Dívida | Evidência | Severidade |
|---|---|---|
| Sem score final consolidado | output só tem `individual_results` e `detector_scores` | Média |
| Thresholds fixos | `pipeline.py` constantes `0.66/0.34` | Média |
| Matching frágil de labels HF | `ai_keywords`/`real_keywords` em listas | Média |
| Modelos legados (XGBoost/NPR/CLIDE/SAFE/Effort) ocupam disco | `models/sepael/`, `vendor/`, `models/clide/`, etc. | Baixa |

### 8.3. Operacional

| Dívida | Evidência | Severidade |
|---|---|---|
| Sem warmup específico | `worker_bootstrap.py` | Média |
| Lock global GPU por técnica | `ml_gpu_job_slot` | Média |
| Residência padrão `true` | `config.py` | Baixa |
| Sem benchmarks de throughput/latência | `results/benchmarks/` | Média |

---

## 10. Recomendações Prioritárias

1. **Segurança:** migrar `torch.load(...)` para `weights_only=True` onde possível; para pesos legados que exigem pickle, validar checksums SHA-256 antes do carregamento.
2. **Checksums:** criar `models/sepael/manifest.json` com SHA-256 dos pesos ativos e verificar no `runtime_status()`.
3. **Score final:** expor um `ensemble_score` consolidado (média ponderada, votação ou LR calibrada) no JSON de resultado.
4. **Thresholds:** tornar thresholds configuráveis por parâmetro ou por população de referência.
5. **Warmup:** adicionar warmup específico de `synthetic_image_detection` no worker-gpu.
6. **Escalabilidade:** avaliar paralelismo parcial (B-Free/Corvi2023 podem não precisar do mesmo lock que os grandes modelos HF).
7. **Limpeza:** considerar remoção dos modelos legados não utilizados (XGBoost/NPR/CLIDE/SAFE/Effort) do path de produção, mantendo backups versionados fora do runtime.
8. **Documentação:** manter `docs/specs/modules/06-module-image.md` alinhado com o código real.
9. **Testes:** adicionar testes de integração end-to-end do ensemble completo e benchmarks de latência/VRAM.
10. **Refatoração:** consolidar `truebees_clip_d/clipd_pipeline.py` com `clipbased_synthetic_adapter.py` para evitar duplicação de vendor/pesos.

---

## 11. Referências

- Especificação alinhada: `docs/specs/modules/06-module-image.md`
- Relatórios intermediários: `.dev-logs/multiagent-analysis/synthetic-image-detection-*.md`
- Knowledge base atualizada: `knowledge/ml_assets_catalog.md`, `knowledge/feature_catalog.md`
