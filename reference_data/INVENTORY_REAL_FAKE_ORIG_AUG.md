# Inventário reference_data — real/fake × original/aumentado

Gerado historicamente por script de inventário (path antigo fora do clone); este Markdown permanece como snapshot.

Legenda:
- `FAKE_ONLY_AUG` / `REAL_ONLY_AUG`: só aumentados (originais faltando)
- `FAKE_NO_AUG` / `REAL_NO_AUG`: só originais (aumentados faltando)
- `NO_FAKE` / `NO_REAL`: classe ausente
- `OK`: cobertura completa na matriz
- `OK_SCORES`: scores base (sem coluna de aug) com real e fake

## synthetic_image

- **scores**: `reference_data/synthetic_image/features/scores/lr_scores_balanced_full.csv` — 25331 rows ok, 9 error
- **scores_augmented**: `reference_data/synthetic_image/features/scores/lr_scores_balanced_full_augmented.csv` — 229295 rows ok, 9 error
- **representations**: `reference_data/synthetic_image/features/representations/representations.csv` — 222495 rows ok, 0 error

### synthetic_image / representations

| dataset | orig_real | orig_fake | aug_real | aug_fake | flags | gens_missing_orig_fake | n_ok_orig | n_ok_aug |
|---|---:|---:|---:|---:|---|---|---:|---:|
| AIGCDetectBenchmark | 0 | 0 | 34000 | 32800 | FAKE_ONLY_AUG REAL_ONLY_AUG | ADM, BigGAN, CycleGAN, DALLE2, GLIDE, GauGAN, Midjourney, ProGAN, SD14, SD15, SDXL, StarGAN, StyleGAN, StyleGAN2, VQDM (+2) | 0 | 17 |
| AIGIBench | 750 | 750 | 12600 | 12600 | OK | Midjourney | 5 | 6 |
| BFree_extended_synthbuster | 160 | 160 | 4000 | 4000 | OK | — | 2 | 2 |
| Defactify_MS_COCOAI | 3500 | 3500 | 14000 | 14000 | OK | — | 5 | 5 |
| GenImage | 3991 | 4000 | 15964 | 16000 | OK | — | 8 | 8 |
| OpenSDI_test | 600 | 600 | 4000 | 4000 | OK | — | 2 | 2 |
| Synthbuster | 160 | 360 | 18000 | 18000 | OK | — | 9 | 9 |

#### Detalhe por generator (synthetic_image / representations)

**AIGCDetectBenchmark** — FAKE_ONLY_AUG, REAL_ONLY_AUG

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| ADM ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| BigGAN ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| CycleGAN ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| DALLE2 ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| GLIDE ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| GauGAN ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Midjourney ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| ProGAN ⚠️ fake só aug | 0 | 0 | 0 | 800 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Real (pool real) | 0 | 0 | 34000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SD14 ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SD15 ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SDXL ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| StarGAN ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| StyleGAN ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| StyleGAN2 ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| VQDM ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| WhichFaceIsReal ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Wukong ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |

**AIGIBench** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| CommunityAI | 0 | 150 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| CommunityAI_real (pool real) | 150 | 0 | 2000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| DALLE-3 | 0 | 150 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| DALLE-3_real (pool real) | 150 | 0 | 2000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| FLUX1-dev | 0 | 150 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| FLUX1-dev_real (pool real) | 150 | 0 | 2000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Midjourney ⚠️ fake só aug | 0 | 0 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Midjourney_real (pool real) | 0 | 0 | 2000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SD3 | 0 | 150 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SD3_real (pool real) | 150 | 0 | 2000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SocialRF | 0 | 150 | 0 | 2600 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SocialRF_real (pool real) | 150 | 0 | 2600 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |

**BFree_extended_synthbuster** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| FLUX | 0 | 80 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| RAISE (pool real) | 160 | 0 | 4000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| latent-diffusion | 0 | 80 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |

**Defactify_MS_COCOAI** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| DALL-E_3 | 0 | 700 | 0 | 2800 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Midjourney_v6 | 0 | 700 | 0 | 2800 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Real (pool real) | 3500 | 0 | 14000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SD2.1 | 0 | 700 | 0 | 2800 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SD3 | 0 | 700 | 0 | 2800 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| SDXL | 0 | 700 | 0 | 2800 | crop_upscale,jpeg_85,resize_down_50,webp_80 |

