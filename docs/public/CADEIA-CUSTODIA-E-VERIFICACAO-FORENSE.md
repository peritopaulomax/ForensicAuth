# Cadeia de custódia, assinaturas e verificação forense

Documento técnico para peritos, auditores e administradores que precisam entender **como o ForensicAuth garante rastreabilidade**, **o que cada verificação faz** e **como ataques ou adulterações são detectados**.

---

## 1. Objetivo da cadeia de custódia no ForensicAuth

A cadeia de custódia responde a três perguntas forenses:

1. **O que aconteceu?** — upload, derivado salvo, laudo, compartilhamento, fechamento, exclusão, importação VCP, etc.
2. **Quem fez?** — usuário autenticado (`user_id`) no momento do evento.
3. **Com que integridade?** — hashes SHA-256 dos bytes envolvidos + encadeamento criptográfico + assinatura Ed25519 da instalação.

Registros são **somente inserção** (append-only). A aplicação não reescreve elos antigos em operação normal.

---

## 2. O que entra (e o que não entra) na cadeia

| Ação do usuário | Registra na cadeia? | Tipo típico |
|-----------------|---------------------|-------------|
| Upload de evidência original | Sim | `evidence_upload` |
| Exclusão de evidência (soft-delete) | Sim | `evidence_deleted` |
| Exclusão de caso | Sim | `case_deleted` |
| Executar análise para preview | **Não** | — |
| Salvar derivado ao caso | Sim | `derivative_saved` |
| Gerar laudo PDF | Sim | `report_generated` |
| Compartilhar / revogar caso | Sim | `case_shared` / `case_unshared` |
| Fechar / reabrir caso | Sim | `case_closed` / `case_reopened` |
| Exportar / importar VCP | Sim | `case_exported` / `case_imported` |

**Por quê:** tentativas de parâmetros (ELA, PRNU, etc.) são exploratórias. Só o ato **deliberado** de incorporar um resultado ao caso gera prova de custódia.

---

## 3. Anatomia de um registro (`custody_records`)

Cada elo contém:

| Campo | Função |
|-------|--------|
| `id` | UUID único do registro |
| `record_type` | Classificação do evento |
| `case_id` | Caso ao qual pertence |
| `evidence_id` / `job_id` | Referências opcionais |
| `user_id` | Autor da ação |
| `sha256_input` | Hash de entrada (ex.: arquivo original) |
| `sha256_output` | Hash de saída (ex.: derivado) |
| `sha256_params` | Hash canônico de parâmetros/algoritmo |
| `details` | JSON (proveniência, metadados, snapshot de exclusão, etc.) |
| `chain_sequence` | Posição 1…N no caso |
| `previous_record_hash` | Hash do elo anterior (null no genesis) |
| `record_hash` | SHA-256 do payload canônico deste elo |
| `system_signature` | Assinatura Ed25519 sobre `record_hash` |
| `signing_key_id` | Identificador da chave da instalação |
| `timestamp` | Momento UTC do registro |

---

## 4. Cálculo do `record_hash` (encadeamento SHA-256)

O hash de cada registro é **determinístico**. O serviço monta um objeto JSON com campos fixos (ordenados), serializa de forma canônica e aplica SHA-256:

```
payload = {
  record_type, case_id, evidence_id, job_id, user_id,
  sha256_input, sha256_output, sha256_params,
  details (JSON normalizado),
  previous_record_hash,
  chain_sequence,
  timestamp (ISO)
}
record_hash = SHA256(JSON_canônico(payload))
```

O **primeiro** registro do caso (genesis) tem `previous_record_hash = null`. Cada elo seguinte aponta para o `record_hash` do anterior.

### Propriedade de detecção

Se um atacante alterar no banco:

- o texto de `details`,
- um `sha256_*`,
- a ordem (`chain_sequence`),
- ou o link `previous_record_hash`,

então o `record_hash` recalculado **não coincide** com o armazenado → falha em **Verificar cadeia**.

Alterar um elo **no meio** também invalida todos os elos posteriores (que referenciam hash errado).

---

## 5. Assinatura Ed25519 (`system_signature`)

Após calcular `record_hash`, a instalação assina esse digest com **Ed25519** (chave privada em `CUSTODY_SIGNING_PRIVATE_KEY`).

| Aspecto | Detalhe |
|---------|---------|
| O que é assinado | Apenas o `record_hash` (64 hex), não o JSON inteiro |
| O que prova | Que **esta instalação** reconheceu aquele digest naquele momento |
| Chave pública | Exportada em VCP (`crypto/public_key.pem`) para verificação offline |
| Registros antigos | Podem existir sem assinatura (migração); verificação forense emite aviso |

**Ataque:** modificar `record_hash` sem refazer assinatura → assinatura inválida na **Verificação forense**.

**Ataque:** refazer assinatura com outra chave → só funciona se o atacante controlar a chave privada da instalação (comprometimento de segredo).

---

## 6. Verificar cadeia vs Verificação forense

### 6.1 Verificar cadeia (`verify_chain`)

Escopo: **integridade lógica do diário digital** no banco.

Verifica:

1. Estrutura — genesis único, sem registros órfãos.
2. Sequência — `chain_sequence` contínua de 1 até N.
3. Encadeamento — cada `previous_record_hash` = `record_hash` do elo anterior.
4. Digest — `record_hash` recalculado = valor armazenado.

