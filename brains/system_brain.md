# System Brain — ForensicAuth

**Atualizado:** 2026-07-04

## Arquitetura em 60 Segundos

```text
Perito/Admin → React SPA → FastAPI → Services → PostgreSQL/Redis/FS
                                    ↓
                           Celery Workers → Plugins → Legacy/Vendor/Models
```

## Componentes Críticos

| Componente | Tier | Função |
|---|---|---|
| FastAPI App | 0 | API, lifespan, routers |
| PostgreSQL | 0 | Estado e cadeia de custódia |
| Redis | 0 | Fila Celery, backend, lock GPU |
| Filesystem | 0 | uploads, results, derivatives, models (local) |
| CustodyService | 0 | Cadeia SHA-256 + Ed25519 |
| JobService | 0 | Jobs e reproducibilidade |
| PluginRegistry | 1 | ~35 adapters ativos |
| GPUInference | 1 | Filas CPU/GPU, serialização |
| synthetic_lr_reference | 1 | Meta-LR calibrado (imagens sintéticas) |
| audio_spoofing pipeline | 1 | Hub DF Arena + SLS + WeDefense |
| React SPA | 1 | Hubs image-group, áudio, PDF, vídeo |

## Fluxos Críticos

1. **Upload** → SHA-256 → `Evidence` + `CustodyRecord`
2. **Análise imagem sintética** → ensemble GPU → scores + LR opcional
3. **Análise spoofing áudio** → 3 detectores CPU → scores independentes
4. **Derivado** → `Evidence` derivada + provenance + `CustodyRecord`
5. **Verificação forense** → cadeia + arquivos + assinaturas
6. **Login** → JWT HS256

## Dependências Críticas

PostgreSQL 15, Redis 7, PyTorch/CUDA 12.4, filesystem local, jpegio, PyMuPDF, librosa, fairseq (SLS), transformers (DF Arena).

## Dados Críticos

| Dado | Onde | Risco |
|---|---|---|
| CustodyRecord | PostgreSQL | Imutabilidade PG pendente |
| Evidence | PostgreSQL + FS | Perda de FS = perda de evidência |
| Modelos | `models/` (gitignored) | ~43+ GB, download manual |
| LR reference matrix | `outputs/` (gitignored) | Não clonável sem recompute |
| AnalysisJob | PostgreSQL | Não gera custódia |

## Top 10 Riscos (jul/2026)

1. Commit acidental de pesos/outputs (>100 MB / >2 GB LFS)
2. GPU singleton / lock distribuído
3. `torch.load(weights_only=False)` em pipelines legados
4. PostgreSQL único
5. Credenciais padrão docker-compose
6. Modelos não versionados com checksum
7. Imutabilidade cadeia (trigger SQLite vs PG)
8. JWT em localStorage
9. Discordância entre detectores ML (não é bug)
10. Observabilidade ausente

## Top 10 Dívidas (jul/2026)

1. Laudos PDF não implementados
2. Testes regressão forense / golden parity
3. DeeCLIP fora do ensemble sintético
4. Modo "compatível autores" para spoofing áudio
5. Frontend páginas grandes + rotas legadas
6. Observabilidade ausente
7. Submódulos vendor com LFS frágil
8. Cobertura frontend baixa
9. Migrations ad-hoc + Alembic
10. Validações domínio (caso fechado, media type)

## Decisões Chave

- Monólito modular; plugins preservam legados forenses
- Pesos e experimentos **fora do Git** (scripts download + `.gitignore`)
- Jobs = previews; custódia em upload/derivado/fechamento
- Multi-detector sem meta-fusão ainda (spoofing e sintético parcial)

## Roadmap Imediato

1. Push limpo (só código) — `.gitignore` reforçado
2. Golden parity áudio (ASVspoof)
3. Integrar DeeCLIP ou marcar experimental
4. Laudos PDF
5. Observabilidade + checksums de modelos
