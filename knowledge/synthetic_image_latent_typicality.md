# Latent Typicality (k-NN) para Detecção de Imagens Sintéticas

## Resumo

Replicou-se, para imagens sintéticas, o pipeline de calibração LR com tipicidade latente já existente para áudio. O vetor de features do meta-classificador agora pode incluir, além dos escores logit dos detectores, medidas de tipicidade extraídas das embeddings de penúltima camada (k-NN densidade) de cada detector selecionado.

## Arquivos alterados/criados

- `src/backend/core/legacy/synthetic_image_detection/embedding_utils.py` — extratores de embeddings para os 5 detectores (SAFE, ai-image-detector-deploy, sdxl-flux-detector v1.1, B-Free, Corvi2023).
- `src/backend/core/legacy/synthetic_image_detection/pipeline.py` — `predict_ensemble` e `run_synthetic_image_detection_analysis` aceitam `return_embedding=True`.
- `src/backend/core/synthetic_lr_reference.py` — integração completa da tipicidade latente (`use_latent_typicality`, sistemas A/B/C/D, cache, report).
- `src/backend/core/plugins/synthetic_image_detection_adapter.py` — valida e repassa `use_latent_typicality`, `typicality_system`, `typicality_k`, `typicality_distance`; passa `return_embedding=True` quando necessário.
- `src/backend/services/derivative_service.py` — metadados da cadeia de derivação incluem flags de tipicidade.
- `src/frontend/src/pages/SyntheticImageDetectionAnalysis.tsx` — checkbox "Usar tipicidade latente (k-NN sobre embeddings)".
- `scripts/extract_synthetic_image_representations_optimized.py` — extração detector-a-detector otimizada para GPU/memória.
- `config/image_synthetic_typicality.yaml` — configuração padrão.
- `tests/unit/test_synthetic_lr_reference.py` — testes de tipicidade latente (sistema D, subconjunto de detectores, cache).

## Matriz de representações

- Origem: `outputs/lr_calibration/score_matrices/lr_scores_balanced_full_augmented.csv` (~229k linhas, originais + 4 augmentações).
- Destino: `outputs/lr_calibration/synthetic_image/representations/representations.csv` + `embeddings/*.npy`.
- Script em execução: `scripts/extract_synthetic_image_representations_optimized.py`.
- PID/log: `outputs/lr_calibration/synthetic_image/extraction.pid` / `extraction.log`.

## Estado da extração (snapshot)

- Linhas únicas na matriz: ~203.834.
- Arquivos não encontrados (erros persistentes): ~8.093 (~4% das linhas), principalmente OpenSDI_test (~931), Synthbuster (~160) e AIGCDetectBenchmark (~18).
- Embeddings extraídos até o momento: apenas `ai_image_detector_deploy` parcial (~21k).
- Detectores pendentes: `ai_image_detector_deploy` (restante), `sdxl_flux_detector_v1_1`, `bfree`, `corvi2023`, `safe`.

## Estimativa de tempo

Com o script otimizado (um detector por vez, modelos mantidos em GPU dentro de cada detector):

- `ai_image_detector_deploy`: ~0,05 s/amostra.
- `sdxl_flux_detector_v1_1`: ~0,05 s/amostra.
- `bfree`: ~0,11 s/amostra.
- `corvi2023`: ~0,12 s/amostra.
- `safe`: ~0,01 s/amostra.

Para ~196k amostras válidas: **~15–18 horas** de processamento contínuo a partir do snapshot acima. O processo está rodando em background.

## Observações

- As linhas com `FileNotFoundError` serão filtradas pelo backend (`_filter_rows_with_embeddings`). Subgrupos afetados serão amostrados com reposição se necessário.
- A interface usa os defaults de `config/image_synthetic_typicality.yaml` (sistema D, k=5, distância cosseno).
- Testes unitários passam: `tests/unit/test_synthetic_lr_reference.py`, `tests/unit/test_synthetic_image_detection.py`, `tests/unit/test_synthetic_image_embeddings.py`, `tests/unit/test_audio_spoofing_lr_typicality.py`.
