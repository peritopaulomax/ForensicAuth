# Deploy — Custódia ampliada e compartilhamento

## Ambiente

```bash
conda activate forensicauth
```

## Migração de schema

O backend em `src/backend` usa `src/backend/.env` (SQLite por padrão). Execute na **raiz do projeto**:

```bash
conda activate forensicauth
python scripts/migrate_custody_lifecycle.py
```

Se aparecer `Connection refused` na porta 5432, o script leu o `.env` da raiz (PostgreSQL). O script atualizado força `src/backend/.env`. **Alternativa:** só reinicie a API — as migrações rodam no startup:

```bash
cd src/backend
conda activate forensicauth
python -m uvicorn app.main:app --reload --port 8001
```

## Chaves Ed25519 (produção)

```bash
python scripts/generate_custody_signing_key.py
```

Variáveis no `.env` (não versionar a chave privada):

- `CUSTODY_SIGNING_KEY_ID=forensicauth-ed25519-v1`
- `CUSTODY_SIGNING_PRIVATE_KEY=` (base64 raw 32 bytes ou PEM)
- `CUSTODY_SIGNING_PUBLIC_KEY=` (opcional; derivada da privada se vazia)

Em desenvolvimento, sem variáveis, o backend gera chave efêmera na memória.

## Testes

```bash
pytest tests/unit/test_case_shares.py tests/unit/test_custody_signing.py \
  tests/unit/test_case_lifecycle.py tests/unit/test_forensic_integrity.py \
  tests/unit/test_custody.py tests/integration/test_case_shares_api.py
```

## ICP-Brasil

Reservado para fase futura: UI desabilitada; `POST /cases/{id}/close` com `signature_mode=icp_brasil` retorna HTTP 501.
