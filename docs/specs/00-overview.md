# 00-overview.md - Especificacao Comportamental Geral

## Proposito

O ForensicAuth e uma plataforma forense digital unificada para peritos criminais da Policia Federal. Consolida tecnicas de analise de imagem, audio, video e PDF em uma aplicacao web profissional com autenticacao multiusuario, cadeia de custodia digital rastreavel e geracao de relatorios tecnicos.

## Usuarios e Perfis

| Perfil | Descricao | Permissoes |
|--------|-----------|------------|
| **Admin** | Gestor do sistema | CRUD de usuarios, configuracoes, auditoria completa |
| **Perito** | Analista forense senior | Criar casos, submeter evidencias, executar todas as tecnicas, gerar laudos |
| **Analista** | Analista forense junior | Visualizar casos designados, executar tecnicas autorizadas, visualizar resultados |

## Historias de Usuario

### Autenticacao e Controle de Acesso
- Como **Admin**, quero criar usuarios com perfis distintos, para que o acesso ao sistema seja controlado.
- Como **usuario**, quero fazer login com usuario e senha, para que minhas acoes sejam auditadas.
- Como **Admin**, quero visualizar logs de auditoria de todos os usuarios, para garantir conformidade.

### Gestao de Casos
- Como **Perito**, quero criar um caso com numero protocolar, para organizar evidencias relacionadas.
- Como **Perito**, quero associar evidencias (arquivos) a um caso, para manter a cadeia de custodia.
- Como **Analista**, quero visualizar apenas os casos designados a mim, para nao acessar dados alheios.

### Cadeia de Custodia
- Como **Perito**, quero que todo arquivo submetido tenha seu hash SHA-256 calculado automaticamente, para garantir integridade.
- Como **Perito**, quero que todo processamento aplicado a uma evidencia seja registrado com parametros e timestamp, para permitir reproducao.
- Como **Perito**, quero reexecutar um processamento anterior e comparar os hashes, para validar reproducibilidade.

### Analise Forense
- Como **Perito**, quero submeter uma imagem e aplicar tecnicas como PRNU, JPEG Ghosts, BAG/ZERO, PatchMatch, Detecção de imagens sintéticas e Deepfake, para detectar adulteracoes.
- Como **Perito**, quero submeter um audio e aplicar analise de MP3, Opus, WAV IMA ADPCM, ENF e espectrograma, para verificar autenticidade.
- Como **Perito**, quero submeter um video e analisar sua estrutura ISO BMFF e metadados temporais STTS/ELST, para detectar edicoes.
- Como **Perito**, quero submeter um PDF e analisar sua estrutura, fontes e edicoes TouchUp, para detectar manipulacoes.

### Jobs e Processamento
- Como **Perito**, quero acompanhar o status dos processamentos em fila, para saber quando os resultados estarao prontos.
- Como **Perito**, quero que jobs que usam GPU sejam serializados automaticamente, para evitar travamentos por falta de VRAM.

### Relatorios
- Como **Perito**, quero gerar um laudo PDF oficial com resultados, screenshots, hashes e assinatura digital, para uso em processos.
- Como **Perito**, quero que o relatorio seja imutavel apos geracao (hash registrado), para garantir integridade probatoria.

## Fluxos de Usuario Principais

### Fluxo 1: Criacao de Caso e Submissao de Evidencia
1. Perito faz login
2. Cria novo caso (numero protocolar, descricao)
3. Faz upload de evidencia (imagem, audio, video ou PDF)
4. Sistema calcula SHA-256 do arquivo, registra em cadeia de custodia
5. Sistema armazena arquivo em diretorio seguro do caso

### Fluxo 2: Execucao de Analise
1. Perito seleciona evidencia dentro de um caso
2. Escolhe tecnica(s) forense(s) a aplicar
3. Sistema cria job(s) na fila (Celery)
4. Sistema executa processamento (GPU quando necessario)
5. Resultados sao armazenados com hash e parametros
6. Perito visualiza resultados (imagens, graficos, metricas, mapas)

### Fluxo 3: Geracao de Laudo
1. Perito seleciona resultados de analises desejados
2. Sistema gera PDF com template institucional
3. PDF inclui: metadados do caso, hashes, descricao das tecnicas, resultados, screenshots
4. Sistema calcula SHA-256 do laudo e registra na cadeia de custodia
5. Laudo fica disponivel para download

## Regras de Negocio

1. **RN-01**: Todo arquivo submetido DEVE ter seu SHA-256 calculado antes de qualquer processamento.
2. **RN-02**: Todo processamento forense DEVE registrar: usuario, timestamp, tecnica, parametros, hash do arquivo original, hash do resultado.
3. **RN-03**: A cadeia de custodia DEVE ser INSERT-only. Nenhum registro pode ser alterado ou excluido.
4. **RN-04**: Jobs que utilizam GPU DEVEM ser serializados (um por vez) para evitar OOM.
5. **RN-05**: Um Analista NAO pode criar casos; apenas visualizar casos designados por um Perito.
6. **RN-06**: Um Perito NAO pode criar usuarios; apenas Admin pode.
7. **RN-07**: Relatorios PDF gerados DEVEM ser imutaveis. Apos geracao, qualquer modificacao invalida o laudo.
8. **RN-08**: Bibliotecas forenses especificas dos legados (jpegio, libzero, parsers binarios, etc.) NAO podem ser substituidas sem teste de equivalencia exata.

## Requisitos Nao-Funcionais

| ID | Requisito | Descricao |
|----|-----------|-----------|
| RNF-01 | Offline/Local | Sistema deve operar 100% local, sem chamadas a APIs externas ou nuvem. |
| RNF-02 | GPU Opcional | Deve funcionar sem GPU, mas aproveitar CUDA quando disponivel. |
| RNF-03 | Concorrencia | Suportar multiplos usuarios simultaneos, com fila de jobs para GPU. |
| RNF-04 | Auditabilidade | Toda acao deve ser logada com usuario, timestamp e dados relevantes. |
| RNF-05 | Reprodutibilidade | Qualquer processamento deve ser reproduzivel com os mesmos parametros e produzir o mesmo hash de resultado. |
| RNF-06 | Performance | Upload de arquivos ate 500MB. Jobs simples (parsing) < 30s. Jobs complexos (PRNU, Deepfake) podem demorar minutos. |
| RNF-07 | Seguranca | Senhas hasheadas (bcrypt). Tokens JWT com expiracao. SQL injection protegido via ORM. |
| RNF-08 | Disponibilidade | Deve rodar 24/7 no servidor corporativo da PF. |
