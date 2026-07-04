# Hygiene Report — ForensicAuth

**Data:** 2026-06-25  
**Escopo:** Comentários de código, textos de frontend, documentação markdown  
**Metodologia:** Documentation Hygiene Engine

---

## Resumo Executivo

Auditoria identificou **~100 ocorrências** de problemas de higiene documental. A maioria é removível automaticamente com edições seguras:

- **Comentários de código:** cabeçalhos de autoria, e-mails, referências institucionais, instruções pessoais de notebook, TODOs sem contexto, comandos com proxy institucional.
- **Documentação:** referências ao assistente "Kimi", nome antigo "VA Suite", menções a órgão cliente (PF), dados de ambiente específico (IP, usuário, path, hardware).
- **Frontend:** textos em inglês não-técnico, inconsistências ortográficas (falta de acentos), labels técnicos expostos ao usuário, textos de teste (`mock_technique`).

**Score de higiene estimado antes:** 55/100  
**Score de higiene estimado após correções:** 85/100

---

## 1. Comentários Problemáticos

### 1.1 Autoria / Instituição

| Arquivo | Problema | Ação |
|---|---|---|
| `src/backend/core/legacy/dct/estimativaq.py:1-3` | `# Autor: Paulo Max Gil...`, `# Email: paulo.pmgir@dpf.gov.br`, `# Instituição: ...` | Remover cabeçalho |
| `src/backend/core/legacy/pad/utility.py:2-6` | Cabeçalho `@Author : zhuying`, `@Company : Minivision` | Remover bloco |
| `src/backend/core/legacy/pad/generate_patches.py:2-6` | Cabeçalho Minivision | Remover bloco |
| `src/backend/core/legacy/pad/anti_spoof_predict.py:2-6` | Cabeçalho Minivision | Remover bloco |
| `src/backend/core/legacy/pad/model_lib/MiniFASNet.py:2-6` | Cabeçalho Minivision | Remover bloco |
| `src/backend/core/legacy/pad/data_io/transform.py:2-6` | Cabeçalho Minivision | Remover bloco |
| `src/backend/core/legacy/pad/data_io/functional.py:2-6` | Cabeçalho Minivision | Remover bloco |

### 1.2 TODO / Placeholders

| Arquivo | Problema | Ação |
|---|---|---|
| `src/backend/core/plugins/deepfake_adapter.py:63` | `# TODO: Load actual InsightFace model` | Reescrever para explicar limitação atual |
| `src/backend/core/plugins/deepfake_adapter.py:114` | `note: "Pipeline completo implementado. Substituir placeholders..."` | Reescrever mensagem |

### 1.3 Instruções pessoais / CLI residual de notebook

| Arquivo | Problema | Ação |
|---|---|---|
| `src/backend/core/legacy/audio/wav_ima_adpcm.py:314-315` | `Coloque o nome do seu arquivo WAV aqui` + nome real | Remover comentário e neutralizar constante |
| `src/backend/core/legacy/audio/mp3_parser.py:828-829` | `👇 Insira o nome do seu arquivo MP3 aqui` + nome real | Remover comentário e neutralizar constante |
| `src/backend/core/legacy/audio/opus_parser.py:915-916` | `👇 Insira o nome do seu arquivo aqui` + nome real | Remover comentário e neutralizar constante |

### 1.4 Marcações temporais / exportação de notebook

| Arquivo | Problema | Ação |
|---|---|---|
| `src/backend/core/legacy/patchmatch/postprocessing.py:1,6,12,18,24,31` | `# Conteúdo para o arquivo: postprocessing.py` | Remover |
| `src/backend/core/legacy/patchmatch/postprocessing.py:29` | `# --- NOVA IMPORTAÇÃO ---` | Remover marcação |
| `src/backend/core/legacy/patchmatch/postprocessing.py:93` | `# --- LÓGICA CORRIGIDA ---` | Remover marcação |
| `src/backend/core/legacy/patchmatch/postprocessing.py:167` | `# --- LÓGICA DE FILTRAGEM MODIFICADA ---` | Remover marcação |
| `src/backend/core/legacy/patchmatch/patchmatch.py:470-471` | Código comentado obsoleto | Remover |

### 1.5 Outros

