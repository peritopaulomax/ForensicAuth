# TEMPLATE-SPEC.md - Template Padrão de Especificação (SDD+TDD)

> **Como usar:** Copie este arquivo para cada nova spec de módulo. Substitua os
> placeholders `[MOD]`, `[Nome]`, etc. Remova seções que não se aplicam.
> Após estabilizar, copie este template para a skill:
> `~/.config/agents/skills/sddtdd-orchestrator/assets/spec-template.md`

---

# [CÓDIGO]-module-[nome].md — [Nome Completo do Módulo]

- **Status:** Draft | Baseline | Stable | Deprecated
- **Audiência:** LLM codificadora, desenvolvedores, revisores
- **Relacionados:** [links para specs dependentes, ex: SPEC-01-architecture.md, SPEC-04-auth.md]
- **Regra de ouro:** [se houver uma regra absoluta para este módulo]

---

## 1. Responsabilidade Única

Uma frase curta definindo EXATAMENTE o que este módulo faz e o que NÃO faz.

> Exemplo: "Gerenciar identidade de usuários, autenticação via JWT e controle de
> acesso baseado em perfis (RBAC). Não gerencia casos, evidências ou processamentos."

## 2. Contexto (opcional)

Se o módulo depende de conhecimento de domínio específico, descreva o mínimo
necessário para codar corretamente. Máximo 5 parágrafos.

## 3. Interfaces Públicas

### 3.1 API Endpoints / Funções Públicas

Documente cada endpoint ou função pública:

```
- MÉTODO /rota
  - Entrada: {campo: tipo, campo2: tipo}
  - Saída: {campo: tipo, campo2: tipo}
  - Permissão: [público | autenticado | role específica]
  - Erros: [lista de códigos de erro possíveis]
```

Ou, para funções internas:

```python
def nome_funcao(param1: Tipo1, param2: Tipo2) -> TipoRetorno:
    """
    Descrição de uma linha.
    
    Args:
        param1: descrição
        param2: descrição
        
    Returns:
        Descrição do retorno
        
    Raises:
        ExcecaoX: quando...
    """
```

### 3.2 Eventos / Mensagens (se aplicável)

Se o módulo publica ou consome eventos (Celery, webhook, etc.):

| Evento | Produtor | Consumidor | Payload |
|--------|----------|------------|---------|
| `event.name` | Módulo X | Módulo Y | `{campo: tipo}` |

## 4. Dependências de Outros Módulos

Liste explicitamente o que este módulo consome:

- **[Módulo X](SPEC-XX.md):** usa `FuncaoY` para...
- **[Módulo Z](SPEC-ZZ.md):** depende do model `EntidadeW`

## 5. Fluxo Interno (Passo a Passo)

Para CADA operação principal, descreva o fluxo interno numerado:

### Fluxo: [Nome da Operação]

1. [Ação concreta: recebe X, valida Y]
2. [Ação concreta: consulta banco em Z]
3. [Ação concreta: executa algoritmo W]
4. [Ação concreta: persiste em K]
5. [Ação concreta: retorna/dispara evento]

```
[ASCII art opcional para fluxos complexos]
Cliente → API → Service → Repository → Banco
              ↓
              → Evento → Fila
```

## 6. Regras de Negócio Específicas

Cada regra deve ser numerada, atômica e testável:

- **RN-[MOD]-01:** Descrição precisa da regra. Nada de "talvez" ou "quando possível".
- **RN-[MOD]-02:** Segunda regra.
- **RN-[MOD]-03:** Terceira regra.

> Prefixo `[MOD]` = código curto do módulo (ex: AUTH, CORE, CUST, JOB, IMG, AUD, VID, PDF, REP).

## 7. Modelo de Dados (se houver entidades próprias)

```
EntidadeNome
- id: UUID PK
- campo1: str NOT NULL
- campo2: int DEFAULT 0
- relacionamento: FK → OutraEntidade
- created_at: datetime
```

Ou, se preferir, DDL SQL ou SQLAlchemy model.

## 8. Tratamento de Erros

| Código / Cenário | HTTP / Comportamento | Mensagem Padrão |
|------------------|---------------------|-----------------|
| `INVALID_REQUEST` | 400 | "Requisição malformada" |
| `NOT_FOUND` | 404 | "Recurso não encontrado" |
| `PERMISSION_DENIED` | 403 | "Acesso negado" |

## 9. Dados de Entrada/Saída

- **Entrada:** formato, schema, limites, validações
- **Saída:** formato, schema, exemplos concretos
- **Exemplo de entrada válida:**
  ```json
  {"campo": "valor"}
  ```
- **Exemplo de saída esperada:**
  ```json
  {"resultado": "valor"}
  ```

## 10. Testabilidade

### 10.1 Testes Unitários

Mapeie cada regra/fluxo a um teste:

- **TU-[MOD]-001:** [RN-[MOD]-01] — Dado X, deve produzir Y.
- **TU-[MOD]-002:** [RN-[MOD]-02] — Cenário de erro: entrada Z deve lançar W.
- **TU-[MOD]-003:** [Fluxo Principal] — Estado antes/depois, verificações.

### 10.2 Testes de Integração

- **TI-[MOD]-001:** [Módulo X] → [Este módulo] → [Módulo Y]. Verifica...

### 10.3 Mocks/Stubs Necessários

Liste o que deve ser mockado:
- Banco: SQLite em memória / container Postgres efêmero
- Serviços externos: [listar]
- Filas: broker em memória

## 11. Critérios de Aceite

Checklist objetivo para considerar o módulo pronto:

1. [Critério mensurável: ex: "Todos os endpoints respondem em < 200ms"]
2. [Critério mensurável: ex: "Cobertura de testes >= 80%"]
3. [Critério funcional: ex: "RN-[MOD]-01 a RN-[MOD]-05 implementadas e testadas"]
4. [Critério de segurança: ex: "Senhas nunca logadas nem retornadas"]

## 12. Decisões / Notas / Riscos

- **Decisão-01:** Por que foi feita determinada escolha técnica.
- **Risco-01:** O que pode dar errado e mitigação.
- **Suposição-01:** O que estamos assumendo como verdade.

---

## Checklist de Qualidade da Spec

Antes de marcar esta spec como "Baseline", verifique:

- [ ] Responsabilidade única está clara (1 frase)
- [ ] Interfaces públicas documentadas com tipos
- [ ] Fluxo interno é passo a passo (sem lacunas)
- [ ] Regras de negócio são atômicas e numeradas
- [ ] Erros cobrem pelo menos 2 caminhos de falha por funcionalidade
- [ ] Dados de entrada/saída têm exemplos concretos
- [ ] Testes mapeiam diretamente às regras/fluxos
- [ ] Critérios de aceite são mensuráveis
- [ ] Referências cruzadas para outras specs estão corretas
