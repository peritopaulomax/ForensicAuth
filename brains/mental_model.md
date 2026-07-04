# Mental Model — ForensicAuth

## O que é

Laboratório forense digital em uma caixa:
- **Casos** = pastas de investigação
- **Evidências** = itens selados com SHA-256
- **Jobs** = exames técnicos em fila
- **Cadeia de custódia** = logbook imutável e assinado
- **Laudos** = relatórios oficiais com hash

## O que não é

- Serviço em nuvem (100% local)
- Substituto do perito
- Sistema de arquivos genérico

## Entidades principais

| Entidade | Papel |
|---|---|
| User | Admin/Perito (papel `analista` especificado mas migrado para `perito`) |
| Case | Container forense |
| Evidence | Arquivo com SHA-256 |
| AnalysisJob | Exame em fila (preview; não gera CustodyRecord) |
| CustodyRecord | Registro imutável |
| CaseClosure | Fechamento assinado |
| CaseClosureSignature | Assinatura adicional de fechamento |
| CaseShare | Compartilhamento de caso (viewer/editor) |
| Report | Laudo/relatório oficial (modelo existe; service/endpoint planejado) |

## Relações

User → cria Case → contém Evidence → origina AnalysisJob → produz resultado → pode virar Evidence derivada.

## Regras de ouro

1. Toda evidência tem hash antes do processamento.
2. Cadeia de custódia é INSERT-only.
3. Jobs GPU rodam um por vez.
4. Caso fechado deve ser imutável (validação pendente).
5. Legados só mudam com teste de equivalência.

## Fluxo mental

```text
Recebe arquivo → identifica tipo → calcula hash → salva → registra custódia
↓
Perito escolhe técnica → cria job → executa em fila
↓
Gera artefatos → calcula hash → exibe resultado
  (ex: `synthetic_image_detection` retorna scores individuais de 4 detectores, não um score único)
↓
Salva derivado, gera laudo ou verifica integridade
```

## O que pode quebrar

PostgreSQL, Redis, storage, GPU, chaves de assinatura, pesos, validações de domínio ausentes.