| Arquivo | Problema | Ação |
|---|---|---|
| `src/backend/core/legacy/resampling/resampling.py:19` | `#!pip install jupyter_bbox_widget --proxy http://proxy.ditec.pf.gov.br:3128` | Remover comando com proxy |
| `src/backend/core/legacy/safire/safire_runtime.py:13` | Link informal para Google Drive oficial | Reescrever de forma neutra |
| `src/backend/core/legacy/audio/wav_ima_adpcm.py:140,150` | `>>>>> INÍCIO DA CORREÇÃO / FIM DA CORREÇÃO <<<<<` | Remover marcações |

---

## 2. Textos de Frontend Problemáticos

### 2.1 Termos em inglês não-técnico

| Arquivo | Texto atual | Sugestão |
|---|---|---|
| `pages/Dashboard.tsx:20` | `Dashboard` | `Painel` |
| `components/Layout.tsx:22` | `Auto` | `Automático` |
| `components/Layout.tsx:55` | `Layout` | `Disposição` |
| `components/FileListSortToggle.tsx:29` | `Upload` | `Envio` |
| `pages/AudioForensicsHub.tsx:821` | `Customizada` | `Personalizada` |
| `pages/PDFStructureMetricsAnalysis.tsx:147` | `Layout: {result.layout_engine}` | `Motor de layout:` |

### 2.2 Mistura pt-en / termos técnicos expostos

| Arquivo | Texto atual | Sugestão |
|---|---|---|
| `pages/CopyMovePcaAnalysis.tsx:170` | `Alpha mask` | `Máscara alfa` |
| `pages/NoiseprintAnalysis.tsx:67` | `Mascara valid` | `Máscara válida` |
| `pages/NoiseprintAnalysis.tsx:69` | `Overlay valid` | `Sobreposição válida` |
| `pages/NoiseprintAnalysis.tsx:70` | `Overlay heatmap blind` | `Sobreposição do mapa de calor` |
| `pages/PatchMatchAnalysis.tsx:233` | `Campo vect` | `Campo vetorial` |
| `pages/PatchMatchAnalysis.tsx:245` | `dist_field` | `Campo de distância` |
| `components/VideoPlayer.tsx:90` | `fps ref. {fps}` | `fps de referência: {fps}` |
| `pages/FakeVlmAnalysis.tsx:174` | `... consome VRAM` | `... consome memória de vídeo` |
| `pages/ZeroGridAnalysis.tsx:212` | `Nenhuma grade JPEG global detectada (main_grid = -1).` | `Nenhuma grade JPEG global detectada.` |

### 2.3 Inconsistências ortográficas (acentos)

| Arquivo | Texto atual | Sugestão |
|---|---|---|
| `components/Layout.tsx:45` | `Usuarios` | `Usuários` |
| `components/AnalysisPageShell.tsx:64` | `Navegacao` | `Navegação` |
| `components/AnalysisPageShell.tsx:69` | `Analises` | `Análises` |
| `components/FileListSortToggle.tsx:24` | `Ordenacao` | `Ordenação` |
| `pages/NoiseprintAnalysis.tsx:160` | `Execucao` | `Execução` |
| `pages/SafireAnalysis.tsx:164` | `Localizacao binaria` | `Localização binária` |
| `pages/ClipBasedAnalysis.tsx:290` | `Classificacao` | `Classificação` |
| `pages/FakeVlmAnalysis.tsx:246` | `Classificacao` | `Classificação` |
| `pages/PresentationAttackDetectionAnalysis.tsx:263` | `Classificacao` | `Classificação` |
| `pages/DistilDireAnalysis.tsx:230` | `Classificacao` | `Classificação` |
| `components/PeritusFilesPanel.tsx:138` | `Analises e Derivados` | `Análises e Derivados` |
| `pages/CaseDetail.tsx:702` | `Analises` | `Análises` |
| `pages/SyntheticImageDetectionAnalysis.tsx:556` | `Analises a executar` | `Análises a executar` |
| `utils/caseAnalysisNav.ts:82` | `aba Analises` | `aba Análises` |
| `pages/ImdlBencoHub.tsx:192` | `Hub de Localizacao` | `Hub de Localização` |

### 2.4 Textos de teste expostos

