# 00-overview.md - Especificacao Comportamental Geral

## Proposito

O ForensicAuth e uma plataforma forense digital unificada para peritos criminais. Consolida tecnicas de analise de imagem, audio, video e PDF em uma aplicacao web profissional com autenticacao multiusuario e cadeia de custodia digital rastreavel.

## Usuarios e Perfis

| Perfil | Descricao | Permissoes |
|--------|-----------|------------|
| **Admin** | Gestor do sistema | CRUD de usuarios, configuracoes, auditoria completa |
| **Perito** | Analista forense | Criar casos, submeter evidencias, executar tecnicas, compartilhar/fechar casos, exportar/importar VCP |

Colaboracao de leitura/edicao entre peritos ocorre via **compartilhamento de caso** (viewer/editor), nao por um perfil separado.

## Historias de Usuario

### Autenticacao e Controle de Acesso
- Como **Admin**, quero criar usuarios com perfis distintos, para que o acesso ao sistema seja controlado.
- Como **usuario**, quero fazer login com usuario e senha, para que minhas acoes sejam auditadas.
- Como **Admin**, quero visualizar logs de auditoria de todos os usuarios, para garantir conformidade.

### Gestao de Casos
- Como **Perito**, quero criar um caso com numero protocolar, para organizar evidencias relacionadas.
- Como **Perito**, quero associar evidencias (arquivos) a um caso, para manter a cadeia de custodia.
- Como **Perito**, quero compartilhar um caso com outro perito (viewer ou editor), para colaboracao controlada.

### Cadeia de Custodia
- Como **Perito**, quero que todo arquivo submetido tenha seu hash SHA-256 calculado automaticamente, para garantir integridade.
- Como **Perito**, quero que eventos oficiais (upload, derivado promovido, compartilhamento, fechamento, importacao) entrem na cadeia de custodia.
- Como **Perito**, quero reexecutar um processamento anterior e comparar os hashes do job/artefato, para validar reproducibilidade.

### Analise Forense
- Como **Perito**, quero submeter uma imagem e aplicar tecnicas como PRNU, JPEG Ghosts, BAG/ZERO, PatchMatch, Detecção de imagens sintéticas e Deepfake, para detectar adulteracoes.
- Como **Perito**, quero submeter um audio e aplicar analise espectral, ENF e deteccao de spoofing, para verificar autenticidade.
- Como **Perito**, quero submeter um video e analisar sua estrutura ISO BMFF e metadados temporais STTS/ELST, para detectar edicoes.
- Como **Perito**, quero submeter um PDF e analisar sua estrutura, fontes e overlays, para detectar manipulacoes.

### Jobs e Processamento
- Como **Perito**, quero acompanhar o status dos processamentos em fila, para saber quando os resultados estarao prontos.
- Como **Perito**, quero que jobs que usam GPU sejam serializados automaticamente, para evitar travamentos por falta de VRAM.

### Fora de escopo (produto)
- **Laudo PDF oficial unificado** (modulo reports): **nao faz parte do produto**. Resultados saem das tecnicas (artefatos/JSON); a peca oficial de transferencia entre instancias e o **VCP**. Nao ha prazo nem compromisso de implementar geracao de laudo PDF.

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
5. Resultados sao armazenados com hash e parametros no job/artefatos
6. Perito visualiza resultados (imagens, graficos, metricas, mapas)
7. (Opcional) Perito promove artefato a derivado — aih sim novo elo de custodia

### Fluxo 3: Fechamento e transferencia
1. Perito compartilha e/ou fecha o caso (manifesto assinado quando aplicavel)
2. (Opcional) Exporta/importa **VCP** para outra instancia

## Regras de Negocio

1. **RN-01**: Todo arquivo submetido DEVE ter seu SHA-256 calculado antes de qualquer processamento.
2. **RN-02**: Todo job forense DEVE persistir: usuario, timestamp, tecnica, parametros, hash do arquivo de entrada e hash do resultado/artefato (no `AnalysisJob` e no filesystem). Isso **nao** implica automaticamente um `CustodyRecord` por job.
3. **RN-03**: A cadeia de custodia DEVE ser INSERT-only. Nenhum registro pode ser alterado ou excluido.
4. **RN-04**: Jobs que utilizam GPU DEVEM ser serializados (um por vez) para evitar OOM.
5. **RN-05**: Colaboradores sem ownership acessam apenas via **CaseShare** (viewer/editor), conforme regras do modulo de sharing.
6. **RN-06**: Um Perito NAO pode criar usuarios; apenas Admin pode.
7. **RN-07**: *(Reservado / removido)* — laudo PDF oficial unificado fora de escopo.
8. **RN-08**: Bibliotecas forenses protegidas (jpegio, libzero, parsers binarios, etc.) NAO podem ser substituidas sem teste de equivalencia exata.

## Requisitos Nao-Funcionais

| ID | Requisito | Descricao |
|----|-----------|-----------|
| RNF-01 | Offline/Local | Sistema deve operar 100% local, sem chamadas a APIs externas ou nuvem. |
| RNF-02 | GPU Opcional | Deve funcionar sem GPU, mas aproveitar CUDA quando disponivel. |
| RNF-03 | Concorrencia | Suportar multiplos usuarios simultaneos, com fila de jobs para GPU. |
| RNF-04 | Auditabilidade | Toda acao relevante deve ser logada com usuario, timestamp e dados pertinentes. |
| RNF-05 | Reprodutibilidade | Qualquer processamento deve ser reproduzivel com os mesmos parametros e produzir o mesmo hash de resultado. |
| RNF-06 | Performance | Upload de arquivos ate 500MB. Jobs simples (parsing) < 30s. Jobs complexos (PRNU, Deepfake) podem demorar minutos. |
| RNF-07 | Seguranca | Senhas hasheadas (bcrypt). Tokens JWT com expiracao. SQL injection protegido via ORM. |
| RNF-08 | Disponibilidade | Deve rodar 24/7 no servidor corporativo da instituição. |
