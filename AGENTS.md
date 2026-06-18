# AGENTS.md - Regras Maximas do Projeto ForensicAuth

Este arquivo contem as regras absolutas para execucao deste projeto.
Toda instancia do agente Kimi DEVE ler e seguir este arquivo.

## Regra Maxima 1: Complecao Total

Toda execucao, planejamento e automacao de geracao de codigo deve ser pensada de forma COMPLETA, do INICIO ate a ENTREGA do produto final, pronto, como prototipo, e FUNCIONAL.

NUNCA entregue trabalho incompleto. Se uma tarefa parece grande demais, divida em partes, mas cada parte deve ser concluida integralmente antes de avancar.

## Regra Maxima 2: Automatismo Maximo

Toda execucao deve priorizar o AUTOMATISMO de execucao de codigo pelo agente Kimi.
- Crie tudo automaticamente.
- Se Yolo Mode estiver ativo no ambiente, execute ferramentas (Shell, WriteFile, etc.) SEM pedir autorizacao ao usuario.
- Se for possivel configurar o Kimi Code CLI para execucao sem pedir permissao em terminal/shell, ISSO DEVE SER FEITO.

## Regra Maxima 3: Orientacao quando Impossivel Automatizar

Se por algum motivo uma acao REQUERER intervencao humana (ex: credenciais, permissao de sistema, erro ambiental nao resolvivel):
- Forneca passo a passo DETALHADO.
- Forneca o TEXTO EXATO dos comandos ou acoes.
- Deixe claro e sem ambiguidade.
- Aguarde confirmacao antes de prosseguir.

## Regra Maxima 4: Testes Antes de Avancar

TODO codigo gerado DEVE passar nos testes correspondentes antes de avancar para a proxima etapa.
- Crie codigo seguindo as especificacoes.
- Execute os testes IMEDIATAMENTE apos criar o codigo.
- Se falhar, CORRIJA ate passar a contento (verde).
- So entao prossiga para o proximo modulo ou prompt.

## Regra Maxima 5: Leitura de Especificacoes

ANTES de escrever qualquer codigo:
1. Leia `docs/specs/00-overview.md` para entender o comportamento esperado.
2. Leia `docs/specs/01-architecture.md` para entender a arquitetura e contratos.
3. Leia `docs/specs/modules/02-module-*.md` do modulo que vai implementar.
4. Leia `tests/specs/test-module-*.md` para entender o que deve passar.

NUNCA implemente baseado em memoria ou suposicao. Sempre consulte as specs.

## Regra Maxima 6: Prompts de Execucao

Quando o usuario disser "execute prompt X" ou similar:
1. Leia o arquivo `prompts/XX-nome.txt` correspondente.
2. Siga as instrucoes EXATAMENTE como escritas.
3. Ao final, gere relatorio de execucao com status de todos os testes.
4. So considere a etapa concluida quando todos os testes estiverem VERDES.

## Regra Maxima 7: Contexto e Persistencia

Se o contexto da conversa esgotar ou houver interrupcao:
- Releia os arquivos de especificacao em `docs/specs/`.
- Releia este AGENTS.md.
- Continue a partir do ponto deixado, NUNCA recomece do zero sem necessidade.

## Regra Maxima 8: Bibliotecas Forenses Especificas Sao Intocaveis

Bibliotecas e algoritmos forenses especificos dos legados (`Legados/`) NAO devem ser substituidos, reescritos ou alterados sem teste rigoroso de equivalencia exata.

### Bibliotecas protegidas (lista nao exaustiva):
- `jpegio` — acesso direto a coeficientes DCT quantizados e tabelas de quantizacao
- `libzero.so_` + `cffi` — algoritmo ZERO para deteccao de grid JPEG
- Parser binario customizado de MP3 (struct puro)
- Parser binario customizado de Ogg/Opus (struct puro)
- Parser binario customizado de ISO BMFF (struct puro)
- `PyMuPDF (fitz)` + tokenizador customizado de content streams PDF
- `insightface`, modelos XGBoost de detecção de imagens sintéticas, modelos PyTorch de deepfake
- Pipeline PRNU (wavelet db4 + filtro Wiener-like portado do Rice Wavelet Toolbox)
- PatchMatch com momentos de Zernike acelerado por Numba

### Politica de adaptacao:
- A camada de abstracao (`src/backend/core/forensic_plugin.py`) apenas ORQUESTRA a chamada dessas bibliotecas.
- Adaptadores em `src/backend/adapters/` padronizam ENTRADAS e SAIDAS, mas preservam o algoritmo interno.
- Qualquer modificacao em algoritmo forense exige:
  1. Teste de regressao comparando saida do adaptador vs. saida original do notebook
  2. Metrica de erro zero (ou tolerancia explicitamente documentada e aprovada pelo usuario)
  3. Aprovacao explicita do usuario antes de merge
- Flexibilidade e permitida para evolucao futura, desde que precedida de validacao forense rigorosa.

## Regra Maxima 9: Cadeia de Custodia Digital

Todo processamento forense deve ser rastreavel e reprodutivel:
- SHA-256 do arquivo de evidencia original
- SHA-256 dos parametros de processamento (JSON canonicalizado)
- SHA-256 do resultado/artefato gerado
- Timestamp, usuario, tecnica aplicada
- Log encadeado (hash do registro anterior) para detectar tampering
- Reexecucao idempotente permitida para verificacao por terceiros

## Estrutura do Projeto

```
ForensicAuth/
├── AGENTS.md                 # Este arquivo
├── docs/
│   └── specs/
│       ├── 00-overview.md    # Comportamental geral
│       ├── 01-architecture.md # Tecnica e contratos
│       └── modules/
│           └── 02-module-*.md # Especificacoes modulares
├── tests/
│   └── specs/
│       └── test-module-*.md  # Especificacoes de testes
├── src/
│   ├── backend/
│   └── frontend/
└── prompts/
    ├── 00-master.txt         # Contexto geral e regras
    ├── 01-setup.txt          # Setup de ambiente
    ├── 02-tests.txt          # Criacao dos testes
    └── 03-module-*.txt       # Execucao por modulo
```
