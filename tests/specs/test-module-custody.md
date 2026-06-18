# test-module-custody.md - Especificacao de Testes: Cadeia de Custodia

## Testes Unitarios

### TU-CUST-001: Criacao de registro de custodia
- **Funcao**: `CustodyService.create_record(...)`
- **Setup**: Caso existente no banco
- **Entrada**: record_type="evidence_upload", case_id, evidence_id, user_id, sha256_input="abc123..."
- **Saida esperada**: CustodyRecord com record_hash calculado
- **Verificacoes**:
  - `previous_record_hash` e null (primeiro registro)
  - `record_hash` tem 64 caracteres hex
  - `timestamp` preenchido

### TU-CUST-002: Encadeamento de registros
- **Funcao**: `CustodyService.create_record(...)`
- **Setup**: Caso com 1 registro existente (hash=X)
- **Entrada**: Segundo registro do mesmo caso
- **Saida esperada**: CustodyRecord com `previous_record_hash` = X
- **Verificacoes**:
  - `record_hash` inclui X na concatenacao
  - Hash do segundo registro != hash do primeiro

### TU-CUST-003: Verificacao de cadeia valida
- **Funcao**: `CustodyService.verify_chain(case_id)`
- **Setup**: Caso com 3 registros validos
- **Saida esperada**: `{valid: true, records_checked: 3, first_invalid: null}`

### TU-CUST-004: Deteccao de tampering
- **Funcao**: `CustodyService.verify_chain(case_id)`
- **Setup**: Caso com 3 registros, mas o segundo foi manualmente alterado no banco (simulando ataque)
- **Saida esperada**: `{valid: false, records_checked: 3, first_invalid: record_2_id}`
- **Verificacoes**: Identifica exatamente qual registro foi comprometido

### TU-CUST-005: Imutabilidade (INSERT-only)
- **Funcao**: Tentar UPDATE em custody_records
- **Setup**: Registro existente
- **Acao**: `session.execute(update(CustodyRecord).values(...))`
- **Saida esperada**: Falha ou nenhuma linha afetada (depende da implementacao: trigger, permissao, ou ORM read-only)

### TU-CUST-006: Reexecucao reprodutivel
- **Funcao**: `CustodyService.recompute_job_hash(job_id)`
- **Setup**: Job completado com result_sha256="hash_original"
- **Saida esperada**: `{reproducible: true, original_hash: "hash_original", new_hash: "hash_original"}`
- **Verificacoes**: novo_hash == hash_original

### TU-CUST-007: Reexecucao nao reprodutivel (tampered)
- **Setup**: Job completado, mas artefato no disco foi alterado
- **Saida esperada**: `{reproducible: false, original_hash: "hash_original", new_hash: "hash_diferente"}`

### TU-CUST-008: Assinatura Ed25519 em registro novo
- **Verificacoes**: `system_signature` e `signing_key_id` preenchidos; `verify_signature` retorna true.

### TU-CUST-009: Assinatura invalida apos adulteracao
- **Setup**: Alterar `record_hash` no banco (SQLite sem trigger em teste controlado)
- **Saida**: `signature_valid: false`

### TU-CUST-010: Verificacao forense — arquivo adulterado
- **Funcao**: `ForensicIntegrityService.verify_case_forensic_integrity`
- **Saida**: `valid: false`, `files.hash_mismatch` preenchido

### TU-CUST-011: Verificacao forense — proveniencia inconsistente
- **Saida**: `provenance.issues` nao vazio

## Testes de Integracao

### TI-CUST-001: Upload gera registro automatico
- **Endpoint**: POST /api/v1/evidence
- **Fluxo**: Faz upload de arquivo
- **Verificacoes**:
  - Banco contem CustodyRecord do tipo evidence_upload
  - SHA-256 do arquivo bate com sha256_input do registro
  - Cadeia verificavel

### TI-CUST-002: Permissao de auditoria
- **Endpoint**: GET /api/v1/audit
- **Fluxo**:
  1. Admin consulta audit de caso qualquer → 200
  2. Perito consulta audit de caso proprio → 200
  3. Perito consulta audit de caso alheio → 403
  4. Analista consulta audit de caso designado → 200
  5. Analista consulta audit de caso nao designado → 403

## Mocks/Stubs

- Mock de AnalysisJob para testes de reexecucao
- Mock de adapter que retorna resultado deterministico (mesmo hash sempre)