| Arquivo | Problema | Ação |
|---|---|---|
| `config/forensicTechniqueMeta.ts:319` | `mock_technique: "Técnica de Teste"` | Remover do registro visível |
| `utils/caseAnalysisNav.ts:94` | `mock_technique` em conjuntos ocultos | Remover se não necessário |
| `components/TechniqueConfig.tsx:19` | `mock_technique: {}` | Remover configuração de teste |

### 2.5 Placeholders / labels confusos

| Arquivo | Texto atual | Sugestão |
|---|---|---|
| `pages/Analysis.tsx:56` | `placeholder="UUID da evidência"` | `placeholder="ID da evidência"` |
| `pages/Upload.tsx:46` | `placeholder="UUID do caso"` | `placeholder="ID do caso"` |
| `pages/CopyMovePcaAnalysis.tsx:146-149` | Labels em inglês | Traduzir labels |

---

## 3. Documentação Markdown Problemática

### 3.1 Referências ao assistente / ferramentas de IA

| Arquivo | Problema | Ação |
|---|---|---|
| `docs/MIGRATION-GPU.md` | Múltiplas menções a "Kimi" e diálogos com assistente | Reescrever como instruções neutras |
| `knowledge/fase6_execution_report.md:4` | `**Responsável:** Kimi Code CLI` | `**Responsável:** Equipe de Engenharia ForensicAuth` |
| `knowledge/architecture.md:10` | `Autor: Repository Intelligence / Kimi Code CLI` | `Autor: ForensicAuth Team` |
| `knowledge/final_audit_2026-06-25.md:4-5` | Metadado de comando `/revisar-analise` | Remover |
| `knowledge/final_gates.md:1` | `Final Gates — ForensicAuth Repository Intelligence` | `Final Gates — ForensicAuth` |
| `docs/specs/TEMPLATE-SPEC.md:6` | Path de skill externa | Remover referência |

### 3.2 Nome antigo do projeto (`VA Suite`)

| Arquivo | Problema | Ação |
|---|---|---|
| `docs/deploy/WORKER-REMOTE.md` | Paths `~/VA Suite/`, `/home/bfl-pcf/VA Suite/`, `va-suite` env | Substituir por `forensicauth` |
| `docs/references/papers/imdl/README.md:3` | `ID da técnica no VA Suite` | `ID da técnica no ForensicAuth` |
| `docs/references/papers/imdl/manifest.json:2` | `integradas no VA Suite` | `integradas no ForensicAuth` |
| `docs/specs/modules/12-module-case-transfer.md:7` | `VCP (VA Case Package)` | `VCP (Verification Case Package)` |
| `knowledge/data_catalog.md:44` | `` `va` or `peritus` `` | `` `forensicauth` or `peritus` `` |
| `knowledge/domain_model.md:29,90` | `storage_mode (va ou peritus)` / `Analista` | Atualizar para `forensicauth` e confirmar papel |

### 3.3 Menções a cliente / órgão

| Arquivo | Problema | Ação |
|---|---|---|
| `docs/specs/00-overview.md:5` | `peritos criminais da Policia Federal` | `peritos criminais` |
| `docs/specs/00-overview.md:90` | `servidor corporativo da PF` | `servidor corporativo da instituição` |
| `docs/specs/01-architecture.md:218` | `servidor corporativo da PF` | `servidor corporativo da instituição` |
| `docs/specs/modules/10-module-reports.md:12,82,102` | `padrao_pf`, `logo PF` | `padrao_institucional`, `logo` |
| `knowledge/architecture.md:15` | `peritos criminais (Polícia Federal)` | `peritos criminais da instituição cliente` |

### 3.4 Dados de ambiente específico

