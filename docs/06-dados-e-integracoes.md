# 06 — Dados e integrações

## Visão dos stores

| Store | Conteúdo | Path / serviço |
|-------|----------|----------------|
| PostgreSQL | Metadados, jobs, custódia, shares, closures | Compose `db` / `DATABASE_URL` |
| Filesystem | Binários forenses | `data/uploads`, `results`, `derivatives`, `peritus_cases` |
| Redis | Filas Celery + lock GPU | broker (efêmero) |
| models/ | Pesos | montado no container |
| reference_data/ | Populações LR / typicality (calibração) | montado no container |

> Calibração **não** vive em YAMLs de protocolo sob `config/`. Ativos publicados ficam em `reference_data/`.

## Modelo mental de entidades

```mermaid
erDiagram
  User ||--o{ Case : cria
  Case ||--o{ Evidence : contem
  Evidence ||--o{ AnalysisJob : gera
  Case ||--o{ CustodyRecord : cadeia
  Case ||--o{ CaseShare : compartilha
  Case ||--o{ CaseClosure : fecha
```

## Ciclo de vida dos arquivos

```text
Upload  → data/uploads + Evidence + custody evidence_upload
Job     → data/results/{case}/{evidence}/{job}/
Promote → data/derivatives + Evidence + custody derivative_saved
Peritus → ZIP legado → data/peritus_cases/{case_id}/ (workspace + binding)
VCP     → pacote .vcp.zip nativo (export/import entre instâncias ForensicAuth)
```

Soft-delete de caso/evidência **não** apaga a cadeia de custódia.

**Peritus ≠ VCP.** São canais distintos (`peritus_bridge_service` vs `case_transfer_service`). O diretório `data/peritus_cases/` é o workspace do bridge legado do Peritus (cópia/extração do ZIP), não o destino do VCP.

## Migrações

- Alembic: `alembic/` + `alembic.ini`  
- Revision bootstrap: `alembic/versions/20260625_initial_schema.py`

## Integrações de produto

| Integração | Direção | Docs |
|------------|---------|------|
| **VCP** | export/import `.vcp.zip` entre instâncias VA | [`public/PACOTE-VERIFICATION-CASE-PACKAGE.md`](public/PACOTE-VERIFICATION-CASE-PACKAGE.md), spec 12 |
| **Peritus** | import/export ZIP+XML legado → `data/peritus_cases/` | `peritus_bridge_service` (+ `peritus_*`); guia contribuidor |
| **PRNU fingerprints** | API dedicada | endpoints `prnu` |
| **ICP-Brasil** no fechamento | planejado | stub HTTP 501 hoje |
| **Worker GPU remoto** | LAN + Redis/FS | [`deploy/WORKER-REMOTE.md`](deploy/WORKER-REMOTE.md) |

## Lineage de derivados

Spec [`specs/modules/14-module-derivation-lineage.md`](specs/modules/14-module-derivation-lineage.md).

## Segredos e sensibilidade

Evidências = material sensível. Backup: **DB + `data/` + chaves Ed25519 + `.env`**.

## Como verificar

```bash
ls data/uploads data/results data/derivatives reference_data
```

## Atenção

- Apagar só o banco deixa órfãos no disco (e vice-versa).  
- Worker remoto sem NFS/mesmo path quebra jobs.  
- `reference_data` incompleto → LR calibrado falha ou degrada.  
- Não confundir VCP com pacote Peritus: pacotes e endpoints não são intercambiáveis.

## Próximo

[07 — Operação e setup](07-operacao-e-setup.md)
