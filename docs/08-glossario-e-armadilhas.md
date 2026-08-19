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
| **Standby plugin** | Código no disco, fora do registry ativo |



## Próximo

[10 — Testes](10-testes-e-qualidade.md) · índice [README](README.md)
