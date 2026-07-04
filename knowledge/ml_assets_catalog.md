# ML Assets Catalog — ForensicAuth

## Overview

ForensicAuth orchestrates multiple ML models for image, audio, video and PDF forensic analysis. Weights and vendor code live under `models/` and `vendor/`.

---

## Image Forensics Models (`models/`)

| Model | Technique | Vendor Source | Purpose |
|---|---|---|---|
| `bfree` | `synthetic_image_detection` | `vendor/bfree` | B-Free / Bias-free synthetic image detection |
| `camo` | standby legacy | — | Camera model identification |
| `clide` | `clide` | `vendor/clide` | CLIP-based synthetic image detection |
| `deeclip` | `deeclip` | `vendor/deeclip` | Deepfake detection via CLIP |
| `distildire` | standby legacy | `vendor/distildire` | DistilDire deepfake detection |
| `effort` | standby legacy | `vendor/Effort-main` | Effort deepfake detection |
| `fakevlm` | standby legacy | `vendor/fakevlm` | FakeVLM detection |
| `fsd` | — | — | Face-spoofing detection |
| `grip_clipd` | `synthetic_image_detection` | `vendor/grip_clipbased_synthetic` | Corvi2023 / DMimageDetection synthetic detection |
| `iapl` | standby legacy | `vendor/IAPL` | Image analysis plugin library |
| `imdlbenco` | `imdlbenco` | `vendor/IMDL-BenCo` | IMDL benchmark coordinator |
| `iml_vit` | — | `vendor/IML-ViT-main` | Image manipulation localization ViT |
| `lowres_fake_video` | `lowres_fake_video` | `vendor/fake-video-detection` | Low-resolution fake video |
| `noiseprint` | `noiseprint` | `vendor/grip-unina-noiseprint` | Noiseprint camera fingerprint |
| `pad` | `presentation_attack_detection` | — | Presentation attack detection |
| `prnu` | `prnu` | — | PRNU camera fingerprint |
| `safe` | standby legacy | `vendor/SAFE` | Synthetic face detection |
| `safire` | `safire` | `vendor/SAFIRE` | SAFIRE |
| `sepael` | `sepael` / `synthetic_image_detection` | — | SepaEL |
| `sidbench_weights` | — | `vendor/sidbench` | SID benchmark weights |
| `stil` | `stil_video_detection` | `vendor/Mesorch` | STIL video detection |
| `truebees_clip_d` | — | — | TrueBees CLIP |
| `universal_fake_detect` | standby legacy | — | Universal fake detection |
| `videofact` | `videofact` | — | VideoFact video deepfake |

## Vendor Research Code (`vendor/`)

| Vendor | Source | Models Served |
|---|---|---|
| `bitmind-subnet` | Bitmind | Synthetic image detection |
| `BR-Gen-main` | — | Boundary artifact generation |
| `bfree` | GRIP-UNINA B-Free | Bias-free synthetic image detection |
| `CAT-Net-main` | — | Copy-move detection |
| `clide` | CLIDE | CLIP-based detection |
| `Co-Transformers-main` | — | Detection transformers |
| `deeclip` | DEClip | CLIP deepfake |
| `deepfakebench` | DeepFakeBench | Benchmark suite |
| `dinov3` / `DINOv3-IML` | DINOv3 | Image manipulation localization |
| `distildire` | DistilDire | Deepfake detection |
| `dmimage_detection` | — | Image forensics |
| `fake-video-detection` | — | Video deepfake |
| `fakevlm` | FakeVLM | VLM-based detection |
| `fsd` | — | Face spoofing |
| `grip_clipbased_synthetic` | GRIP | CLIP synthetic |
| `grip-unina-noiseprint` / `grip-unina-trufor` | UniNa | Noiseprint / TruFor |
| `IAPL` | IAPL | Image analysis |
| `IMDL-BenCo` | IMDL-BenCo | Benchmark framework |
| `IML-ViT-main` | — | ViT localization |
| `Mesorch` | — | STIL |
| `MIML` | — | Multiple instance learning |
| `noiseprint-pytorch-main` | — | Noiseprint PyTorch |
| `SAFE` | SAFE | Synthetic face |
| `SAFIRE` / `SAFIRE-main` | SAFIRE | Deepfake detection |
| `sidbench` | SIDBench | Benchmark weights |

## Notes

- Models are loaded on-demand via adapters in `src/backend/core/plugins/`.
- GPU-resident models are cached by `GPUResidency` (`src/backend/services/gpu_residency.py`).
- Weights are mounted as volumes in Docker (`./models:/app/models`).
- Offline mode: `TRANSFORMERS_OFFLINE=1` prevents HuggingFace downloads in production.
