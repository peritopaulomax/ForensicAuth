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

## Notes

- Path parameters use UUIDs unless otherwise noted.
- All `POST /evidences/*-upload` endpoints require edit permission on the case and reject closed cases.
- All `/analysis` job submission endpoints require edit permission and reject closed cases.
