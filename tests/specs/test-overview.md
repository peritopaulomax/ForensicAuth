# test-overview.md - Estrategia de Testes Geral

## Framework

- **Backend**: pytest >= 7.4, pytest-asyncio, pytest-cov
- **Frontend**: Vitest + React Testing Library + MSW (Mock Service Worker)
- **E2E**: Playwright (ou Cypress) para fluxos criticos

## Piramide de Testes

```
      /\
     /  \  E2E (5%): Fluxos completos de usuario
    /____\
   /      \  Integracao (15%): API + Banco + Fila
  /________\
 /          \  Unitario (80%): Funcoes, adapters, services
/____________\
```

## Cobertura Minima

- Backend: 80% de cobertura de linhas
- Frontend: 70% de cobertura de componentes criticos
- Testes devem cobrir: caminho feliz + pelo menos 2 caminhos de erro por funcionalidade

## Fixtures Compartilhadas

### Backend (conftest.py)
- `db_session`: sessao SQLAlchemy em transacao rollback
- `client`: TestClient do FastAPI
- `auth_headers`: header Authorization com token JWT de usuario de teste
- `sample_evidence`: arquivo de evidencia temporario para upload
- `sample_case`: caso de teste pre-criado no banco

### Frontend
- `renderWithProviders`: renderiza componente com contexto de auth, router, query client
- `mockApiHandlers`: handlers MSW para endpoints comuns

## Dados de Teste

- Usar factory-boy (Python) ou faker para gerar dados de teste
- Nunca usar dados de producao
- Evidencias de teste: arquivos pequenos (<< 1MB) em `tests/fixtures/`

## Execucao

```bash
# Backend
pytest tests/unit/ -v --cov=src/backend --cov-report=term-missing
pytest tests/integration/ -v --cov-append
pytest tests/e2e/ -v

# Frontend
npm run test
npm run test:e2e
```
