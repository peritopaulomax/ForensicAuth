# Reflexão — Quantização do DF Arena 1B

## Contexto

O detector DF Arena 1B possui ~1 bilhão de parâmetros. O arquivo `pytorch_model.bin` local ocupa aproximadamente 4,4 GB, o que indica pesos em ponto flutuante de 32 bits (float32). A GPU disponível (RTX 3090, 24 GB) comporta o modelo com folga para inferência em janelas de 4 segundos.

## Pergunta

Seria o caso de quantizar o modelo para reduzir o consumo de VRAM? Como fazer isso de forma correta?

## Análise

### 1. Ganho potencial

- **float32 → int8**: redução de ~4 GB para ~1,1 GB (sem contar ativações e overhead do runtime).
- **float32 → bfloat16/float16**: redução para ~2,2 GB, com perda geralmente menor.
- Menor latência de carga e maior vazão em batch, mas nem sempre menor latência por amostra (depende do kernel e hardware).

### 2. Riscos forenses

A quantização de um classificador forense pode alterar:

- Os logits de cada janela, especialmente próximo à fronteira de decisão.
- A calibração de probabilidades (softmax).
- A composição da agregação por média de logits em áudios longos.
- A reprodutibilidade da cadeia de custódia digital.

A **Regra Máxima 8** do projeto proíbe substituir ou alterar bibliotecas/algoritmos forenses sem teste rigoroso de equivalência exata. Quantização é uma alteração do algoritmo de inferência e, portanto, está sob essa regra.

### 3. Recomendação imediata

**Não quantizar o DF Arena 1B neste primeiro momento.**

A RTX 3090 (24 GB) carrega o modelo em float32 sem problemas. A prioridade agora é:

1. Validar o pipeline de janelas de 4 s e a agregação por média de logits.
2. Montar populações de referência (spoof/bonafide) e calibrar LR (CLLr, EER).
3. Estabelecer uma baseline forense reprodutível.

Somente **depois** da baseline estabelecida, e se houver necessidade real (VRAM escassa, latência crítica, execução em CPU), deve-se avaliar a quantização.

### 4. Como quantizar corretamente, se for necessário no futuro

Caso decida quantizar, o processo deve ser:

1. **Manter o modelo float32 como referência (ground truth).**
2. Aplicar uma técnica de quantização:
   - **Post-training static quantization (PyTorch)**: rápido, mas pode degradar acurácia.
   - **Quantization-aware training (QAT)**: melhor preservação, exige dados rotulados e re-treino.
   - **bitsandbytes 8-bit**: camada intermediária entre float32 e int8, fácil de aplicar no `transformers`.
   - **ONNX Runtime com quantização dinâmica/int8**: alternativa para CPU.
3. **Validação forense obrigatória**:
   - Comparar logits/probabilidades janela a janela contra o modelo float32.
   - Calcular erro máximo, MSE e variação de label por janela.
   - Recomputar CLLr/EER na população de referência.
   - Aprovação explícita antes de tornar a versão quantizada padrão.

### 5. Alternativa imediata ao problema do `.bin`

O modelo só carrega com `pytorch_model.bin` se o PyTorch for >= 2.6. Caso contrário, a alternativa correta é converter os pesos para `safetensors`, usando o script já presente em `Legados/audio/DF_ARENA_1B/convert_pytorch_bin_to_safetensors.py`. Isso **não altera os valores dos pesos**, apenas o formato, e portanto não viola a Regra Máxima 8.

## Decisão

- **Não quantizar o DF Arena 1B agora.**
- **Usar float32 na RTX 3090 até a baseline forense estar validada.**
- Se necessário no futuro, executar estudo de equivalência forense antes de adotar qualquer versão quantizada.
