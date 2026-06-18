# Verification Case Package (VCP) — estrutura e funcionamento

O **Verification Case Package (VCP)** é o formato de transferência forense entre instalações **ForensicAuth**. É um arquivo ZIP (convenção de nome: `caso-{protocolo}.vcp.zip`) que contém metadados, cadeia de custódia, fechamentos, chave pública de assinatura e **todos os binários** referenciados, endereçados por SHA-256.

**Versão de schema atual:** `vcp_schema_version: "1"`

---

## 1. Para que serve

| Objetivo | Como o VCP atende |
|----------|-------------------|
| Transferir caso completo para outro órgão | UUIDs, cadeia e hashes preservados |
| Auditoria offline | Validar sem gravar (`validate`) |
| Disaster recovery | Restaurar caso em nova instalação |
| Substituir tombstone | Reimportar caso excluido (soft-delete) com audit trail |

O pacote **não contém chaves privadas** Ed25519.

---

## 2. Árvore de arquivos do ZIP

```
nome-do-caso.vcp.zip
├── package.json                    # Manifesto do pacote
├── crypto/
│   ├── signing_key_id.txt          # ID da chave exportadora
│   └── public_key.pem              # Chave pública Ed25519 (PEM)
├── case/
│   ├── case.json                   # Metadados do caso
│   ├── users.json                  # Usuários referenciados
│   ├── evidences.json              # Metadados de evidências
│   ├── custody_records.json        # Cadeia completa (ordem por chain_sequence)
│   ├── analysis_jobs.json          # (Opcional) Jobs referenciados na cadeia
│   ├── closures.json               # Fechamentos do caso
│   └── closure_signatures.json     # Assinaturas adicionais de fechamento
└── files/
    └── {sha256_hex_64_chars}       # Um arquivo por hash único (sem extensão)
```

### Convenções

- JSON em UTF-8, serialização **canônica** (chaves ordenadas) onde aplicável.
- Arquivos em `files/` são nomeados **somente** pelo SHA-256 de 64 caracteres hex.
- O mesmo hash aparece uma vez no ZIP, mesmo que várias evidências compartilhem bytes (deduplicação).

---

## 3. `package.json`

Manifesto raiz do pacote.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `vcp_schema_version` | string | Deve ser `"1"` |
| `exported_at` | ISO 8601 UTC | Momento da exportação |
| `exported_by` | UUID | Usuário que exportou |
| `exported_by_username` | string | Login do exportador |
| `origin` | object | `app_name`, `app_version`, `hostname` da instância origem |
| `case_id` | UUID | ID do caso exportado |
| `protocol_number` | string | Protocolo forense |
| `file_manifest` | object | Mapa `{ sha256: sha256_verificado_no_zip }` para cada entrada em `files/` |
| `package_sha256` | string | SHA-256 do JSON do pacote **sem** este campo (integridade do manifesto) |

**Validação:** recalcula hash de cada arquivo em `files/` e compara com `file_manifest`; verifica `package_sha256`.

---

## 4. `crypto/`

### `signing_key_id.txt`

Texto plano, uma linha — identificador lógico da chave (ex.: `forensicauth-ed25519-v1`). Corresponde a `signing_key_id` nos registros de custódia.

### `public_key.pem`

Chave pública Ed25519 em PEM. Usada na importação/validação para verificar `system_signature` de cada registro e fechamento **como na origem**, sem confiar na chave da instância destino.

---

## 5. `case/case.json`

Snapshot do caso no momento da exportação.

| Campo | Descrição |
|-------|-----------|
| `id` | UUID (preservado na importação) |
| `protocol_number` | Identificador único de negócio |
| `inquiry_number` / `process_number` | Referências processuais (opcional) |
| `title` / `description` | Texto descritivo |
| `status` | `aberto`, `fechamento_pendente`, `fechado` |
| `created_by` / `assigned_to` | UUIDs de usuários |
| `created_at` / `updated_at` | Timestamps ISO |

**Importação:** recria linha em `cases` com os mesmos UUIDs. Conflito se já existir caso **ativo** com mesmo `id` ou `protocol_number`.

---

## 6. `case/users.json`

