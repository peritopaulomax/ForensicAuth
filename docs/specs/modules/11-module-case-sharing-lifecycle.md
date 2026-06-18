# 11-module-case-sharing-lifecycle.md — Compartilhamento e ciclo de vida do caso

## Responsabilidade

Gerenciar compartilhamento controlado de casos entre peritos, bloqueio de mutações em casos fechados, fechamento com manifesto assinado e reabertura auditada.

## Modelo `case_shares`

| Coluna | Tipo | Notas |
|--------|------|-------|
| id | UUID PK | |
| case_id | FK cases | |
| shared_with_user_id | FK users | |
| role | `viewer` \| `editor` | |
| shared_by | FK users | |
| created_at | datetime | |
| revoked_at | datetime nullable | |

## Papéis de compartilhamento

- **viewer**: leitura, audit, verificação forense, exportar relatório.
- **editor**: viewer + upload, derivados, jobs; **não** pode excluir caso, compartilhar nem fechar.

## API

- `POST /api/v1/cases/{id}/shares` — `{ user_id, role }`
- `GET /api/v1/cases/{id}/shares`
- `DELETE /api/v1/cases/{id}/shares/{share_id}`
- `GET /api/v1/cases/shared-with-me`
- `GET /api/v1/cases?scope=mine|shared|all`
- `POST /api/v1/cases/{id}/close`
- `POST /api/v1/cases/{id}/reopen`
- `POST /api/v1/cases/{id}/close/sign`

## Regras de negócio

- **RN-SHARE-01**: Apenas criador do caso ou admin pode compartilhar/revogar.
- **RN-SHARE-02**: Não compartilhar com o próprio criador; não duplicar share ativo.
- **RN-SHARE-03**: Share/revoke gera `case_shared` / `case_unshared` na cadeia.
- **RN-LIFE-01**: Caso `fechado` bloqueia upload, derivados, jobs e novo share.
- **RN-LIFE-02**: Fechar caso: só criador ou admin; assinatura padrão `system`.
- **RN-LIFE-03**: Reabrir: só criador ou admin; preserva histórico em `case_closures`.
- **RN-LIFE-04**: `signature_mode=icp_brasil` retorna HTTP 501 (stub).
- **RN-LIFE-05**: Múltiplas assinaturas de sistema no mesmo fechamento via `close/sign`.

## Conflitos

- Caso fechado: leitura e verificação permitidas; mutações → 409.
- Concorrência em PUT do caso: `expected_updated_at` opcional → 409 se divergir.
