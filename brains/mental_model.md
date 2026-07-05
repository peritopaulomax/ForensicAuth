# Mental Model — ForensicAuth

**Atualizado:** 2026-07-04

## O que é

Laboratório forense digital em uma caixa:
- **Casos** = pastas de investigação
- **Evidências** = itens selados com SHA-256
- **Jobs** = exames técnicos em fila
- **Cadeia de custódia** = logbook imutável e assinado
- **Detectores ML** = especialistas que **podem discordar** — o perito interpreta

## Camadas de mídia no frontend

| Mídia | UX |
|---|---|
| Imagem | Hubs `image-group/:groupId` (clássicas, DL manipulação, sintético, biometria) |
| Áudio espectral | `AudioForensicsHub` (ENF, espectrograma, níveis) |
| Áudio spoofing | `AudioSpoofingAnalysis` (DF Arena, SLS, WeDefense) |
| Vídeo/PDF | Páginas dedicadas por técnica |

## O que não versionar no Git

- `models/` — pesos (dezenas de GB)
- `outputs/` — calibração LR, caches joblib
- `uploads*`, `results*`, `peritus_cases*`
- Binários >100 MB (limite GitHub)

## Regras de ouro

1. Toda evidência tem hash antes do processamento.
2. Cadeia de custódia é INSERT-only.
3. Jobs GPU rodam serializados.
4. Legados forenses intocáveis sem teste de equivalência (AGENTS.md).
5. Paridade com autores ≠ consenso entre detectores.

## Fluxo mental spoofing áudio

```text
Áudio → resample 16 kHz mono → janelas 4s
  → cada detector → spoof_prob / bonafide_prob
  → tabela + gráfico temporal
  (sem fusão automática ainda)
```

## O que pode quebrar

PostgreSQL, Redis, storage, pesos não baixados, Git LFS/submódulos, interpretação errada de multi-detector.
