# Executive Summary — ForensicAuth

**Atualizado:** 2026-07-04 (Repository Intelligence)

## O que é

Plataforma forense digital unificada para peritos criminais analisarem imagem, áudio, vídeo e PDF, com cadeia de custódia rastreável e laudos.

## O que entrega

- Gestão de casos periciais
- Upload de evidências com SHA-256
- Análises forenses assíncronas (CPU/GPU)
- Cadeia de custódia SHA-256 + Ed25519
- Derivados, laudos PDF (planejado) e verificação forense
- Integração Peritus Desktop e VCP
- **Novo (jul/2026):** hub multi-detector de spoofing de áudio; calibração LR para imagens sintéticas

## Como funciona

React SPA → FastAPI → Services → PostgreSQL/Redis/FS
                  ↓
          Celery Workers → Plugins → Legacy/Vendor/ML

## Componentes principais

| Componente | Papel |
|---|---|
| FastAPI | API REST |
| React | Interface do perito (hubs por grupo de imagem, áudio espectral vs spoofing) |
| PostgreSQL | Estado e custódia |
| Redis | Fila e lock GPU |
| Celery | Jobs assíncronos |
| Plugins (~35 ativos) | Adapters forenses |
| GPU Worker | Inferência ML serializada |

## Fluxos críticos

| Fluxo | Entrada | Saída |
|---|---|---|
| Upload | `POST /evidences/upload` | Evidence + CustodyRecord |
| Análise | `POST /analysis` | AnalysisJob → resultado |
| Spoofing áudio | `audio_spoofing_detection` | Vetor de scores por detector |
| Sintético + LR | `synthetic_image_detection` | Scores + LR calibrado (opcional) |
| Derivado | `POST /evidences/derivatives` | Evidence derivada |
| Verificação | `GET /audit/verify-case-forensic/*` | Relatório de integridade |

## Top 5 riscos (jul/2026)

1. **GitHub/pesos:** artefatos >100 MB ou LFS >2 GB bloqueiam push; pesos devem ficar locais
2. GPU singleton (gargalo de throughput ML)
3. `torch.load(weights_only=False)` em pipelines legados
4. Credenciais padrão / SECRET_KEY fraco em dev
5. Detectores ML discordam (spoofing áudio, sintético) — interpretação pericial necessária

## Top 5 dívidas

1. Laudos PDF não implementados (spec RN-07)
2. Testes de regressão forense / golden parity ausentes
3. DeeCLIP implementado mas fora do ensemble sintético
4. Validações caso fechado / tipo de mídia incompletas
5. Observabilidade ausente

## Confiabilidade

Alta no backend e arquitetura de custódia; média no ML/legados e frontend; atenção em Git hygiene e interpretação multi-detector.

## Onde ler mais

| Camada | Arquivo |
|---|---|
| Knowledge | `knowledge/repository_map.md`, `knowledge/audio_spoofing_pipeline.md` |
| Divergências | `knowledge/divergence_report_2026-07-04.md` |
| Summaries | `summaries/backend_summary.md`, `summaries/ml_forensic_summary.md` |
| Brain | `brains/system_brain.md`, `brains/critical_paths.md` |
