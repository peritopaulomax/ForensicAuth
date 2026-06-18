# 12-module-case-transfer.md — Exportação e importação de casos (VCP)

## Responsabilidade

Permitir transferência forense de um caso completo entre instâncias ForensicAuth (outra instituição ou instalação standalone), com validação obrigatória antes da ingestão.

## Formato VCP (VA Case Package)

Arquivo ZIP com versão `vcp_schema_version: "1"`:

```
*.vcp.zip
├── package.json           # metadados, manifesto de arquivos, hash do pacote
├── crypto/
│   ├── signing_key_id.txt
│   └── public_key.pem     # Ed25519 da instância exportadora
├── case/
│   ├── case.json
│   ├── users.json         # usuários referenciados (stubs na importação)
│   ├── evidences.json
│   ├── custody_records.json
│   ├── closures.json
│   └── closure_signatures.json
└── files/
    └── {sha256}           # um arquivo por hash (deduplicado)
```

## API

- `POST /api/v1/cases/{id}/export` → download ZIP (permissão: acesso ao caso)
- `POST /api/v1/cases/import/validate` → multipart `.vcp.zip`, dry-run, relatório JSON
- `POST /api/v1/cases/import` → multipart + `confirm=true`, ingestão após validação OK

## Regras de negócio

- **RN-XFER-01**: Export inclui binários, metadados, cadeia completa, fechamentos e chave pública de assinatura.
- **RN-XFER-02**: Validação offline verifica hashes de arquivos, cadeia SHA-256, assinaturas Ed25519 (chave exportada) e manifestos de fechamento.
- **RN-XFER-03**: Importação preserva UUIDs originais (caso, evidências, registros) para manter integridade criptográfica da cadeia.
- **RN-XFER-04**: Usuários ausentes na instância destino são criados como stubs inativos (`imported_stub=true`).
- **RN-XFER-05**: Conflito de `protocol_number` ou `case_id` **ativo** → rejeitar importação (409). Caso **soft-deleted** (tombstone) com mesmo `case_id` → permitir: purge do tombstone com snapshot em `case_imported.replaced_tombstone`, depois ingestão.
- **RN-XFER-06**: Após importação bem-sucedida, registra `case_imported` na cadeia local (novo elo, usuário importador).
- **RN-XFER-07**: Não re-assina registros históricos na importação.

## Validação (dry-run)

Ordem: integridade ZIP → arquivos → cadeia → assinaturas → fechamentos → conflitos de ID/protocolo.

## Segurança

- Apenas usuários autenticados; import exige papel que pode criar casos (perito/admin).
- Pacote não contém chaves privadas.