**Não verifica:** existência de arquivos no disco, assinaturas Ed25519, manifestos de fechamento.

Uso: checagem rápida após operação ou suspeita de tampering no log.

### 6.2 Verificação forense (`verify_case_forensic_integrity`)

Escopo: **auditoria ampliada do caso**. Só retorna `valid: true` se **tudo** abaixo passar:

| Bloco | Verificação |
|-------|-------------|
| Cadeia | Resultado de `verify_chain` |
| Assinaturas | Ed25519 de cada registro com `system_signature` |
| Arquivos | Evidências ativas: arquivo existe; SHA-256 no disco = SHA na base; coerência com evento de upload |
| Proveniência | Metadados de derivados vs registros `derivative_saved` |
| Fechamentos | Manifesto recomposto = `manifest_sha256`; assinaturas primárias e adicionais |

Uso: laudo, auditoria externa, decisão de confiar no caso antes de exportar VCP.

### 6.3 Verificar registro (unitário)

Valida um único elo: hash + assinatura daquele registro.

---

## 7. Proveniência de derivados (v1)

Ao salvar um derivado, o sistema registra em `details` e em `evidence.extra_metadata`:

- **Insumos** (`parent_inputs`): evidence_id, sha256, papel (questioned, reference, etc.).
- **Operação** (`operation`): técnica, parâmetros, job de origem.
- **Saída** (`output`): sha256 e nome do arquivo derivado.

A verificação forense compara proveniência na evidência vs registro de custódia. Divergência indica adulteração de metadados **após** o salvamento.

---

## 8. Fechamento de caso e manifesto

Ao fechar um caso:

1. Gera-se um **manifesto JSON** (snapshot do estado forense acordado).
2. Calcula-se `manifest_sha256`.
3. Assina-se o manifesto (Ed25519).
4. Registra-se na cadeia (`case_closed`, `case_closure_signed`).

Reabertura gera novo elo auditado. Manifestos antigos permanecem verificáveis.

---

## 9. Cenários de ataque e como o sistema responde

| Cenário | Detecção |
|---------|----------|
| Editar registro antigo no PostgreSQL | `verify_chain` → `record_hash_mismatch` ou `previous_record_hash_mismatch` |
| Reordenar ou apagar elos | `chain_sequence_gap` ou `unlinked_custody_records` |
| Trocar bytes de evidência no disco | Verificação forense → `files.hash_mismatch` |
| Apagar arquivo mantendo metadado | Verificação forense → `files.missing` |
| Falsificar derivado sem proveniência coerente | `provenance.issues` |
| Adicionar registro falso sem chave privada | Hash/sequência quebram; assinatura ausente ou inválida |
| Importar VCP adulterado | Validação VCP falha (hashes, cadeia, assinaturas) antes de gravar |
| Reimportar caso sem autorização | Conflito de protocolo/ID; tombstone exige purge auditado |

### Limitações honestas

- **Comprometimento root + chave Ed25519:** atacante com DB, disco e chave privada pode fabricar elos **aparentemente** válidos. Mitigação: HSM, segregação de duties, backup WORM, auditoria externa.
- **PostgreSQL sem REVOKE:** imutabilidade depende da aplicação; recomenda-se política de banco em produção.
- **Preview não custodiado:** artefatos em `results/` não são prova até o usuário salvar derivado.

---

## 10. Imutabilidade técnica

- **SQLite (dev):** trigger bloqueia UPDATE em `custody_records`.
- **PostgreSQL (prod):** recomenda-se `REVOKE UPDATE, DELETE` na tabela ou equivalente.
- **Exceções controladas:** importação VCP e ferramentas administrativas usam janelas explícitas (`_allow_custody_record_updates`) — não disponíveis ao usuário comum.

---

## 11. Exportação VCP e custódia

O **Verification Case Package (VCP)** transporta a cadeia **com hashes e assinaturas originais** (sem re-assinar). A instância destino valida com a chave pública exportada e grava um novo elo `case_imported` referenciando tombstone substituído, se houver.

Ver: [PACOTE-VERIFICATION-CASE-PACKAGE.md](PACOTE-VERIFICATION-CASE-PACKAGE.md).

---

## 12. APIs relacionadas

| Endpoint | Função |
|----------|--------|
| `GET /api/v1/audit/verify-case/{case_id}` | Verificar cadeia |
| `GET /api/v1/audit/verify-case-forensic/{case_id}` | Verificação forense (JSON) |
| `GET /api/v1/audit/verify-case-forensic/{case_id}/report` | Relatório HTML/JSON |
| `GET /api/v1/audit/verify/{record_id}` | Verificar um registro |
| `GET /api/v1/audit/signing-keys` | Chave pública para verificação offline |

---

## 13. Resumo para o perito

- **Cadeia** = diário encadeado por hash; detecta adulteração do log.
- **Assinatura** = carimbo criptográfico da instalação sobre cada digest.
- **Verificação forense** = cadeia + assinaturas + arquivos reais + proveniência + fechamentos.
- **Confiança operacional** = chave Ed25519 persistente, backup, TLS, controle de acesso e política de imutabilidade no banco.
