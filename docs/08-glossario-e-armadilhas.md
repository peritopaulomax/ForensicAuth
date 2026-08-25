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

## Armadilhas operacionais e de desenvolvimento

| Armadilha | Sintoma / detecção | Recuperação | Risco residual |
|-----------|--------------------|------------|----------------|
| UUID tratado como autorização | Outro perito acessa job/artefato por `job_id` | Aplicar `get_accessible_job` e testar com dois peritos | Crítico até corrigir todas as rotas |
| Custódia PostgreSQL só por convenção | `UPDATE custody_records` funciona com a role da aplicação | Trigger/`REVOKE` + teste de integração | DBA continua trust boundary |
| Compose padrão sem worker GPU | Job ML fica `pending` | Subir `docker-compose.gpu.yml` ou worker `-Q gpu -c 1` | Pesos/CUDA ainda podem faltar |
| SQLite ou falha Celery usa uvicorn | API lenta ou VRAM presa na API | Identificar PID e reiniciar o processo detentor | Job interrompido precisa diagnóstico |
| Clone Git incompleto para ML | Técnica indisponível, vendor/peso ausente | Provisionar upstream homologado e conferir hash | Upstream pode mudar/desaparecer |
| Seis gitlinks sem `.gitmodules` | `git submodule update` falha | Usar manifesto/procedimento institucional | Bootstrap ainda não é reprodutível |
| Health interpretado como smoke completo | `/health` verde, mas DB/Redis/worker falham | Testar login, upload e job real | Falhas condicionais permanecem |
| Backup só do banco ou só dos arquivos | Metadados órfãos ou bytes sem vínculo | Restaurar DB+FS+chaves no mesmo ponto e verificar cadeia | Perda sem snapshot íntegro |
| `cache_clear()` tratado como purge VRAM | Memória CUDA não volta | mover modelo para CPU, liberar refs, `empty_cache` | Bibliotecas podem manter refs |
| ID do frontend divergente do backend | card some, 404 ou fila errada | comparar registry com `/analysis/techniques` e `ML_GPU_TECHNIQUES` | Dupla manutenção |
| “Offline” assumido antes do bootstrap | download/font/model falha em air-gap | provisionar vendors/pesos/referências e self-host fonts | Licenças e atualização manual |
| Comando pytest sem `PYTHONPATH` | imports `app/core/services` falham | usar o comando canônico do capítulo 10 | Dependências opcionais seguem fora |

## Como reagir a incidente forense

1. Preserve logs, banco e filesystem antes de “corrigir”.
2. Não reescreva hashes ou assinaturas para fazer a cadeia voltar a passar.
3. Identifique se o job rodou no worker ou no uvicorn.
4. Restaure uma cópia consistente e execute a verificação forense.
5. Registre versão, parâmetros, hashes e ação de recuperação.

## Próximo

[10 — Testes](10-testes-e-qualidade.md) · índice [README](README.md)
