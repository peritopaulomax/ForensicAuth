# test-module-case-transfer.md

## TU-XFER-001: Export gera VCP válido
- **Função**: `CaseTransferService.export_case`
- **Verificações**: ZIP contém package.json, case/*.json, files/{sha256}, crypto/public_key.pem

## TU-XFER-002: Validate pacote exportado
- **Função**: `CaseTransferService.validate_package`
- **Verificações**: `valid=true`, cadeia OK, assinaturas OK (se presentes)

## TU-XFER-003: Import roundtrip
- **Cenário**: export → remover caso do DB → import
- **Verificações**: caso restaurado, evidência com mesmo sha256, verify_chain OK

## TU-XFER-004: Import rejeita protocolo duplicado
- **Verificações**: HTTP 409, caso existente intacto

## TU-XFER-005: Validate detecta arquivo adulterado
- **Verificações**: `valid=false`, `files.hash_mismatch` não vazio
