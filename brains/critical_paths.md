# Critical Paths — ForensicAuth

## Path 1: Upload (Tier 0)

```text
POST /evidences/upload
  → _require_case_mutable
  → EvidenceService.upload_evidence
      → valida tamanho/tipo (max 500MB)
      → calcula SHA-256
      → salva arquivo → cria Evidence
  → CustodyService.create_record("evidence_upload")
```

**Deps:** PostgreSQL, Filesystem, Ed25519 | **Risco:** caso fechado não bloqueia upload

## Path 2: Análise (Tier 0)

```text
POST /analysis
  → JobService.submit_job
      → resolve técnica/aliases
      → valida plugin e parâmetros
      → cria AnalysisJob (pending)
  → run_job_in_background
      → JobRunner decide Celery/thread
      → queue_for_technique (CPU/GPU)
  → Celery task
      → gpu_distributed_lock + ml_gpu_job_slot (se GPU)
      → JobService.run_job
          → plugin.analyze → stage artifacts → runtime_manifest → result.json → result_sha256 + artifact_sha256
```

> Não gera `CustodyRecord` no ciclo de vida do job no código atual (apenas upload, derivado, fechamento, compartilhamento).

**Exemplo `synthetic_image_detection`:**
- Ensemble ativo: 2 modelos HuggingFace + B-Free + Corvi2023/CLIP-D.
- Modelos carregados lazy; output é tabela de scores individuais (thresholds `0.66/0.34`).
- CLIDE, SAFE, Effort, XGBoost, NPR são legados/testados e **não fazem parte** do ensemble atual.
- `torch.load` inseguro no NPR legado; pesos sem checksums SHA-256.

**Deps:** Redis, Celery, Plugin, GPU/CPU, Filesystem, PostgreSQL
**Riscos:** GPU singleton, caso fechado não bloqueia em todos os endpoints, tipo de mídia não validado em `submit_job`, pesos sem checksums

## Path 3: Derivado (Tier 1)

```text
POST /evidences/derivatives
  → DerivativeService.save_from_job
      → materializa artefato → calcula SHA-256
      → provenance snapshot → cria Evidence derivada
      → CustodyService.create_record("derivative_saved")
```

**Deps:** Filesystem, PostgreSQL, Ed25519

## Path 4: Verificação Forense (Tier 0)

```text
GET /audit/verify-case-forensic/{case_id}
  → ForensicIntegrityService
      → verify_chain → assinaturas → arquivos vs hashes → provenance → fechamentos
```

**Deps:** PostgreSQL, Filesystem, Ed25519 | **Risco:** chave dev efêmera

## Path 5: Login (Tier 0)

```text
POST /auth/login
  → AuthService.authenticate → bcrypt → JWT HS256
```

**Deps:** PostgreSQL, SECRET_KEY | **Riscos:** SECRET_KEY padrão, token em localStorage

## Path 6: Fechamento de Caso (Tier 1)

```text
POST /cases/{id}/close
  → CaseLifecycleService.close_case
      → build manifesto → manifest_sha256 → cria CaseClosure
      → CustodyService.create_record("case_closed")
  → /close/sign → status = fechado
```

**Deps:** PostgreSQL, Ed25519 | **Risco:** caso fechado ainda aceita uploads/jobs

## Priorização

1. Upload (0) | 2. Análise (0) | 3. Login (0) | 4. Verificação forense (0) | 5. Fechamento (1) | 6. Derivado (1)

## O que para o sistema

- PostgreSQL → tudo
- Redis → jobs e lock GPU
- Filesystem → upload/download/resultados
- GPU → ML cai para CPU
- Ed25519 → cadeia perde valor probatório
