# Worker GPU remoto (LAN) — ForensicAuth

Este guia prepara uma **segunda máquina** na rede local com GPU NVIDIA como `worker-gpu` adicional, **sem alterar o núcleo da aplicação**. A máquina principal continua hospedando API, PostgreSQL, Redis e o primeiro `worker-gpu`.

## Premissas

- Mesma versão do código e modelos em ambas as máquinas.
- Paths de dados **idênticos** em todas as máquinas: em produção o `docker-compose.prod.yml` monta `./data/...`, `./models` e `./reference_data` nos **mesmos** caminhos `/opt/forensicauth/...` dentro e fora do container (nada de `/app`, nada de symlink). No worker remoto, monte esses mesmos caminhos via NFS.
- Redis e PostgreSQL acessíveis pela LAN (portas liberadas no firewall).
- Celery consome a fila global `gpu`; cada placa usa uma `GPU_LOCK_KEY` **distinta** (ex.: `forensicauth:gpu:prod1-3090`, `forensicauth:gpu:prod2-ada`) para paralelizar jobs entre GPUs — com a mesma chave, só 1 job GPU roda de cada vez.

## 1. NFS no servidor (máquina principal)

Exporte os diretórios de dados para a máquina worker (NFS), configurando `/etc/exports` manualmente com os paths de `data/uploads`, `data/results`, `data/derivatives`, `data/peritus_cases`, `models/` e `reference_data/` (o roteiro completo traz o bloco pronto em formato `IP/rede(opcoes)`).

```bash
sudo mkdir -p /srv/nfs-forensicauth
# ou exporte diretamente ~/forensicauth/...
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
```

No worker, monte com o mesmo caminho local:

```fstab
<NFS_SERVER>:/opt/forensicauth/data/uploads      /opt/forensicauth/data/uploads      nfs defaults 0 0
<NFS_SERVER>:/opt/forensicauth/data/results      /opt/forensicauth/data/results      nfs defaults 0 0
<NFS_SERVER>:/opt/forensicauth/data/derivatives  /opt/forensicauth/data/derivatives  nfs defaults 0 0
<NFS_SERVER>:/opt/forensicauth/models            /opt/forensicauth/models            nfs defaults 0 0
```

> **Importante:** o caminho montado no worker deve coincidir com `UPLOAD_DIR`, `RESULTS_DIR`, etc. no `.env`.

## 2. Bundle no worker

Na máquina principal, sincronize código + deps para o worker (rsync/scp do clone). Exemplo:

```bash
rsync -a --exclude '.git' --exclude 'data/uploads' --exclude 'data/results' \
  ./ user@<WORKER_IP>:~/forensicauth/
```

No worker:

```bash
cd ~/forensicauth
conda create -y -n forensicauth python=3.11
conda activate forensicauth
pip install -r requirements.txt -r requirements-gpu.txt
cp src/backend/.env.worker-gpu.example src/backend/.env
# Ajuste DATABASE_URL e REDIS_URL para o IP da máquina principal
```

## 3. Variáveis do worker remoto

```env
FORENSICAUTH_PROCESS_ROLE=worker-gpu
FORENSICAUTH_WORKER_QUEUE=gpu
# Raiz do workspace: o codigo resolve vendor/, models/ e src/backend/lib/native
# a partir daqui (forensics/paths.py). Sem isto o worker quebra com caminho errado.
FORENSICAUTH_WORKSPACE_ROOT=/opt/forensicauth
GPU_AVAILABLE=true
# Warmup desabilitado em producao: varios workers GPU carregando modelo no
# boot causa contencao de VRAM/disco e pode travar processos filhos.
ML_WARMUP_ON_STARTUP=false
EFFORT_WARMUP_ON_STARTUP=false
SYNTHETIC_KEEP_RESIDENT=true
GPU_RESIDENT_TECHNIQUES=synthetic,effort,safe
GPU_DISTRIBUTED_LOCK=true
GPU_MIN_FREE_MB=1500
GPU_ALLOW_CPU_FALLBACK=false
GPU_LOCK_KEY=forensicauth:gpu:<maquina>-<placa>

DATABASE_URL=postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@<DB_HOST>:5432/forensicauth
REDIS_URL=redis://<REDIS_HOST>:6379/0
CELERY_BROKER_URL=redis://<REDIS_HOST>:6379/0
CELERY_RESULT_BACKEND=redis://<REDIS_HOST>:6379/0

UPLOAD_DIR=/opt/forensicauth/data/uploads
RESULTS_DIR=/opt/forensicauth/data/results
DERIVATIVES_DIR=/opt/forensicauth/data/derivatives
PERITUS_CASES_DIR=/opt/forensicauth/data/peritus_cases
MODELS_DIR=/opt/forensicauth/models
REFERENCE_DATA_DIR=/opt/forensicauth/reference_data
FORENSICAUTH_REFERENCE_DATA_DIR=/opt/forensicauth/reference_data
HF_HUB_CACHE=/opt/forensicauth/models/synthetic_image_detection/huggingface
TRANSFORMERS_OFFLINE=1

# Obrigatorio: o console script do celery nao coloca o cwd no sys.path dos
# processos filhos — sem isto imports de app/forensics/models falham.
PYTHONPATH=/opt/forensicauth/src/backend
SECRET_KEY=<MESMO_SECRET_KEY_DA_PRINCIPAL>
DEBUG=false
```

> Roteiro operacional completo (do zero, com drivers, NFS, systemd e verificações): `docs/deploy/INSTALACAO-PROD-WORKERS.md`.

## 4. Subir o worker

```bash
cd src/backend
conda activate forensicauth
celery -A app.celery_app worker -Q gpu -c 1 -n gpu-worker2@%h --loglevel=info
```

O nome `-n gpu-maquina2@%h` aparece em logs e no `runtime_manifest.hostname` para custódia.

## 5. Verificação

1. `celery -A app.celery_app inspect active_queues` — deve listar `gpu` em ambos os workers.
2. Submeta um job `synthetic_image_detection` — deve ir para fila `gpu` e executar em qualquer worker disponível.
3. Dois jobs GPU simultâneos: com `GPU_LOCK_KEY` **distintas** por placa, os dois rodam em paralelo em placas diferentes; com a **mesma** chave, o segundo aguarda o lock (UX: “Aguardando GPU (N na fila)”).

## Firewall (referência)

| Porta | Serviço   | Direção        |
|-------|-----------|----------------|
| 5432  | PostgreSQL| worker → main  |
| 6379  | Redis     | worker → main  |
| 2049  | NFS       | worker → main  |

## Troubleshooting

- **Job pending indefinidamente:** nenhum worker `-Q gpu` ativo; verifique `docker compose ps` / `celery inspect active` ou os processos locais do worker-gpu.
- **FileNotFoundError em evidência:** path NFS diferente entre máquinas — alinhe montagens.
- **OOM na GPU:** reduza `GPU_RESIDENT_TECHNIQUES` ou aumente `GPU_MIN_FREE_MB`; TruFor/DistilDIRE continuam exclusivos por job.
