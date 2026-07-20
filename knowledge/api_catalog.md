# API Catalog — ForensicAuth

## Overview

Base path: `/api/v1`

Authentication: Bearer JWT token (except `/login`, `/first-access`, `/register`).

---

## Authentication

| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Obtain JWT access token |
| POST | `/auth/first-access` | Set password on first login |
| POST | `/auth/register` | Register new user (admin only) |
| GET | `/auth/me` | Current user profile |

## Users

| Method | Path | Description |
|---|---|---|
| GET | `/users` | List users (admin) |
| POST | `/users` | Create user (admin) |
| PUT | `/users/{user_id}` | Update user (admin) |
| POST | `/users/{user_id}/reset-password` | Reset user password (admin) |

## Cases

| Method | Path | Description |
|---|---|---|
| POST | `/cases` | Create case |
| GET | `/cases` | List accessible cases |
| GET | `/cases/{case_id}` | Get case details |
| PUT | `/cases/{case_id}` | Update case metadata |
| DELETE | `/cases/{case_id}` | Soft-delete case |
| GET | `/cases/{case_id}/closure-status` | Closure workflow status |
| POST | `/cases/{case_id}/close` | Initiate/sign case closure |
| POST | `/cases/{case_id}/close/sign` | Add closure signature |
| POST | `/cases/{case_id}/reopen` | Reopen closed case |
| GET | `/cases/{case_id}/closures` | List closure records |

## Case Shares

| Method | Path | Description |
|---|---|---|
| POST | `/cases/{case_id}/shares` | Share case with user |
| GET | `/cases/{case_id}/shares` | List shares |
| DELETE | `/cases/{case_id}/shares/{share_id}` | Revoke share |
| GET | `/users/for-sharing` | Users available for sharing |
| GET | `/cases/shared-with-me` | Cases shared with current user |

## Evidences

| Method | Path | Description |
|---|---|---|
| POST | `/evidences/upload` | Upload evidence file |
| POST | `/evidences/prnu-reference-upload` | Upload PRNU reference images |
| POST | `/evidences/pdf-structure-reference-upload` | Upload PDF reference |
| POST | `/evidences/isom-structure-reference-upload` | Upload ISO BMFF reference |
| POST | `/evidences/jpeg-structure-reference-upload` | Upload JPEG reference |
| POST | `/evidences/reference-upload` | Upload DCT reference |
| POST | `/evidences/global-reference-upload` | Upload global reference |
| POST | `/evidences/derivatives` | Save job artifact as derivative |
| DELETE | `/evidences/{evidence_id}` | Soft-delete evidence |
| GET | `/evidences/{evidence_id}` | Get evidence metadata |
| GET | `/evidences/{evidence_id}/thumbnail` | Download thumbnail |
| GET | `/evidences/{evidence_id}/file` | Download original file |
| GET | `/evidences/{evidence_id}/lineage` | Derivation lineage graph |
| GET | `/cases/{case_id}/evidences` | List case evidences |
| GET | `/cases/{case_id}/audio-metadata` | Audio metadata summary |
| GET | `/cases/{case_id}/references` | Case technical references |
| GET | `/cases/{case_id}/derivatives` | Case derivative evidences |

## Analysis Jobs

| Method | Path | Description |
|---|---|---|
| GET | `/analysis/techniques` | List available techniques |
| GET | `/analysis/imdlbenco/methods` | List IMDL-BenCo methods (admin) |
| POST | `/analysis` | Submit analysis job |
| GET | `/analysis/gpu-queue` | GPU queue snapshot |
| GET | `/analysis/{job_id}` | Get job metadata |
| GET | `/analysis/{job_id}/result` | Get job result JSON |
| POST | `/analysis/{job_id}/reproduce` | Re-run job and compare |
| GET | `/analysis/{job_id}/result/file` | Download result file |
| GET | `/analysis/{job_id}/result/spectrogram-display` | Spectrogram display data |
| GET | `/analysis/{job_id}/result/audio-plot-data` | Audio plot traces |
| POST | `/analysis/{job_id}/spectrogram/snapshot` | Save spectrogram snapshot |
| POST | `/analysis/{job_id}/plot-snapshot` | Save plot snapshot |
| POST | `/analysis/{job_id}/result/wavelet-noise-residue-preview` | WNR preview |
| GET | `/analysis/audio-spoofing-reference-catalog` | Audio spoofing reference-population catalog |