Array de usuários **referenciados** (criador, uploaders, signatários, etc.).

| Campo | Descrição |
|-------|-----------|
| `id` | UUID |
| `username` | Login |
| `email` | E-mail |
| `role` | `admin`, `perito`, `analista` |

**Importação:** se UUID não existir na instância destino, cria **stub** inativo (`imported_stub`) com username/email ajustados em caso de colisão. Preserva `user_id` nos registros de custódia.

---

## 7. `case/evidences.json`

Array de evidências do caso (inclui referenciadas na cadeia, inclusive soft-deleted na origem quando aplicável).

| Campo | Descrição |
|-------|-----------|
| `id` | UUID da evidência |
| `case_id` | UUID do caso |
| `filename` / `original_filename` | Nomes de arquivo |
| `file_size` | Bytes |
| `file_type` | `imagem`, `audio`, `video`, `pdf` |
| `mime_type` | MIME (opcional) |
| `sha256` | Hash do conteúdo — chave em `files/` |
| `extra_metadata` | JSON (proveniência, flags, etc.) |
| `uploaded_by` | UUID usuário |
| `created_at` | ISO |
| `storage_kind` | `upload` ou `derivative` — define pasta destino na importação |

**Importação:** extrai `files/{sha256}` para `UPLOAD_DIR/{case_id}/` ou `DERIVATIVES_DIR/{case_id}/`.

---

## 8. `case/custody_records.json`

Array com **todos** os registros de custódia do caso, ordem lógica por `chain_sequence`.

| Campo | Descrição |
|-------|-----------|
| `id` | UUID do registro |
| `record_type` | Ex.: `evidence_upload`, `derivative_saved`, `case_closed`, `case_deleted`, … |
| `case_id` | UUID |
| `evidence_id` / `job_id` | FKs opcionais |
| `user_id` | Autor |
| `sha256_input` / `sha256_output` / `sha256_params` | Hashes forenses |
| `details` | JSON livre (proveniência, snapshots, etc.) |
| `previous_record_hash` | Elo anterior (null no genesis) |
| `record_hash` | Digest encadeado |
| `chain_sequence` | Inteiro 1…N |
| `system_signature` | Ed25519 (hex/base64 conforme armazenado) |
| `signing_key_id` | ID da chave na origem |
| `timestamp` | ISO |

**Importação:** insere registros **sem recalcular** hashes ou re-assinar (RN-XFER-07). Adiciona elo local `case_imported` após sucesso.

**Validação:** executa equivalente a `verify_chain` + verificação de assinaturas com `public_key.pem` do pacote.

---

## 9. `case/analysis_jobs.json` (opcional)

Presente quando a cadeia referencia `job_id`. Permite restaurar jobs reais em vez de stubs.

| Campo | Descrição |
|-------|-----------|
| `id` | UUID do job |
| `evidence_id` | Evidência analisada |
| `technique` | Nome da técnica |
| `status` | Estado na exportação |
| `parameters` | JSON de parâmetros |
| `result_path` / `result_sha256` | Saída (opcional) |
| `created_by` / `created_at` | Autoria |

Pacotes antigos sem este arquivo: importação cria **stubs** mínimos para satisfazer FK da cadeia.

---

## 10. `case/closures.json`

Histórico de fechamentos do caso.

| Campo | Descrição |
|-------|-----------|
| `id` | UUID |
| `case_id` | UUID |
| `closure_sequence` | Número sequencial do fechamento |
| `manifest_sha256` | Hash do manifesto |
| `manifest_json` | Conteúdo do manifesto |
| `signature_mode` | `system` (ICP-Brasil reservado) |
| `system_signature` | Assinatura Ed25519 do manifesto |
| `signed_by` | UUID |
| `signed_at` | ISO |
| `custody_record_id` | Elo de custódia associado |
| `accepts_additional_signatures` | Flag |

---

## 11. `case/closure_signatures.json`

Assinaturas adicionais vinculadas a fechamentos (co-assinaturas).

| Campo | Descrição |
|-------|-----------|
| `id` | UUID |
| `closure_id` | Fechamento |
| `user_id` | Signatário |
| `system_signature` | Assinatura sobre `manifest_sha256` |
| `signed_at` | ISO |