| Arquivo | Problema | Ação |
|---|---|---|
| `docs/deploy/WORKER-REMOTE.md:26-29,39,63-66` | IP `10.61.242.242`, usuário `bfl-pcf`, path `/home/bfl-pcf/VA Suite`, credenciais `postgres:postgres` | Generalizar com placeholders |
| `docs/MIGRATION-GPU.md:120` | `NVIDIA RTX 3090` | `<MODELO_GPU>` |
| `docs/MIGRATION-GPU.md:171` | `No seu notebook Windows (agora)` | `No ambiente de desenvolvimento atual` |
| `docs/public/INSTALACAO-PRODUCAO-LINUX.md:270` | `username além de paulo.pmgir` | `username padrão` |
| `docs/public/INSTALACAO-PRODUCAO-LINUX.md:91` | `github.com/SEU_ORGANIZACAO/forensicauth.git` | `<URL_DO_REPOSITORIO>` |
| `scripts/nfs-exports.example` | Paths `/home/bfl-pcf/VA Suite/*` e rede `10.61.242.0/24` | Substituir por `/opt/forensicauth/*` e `<WORKER_SUBNET>` |
| `scripts/dev-stack.sh` | Título `VA Suite dev stack` | `ForensicAuth dev stack` |
| `scripts/diagnose_gpu.py` | Referências ao "Kimi assistant" no docstring e rodapé | Reescrever de forma neutra |
| `scripts/start-postgres-dev.ps1` | Path fallback `C:\Users\Paulo\miniconda3` | `C:\Users\<USER>\miniconda3` |
| `scripts/prepare-worker-bundle.sh` | Exemplo com usuário/perito, IP e path `VA Suite` | Placeholders genéricos |

### 3.5 Referências externas indevidas

| Arquivo | Problema | Ação |
|---|---|---|
| `docs/specs/modules/13-module-pad.md:5` | `baseada no modelo open source` | `utiliza o modelo open source` |
| `docs/specs/modules/07-module-audio.md:14-19` | `interface_gradio_Paulo.ipynb` | `notebook legado de análise de áudio` |

### 3.6 Informação obsoleta / contraditória

| Arquivo | Problema | Ação |
|---|---|---|
| `knowledge/final_audit_2026-06-25.md:10-11,48,133` | Snapshot obsoleto do working tree, ausência de catálogos e baseline | Atualizar ou remover |
| `knowledge/health_report_2026-06-25.md:28` | Discussão de scores conflitantes | Simplificar |
| `knowledge/domain_model.md:21,90` | `Analista (legacy; sendo migrado)` | Confirmar status atual |

---

## 4. Plano de Correção

### 4.1 Comentários de código (22 arquivos)

Ações:
1. Remover cabeçalhos de autoria/instituição.
2. Reescrever TODO de `deepfake_adapter.py`.
3. Neutralizar blocos `__main__` em parsers de áudio.
4. Remover marcações temporais em `patchmatch`.
5. Remover proxy institucional em `resampling.py`.
6. Reescrever comentário externo em `safire_runtime.py`.

### 4.2 Frontend (30+ arquivos)

Ações:
1. Traduzir labels em inglês não-técnico.
2. Corrigir acentos em labels (`Usuários`, `Análises`, `Classificação`, etc.).
3. Simplificar labels técnicos (`Alpha mask` → `Máscara alfa`).
4. Remover `mock_technique` dos registros visíveis.
5. Ajustar placeholders (`UUID` → `ID`).

### 4.3 Documentação markdown (15+ arquivos)

Ações:
1. Reescrever `docs/MIGRATION-GPU.md` em tom institucional neutro.
2. Substituir `VA Suite` → `ForensicAuth` onde for nome do produto.
3. Remover/neutralizar menções a PF, Kimi, dados de ambiente.
4. Atualizar `final_audit_2026-06-25.md` para refletir estado atual.
5. Corrigir `interface_gradio_Paulo.ipynb` e `baseada no`.

---

## 5. Score de Higiene

| Área | Antes | Depois (estimado) |
|---|---|---|
| Comentários | 50 | 90 |
| Frontend | 55 | 80 |
| Documentação | 60 | 85 |
| **Geral** | **55** | **85** |

---

## 6. Aprovação e Aplicação

O usuário aprovou o modo **"Relatório + Correções"** e, em seguida, a opção **"Aplicar Tudo"**. Todas as correções listadas neste relatório foram aplicadas, incluindo as adicionais identificadas durante a validação residual em `scripts/`.

## 7. Validação

- **Sintaxe frontend:** verificação básica de balanceamento de chaves/aspas nos arquivos `.ts`/`.tsx` alterados — sem erros óbvios.
- **Type-check / lint / testes de frontend:** não executados porque o Node.js disponível é o binário Windows (`tools/node-v20.14.0-win-x64/node.exe`). Devem ser rodados em ambiente Node/Linux antes do merge.
- **Testes de backend:** baseline unitária concluída com sucesso.
  - `conda run -n va-suite python scripts/run_test_baseline.py`
  - **Resultado:** 461 passed, 0 failed, 5 skipped, 0 error
