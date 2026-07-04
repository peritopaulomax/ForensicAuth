# ML/Forensic Summary — ForensicAuth

## O que é

Pipeline forense plugável que orquestra dezenas de técnicas de análise de imagem, áudio, vídeo e PDF.

## Contrato

`ForensicPlugin` em `core/forensic_plugin.py` define:
- `name`
- `supported_types`
- `validate_parameters`
- `analyze`

## Técnicas por mídia

### Imagem (CPU)
- ELA, metadata, DCT quantization, JPEG ghosts, double compression, resampling, BAG extraction, ZERO grid, wavelet noise residue, PRNU, PatchMatch, copy-move PCA, JPEG structure compare

### Imagem (GPU/ML)
- Synthetic image detection (ai-image-detector-deploy, sdxl-flux-detector v1.1, B-Free/Bias-free e Corvi2023/DMimageDetection em tiles 1024px)
- SAFIRE, Noiseprint, IMDL-BenCo hub (nativos + ecosystem)
- Presentation Attack Detection (PAD)

### Áudio
- ENF, spectrogram, levels, LTAS, DC local
- Parsers MP3/Opus/WAV IMA ADPCM em `STANDBY_PLUGIN_NAMES`

### Vídeo
- ISO BMFF parser/compare, VideoFACT, STIL, Low-Res Fake Video

### PDF
- Forensic extract, structure metrics, structure similarity, font color overlay
- pdf_touchup em `STANDBY_PLUGIN_NAMES`

## Orquestração

```text
POST /analysis → JobService.submit_job → JobRunner → Celery/Thread → plugin.analyze → stage artifacts → (CustodyRecord não gerado no código atual)
```

## GPU

- Serialização por `ml_gpu_job_slot` (local) + `gpu_distributed_lock` (Redis)
- Cache LRU de modelos residentes (`gpu_residency.py`)
- Fallback CPU quando GPU indisponível
- Técnicas GPU (IDs canônicos): `synthetic_image_detection`, `deepfake_similarity`, `safire`, `noiseprint`, `imdlbenco`, `videofact`, `stil_video_detection`, `lowres_fake_video`, `presentation_attack_detection`

## Modelos

- ~20 famílias de modelos em `models/`
- Tamanho total aproximado: 43 GB
- Duplicatas com `vendor/`
- Download via scripts manuais (gdown, huggingface_hub, wget)

## Reproducibilidade

- `REPRODUCIBILITY_REGISTRY` por técnica
- Runtime manifests com versões de libs e hashes de modelos
- Job execution receipts com perfis de determinismo (`strict`, `numeric`, `parallel`, `gpu_ml`, `canonical`)

## Riscos

- GPU singleton (gargalo)
- Modelos não versionados automaticamente
- `deepfake_similarity` placeholder em standby
- Métodos IMDL-BenCo ecosystem faltando pesos/vendors
- `torch.load(weights_only=False)` em ~22 pipelines legados
- Ausência de drift monitoring
- Vendor forks sem versionamento claro
- Fallback para CPU é logado, mas pode passar despercebido na UI
- Worker GPU não incluído no `docker-compose.yml` base

## Dívidas

- Testes de regressão forense ausentes
- sys.path manipulado por vendors
- Duplicação de pesos (`models/` vs `vendor/`)
- Política de cache distribuída entre múltiplos caches específicos, sem invalidação centralizada unificada
- Thresholds hardcoded
- Scripts de download de pesos espalhados (23 scripts)

## Confiabilidade

Média — ecossistema abrangente, mas dependente de pesos, vendors e validação forense rigorosa.