## PRNU

| Method | Path | Description |
|---|---|---|
| GET | `/cases/{case_id}/prnu/fingerprints` | List PRNU fingerprints |
| POST | `/cases/{case_id}/prnu/fingerprints` | Create PRNU fingerprint |

## Audit / Custody

| Method | Path | Description |
|---|---|---|
| GET | `/audit` | List custody records |
| GET | `/audit/verify/{record_id}` | Verify single record |
| GET | `/audit/verify-case/{case_id}` | Verify case chain |
| GET | `/audit/signing-keys` | List signing keys metadata |
| GET | `/audit/verify-case-forensic/{case_id}` | Forensic verification |
| GET | `/audit/verify-case-forensic/{case_id}/report` | Verification report |
| GET | `/audit/case/{case_id}/narrative-report` | Narrative report |

## Case Transfer (VCP)

| Method | Path | Description |
|---|---|---|
| POST | `/cases/{case_id}/export` | Export case package |
| POST | `/cases/import/validate` | Validate import package |
| POST | `/cases/import` | Import case package |

## Peritus Transfer

| Method | Path | Description |
|---|---|---|
| POST | `/cases/peritus/import/validate` | Validate Peritus import |
| POST | `/cases/peritus/import` | Import Peritus package |
| POST | `/cases/{case_id}/peritus/custody/register-files` | Register Peritus files |
| GET | `/cases/{case_id}/peritus/meta` | Peritus metadata |
| POST | `/cases/{case_id}/peritus/files/resolve-analysis` | Resolve analysis files |
| POST | `/cases/{case_id}/peritus/export` | Export to Peritus |
| GET | `/cases/{case_id}/peritus/files` | List Peritus files |
| GET | `/cases/{case_id}/peritus/files/thumbnail` | Peritus thumbnail |
| GET | `/cases/{case_id}/peritus/files/download` | Download Peritus file |

## References

| Method | Path | Description |
|---|---|---|
| GET | `/references/papers/imdl` | List IMDL reference papers |
| GET | `/references/papers/imdl/{technique_id}` | Papers for technique |
| GET | `/references/papers/imdl/{technique_id}/file` | Download paper |
| GET | `/references/papers/imdl/{technique_id}/file/{paper_index}` | Download paper by index |

---

## Audio Spoofing LR Calibration

The `audio_spoofing_detection` technique supports reference-population likelihood-ratio (LR) calibration, mirroring the synthetic-image LR pipeline for the three active audio spoofing detectors:

- `df_arena_1b` — DF Arena 1B
- `sls_xlsr` — SLS XLS-R (ACM MM 2024)
- `wedefense_wavlm_mhfa` — WeDefense ASV2025 WavLM + MHFA

LR > 1 favors `H1 = bonafide/authentic`; LR < 1 favors `H0 = spoof/synthetic`.

### Reference data files

| File | Path |
|---|---|
| Default score matrix | `outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv` |
| Augmented score matrix | `outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full_augmented.csv` |
| Representations matrix (scores + embeddings) | `outputs/lr_calibration/audio_spoofing/representations/representations.csv` |

### Reference population sampling

For each selected base-group / subgroup pair:

- `SAMPLE_PER_CLASS = 500` samples per class (bonafide / spoof).
- `TRAIN_PER_CLASS = 250` assigned to `train_logreg`.
- `CALIB_PER_CLASS = 125` assigned to `calibration_bigauss`.
- `TEST_PER_CLASS = 125` assigned to `test_bigauss`.