**GenImage** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| ADM | 500 | 500 | 2000 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| BigGAN | 500 | 500 | 2000 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Midjourney | 500 | 500 | 2000 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| VQDM | 500 | 500 | 2000 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| glide | 500 | 500 | 2000 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| stable_diffusion_v_1_4 | 500 | 500 | 2000 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| stable_diffusion_v_1_5 | 491 | 500 | 1964 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| wukong | 500 | 500 | 2000 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |

**OpenSDI_test** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| OpenSDI_real (pool real) | 600 | 0 | 4000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| flux | 0 | 300 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| sd3 | 0 | 300 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |

**Synthbuster** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| Adobe_Firefly | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| DALL-E_2 | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| DALL-E_3 | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| GLIDE | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Midjourney_v5 | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| RAISE (pool real) | 160 | 0 | 18000 | 0 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Stable_Diffusion_1.3 | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Stable_Diffusion_1.4 | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Stable_Diffusion_2 | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |
| Stable_Diffusion_XL | 0 | 40 | 0 | 2000 | crop_upscale,jpeg_85,resize_down_50,webp_80 |

### synthetic_image / scores

| dataset | orig_real | orig_fake | aug_real | aug_fake | flags | gens_missing_orig_fake | n_ok_orig | n_ok_aug |
|---|---:|---:|---:|---:|---|---|---:|---:|
| AIGCDetectBenchmark | 3400 | 3400 | 0 | 0 | OK_SCORES | — | 17 | 0 |
| AIGIBench | 750 | 750 | 0 | 0 | OK_SCORES | — | 5 | 0 |
| BFree_extended_synthbuster | 160 | 160 | 0 | 0 | OK_SCORES | — | 2 | 0 |
| Defactify_MS_COCOAI | 3500 | 3500 | 0 | 0 | OK_SCORES | — | 5 | 0 |
| GenImage | 3991 | 4000 | 0 | 0 | OK_SCORES | — | 8 | 0 |
| OpenSDI_test | 600 | 600 | 0 | 0 | OK_SCORES | — | 2 | 0 |
| Synthbuster | 160 | 360 | 0 | 0 | OK_SCORES | — | 9 | 0 |

### synthetic_image / scores_augmented

| dataset | orig_real | orig_fake | aug_real | aug_fake | flags | gens_missing_orig_fake | n_ok_orig | n_ok_aug |
|---|---:|---:|---:|---:|---|---|---:|---:|
| AIGCDetectBenchmark | 3400 | 3400 | 34000 | 32800 | OK | — | 17 | 17 |
| AIGIBench | 750 | 750 | 12600 | 12600 | OK | Midjourney | 5 | 6 |
| BFree_extended_synthbuster | 160 | 160 | 4000 | 4000 | OK | — | 2 | 2 |
| Defactify_MS_COCOAI | 3500 | 3500 | 14000 | 14000 | OK | — | 5 | 5 |
| GenImage | 3991 | 4000 | 15964 | 16000 | OK | — | 8 | 8 |
| OpenSDI_test | 600 | 600 | 4000 | 4000 | OK | — | 2 | 2 |
| Synthbuster | 160 | 360 | 18000 | 18000 | OK | — | 9 | 9 |

## audio_spoofing

- **scores**: `reference_data/audio_spoofing/features/scores/lr_scores_balanced_full.csv` — 32473 rows ok, 0 error
- **scores_augmented**: AUSENTE
- **representations**: `reference_data/audio_spoofing/features/representations/representations.csv` — 162800 rows ok, 0 error

### audio_spoofing / representations

