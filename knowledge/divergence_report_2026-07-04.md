# Divergence Report — 2026-07-04

## Missão
Registrar divergências entre código, specs, documentação e operação (Repository Intelligence).

## Gate de Qualidade
Discovery concluído com evidências de código + testes + operação Git.

---

## 1. Git / Repositório vs Operação

| Item | Esperado | Observado | Severidade |
|---|---|---|---|
| Pesos ML no Git | Não commitar | Commit anterior incluía `pytorch_model.bin` (4.6 GB) e `outputs/` (>100 MB) | **Crítico** |
| `.gitignore` | Cobrir outputs/models | Reforçado em jul/2026; `outputs/`, `*.joblib`, `*.bin`, vendor runs | Resolvido localmente |
| GitHub LFS | Max 2 GB/arquivo | DF Arena rejeitado com 422 | **Alto** |
| GitHub normal | Max 100 MB/arquivo | CSV/joblib de calibração LR rejeitados | **Alto** |
| Submódulo `vendor/grip_clipbased_synthetic` | LFS funcional | `git status` falha se LFS tmp indisponível | Médio |

**Ação:** manter pesos e artefatos de experimento **fora do Git**; usar `scripts/download_*.py`.

---

## 2. Specs vs Implementação

| Spec / RN | Divergência | Confiança |
|---|---|---|
| RN-07 Laudos PDF imutáveis | `ReportService` não implementado | Alta |
| RN-04 GPU serializado | `audio_spoofing_detection` roda na fila CPU | Média |
| Overview: áudio MP3/Opus parsers | Plugins em `STANDBY_PLUGIN_NAMES` | Alta |
| Overview: deepfake imagem Effort | Integrado no ensemble sintético via warmup GPU, não como plugin standalone ativo | Média |

---

## 3. Documentação vs Código (Knowledge Layer)

| Doc antigo | Realidade jul/2026 |
|---|---|
| `ml_forensic_summary`: deepfake_similarity GPU | `deepfake_similarity` em STANDBY; Effort no warmup/ensemble |
| `system_brain`: ~22 pipelines torch.load inseguro | Ainda válido; DeeCLIP adicionado com runtime próprio |
| Ensemble sintético "4 detectores" | HF×2 + B-Free + Corvi2023 + SAFE + LR opcional; DeeCLIP/CLIDE infra sem ensemble |
| Áudio spoofing ausente na knowledge | Hub multi-detector implementado |

---

## 4. Frontend vs Backend

| Área | Divergência |
|---|---|
| Rotas legadas `/analysis/ela` etc. | Redirecionam para `image-group/:groupId` — OK |
| Hub IMDL `/analysis/imdlbenco` | Rota removida; redirect para tab |
| `audio_spoofing` | Página dedicada; não confundir com `AudioForensicsHub` (espectral) |

---

## 5. ML / Forense

| Tópico | Divergência | Impacto |
|---|---|---|
| Spoofing áudio: concordância entre detectores | Não esperada; modelos independentes | Percepção de "resultado errado" |
| Spoofing: protocolo VA vs autores | Janelas + média logits vs clipe único | Scores diferentes em áudio >4 s |
| LR sintético | Matriz de referência em `outputs/` (local) | Não reprodutível em clone limpo sem recompute |
| DeeCLIP | Pipeline + testes; **não** no ensemble `synthetic_image_detection` | Feature incompleta |

---

## 6. Testes vs Cobertura

| Gap | Evidência |
|---|---|
| Paridade numérica áudio vs autores | Testes smoke apenas; sem golden files ASVspoof |
| Regressão forense legados | Ainda ausente (dívida histórica) |
| Frontend Vitest | ~26 testes; cobertura baixa |
| E2E áudio spoofing backend | Integration only; sem pytest e2e dedicado |

---

## Recomendações Prioritárias

1. **Operação:** push apenas código; nunca `outputs/`, `models/`, pesos >100 MB.
2. **Áudio:** modo "compatível autores" (1 clipe 64600) como opção de parâmetro.
3. **Sintético:** integrar DeeCLIP ao ensemble ou documentar como experimental.
4. **Testes:** golden parity script para 3 detectores de áudio com ASVspoof LA.
5. **Submódulos:** auditar LFS em `vendor/grip_clipbased_synthetic`.

## Evidências

- Auditoria Git jul/2026 (push 422)
- `knowledge/audio_spoofing_pipeline.md`
- Subagent explore backend/frontend
- `tests/integration/test_audio_spoofing_multi.py`
