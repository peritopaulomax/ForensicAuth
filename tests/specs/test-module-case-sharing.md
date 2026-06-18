# test-module-case-sharing.md — Testes: compartilhamento e ciclo de vida

## Testes unitários

### TU-SHARE-001: Query inclui share ativo
- `cases_query_for_user` retorna caso compartilhado não revogado.

### TU-SHARE-002: Share revogado excluído
- Após `revoked_at`, caso não aparece para destinatário.

### TU-SHARE-003: assert_can_share_case
- Criador OK; terceiro → 403.

### TU-LIFE-001: assert_case_not_closed
- Caso fechado → HTTPException 409.

### TU-LIFE-002: Manifest SHA estável
- `ForensicManifestBuilder` produz mesmo hash em duas chamadas.

## Testes de integração

### TI-SHARE-001: Compartilhar e listar
- Perito A compartilha com B (editor); B em `shared-with-me`; C → 403.

### TI-SHARE-002: Custódia case_shared
- POST share gera registro `case_shared`.

### TI-LIFE-001: Fechar bloqueia upload
- POST close → upload → 409.

### TI-LIFE-002: Reabrir libera upload
- reopen → upload OK.

### TI-LIFE-003: ICP stub 501
- close com `icp_brasil` → 501.
