# 04-module-custody.md - Modulo de Cadeia de Custodia

## Responsabilidade Unica

Garantir a rastreabilidade, integridade e imutabilidade de evidencias **originais**, **derivadas salvas pelo usuario** e laudos, atraves de registros de auditoria encadeados com hash criptografico.

**Importante:** execucoes exploratorias de analise (tentativa e erro de parametros) **NAO** entram na cadeia. Apenas acoes forenses deliberadas do usuario.

## O que entra na cadeia (e o que NAO entra)

| Acao | Registra na cadeia? | Tipo |
|------|---------------------|------|
| Upload de evidencia original | **Sim** | `evidence_upload` |
| Exclusao (soft-delete) de evidencia | **Sim** | `evidence_deleted` |
| Exclusao de caso inteiro (perito/admin) | **Sim** | `case_deleted` — arquivos apagados; logs preservados |
| Rodar ELA/DCT/etc. para preview | **Nao** | — |
| Usuario clica "Adicionar aos derivados" / "Adicionar ao relatorio" | **Sim** | `derivative_saved` |
| Geracao de laudo PDF | **Sim** | `report_generated` |

## Tres cadeias complementares (visao do usuario)

1. **Cadeia de upload** — arquivo original, SHA-256, usuario, timestamp (futuro: assinatura do registro).
2. **Cadeia de derivacao** — insumo(s) + algoritmo + parametros → arquivo derivado salvo (proveniencia).
3. **Cadeia do derivado** — o arquivo derivado vira nova evidencia com seu proprio SHA-256 registrado.

## Interfaces Publicas

### API Endpoints

- `GET /api/v1/audit`
  - Entrada: Query params `case_id`, `user_id`, `from`, `to`, `evidence_id`, `job_id`
  - Saida: `List[CustodyRecord]` ordenado por timestamp descendente
  - Permissao: Admin (tudo), Perito (casos que criou/participa), Analista (casos designados)

- `GET /api/v1/audit/verify/{record_id}`
  - Entrada: `record_id: UUID`
  - Saida: `{valid: bool, record: CustodyRecord, computed_hash: str}`

- `GET /api/v1/audit/verify-case/{case_id}`
  - Verifica integridade da cadeia inteira do caso

- `POST /api/v1/evidences/derivatives` *(futuro)*
  - Entrada: `{job_id, artifact_filename, label?}` ou artefato + metadados do job congelado
  - Acao: salva arquivo em pasta de derivados, calcula SHA-256, cria evidencia derivada, registra `derivative_saved`

### Servico Interno (CustodyService)

```python
class CustodyService:
    def create_record(...) -> CustodyRecord:
        """Cria registro encadeado INSERT-only."""

    def verify_chain(self, case_id: UUID) -> dict:
        """Verifica integridade da cadeia do caso."""

    def recompute_job_hash(self, job_id: UUID) -> dict:
        """Reexecuta job para validar reproducibilidade de um derivado salvo."""
```

## Fluxo: Salvar derivado (exemplo ELA)

1. Perito abre evidencia, roda ELA varias vezes (preview — sem custodia).
2. Escolhe 2–3 resultados para o laudo.
3. Em cada resultado, clica **"Adicionar aos derivados"**.
4. Sistema:
   - Copia artefato para `{DERIVATIVES_DIR}/{case_id}/`
   - Calcula SHA-256 do arquivo derivado
   - Cria `Evidence` com `origin=derived`, `parent_inputs[]` (id + sha256 + role), `provenance` v1
   - Cria `CustodyRecord` tipo `derivative_saved` com:
     - `sha256_input` = hash do(s) insumo(s) (ou hash canonico da lista)
     - `sha256_output` = hash do derivado
     - `sha256_params` = hash canonico de `{technique, derivation_step, parameters, algorithm}`
     - `details` = proveniencia v1 (`parent_inputs`, `operation`, `output`) — autossuficiente para auditoria

### Proveniencia v1 (`provenance_schema_version: "1"`)

