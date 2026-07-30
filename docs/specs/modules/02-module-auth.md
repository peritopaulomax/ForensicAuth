# 02-module-auth.md - Modulo de Autenticacao e Autorizacao

## Responsabilidade Unica

Gerenciar identidade de usuarios, autenticacao via JWT de acesso curto + refresh opaco revogavel, e controle de acesso baseado em perfis (RBAC).

## Interfaces Publicas

### API Endpoints

- `POST /api/v1/auth/login`
  - Entrada: `{username: str, password: str}`
  - Saida: `{access_token: str, refresh_token: str, token_type: str, expires_in: int, user: {id: uuid, username: str, role: str, ...}}`
  - `expires_in`: segundos de validade do access token
  - Erros: 401 (credenciais invalidas / usuario inativo / senha nao definida)

- `POST /api/v1/auth/refresh`
  - Entrada: `{refresh_token: str}`
  - Saida: `{access_token: str, refresh_token: str, token_type: str, expires_in: int}`
  - Comportamento: valida refresh no banco (hash); se ok, emite novo access e **rotaciona** o refresh (revoga o antigo, emite novo)
  - Erros: 401 (refresh invalido, expirado, revogado, usuario inativo); reuso de refresh ja rotacionado invalida a familia de sessoes do usuario

- `POST /api/v1/auth/logout`
  - Entrada: `{refresh_token: str}`
  - Saida: `{ok: true}`
  - Comportamento: revoga o refresh informado (idempotente se ja revogado/inexistente)
  - Erros: nenhum bloqueante — sempre 200 apos tentativa de revogacao (evita enumeracao)

- `POST /api/v1/auth/register` (Admin only)
  - Entrada: `{username: str, email: str, password: str, role: str}`
  - Saida: `{id: uuid, username: str, email: str, role: str, created_at: datetime}`
  - Erros: 409 (username/email duplicado), 403 (sem permissao)

- `GET /api/v1/auth/me`
  - Entrada: Header `Authorization: Bearer <access_token>`
  - Saida: `{id: uuid, username: str, email: str, role: str, is_active: bool}`
  - Erros: 401 (token invalido/expirado / token que nao e access)

### Dependencias de Outros Modulos

- **Core**: Utiliza `src/backend/core/dependencies.py` / `app/dependencies.py` para injecao de dependencia `get_current_user()` e `require_role()`.
- **Database**: Depende dos models `User`, `RefreshToken` e sessao SQLAlchemy.

## Fluxo Interno

### Login
1. Recebe username e password
2. Busca usuario no banco por username
3. Se nao encontrado ou inativo: retorna 401
4. Verifica password com bcrypt
5. Se invalido: retorna 401
6. Gera access JWT com claims: `sub` (user_id), `role`, `type=access`, `exp` curto (`ACCESS_TOKEN_EXPIRE_MINUTES`)
7. Gera refresh opaco (random), persiste `sha256(refresh)` em `refresh_tokens` com `user_id`, `expires_at` (`REFRESH_TOKEN_EXPIRE_DAYS`), `revoked_at=null`
8. Retorna access + refresh + `expires_in` + dados do usuario

### Refresh
1. Recebe refresh_token em texto claro
2. Calcula hash e busca registro ativo (nao revogado, nao expirado)
3. Se nao encontrado: se o hash bate em registro ja revogado com `replaced_by` (reuso), revoga todos os refresh do usuario e retorna 401
4. Se usuario inativo: 401
5. Revoga o refresh atual; emite novo access + novo refresh (rotacao); liga `replaced_by` do antigo ao novo
6. Retorna novo par de tokens

### Logout
1. Recebe refresh_token
2. Se existir registro correspondente e nao revogado: seta `revoked_at`
3. Retorna `{ok: true}`

### Registro
1. Verifica se usuario atual tem role "admin"
2. Valida formato de email e forca minima de senha (8 chars, 1 maiuscula, 1 numero)
3. Verifica unicidade de username e email
4. Hasheia senha com bcrypt (rounds=12)
5. Insere no banco
6. Retorna dados do usuario (sem password)

### Verificacao de Token (APIs protegidas)
1. Extrai token do header Authorization
2. Decodifica JWT com SECRET_KEY e algoritmo HS256
3. Verifica expiracao e claim `type` (deve ser `access`; tokens sem `type` sao aceitos como access)
4. Refresh opaco ou JWT com `type=refresh` no Bearer → 401
5. Busca usuario no banco pelo sub (user_id)
6. Se inativo: 401
7. Retorna objeto User

### Revogacao em cascata
- Reset de senha (admin) e desativacao de usuario: revoga **todos** os refresh tokens do usuario.

## Regras de Negocio Especificas

- Senhas devem ter no minimo 8 caracteres, 1 letra maiuscula e 1 numero.
- Access JWT: TTL curto via `ACCESS_TOKEN_EXPIRE_MINUTES` (default 15).
- Refresh opaco: TTL longo via `REFRESH_TOKEN_EXPIRE_DAYS` (default 14); armazenado apenas como hash no DB.
- Rotacao obrigatoria em `POST /auth/refresh` (one-time refresh).
- Apenas Admin pode registrar novos usuarios.
- Usuarios inativos (`is_active=false`) nao podem fazer login nem renovar sessao.
- Roles validas: `admin` e `perito`. Colaboracao entre peritos usa CaseShare (viewer/editor), nao um terceiro perfil.

## Tratamento de Erros

| Cenario | HTTP | Mensagem |
|---------|------|----------|
| Credenciais invalidas | 401 | "Usuario ou senha incorretos" |
| Token expirado | 401 | "Sessao expirada, faca login novamente" |
| Token invalido | 401 | "Token de autenticacao invalido" |
| Refresh invalido/expirado/revogado | 401 | "Refresh token invalido ou expirado" |
| Sem permissao | 403 | "Acesso negado para este recurso" |
| Username duplicado | 409 | "Username ja existe" |
| Email duplicado | 409 | "Email ja cadastrado" |
| Senha fraca | 422 | "Senha deve ter no minimo 8 caracteres, 1 maiuscula e 1 numero" |

## Dados de Entrada/Saida

- Entrada: JSON (login, refresh, logout, registro)
- Saida: JSON com tokens e/ou dados do usuario
- Senhas e refresh em claro: nunca persistidos; refresh so trafega na resposta/request, DB guarda hash
- Senhas: nunca retornadas em nenhuma resposta

## Persistencia

Tabela `refresh_tokens`:
- `id` (UUID PK)
- `user_id` (FK users)
- `token_hash` (SHA-256 hex, unique)
- `expires_at`
- `revoked_at` (nullable)
- `replaced_by` (FK refresh_tokens.id, nullable — rotacao)
- `created_at`
