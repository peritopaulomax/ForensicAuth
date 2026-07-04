# Data Catalog — ForensicAuth

## Overview

Database: PostgreSQL (production) / SQLite (dev/test)
ORM: SQLAlchemy 2.x
Migrations: Alembic (`alembic/versions/`)

---

## Tables

### users

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | User identifier |
| username | VARCHAR(50) | False |  |  | Login username |
| email | VARCHAR(255) | False |  |  | Email address |
| hashed_password | VARCHAR(255) | False |  |  | Bcrypt hash |
| password_set | BOOLEAN | False |  |  | Whether password has been set |
| role | VARCHAR(6) | False |  |  | `admin` or `perito` |
| is_active | BOOLEAN | False |  |  | Account enabled |
| created_at | DATETIME | False |  |  | Creation timestamp |
| updated_at | DATETIME | False |  |  | Last update timestamp |

### cases

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | Case identifier |
| protocol_number | VARCHAR(50) | False |  |  | Unique protocol |
| inquiry_number | VARCHAR(100) | True |  |  | Inquiry number |
| process_number | VARCHAR(100) | True |  |  | Process number |
| title | VARCHAR(255) | False |  |  | Case title |
| description | TEXT | True |  |  | Case description |
| created_by | UUID | False |  | users.id | Case owner |
| assigned_to | UUID | True |  | users.id | Assigned expert |
| status | VARCHAR(19) | False |  |  | `aberto`, `fechamento_pendente`, `fechado` |
| created_at | DATETIME | False |  |  | Creation timestamp |
| updated_at | DATETIME | False |  |  | Last update timestamp |
| deleted_at | DATETIME | True |  |  | Soft-delete timestamp |
| deleted_by | UUID | True |  | users.id | User who deleted |
| storage_mode | VARCHAR(20) | False |  |  | `forensicauth` or `peritus` |
| custody_seal | VARCHAR(64) | True |  |  | Case closure seal hash |
| custody_seal_signature | TEXT | True |  |  | Ed25519 signature |
| custody_seal_record_hash | VARCHAR(64) | True |  |  | Last custody record hash |
| custody_seal_timestamp | DATETIME | True |  |  | Seal timestamp |

### case_shares

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | Share identifier |
| case_id | UUID | False |  | cases.id | Shared case |
| shared_with_user_id | UUID | False |  | users.id | Recipient |
| role | VARCHAR(20) | False |  |  | `viewer` or `editor` |
| shared_by | UUID | False |  | users.id | Grantor |
| created_at | DATETIME | False |  |  | Grant timestamp |
| revoked_at | DATETIME | True |  |  | Revocation timestamp |

### evidences

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | Evidence identifier |
| case_id | UUID | False |  | cases.id | Parent case |
| filename | VARCHAR(255) | False |  |  | Stored filename |
| original_filename | VARCHAR(255) | False |  |  | Original filename |
| file_path | VARCHAR(512) | False |  |  | Filesystem path |
| file_size | INTEGER | False |  |  | Size in bytes |
| file_type | VARCHAR(9) | False |  |  | `imagem`, `audio`, `video`, `pdf`, `documento` |
| mime_type | VARCHAR(100) | True |  |  | MIME type |
| sha256 | VARCHAR(64) | False |  |  | File hash |
| extra_metadata | JSON | False |  |  | Technical metadata |
| uploaded_by | UUID | False |  | users.id | Uploader |
| created_at | DATETIME | False |  |  | Upload timestamp |
| deleted_at | DATETIME | True |  |  | Soft-delete timestamp |
| deleted_by | UUID | True |  | users.id | Deleter |

### reports

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | Report identifier |
| case_id | UUID | False |  | cases.id | Parent case |
| title | VARCHAR(255) | False |  |  | Report title |
| file_path | VARCHAR(512) | False |  |  | PDF path |
| sha256 | VARCHAR(64) | False |  |  | File hash |
| generated_by | UUID | False |  | users.id | Generator |
| created_at | DATETIME | False |  |  | Generation timestamp |