```json
{
  "provenance_schema_version": "1",
  "parent_inputs": [
    {
      "evidence_id": "uuid",
      "role": "questioned|reference_input|fingerprint|input",
      "original_filename": "3.jpg",
      "sha256": "64hex",
      "file_type": "imagem",
      "origin": "upload|derived|reference"
    }
  ],
  "operation": {
    "technique": "prnu",
    "derivation_step": "correlation_surface_C",
    "parameters": {},
    "algorithm": {"plugin": "forensic_plugin", "version": "1"},
    "source_job_id": "uuid",
    "outputs_metrics": {"pce": 42.0}
  },
  "output": {
    "evidence_id": "uuid",
    "original_filename": "prnu_superficie_C_3.html",
    "sha256": "64hex",
    "artifact_role": "prnu_correlation_surface"
  }
}
```

O mesmo bloco fica em `evidences.extra_metadata.provenance` e em `custody_records.details` ao salvar derivado.
5. Derivado aparece na aba **Derivados** do caso (agrupado por tipo: imagem, audio, etc.).

## UI prevista

- **Aba Cadeia de Custodia** — timeline de eventos registrados (upload, derivados salvos, laudos, exclusoes).
- **Aba Derivados** *(futuro)* — arquivos derivados salvos, separados por tipo, com link para proveniencia (evidencia original + job + params).

## Regras de Negocio

- **RN-CUST-01**: Tabela `custody_records` e INSERT-only.
- **RN-CUST-02**: Todo upload de evidencia gera `evidence_upload` com SHA-256 do arquivo.
- **RN-CUST-03**: Execucao de job de analise **nao** gera registro de custodia (preview exploratorio).
- **RN-CUST-04**: Salvar derivado gera `derivative_saved` com hashes de entrada, saida e parametros.
- **RN-CUST-05**: Todo laudo gerado gera `report_generated`.
- **RN-CUST-06**: Hash do registro anterior incluido no calculo do hash atual (encadeamento).
- **RN-CUST-07**: Upload futuro deve suportar assinatura do registro (Ed25519/RSA sobre `record_hash`) ou registro externo (ex.: blockchain).
- **RN-CUST-08**: A verificacao (`verify_chain`) apenas **detecta** adulteracao ou inconsistencia; a aplicacao **nao** reescreve hashes nem reencadeia registros. Novos elos usam `chain_sequence` monotona por caso na criacao (`create_record`).
- **RN-CUST-07** (implementado): Todo novo registro recebe assinatura Ed25519 do sistema sobre `record_hash` (campos `system_signature`, `signing_key_id`). A assinatura **nao** entra no payload SHA encadeado. Registros legados sem assinatura permanecem verificaveis apenas pelo hash encadeado.
- **RN-CUST-09**: Compartilhar caso gera `case_shared` com `shared_with_user_id`, `role` em `details`.
- **RN-CUST-10**: Revogar compartilhamento gera `case_unshared`.
- **RN-CUST-11**: Fechar caso gera `case_closed` e `case_closure_signed`.
- **RN-CUST-12**: Reabrir caso gera `case_reopened` referenciando `closure_sequence`.
- **RN-CUST-13**: `verify_case_forensic_integrity` valida cadeia, assinaturas, arquivos em disco, proveniencia e manifestos de fechamento.
- **RN-CUST-14** (reservado): Assinatura ICP-Brasil no fechamento — contrato futuro PKCS#7; MVP retorna 501 e UI desabilitada.

### Novos endpoints

- `GET /api/v1/audit/verify-case-forensic/{case_id}` — relatorio JSON estruturado.
- `GET /api/v1/audit/verify-case-forensic/{case_id}/report` — download JSON/HTML.
- `GET /api/v1/audit/signing-keys` — chave publica para verificacao offline.

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| Tentativa de update/delete em custody_records | Bloqueado pelo ORM / trigger |
| Corrupcao ou adulteracao na cadeia | `verify-case` retorna `valid: false` e motivo (`record_hash_mismatch`, `previous_record_hash_mismatch`, `chain_sequence_gap`); sem acao de "reparo" |
| Salvar derivado de job incompleto | 409 — job deve estar `completed` |

## Dados de Entrada/Saida

- Entrada: UUIDs, strings SHA-256, dict JSON canonico de detalhes
- Saida: `CustodyRecord` com hash encadeado
- Hash: SHA-256 hex (64 caracteres)
