# test-module-moe-ffd.md — Specs de Teste MoE-FFD

## Objetivo

Garantir registro, runtime, inferência (mocked e opcionalmente real), API e navegação frontend/e2e do hub facial + técnica MoE-FFD.

## Matriz

| Caso | Tipo | Critério de aceite |
|---|---|---|
| `test_moe_ffd_plugin_registered` | unit | `moe_ffd` no PluginRegistry, tipo `imagem` |
| `test_moe_ffd_runtime_missing_weights` | unit | Sem checkpoint → `(False, reason)` |
| `test_moe_ffd_runtime_ok_when_paths_exist` | unit | Vendor+ckpt+RetinaFace+health OK → available |
| `test_checkpoint_health_rejects_zero_gates` | unit | training_tar com w_gate=0 → rejeitado |
| `test_checkpoint_health_accepts_trained_gates` | unit | raw state_dict com gates → ok |
| `test_moe_ffd_validate_threshold` | unit | threshold inválido rejeitado |
| `test_moe_ffd_analyze_mocked` | unit | Adapter retorna label/fake_prob/artefatos + face crop |
| `test_moe_ffd_pipeline_softmax_contract` | unit | Classe 1 = fake; threshold aplica |
| `test_face_crop_square_with_margin` | unit | Crop RetinaFace mock → quadrado com margem |
| `test_moe_ffd_api_job_mocked` | integration | POST analysis → job completed com adapter |
| `test_dl_facial_spoofing_group_config` | frontend unit | Grupo renomeado; abas PAD + moe_ffd |
| `card click opens facial spoofing hub` | e2e | Card "Deep Learning: Manipulação e Spoofing Facial" → `dl-facial-spoofing` |
| `tabs show PAD and MoE-FFD` | e2e | Ambas as abas visíveis |

## Comandos

```bash
conda activate va-suite
PYTHONPATH=src/backend pytest tests/unit/test_moe_ffd.py tests/integration/test_moe_ffd_api.py -v
cd src/frontend && npx vitest run src/config/imageAnalysisGroups.test.ts
cd src/frontend && npx playwright test e2e/moe-ffd-navigation.spec.ts e2e/pad-navigation.spec.ts
```