| dataset | orig_real | orig_fake | aug_real | aug_fake | flags | gens_missing_orig_fake | n_ok_orig | n_ok_aug |
|---|---:|---:|---:|---:|---|---|---:|---:|
| ADD2022 | 1000 | 1000 | 4000 | 4000 | OK | — | 2 | 2 |
| ADD2023 | 1002 | 1000 | 4000 | 4000 | OK | — | 2 | 2 |
| ASVspoof2019_LA | 500 | 500 | 2000 | 2000 | OK | — | 1 | 1 |
| ASVspoof2021_LA_eval | 500 | 500 | 2000 | 2000 | OK | — | 1 | 1 |
| ASVspoof5 | 500 | 500 | 2000 | 2000 | OK | — | 1 | 1 |
| CodecFake | 3500 | 3500 | 14000 | 14000 | OK | — | 7 | 7 |
| DFADD | 2500 | 2500 | 10000 | 10000 | OK | — | 5 | 5 |
| Fake-or-Real | 999 | 796 | 2000 | 1592 | OK | — | 1 | 1 |
| In-The-Wild | 500 | 500 | 2000 | 2000 | OK | — | 1 | 1 |
| LibriSeVoc | 3000 | 3000 | 12000 | 12000 | OK | — | 6 | 6 |
| SONAR | 4000 | 1519 | 16000 | 5892 | OK | — | 8 | 8 |

#### Detalhe por generator (audio_spoofing / representations)

**ADD2022** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| track1test | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| track32test | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**ADD2023** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| Track1.2_testR1 | 501 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| Track1.2_testR2 | 501 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**ASVspoof2019_LA** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| flac_E | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**ASVspoof2021_LA_eval** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| LA_eval | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**ASVspoof5** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| flac_E_eval | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**CodecFake** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| C1 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| C2 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| C3 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| C4 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| C5 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| C6 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| C7 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**DFADD** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| GradTTS | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| NaturalSpeech2 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| StyleTTS2 | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| matcha | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| pflow | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**Fake-or-Real** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| Fake-or-Real | 999 | 796 | 2000 | 1592 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**In-The-Wild** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| In-The-Wild | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**LibriSeVoc** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| diffwave | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| melgan | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| parallel_wave_gan | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| wavegrad | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| wavenet | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| wavernn | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

**SONAR** — OK

| generator | orig_real | orig_fake | aug_real | aug_fake | augs |
|---|---:|---:|---:|---:|---|
| AudioGen | 500 | 100 | 2000 | 400 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| FlashSpeech | 500 | 118 | 2000 | 472 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| NaturalSpeech3 | 500 | 32 | 2000 | 128 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| OpenAI_fixed | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| PromptTTS2 | 500 | 25 | 2000 | 100 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| VALLE | 500 | 140 | 2000 | 376 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| VoiceBox | 500 | 104 | 2000 | 416 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |
| xTTS | 500 | 500 | 2000 | 2000 | mp3_128k,noise_snr_15,noise_snr_20,opus_32k |

### audio_spoofing / scores

| dataset | orig_real | orig_fake | aug_real | aug_fake | flags | gens_missing_orig_fake | n_ok_orig | n_ok_aug |
|---|---:|---:|---:|---:|---|---|---:|---:|
| ADD2022 | 1000 | 1000 | 0 | 0 | OK_SCORES | — | 2 | 0 |
| ADD2023 | 1000 | 1000 | 0 | 0 | OK_SCORES | — | 2 | 0 |
| ASVspoof2019_LA | 500 | 500 | 0 | 0 | OK_SCORES | — | 1 | 0 |
| ASVspoof2021_LA_eval | 500 | 500 | 0 | 0 | OK_SCORES | — | 1 | 0 |
| ASVspoof5 | 500 | 500 | 0 | 0 | OK_SCORES | — | 1 | 0 |
| CodecFake | 3500 | 3500 | 0 | 0 | OK_SCORES | — | 7 | 0 |
| DFADD | 2500 | 2500 | 0 | 0 | OK_SCORES | — | 5 | 0 |
| Fake-or-Real | 500 | 500 | 0 | 0 | OK_SCORES | — | 1 | 0 |
| In-The-Wild | 500 | 500 | 0 | 0 | OK_SCORES | — | 1 | 0 |
| LibriSeVoc | 3000 | 3000 | 0 | 0 | OK_SCORES | — | 6 | 0 |
| SONAR | 4000 | 1473 | 0 | 0 | OK_SCORES | — | 8 | 0 |

## Arquivos ausentes

- audio `scores_augmented` (`lr_scores_balanced_full_augmented.csv`): **AUSENTE**

