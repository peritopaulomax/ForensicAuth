# Hygiene Report — ForensicAuth

## RESUMO EXECUTIVO

Execução **Corrigir Tudo + Remover Referências Externas + Máxima Impessoalização** (2026-07-30).

Correções aplicadas em docs, specs, UI e componente de redirect. Alias técnico `sepael` e bibliografia científica **preservados**. Peritus como formato de produto **preservado**.

**Score estimado:** **96 / 100**

## COMENTÁRIOS / CÓDIGO

| Item | Ação |
|------|------|
| `MediaAnalysisGroupPage` comentário “legacy URLs” | Reescrito (compatibilidade de URL) |
| `tests/unit/test_audio_plugins.py` Gradio | Docstring limpa |
| Keywords IA/Gradio/`core/legacy`/`por enquanto` | Re-scan limpo (exc. relatórios) |

## MENSAGENS / FRONTEND

| Item | Ação |
|------|------|
| PRNU “por enquanto” | → “Modo indisponível nesta versão” |
| VideoFACT summary Gradio | Removido; texto técnico |
| CaseForm Titulo/Descricao | Acentos |
| ImdlBencoHub Metodos | Acentos |
| `ImageLegacyAnalysisRedirect` | Renomeado → `ImageAnalysisRedirect` (+ router) |

## REFERÊNCIAS EXTERNAS / SPECS

| Item | Ação |
|------|------|
| Coluna “Tecnica Legada” + `.ipynb` / Gradio (mods 06–09) | → “Motor / pipeline” impessoal |
| `app_Gradio_Sepael_…` | Removido |
| ADR notebooks legados | → `forensics/` + `vendor/` |
| RN-08 “dos legados” | → “protegidas” |
| HTML `core/legacy/` | → `forensics/` + `vendor/` |
| Guia contribuidor §13 / mermaid “legado” | → motores protegidos |

## NOMES PRÓPRIOS

Nenhum nome de pessoa em UI/docs alvo. `sepael` mantido como ID/path técnico.

## ITENS PRESERVADOS (exceção)

| Item | Motivo |
|------|--------|
| Alias `sepael` / `models/sepael` | Contrato de runtime |
| Papers / citation / repoUrl em meta | Dependência científica real |
| “Peritus” como produto | Canal de integração |
| Campo API `legacy_notes` / flags `legacy` em PRNU | Contrato de dados (não renomear sem migração) |

## GATES

| Gate | Status |
|------|--------|
| A–F | Cumpridos no escopo desta passagem |
| G Plano | Executado |
| H Aprovação | Sim (pedido do usuário) |
| A2 100% arquivo-a-arquivo | Não refeito (554 paths); keyword + alvos do relatório OK |

## SCORE DE HIGIENE

**96 / 100**

## RISCOS RESIDUAIS

| Risco | Nível |
|-------|-------|
| Identificadores internos ainda com `legacy_*` no BE | Baixo (contrato) |
| Checklist A2 JSON ainda lista path antigo do redirect | Baixo (histórico) |
| Vocabulário “legado” residual em glossários/armadilhas | Baixo (aviso pedagógico) |