---

## 12. `files/{sha256}`

Conteúdo binário bruto.

- Nome = SHA-256 do conteúdo (64 hex).
- Validado contra `file_manifest` em `package.json` e contra `evidences[].sha256`.
- Deduplicação: um hash, um arquivo no ZIP.

---

## 13. Fluxo de exportação (servidor)

1. Verifica permissão de acesso ao caso.
2. Coleta caso, evidências (incl. referenciadas na cadeia), registros, fechamentos, jobs, usuários.
3. Monta JSON canônicos e manifesto de arquivos.
4. Empacota ZIP + registra evento `case_exported` na cadeia local.
5. Envia arquivo ao cliente HTTP.

---

## 14. Fluxo de validação (`POST .../import/validate`)

Ordem típica:

1. Integridade do ZIP e schema `vcp_schema_version`.
2. `package_sha256` e `file_manifest` vs bytes em `files/`.
3. Cadeia SHA-256 (`chain_sequence`, encadeamento, digests).
4. Assinaturas Ed25519 com chave do pacote.
5. Manifestos e assinaturas de fechamento.
6. Conflitos com base destino (caso/protocolo ativo; tombstone substituível).

Retorno: relatório JSON (`valid`, `issues`, contagens de arquivos/cadeia, `replaceable_tombstone`).

**Não grava** no banco.

---

## 15. Fluxo de importação (`POST .../import?confirm=true`)

1. Repete validação; aborta se inválido.
2. Se tombstone com mesmo `case_id`: purge auditado (remove dados operacionais antigos).
3. Cria stubs de usuários ausentes.
4. Insere caso, evidências (extrai binários), jobs/stubs, registros, fechamentos.
5. Registra `case_imported` com metadados (`source_origin`, `package_sha256`, `replaced_tombstone`).
6. Executa `verify_chain` pós-commit.

---

## 16. Regras de negócio (resumo)

| ID | Regra |
|----|-------|
| RN-XFER-01 | Export inclui binários, cadeia, fechamentos e chave pública |
| RN-XFER-02 | Validação verifica hashes, cadeia, assinaturas e fechamentos |
| RN-XFER-03 | UUIDs originais preservados |
| RN-XFER-04 | Usuários ausentes → stubs inativos |
| RN-XFER-05 | Conflito com caso ativo → 409; tombstone → substituição auditada |
| RN-XFER-06 | Elo `case_imported` na instância destino |
| RN-XFER-07 | Não re-assina registros históricos |

---

## 17. Endpoints HTTP

| Método | Rota | Função |
|--------|------|--------|
| POST | `/api/v1/cases/{id}/export` | Download do `.vcp.zip` |
| POST | `/api/v1/cases/import/validate` | Multipart file — dry-run |
| POST | `/api/v1/cases/import?confirm=true` | Importação após validação OK |

Requer autenticação JWT. Import exige perfil que pode criar casos (perito/admin).

---

## 18. Boas práticas operacionais

- Exporte **após** verificação forense verde quando possível.
- Armazene VCP em mídia com hash verificado (SHA-256 do arquivo ZIP).
- Na importação, confirme protocolo e `case_id` no relatório antes de `confirm=true`.
- Mantenha backup da chave privada da instância **exportadora** separado do pacote (pacote só traz pública).
- Para pacotes grandes (&gt;500 MB), configure timeout e `client_max_body_size` no nginx.

---

## 19. Glossário rápido

| Termo | Significado |
|-------|-------------|
| **VCP** | Verification Case Package — ZIP forense versionado |
| **Tombstone** | Caso soft-deleted; protocolo renomeado; cadeia preservada |
| **Stub** | Usuário/job/evidência mínimo criado só para integridade referencial |
| **Manifesto** | JSON em `package.json` + mapa de hashes de arquivos |
| **Genesis** | Primeiro elo da cadeia (`previous_record_hash` nulo) |

---

**Ver também:** [Cadeia de custódia](CADEIA-CUSTODIA-E-VERIFICACAO-FORENSE.md) · [Instalação](INSTALACAO-PRODUCAO-LINUX.md) · [Arquitetura](arquitetura-forensicauth.html)
