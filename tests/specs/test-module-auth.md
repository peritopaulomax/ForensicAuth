# test-module-auth.md - Especificacao de Testes: Autenticacao

## Testes Unitarios

### TU-AUTH-001: Login com credenciais validas
- **Funcao**: `AuthService.authenticate(username, password)`
- **Entrada**: username="perito01", password="Senha1234"
- **Setup**: Usuario existente no banco com bcrypt hash de "Senha1234"
- **Saida esperada**: Objeto User (sem password) + token JWT valido
- **Verificacoes**:
  - Token contem claim `sub` = user_id
  - Token contem claim `role` = "perito"
  - Token nao expirado

### TU-AUTH-002: Login com senha incorreta
- **Funcao**: `AuthService.authenticate(username, password)`
- **Entrada**: username="perito01", password="Errada9999"
- **Setup**: Usuario existente
- **Saida esperada**: Lanca excecao `AuthenticationError`
- **Verificacoes**: Mensagem = "Usuario ou senha incorretos" (nao revela qual campo esta errado)

### TU-AUTH-003: Login com usuario inativo
- **Funcao**: `AuthService.authenticate(username, password)`
- **Entrada**: username="inativo01", password="Senha1234"
- **Setup**: Usuario existente com is_active=false
- **Saida esperada**: Lanca excecao `AuthenticationError`
- **Verificacoes**: HTTP 401, "Usuario inativo"

### TU-AUTH-004: Hash de senha com bcrypt
- **Funcao**: `AuthService.hash_password(password)`
- **Entrada**: password="Senha1234"
- **Saida esperada**: String hasheada (60 chars, prefixo $2b$)
- **Verificacoes**:
  - Hash diferente da senha em plain text
  - `bcrypt.checkpw("Senha1234", hash)` retorna True
  - `bcrypt.checkpw("Errada", hash)` retorna False

### TU-AUTH-005: Validacao de forca de senha
- **Funcao**: `AuthService.validate_password_strength(password)`
- **Casos**:
  - "abc" → False (menor que 8)
  - "abcdefgh" → False (sem maiuscula)
  - "Abcdefgh" → False (sem numero)
  - "Abcdefg1" → True
- **Saida esperada**: Tupla (bool, mensagem_erro)

### TU-AUTH-006: Registro por Admin
- **Funcao**: `AuthService.register(data, current_user)`
- **Entrada**: dados de novo usuario, current_user com role="admin"
- **Saida esperada**: Objeto User criado
- **Verificacoes**: Senha hasheada no banco, nunca em plain text

### TU-AUTH-007: Registro negado para nao-Admin
- **Funcao**: `AuthService.register(data, current_user)`
- **Entrada**: dados de novo usuario, current_user com role="perito"
- **Saida esperada**: Lanca excecao `PermissionDenied`
- **Verificacoes**: HTTP 403

## Testes de Integracao

### TI-AUTH-001: Endpoint de login completo
- **Endpoint**: POST /api/v1/auth/login
- **Setup**: Usuario no banco
- **Fluxo**:
  1. Envia JSON com username e password corretos
  2. Recebe 200 + token + dados do usuario
  3. Usa token no header Authorization
  4. GET /api/v1/auth/me retorna dados do usuario

### TI-AUTH-002: Endpoint de login com erro
- **Endpoint**: POST /api/v1/auth/login
- **Fluxo**:
  1. Envia senha errada
  2. Recebe 401
  3. Envia token expirado no /auth/me
  4. Recebe 401

## Mocks/Stubs

- Banco SQLite em memoria para testes unitarios
- Nenhuma chamada externa necessaria
