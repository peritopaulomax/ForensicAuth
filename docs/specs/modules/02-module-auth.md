# 02-module-auth.md - Modulo de Autenticacao e Autorizacao

## Responsabilidade Unica

Gerenciar identidade de usuarios, autenticacao via JWT e controle de acesso baseado em perfis (RBAC).

## Interfaces Publicas

### API Endpoints

- `POST /api/v1/auth/login`
  - Entrada: `{username: str, password: str}`
  - Saida: `{access_token: str, token_type: str, user: {id: uuid, username: str, role: str}}`
  - Erros: 401 (credenciais invalidas), 403 (usuario inativo)

- `POST /api/v1/auth/register` (Admin only)
  - Entrada: `{username: str, email: str, password: str, role: str}`
  - Saida: `{id: uuid, username: str, email: str, role: str, created_at: datetime}`
  - Erros: 409 (username/email duplicado), 403 (sem permissao)

- `GET /api/v1/auth/me`
  - Entrada: Header `Authorization: Bearer <token>`
  - Saida: `{id: uuid, username: str, email: str, role: str, is_active: bool}`
  - Erros: 401 (token invalido/expirado)

### Dependencias de Outros Modulos

- **Core**: Utiliza `src/backend/core/dependencies.py` para injecao de dependencia `get_current_user()` e `require_role()`.
- **Database**: Depende do model `User` e sessao SQLAlchemy.

## Fluxo Interno

### Login
1. Recebe username e password
2. Busca usuario no banco por username
3. Se nao encontrado ou inativo: retorna 401
4. Verifica password com bcrypt
5. Se invalido: retorna 401
6. Gera JWT com claims: sub (user_id), role, exp (30 minutos)
7. Retorna token + dados do usuario

### Registro
1. Verifica se usuario atual tem role "admin"
2. Valida formato de email e forca minima de senha (8 chars, 1 maiuscula, 1 numero)
3. Verifica unicidade de username e email
4. Hasheia senha com bcrypt (rounds=12)
5. Insere no banco
6. Retorna dados do usuario (sem password)

### Verificacao de Token
1. Extrai token do header Authorization
2. Decodifica JWT com SECRET_KEY e algoritmo HS256
3. Verifica expiracao
4. Busca usuario no banco pelo sub (user_id)
5. Se inativo: 401
6. Retorna objeto User

## Regras de Negocio Especificas

- Senhas devem ter no minimo 8 caracteres, 1 letra maiuscula e 1 numero.
- Tokens JWT expiram em 30 minutos.
- Apenas Admin pode registrar novos usuarios.
- Usuarios inativos (is_active=false) nao podem fazer login.
- A role "analista" nao pode criar casos.

## Tratamento de Erros

| Cenario | HTTP | Mensagem |
|---------|------|----------|
| Credenciais invalidas | 401 | "Usuario ou senha incorretos" |
| Token expirado | 401 | "Sessao expirada, faca login novamente" |
| Token invalido | 401 | "Token de autenticacao invalido" |
| Sem permissao | 403 | "Acesso negado para este recurso" |
| Username duplicado | 409 | "Username ja existe" |
| Email duplicado | 409 | "Email ja cadastrado" |
| Senha fraca | 422 | "Senha deve ter no minimo 8 caracteres, 1 maiuscula e 1 numero" |

## Dados de Entrada/Saida

- Entrada: JSON (login, registro)
- Saida: JSON com token e dados do usuario
- Senhas: nunca retornadas em nenhuma resposta
