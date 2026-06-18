# 03-module-core.md - Modulo Core (Engine Forense e Infraestrutura)

## Responsabilidade Unica

Fornecer a infraestrutura base do backend: configuracao, conexao com banco, dependencias compartilhadas, e a interface abstrata `ForensicPlugin` que padroniza como todas as tecnicas forenses sao orquestradas.

## Interfaces Publicas

### ForensicPlugin (Classe Abstrata)

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class ForensicPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Nome unico da tecnica (ex: 'prnu', 'jpeg_ghosts')"""
        pass

    @property
    @abstractmethod
    def supported_types(self) -> list[str]:
        """Tipos de evidencia suportados: ['imagem', 'audio', 'video', 'pdf']"""
        pass

    @abstractmethod
    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executa a analise forense.
        
        Args:
            evidence_path: caminho absoluto do arquivo de evidencia
            parameters: dict com parametros especificos da tecnica
            
        Returns:
            Dict com:
                - success: bool
                - artifacts: list[dict] -- artefatos gerados (imagens, JSON, etc.)
                - metrics: dict -- metricas numericas/estatisticas
                - logs: list[str] -- mensagens de log do processamento
        """
        pass

    @abstractmethod
    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str]:
        """Valida parametros antes da execucao. Retorna (valido, mensagem_de_erro)"""
        pass
```

### Dependencias Compartilhadas

- `get_db()` → Generator[Session, None, None]
- `get_current_user(token)` → User
- `require_role(role: str)` → Dependency que retorna 403 se role nao match

### Configuracao

- `Settings` (Pydantic Settings): le variaveis de ambiente ou .env
  - DATABASE_URL
  - REDIS_URL
  - SECRET_KEY
  - ALGORITHM (default: HS256)
  - ACCESS_TOKEN_EXPIRE_MINUTES (default: 30)
  - UPLOAD_DIR
  - RESULTS_DIR
  - GPU_AVAILABLE (bool, auto-detect)
  - CELERY_BROKER_URL

## Dependencias de Outros Modulos

- **Database**: SQLAlchemy engine, sessionmaker, Base declarativa
- **Models**: Todos os models SQLAlchemy (User, Case, Evidence, etc.)
- **Adapters**: Nenhuma dependencia direta; adapters IMPLEMENTAM ForensicPlugin

## Fluxo Interno

### Inicializacao da Aplicacao
1. Carrega `Settings` do ambiente
2. Cria engine SQLAlchemy e tabelas (create_all) se nao existirem
3. Configura Celery app
4. Registra plugins forenses disponiveis (discovery dinamico em `adapters/`)

### Registro de Plugins
1. No startup, escaneia `src/backend/adapters/`
2. Para cada modulo, verifica se exporta uma classe que herda de `ForensicPlugin`
3. Registra em dicionario `PLUGINS: dict[str, ForensicPlugin]`
4. Endpoint `/api/v1/analysis/techniques` consulta este registro

## Regras de Negocio Especificas

- Todo adapter forense DEVE implementar `ForensicPlugin`.
- A validacao de parametros DEVE ocorrer antes da criacao do job.
- A aplicacao DEVE falhar no startup se DATABASE_URL ou REDIS_URL nao estiverem configuradas.

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| Variavel de ambiente obrigatoria ausente | Levanta `ValueError` no startup, app nao sobe |
| Banco de dados indisponivel | HTTP 503 com mensagem "Servico indisponivel" |
| Plugin sem implementacao correta | Log de warning no startup, plugin ignorado |

## Dados de Entrada/Saida

- Configuracao: variaveis de ambiente ou arquivo `.env`
- Plugins: classes Python que herdam `ForensicPlugin`
