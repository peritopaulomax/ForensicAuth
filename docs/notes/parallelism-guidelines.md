# Paralelismo em técnicas forenses — guidelines (ago/2026)

Lições da depuração de produção (Dell 14c/28t Docker+Celery vs HP 48c execução direta).

## 1. Dentro do Celery, paralelismo só existe via threads

Processos do pool do Celery são *daemon*. Processos daemon não podem ter filhos,
então **qualquer paralelismo baseado em processos morre em silêncio**:

- `joblib.Parallel(backend="loky")` degrada para `n_jobs=1` com um
  `UserWarning` que quase ninguém vê ("Loky-backed parallel loops cannot be
  called in a multiprocessing");
- `multiprocessing.Pool` / `ProcessPoolExecutor` levantam exceção.

**Regra:** em código que roda via Celery, usar apenas paralelismo por threads —
joblib `backend="threading"`, Numba (`@njit(parallel=True)`), OpenMP nativo
(binários .so). Execução direta (DEV, scripts) pode usar loky normalmente.

## 2. `gc.collect()` custa O(heap) — nunca por operação

Cada `gc.collect()` varre o heap inteiro. No worker Celery, que importa
torch/transformers/plugins (1M+ objetos), um collect custa centenas de ms.
No jpeg_ghosts havia 4 collects por qualidade (~1500 por job) ≈ **290s de GC
por job** — era o verdadeiro culpado dos "timeouts" de 5 min.

**Regra:** `gc.collect()` apenas em pontos estratégicos (fim de job, após
liberar modelo GPU). Intermediários morrem por refcount com `del`.

## 3. Paralelizar o loop externo, não o interno

jpeg_ghosts paralelizava 6 qualidades dentro de um loop serial de 64
deslocamentos → teto de 6 núcleos, maioria do tempo serial. O correto era
paralelizar os 64 deslocamentos (independentes). Ao inverter, cuidado com:

- **Redução determinística:** coletar resultados na ordem original dos itens
  (preserva tie-break e ordenação do output);
- **Memória:** não retornar payloads grandes de todos os itens; recomputar só
  o vencedor (fase 2) quando aplicável;
- **Aninhamento:** dentro de cada worker paralelo, o nível interno fica serial;
- **Progresso:** processar em lotes de `n_jobs` itens e reportar entre lotes —
  mesma percepção de progresso do modo serial.

## 4. O teto é do algoritmo, não da máquina

Antes de culpar hardware, medir onde o tempo vai (trace de progresso com
timestamps no banco foi decisivo: `analysis_jobs.progress_message` polado a
cada 3s). Num contexto, 76x de diferença vinha de GC + daemon, não de CPU.