### analysis_jobs

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | Job identifier |
| evidence_id | UUID | False |  | evidences.id | Input evidence |
| technique | VARCHAR(50) | False |  |  | Technique name |
| status | VARCHAR(20) | False |  |  | `pending`, `running`, `completed`, `failed` |
| progress | INTEGER | False |  |  | 0-100 |
| progress_message | VARCHAR(512) | False |  |  | Status message |
| parameters | JSON | False |  |  | Job parameters |
| result_path | VARCHAR(512) | True |  |  | Result directory |
| result_sha256 | VARCHAR(64) | True |  |  | Hash of result.json |
| artifact_sha256 | VARCHAR(64) | True |  |  | Hash of canonical artifact |
| runtime_manifest | JSON | True |  |  | Execution receipt / runtime |
| determinism_profile | VARCHAR(32) | True |  |  | strict/numeric/parallel/gpu_ml/canonical |
| started_at | DATETIME | True |  |  | Start timestamp |
| completed_at | DATETIME | True |  |  | Completion timestamp |
| created_by | UUID | False |  | users.id | Submitter |
| created_at | DATETIME | False |  |  | Submission timestamp |
| error_message | TEXT | True |  |  | Failure message |

### custody_records

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | Record identifier |
| record_type | VARCHAR(30) | False |  |  | `evidence_upload`, `derivative_saved`, `case_closed`, etc. |
| case_id | UUID | False |  | cases.id | Parent case |
| evidence_id | UUID | True |  | evidences.id | Related evidence |
| job_id | UUID | True |  | analysis_jobs.id | Related job |
| user_id | UUID | False |  | users.id | Actor |
| sha256_input | VARCHAR(64) | True |  |  | Input hash |
| sha256_output | VARCHAR(64) | True |  |  | Output hash |
| sha256_params | VARCHAR(64) | True |  |  | Parameters hash |
| details | JSON | True |  |  | Event details |
| previous_record_hash | VARCHAR(64) | True |  |  | Previous record hash |
| record_hash | VARCHAR(64) | False |  |  | This record hash |
| chain_sequence | INTEGER | False |  |  | Sequence in chain |
| system_signature | TEXT | True |  |  | Ed25519 signature |
| signing_key_id | VARCHAR(64) | True |  |  | Key identifier |
| timestamp | DATETIME | False |  |  | Event timestamp |

### case_closures

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | Closure record identifier |
| case_id | UUID | False |  | cases.id | Closed case |
| closure_sequence | INTEGER | False |  |  | Closure version |
| manifest_sha256 | VARCHAR(64) | False |  |  | Manifest hash |
| manifest_json | JSON | False |  |  | Closure manifest |
| signature_mode | VARCHAR(20) | False |  |  | `system`, `icp`, etc. |
| system_signature | TEXT | True |  |  | System signature |
| icp_signature_payload | TEXT | True |  |  | ICP payload |
| signed_by | UUID | False |  | users.id | Signer |
| signed_at | DATETIME | False |  |  | Signature timestamp |
| custody_record_id | UUID | True |  | custody_records.id | Linked custody record |
| accepts_additional_signatures | VARCHAR(5) | False |  |  | `true`/`false` |

### case_closure_signatures

| Column | Type | Nullable | PK | FK | Description |
|---|---|---|---|---|---|
| id | UUID | False | ✅ |  | Signature identifier |
| closure_id | UUID | False |  | case_closures.id | Parent closure |
| user_id | UUID | False |  | users.id | Signer |
| system_signature | TEXT | False |  |  | Ed25519 signature |
| signed_at | DATETIME | False |  |  | Signature timestamp |

---

## Notes

- All UUID columns use `as_uuid=True` in PostgreSQL and store as strings in SQLite.
- Soft-delete pattern: `deleted_at`/`deleted_by` columns instead of hard deletes.
- JSON columns store flexible metadata/parameters; SQLite uses native JSON type via SQLAlchemy.