The training split feeds the meta-classifier; the calibration split fits the bi-Gaussian; the held-out test split produces `CLLR`, `minCLLR`, `EER`, `AUC`, Tippett, distribution, and identity plots.

### Meta-classifiers

Implemented in `core.audio_spoofing_lr_reference` via `core.synthetic_lr_reference`:

- `logistic` (default)
- `logistic_poly2`
- `xgboost`
- `gradient_boosting`
- `random_forest`
- `extra_trees`
- `svm_rbf`
- `mlp`
- `kde_naive_bayes`

### Calibration

Bi-Gaussian EER calibration (`_fit_bigauss`) produces `mu_real`, `mu_fake`, `sigma`, and an `eer` threshold. The pipeline also reports per-detector EER percentages, feature weights / coefficients, and the logistic intercept when applicable.

### Submission parameters

Extra `parameters` accepted by `POST /analysis` for `audio_spoofing_detection`:

| Parameter | Type | Description |
|---|---|---|
| `reference_lr_enabled` | `bool` | Enable reference-population LR calibration |
| `reference_population` | `object` | Selection of base-group / subgroup pairs; supports `fit_items` and `test_items` for separate train/calibration vs. test roles, or `items` / `macro` for backward-compatible single-role selection |
| `meta_classifier` | `string` | One of the meta-classifiers listed above |
| `use_augmented_reference` | `bool` | Include augmented variants in the reference population |
| `use_latent_typicality` | `bool` | Include latent-typicality k-NN features (system D) |
| `selected_analyses` | `list[string]` | Detectors to run; defaults to all three |
| `window_seconds` | `float` | Analysis window length (1–60 s, default 4) |
| `max_duration_seconds` | `float` | Evidence truncation cap (10–300 s, default 90) |

### Cache

Calibrated models and typicality references are cached as `.joblib` under `outputs/lr_calibration/cache/`. The cache key is a SHA-256 digest of the reference selection, score/representations matrix, meta-classifier, and seed; when `use_latent_typicality` is true, the key also includes the typicality `system`, `k`, and `distance`. Identical selections reuse the cached model.

---

## Latent Typicality

Implemented in `core.latent_typicality`. Adds k-NN typicality features computed over detector embeddings.

### Defaults

- System: `D`
- Distance: `cosine`
- `k = 5`
- `eps = 1e-8`

### Feature families

For each detector `d`:

| Feature | Meaning |
|---|---|
| `S_d` | Detector bonafide logit |
| `T_R_d` | Typicality against the real/bonafide embedding bank |
| `T_S_d` | Typicality against the synthetic/spoof embedding bank |
| `OOD_d` | Out-of-distribution score: `1 - max(T_R_d, T_S_d)` |
| `Delta_r_d` | Difference of k-th neighbor distances: `r_real - r_spoof` |
| `rho_d` | Log ratio of distances: `log((r_real + eps) / (r_spoof + eps))` |
| `r_R_d`, `r_S_d` | Raw k-th neighbor distances |

### Systems A/B/C/D

| System | Features used |
|---|---|
| A | `S_*` only |
| B | `S_*` + `T_R_*` + `T_S_*` |
| C | B + `OOD_*` |
| D | C + `Delta_r_*` + `rho_*` |

### Requirements

Latent typicality requires the representations matrix `representations.csv` containing `*_embedding_path` columns for every selected detector. The adapter validates availability before job submission; the pipeline builds k-NN banks only on the `train_logreg` split to avoid leakage, materializes features in batches, and caches the model plus typicality references in `.joblib` format.

---

## Augmented Reference Population

Offline augmentations mimic common post-synthesis / distribution conditions. Implemented in `scripts/audio_lr_augmentation.py`.

| Augmentation | Description |
|---|---|
| `mp3_128k` | MP3 recompression at 128 kbps (WAV → MP3 → WAV) |
| `opus_32k` | Opus at 32 kbps, `libopus` VOIP application |
| `noise_snr_20` | Pink noise mixed at 20 dB SNR |
| `noise_snr_15` | Pink noise mixed at 15 dB SNR |

