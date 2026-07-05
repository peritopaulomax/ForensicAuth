# Infra Summary — ForensicAuth

**Atualizado:** 2026-07-04

## Deploy

Docker Compose: `docker-compose.yml` (CPU), `docker-compose.gpu.yml`, `docker-compose.dev.yml`

Roles: `FORENSICAUTH_PROCESS_ROLE` = api | worker-cpu | worker-gpu

## Ambiente dev

- Conda: `va-suite` (Python 3.11)
- Scripts: `scripts/dev-stack.sh`, `scripts/dev-lan.sh`
- Postgres/Redis via compose dev

## Storage local (gitignored)

| Path | Conteúdo |
|---|---|
| `uploads-dev/` | Evidências upload |
| `results-dev/` | Artefatos jobs |
| `models/` | Pesos ML (~43+ GB) |
| `outputs/` | Calibração LR, caches |
| `peritus_cases/` | Casos Peritus Desktop |

## Git hygiene (jul/2026)

**.gitignore reforçado:**
- `outputs/`, `models/`, `*.joblib`, `*.bin`, `*.safetensors`
- `Legados/**/pytorch_model.bin` (DF Arena 4GB)
- `vendor/**/runs/`, `vendor/**/*.mp4`
- Lixo pip root: `-`, `=0.7.0`

**Limites GitHub:**
- 100 MB/arquivo (Git normal)
- 2 GB/arquivo (LFS)
- Nunca commitar calibração LR ou pesos

## Git LFS

Instalar system-wide: `sudo apt install git-lfs && git lfs install`

Submódulos vendor podem exigir LFS (`grip_clipbased_synthetic`).

## Workers remotos

`scripts/prepare-worker-bundle.sh`, `docs/deploy/WORKER-REMOTE.md`

## Riscos infra

| Risco | Mitigação |
|---|---|
| Push rejeitado por arquivo grande | .gitignore + git rm --cached |
| git-lfs not found (Cursor) | PATH / apt install |
| Submodule LFS tmp errors | GIT_LFS_SKIP_SMUDGE para status |
| Credenciais default compose | Trocar em produção |
| GPU worker ausente no compose base | Usar gpu compose |

## CI/CD

Testes via pytest + Playwright; sem pipeline CI documentado no repo (dívida)
