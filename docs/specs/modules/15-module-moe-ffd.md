# 15-module-moe-ffd.md — MoE-FFD (Face Forgery Detection)

## 1. Propósito

Integrar ao ForensicAuth a técnica **MoE-FFD** ([Mixture of Experts for Generalized and Parameter-Efficient Face Forgery Detection](https://github.com/LoveSiameseCat/MoE-FFD), IEEE TDSC 2025) para classificação local de frames/imagens faciais como **bonafide (real)** vs **forgery (fake)** — deepfakes / face swap / neural textures etc.

O hub de UI que contém esta técnica passa a se chamar **"Deep Learning: Manipulação e Spoofing Facial"** (antes "Biometria Facial"), com duas abas:

1. **Ataques de Apresentação (PAD)** — técnica já existente `presentation_attack_detection`
2. **MoE-FFD** — nova técnica `moe_ffd`

Pesos oficiais: [Hugging Face luobo91/MoE-FFD](https://huggingface.co/luobo91/MoE-FFD/tree/main) (`MoE-FFD.tar`).

## 2. Escopo

### Dentro do escopo (v0)

- Técnica `moe_ffd` registrada no `PluginRegistry` (tipo `imagem`).
- Vendor do código oficial em `vendor/MoE-FFD` (algoritmo intocável — Regra Máxima 8).
- Adapter + runtime local (sem chamadas externas em produção).
- Inferência sobre imagem RGB: **crop facial RetinaFace** (WiderFace Caffe, mesmos pesos do PAD) → preprocess 224×224 + normalização mean/std=0.5 (contrato albumentations do repo).
- Retorno: `label` (`real`|`fake`), `fake_prob`, `real_prob`, `score` (=fake_prob), `threshold`, `inference_device`, metadados de crop.
- Artefatos: `moe_ffd_result.json`, `moe_ffd_summary.txt`, `moe_ffd_face_crop.png` / preview.
- Card de grupo renomeado + id `dl-facial-spoofing` (redirect legado de `biometria-facial`).
- Jobs GPU com fallback CPU; perfil `gpu_ml`; custódia via fluxo padrão.

### Fora do escopo (v0)

- Agregação multi-frame / vídeo (o paper avalia por vídeo; v0 é single-image).
- Alinhamento por landmarks 5-point / warp afim (crop quadrado com margem; RetinaFace bbox).
- Fine-tuning; laudo PDF dedicado; calibração LR desta técnica.

## 3. Atores

- **Perito / Admin**: seleciona evidência, abre o hub facial, aba MoE-FFD, executa análise.
- **Sistema**: valida runtime, enfileira job GPU, executa adapter, grava artefatos + custódia.

## 4. Requisitos Funcionais

| ID | Requisito |
|---|---|
| MOE-RF-01 | Plugin registrado como `moe_ffd`, tipo suportado `imagem`. |
| MOE-RF-02 | Runtime exige vendor, checkpoint integro (gates MoE treinados) e RetinaFace PAD. O `MoE-FFD.tar` mid-training (gates≈0) e rejeitado. |
| MOE-RF-03 | Inferência usa arquitetura `vit_base_patch16_224_in21k(num_classes=2)` do vendor + `state_dict` do checkpoint (chave `model_state_dict`). |
| MOE-RF-04 | Preprocess: RetinaFace crop quadrado (margem default 1.3) → albumentations Resize 224 + Normalize mean/std=0.5. |
| MOE-RF-05 | Softmax na saída; `fake_prob = p[:,1]`; `label = fake` se `fake_prob >= threshold` senão `real`. |
| MOE-RF-06 | Threshold padrão configurável (`MOE_FFD_DEFAULT_THRESHOLD=0.5`). |
| MOE-RF-07 | GPU preferencial com fallback CPU; device reportado no resultado. |
| MOE-RF-08 | Frontend: grupo "Deep Learning: Manipulação e Spoofing Facial" com abas PAD e MoE-FFD. |
| MOE-RF-09 | Página MoE-FFD exibe label, scores e permite salvar derivado. |
| MOE-RF-10 | Job rastreável na cadeia de custódia (hashes entrada/saída no fluxo padrão). |

## 5. Requisitos Não-Funcionais

| ID | Requisito |
|---|---|
| MOE-RNF-01 | Operação 100% local após instalação de pesos/vendor. |
| MOE-RNF-02 | Listagem de técnicas não deve importar PyTorch/timm MoE (probe leve: paths). |
| MOE-RNF-03 | Código do modelo original preservado via adapter (Regra Máxima 8). |
| MOE-RNF-04 | Perfil de reproducibilidade `gpu_ml`. |

## 6. Componentes

```text
docs/specs/modules/15-module-moe-ffd.md
tests/specs/test-module-moe-ffd.md
vendor/MoE-FFD/                                 # clone oficial
models/moe_ffd/MoE-FFD.tar                      # pesos HF
scripts/download_moe_ffd_weights.py
src/backend/core/technique_ids.py               # MOE_FFD
src/backend/core/legacy/moe_ffd/runtime.py
src/backend/core/legacy/moe_ffd/moe_ffd_pipeline.py
src/backend/core/plugins/moe_ffd_adapter.py
src/frontend/src/config/imageAnalysisGroups.ts
src/frontend/src/pages/MoeFfdAnalysis.tsx
src/frontend/src/config/imageTechniqueRegistry.tsx
src/frontend/src/config/forensicTechniqueMeta.ts
src/frontend/e2e/moe-ffd-navigation.spec.ts
```

## 7. Decisões

| ID | Decisão | Alternativas | Trade-off | Reversibilidade |
|---|---|---|---|---|
| ADR-MOE-001 | Vendor git clone + adapter fino | Reescrita | Preserva paridade forense | Fácil |
| ADR-MOE-002 | Instanciar `VisionTransformer` vendor direto (`pretrained=False`); evita `build_model_with_cfg` do timm≥1 | Factory oficial `vit_base_…` | Compatibilidade com timm do ambiente; mesma arquitetura | Fácil |
| ADR-MOE-003 | Single-image softmax class 1 = fake | Agregar frames | Simples, alinhado a eval | Moderada |
| ADR-MOE-004 | Renomear grupo UI; id `dl-facial-spoofing` | Manter `biometria-facial` | Clareza semântica | Moderada |
| ADR-MOE-005 | Crop RetinaFace (PAD) antes do MoE-FFD | Entrada já cropped; insightface | Reuso operacional; domínio FF++ | Fácil |
| ADR-MOE-006 | Fail-closed se `w_gate`≈0 / training_tar | Aceitar HF tar cego | Evita laudos "sempre real" | Fácil |

## 8. Fluxo de Dados

```text
Frontend (hub dl-facial-spoofing?tab=moe_ffd)
  → POST /api/v1/analysis {evidence_id, technique: "moe_ffd", parameters}
  → JobService / Celery GPU
  → MoeFfdAdapter.analyze
       → RetinaFace crop (face principal)
       → moe_ffd_pipeline.infer(image_path, crop_face=True)
       → artefatos result.json + summary + face_crop.png
  → GET job + artifacts → UI
```

## 9. Contrato de saída (sucesso)

```json
{
  "success": true,
  "adapter": "moe_ffd",
  "status": "completed",
  "label": "fake",
  "fake_prob": 0.91,
  "real_prob": 0.09,
  "score": 0.91,
  "threshold": 0.5,
  "inference_device": "cuda:0",
  "model_checkpoint": "MoE-FFD.tar",
  "face_cropped": true,
  "face_confidence": 0.98,
  "detector_bbox": {"x": 120, "y": 80, "w": 200, "h": 240},
  "crop_bbox": {"x": 90, "y": 40, "w": 260, "h": 260},
  "moe_ffd_result_json_path": "...",
  "moe_ffd_summary_txt_path": "...",
  "moe_ffd_face_crop_path": "...",
  "input_image_path": "..."
}
```

## 10. Riscos

| Risco | Classe | Detecção | Recuperação |
|---|---|---|---|
| Pesos ausentes | Alto | Runtime probe | Script download |
| Incompatibilidade timm/torch | Médio | Teste unitário de load | Pin / adapt shim |
| Entrada sem face | Médio | Score enviesado | Documentar pré-requisito de crop |
| Checkpoint layout diferente do tar | Alto | Validate keys no load | Relatar erro claro |

## 11. Rastreabilidade

| Req | Spec | Teste |
|---|---|---|
| MOE-RF-01 | este | test_moe_ffd_plugin_registered |
| MOE-RF-02 | este | test_moe_ffd_runtime_missing_weights |
| MOE-RF-03..05 | este | test_moe_ffd_infer_mocked |
| MOE-RF-08 | este | e2e moe-ffd-navigation |
| MOE-RF-09 | este | e2e + page unit smoke |
| MOE-RF-10 | este | integration API job |