When `use_augmented_reference` is true, the sample multiplier becomes `AUGMENTATION_MULTIPLIER = 5` (original + 4 augmentations), and all splits grow proportionally. The augmented path is selected when `use_latent_typicality` is true or when the augmented score matrix / representations matrix is present on disk.

---

## Audio Spoofing Reference Catalog

`GET /analysis/audio-spoofing-reference-catalog` returns the hierarchical catalog consumed by the frontend selector.

Response shape:

```json
{
  "categories": [
    {
      "id": "asv_classic",
      "label": "ASVspoof (LA)",
      "year_range": "2019–2025",
      "description": "...",
      "bases": [
        {
          "id": "ASVspoof2019_LA",
          "label": "ASVspoof 2019 LA",
          "generators": [
            {"id": "flac_E", "label": "flac_E", "detector_eer_percent": [...]}
          ]
        }
      ]
    }
  ],
  "detector_eer_order": ["df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa"],
  "detector_eer_labels": ["DF Arena 1B", "SLS XLS-R (ACM MM 2024)", "WeDefense ASV2025 WavLM + MHFA"],
  "default_reference_items": [{"base_group": "...", "subgroup": "..."}]
}
```

Macro categories: `asv_classic`, `codec_conditions`, `deepfake_challenges`, `in_the_wild`. The default selection (`DEFAULT_VOICE_CLONE_REFERENCE`) targets voice-cloning and in-the-wild scenarios.

---

## LR Calibration Artifacts

When `reference_lr_enabled` succeeds, the job result directory contains:

| Artifact | Filename | Description |
|---|---|---|
| JSON report | `lr_reference_report.json` | Full calibration report: hypotheses, selected items, metrics, bigauss params, questioned LR, feature weights |
| Text summary | `lr_reference_summary.txt` | Human-readable summary of the same data |
| Tippett plot | `lr_reference_tippett.png` | Tippett plot for the held-out test set |
| Distribution plot | `lr_reference_distribution.png` | LR distribution with questioned LR marker |
| Identity plot | `lr_reference_identity.png` | Calibration identity function |
| Serialized model | `lr_reference_model.joblib` | Trained meta-classifier, feature columns, calibration, and selected items |
| Test scored CSV | `lr_reference_test_scored.csv` | Scored held-out test rows |

These artifacts are exposed through `GET /analysis/{job_id}/result/file?filename=...` and can be saved as derivative evidences.

---

## Frontend — Audio Spoofing Analysis

Page: `src/frontend/src/pages/AudioSpoofingAnalysis.tsx`.

Controls added for LR calibration and latent typicality:

- Detector multi-selector with availability status from `GET /analysis/audio-spoofing-detectors`.
- `ReferencePopulationSelector` loaded from `GET /analysis/audio-spoofing-reference-catalog`, supporting split roles (`fit_items` / `test_items`) and EER display per generator.
- `MetaClassifierSelect` for choosing the meta-classifier.
- Checkbox `use_augmented_reference` for augmented reference population.
- Checkbox `use_latent_typicality` for k-NN latent typicality (system D).
- `ReferenceLrPanel` displays `log10(LR)`, `LR`, test metrics, and the Tippett / distribution / identity plots.
- `SaveButton` controls allow saving detector scores, plot data, JSON details, and LR artifacts as derivative evidences.

When latent typicality or augmented reference is enabled, the frontend disables the job timeout (`maxWaitMs: Infinity`) because the first calibration of a new selection may take several minutes; subsequent identical selections reuse the cached model.

---

## Notes

- Path parameters use UUIDs unless otherwise noted.
- All `POST /evidences/*-upload` endpoints require edit permission on the case and reject closed cases.
- All `/analysis` job submission endpoints require edit permission and reject closed cases.
- Audio spoofing LR calibration additionally requires the selected reference-population file(s) to exist on disk; the adapter rejects the job if the augmented population or representations matrix is requested but unavailable.
