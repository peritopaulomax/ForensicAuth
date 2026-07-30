# test-module-auth.md - Especificacao de Testes: Autenticacao

## Testes Unitarios

### TU-AUTH-001: Login com credenciais validas
- **Funcao**: `AuthService.authenticate(username, password)`
- **Entrada**: username="perito01", password="Senha1234"
- **Setup**: Usuario existente no banco com bcrypt hash de "Senha1234"
- **Saida esperada**: Objeto User (sem password) + access JWT valido + refresh opaco + expires_in
- **Verificacoes**:
  - Access contem claim `sub` = user_id
  - Access contem claim `role` = "perito"
  - Access contem claim `type` = "access"
  - Access nao expirado
  - Refresh nao vazio; hash persistido em `refresh_tokens`

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

### TU-AUTH-011: Refresh com token valido
- **Funcao**: `AuthService.refresh(refresh_token)`
- **Setup**: Login previo gerou refresh
- **Saida esperada**: Novo access + novo refresh; antigo refresh revogado
- **Verificacoes**: Antigo refresh falha em segundo refresh; novo access tem `type=access`

### TU-AUTH-012: Refresh revogado / logout
- **Funcao**: `AuthService.logout` + `AuthService.refresh`
- **Setup**: Login + logout com o refresh
- **Saida esperada**: Refresh apos logout lanca AuthenticationError

### TU-AUTH-013: Usuario inativo nao renova
- **Funcao**: `AuthService.refresh`
- **Setup**: Login, depois `is_active=false`
- **Saida esperada**: AuthenticationError

## Testes de Integracao

### TI-AUTH-001: Endpoint de login completo
- **Endpoint**: POST /api/v1/auth/login
- **Setup**: Usuario no banco
- **Fluxo**:
  1. Envia JSON com username e password corretos
  2. Recebe 200 + access_token + refresh_token + expires_in + dados do usuario
  3. Usa access_token no header Authorization
  4. GET /api/v1/auth/me retorna dados do usuario

### TI-AUTH-002: Endpoint de login com erro
- **Endpoint**: POST /api/v1/auth/login
- **Fluxo**:
  1. Envia senha errada
  2. Recebe 401
  3. Envia token expirado no /auth/me
  4. Recebe 401

### TI-AUTH-003: Refresh e logout via HTTP
- **Endpoints**: POST /api/v1/auth/refresh, POST /api/v1/auth/logout
- **Fluxo**:
  1. Login → refresh_token
  2. POST /auth/refresh → 200 com novo par
  3. POST /auth/logout com o refresh atual → 200
  4. POST /auth/refresh com o mesmo → 401
  5. Bearer com refresh_token (opaco) em /auth/me → 401

## Mocks/Stubs

- Banco SQLite em memoria para testes unitarios
- Nenhuma chamada externa necessaria
