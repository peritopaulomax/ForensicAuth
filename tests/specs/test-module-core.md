# test-module-core.md - Especificacao de Testes: Core Engine

## Testes Unitarios

### TU-CORE-001: Registro de plugins forenses
- **Funcao**: `PluginRegistry.discover_and_register(adapters_dir)`
- **Setup**: Diretorio com 3 adapters validos (MockPluginA, MockPluginB, MockPluginC) e 1 arquivo invalido
- **Saida esperada**: Registry contem 3 plugins (A, B, C)
- **Verificacoes**:
  - Cada plugin tem `name` unico
  - Plugin invalido e ignorado com warning no log
  - `get_plugin("mock_a")` retorna instancia de MockPluginA

### TU-CORE-002: ForensicPlugin abstrato nao instanciavel
- **Classe**: `ForensicPlugin`
- **Acao**: Tentar instanciar `ForensicPlugin()` diretamente
- **Saida esperada**: `TypeError` (classe abstrata com metodos abstratos)

### TU-CORE-003: Implementacao valida de ForensicPlugin
- **Classe**: `MockValidPlugin(ForensicPlugin)`
- **Setup**: Implementa `name`, `supported_types`, `analyze`, `validate_parameters`
- **Acao**: Instanciar e chamar `validate_parameters({})`
- **Saida esperada**: Funciona sem erro

### TU-CORE-004: Validacao de parametros de plugin
- **Funcao**: `MockValidPlugin.validate_parameters(params)`
- **Casos**:
  - `{}` → (True, "")
  - `{"invalid": 123}` → (False, "Parametro 'invalid' nao reconhecido")
- **Saida esperada**: Tupla (bool, str) conforme casos

### TU-CORE-005: Configuracao via Pydantic Settings
- **Classe**: `Settings`
- **Setup**: Variaveis de ambiente `DATABASE_URL=postgresql://...`, `SECRET_KEY=test123`
- **Saida esperada**:
  - `settings.DATABASE_URL` = "postgresql://..."
  - `settings.SECRET_KEY` = "test123"
  - `settings.ACCESS_TOKEN_EXPIRE_MINUTES` = 30 (default)

### TU-CORE-006: Falta variavel obrigatoria
- **Setup**: DATABASE_URL ausente no ambiente
- **Acao**: Instanciar `Settings()`
- **Saida esperada**: `ValidationError` com mensagem indicando DATABASE_URL obrigatoria

## Testes de Integracao

### TI-CORE-001: Startup da aplicacao
- **Setup**: Variaveis de ambiente completas
- **Fluxo**:
  1. Cria app FastAPI
  2. Verifica que todas as tabelas foram criadas no banco
  3. Verifica que registry de plugins foi populado
  4. GET /api/v1/analysis/techniques retorna lista nao vazia

## Mocks/Stubs

- Mock adapters em `tests/mocks/adapters/`
- Cada mock herda `ForensicPlugin` e retorna dados fixos
