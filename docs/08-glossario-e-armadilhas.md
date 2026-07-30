# 08 — Glossário e armadilhas

## Glossário

| Termo | Significado |
|-------|-------------|
| **Caso (Case)** | Container com número protocolar |
| **Evidência** | Arquivo + metadados + SHA-256 |
| **Job / AnalysisJob** | Execução de uma técnica (preview exploratório) |
| **Plugin / Técnica** | Implementação de `ForensicPlugin` registrada |
| **Custódia** | Cadeia INSERT-only de elos oficiais (não a cada job) |
| **Derivado** | Nova evidência gerada a partir de outra |
| **LR** | Likelihood ratio calibrado vs população em `reference_data/` |
| **Typicality** | Quão “típica” é a amostra no espaço latente |
| **VCP** | Verification Case Package (`.vcp.zip`) — transferência entre instâncias ForensicAuth |
| **Peritus** | Pacote legado ZIP+XML; bridge materializa em `data/peritus_cases/` |
| **Hub de áudio** | UI `__audio_hub__` / card `audio-forense` — várias técnicas `audio_*` num só fluxo |
| **PAD / MoE-FFD** | Detecção facial (spoof / forgery) |
| **Standby plugin** | Código no disco, fora do registry ativo |

## Armadilhas

| Armadilha | Realidade |
|-----------|-----------|
| “Existe role analista” | Só `admin` / `perito` + **shares** |
| “Todo job grava custódia” | Não — só upload, derivado, lifecycle, import |
| “Há laudo PDF oficial” | **Fora de escopo** do produto |
| “Adapters em `adapters/`” | São `core/plugins/` |
| “Calibração em `config/*.yaml`” | Publicada em **`reference_data/`** |
| “Pasta `ops/` no mapa do projeto” | Removida — use Compose / `scripts/technique/` |
| “VCP e Peritus são a mesma coisa” | Canais **diferentes**; `peritus_cases/` é só o bridge legado |
| “Dois cards de análise espectral / níveis” | Um card `audio-forense` → hub unificado |

## Próximo

[10 — Testes](10-testes-e-qualidade.md) · índice [README](README.md)
