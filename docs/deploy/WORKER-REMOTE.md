# Worker GPU remoto (LAN) — ForensicAuth

Este guia prepara uma **segunda máquina** na rede local com GPU NVIDIA como `worker-gpu` adicional, **sem alterar o núcleo da aplicação**. A máquina principal continua hospedando API, PostgreSQL, Redis e o primeiro `worker-gpu`.

## Premissas

- Mesma versão do código e modelos em ambas as máquinas.
- Paths de dados **idênticos** no filesystem lógico: `~/forensicauth/{uploads-dev,results-dev,derivatives-dev,models}` (dev) ou `./uploads`, `./results`, `./derivatives`, `./models` (produção).
- Redis e PostgreSQL acessíveis pela LAN (portas liberadas no firewall).
- Celery consome a fila global `gpu`; o lock Redis `forensicauth:gpu:0` serializa jobs ML entre todas as GPUs.

## 1. NFS no servidor (máquina principal)

Exporte os diretórios de dados para a máquina worker. Exemplo em `scripts/nfs-exports.example`.

```bash
sudo mkdir -p /srv/nfs-forensicauth
# ou exporte diretamente ~/forensicauth/...
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
```

No worker, monte com o mesmo caminho local:

```fstab
<NFS_SERVER>:/opt/forensicauth/uploads-dev    /opt/forensicauth/uploads-dev    nfs defaults 0 0
<NFS_SERVER>:/opt/forensicauth/results-dev    /opt/forensicauth/results-dev    nfs defaults 0 0
<NFS_SERVER>:/opt/forensicauth/derivatives-dev /opt/forensicauth/derivatives-dev nfs defaults 0 0
<NFS_SERVER>:/opt/forensicauth/models         /opt/forensicauth/models         nfs defaults 0 0
```

> **Importante:** o caminho montado no worker deve coincidir com `UPLOAD_DIR`, `RESULTS_DIR`, etc. no `.env`.

## 2. Bundle no worker

Na máquina principal:

```bash
./scripts/prepare-worker-bundle.sh user@<WORKER_IP>
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
GPU_AVAILABLE=true
ML_WARMUP_ON_STARTUP=true
SYNTHETIC_KEEP_RESIDENT=true
GPU_DISTRIBUTED_LOCK=true

DATABASE_URL=postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@<DB_HOST>:5432/forensicauth
REDIS_URL=redis://<REDIS_HOST>:6379/0
CELERY_BROKER_URL=redis://<REDIS_HOST>:6379/0
CELERY_RESULT_BACKEND=redis://<REDIS_HOST>:6379/0
```

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
3. Dois jobs GPU simultâneos: o segundo aguarda o lock Redis (UX: “Aguardando GPU (N na fila)”).

## Firewall (referência)

| Porta | Serviço   | Direção        |
|-------|-----------|----------------|
| 5432  | PostgreSQL| worker → main  |
| 6379  | Redis     | worker → main  |
| 2049  | NFS       | worker → main  |

## Troubleshooting

- **Job pending indefinidamente:** nenhum worker `-Q gpu` ativo; verifique `dev-stack.sh status` ou `docker compose ps`.
- **FileNotFoundError em evidência:** path NFS diferente entre máquinas — alinhe montagens.
- **OOM na GPU:** reduza `GPU_RESIDENT_TECHNIQUES` ou aumente `GPU_MIN_FREE_MB`; TruFor/DistilDIRE continuam exclusivos por job.
