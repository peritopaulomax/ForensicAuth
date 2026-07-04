# ForensicAuth — Instalação em servidor Linux (produção)

Guia passo a passo para implantar o **ForensicAuth** em um servidor Linux limpo, usando **Docker** e **Docker Compose**. Este é o caminho recomendado pela arquitetura do projeto.

---

## 1. Visão geral do que será instalado

| Componente | Função | Porta padrão |
|------------|--------|--------------|
| **frontend** | Interface web (React + nginx) | 80 |
| **app** | API REST (FastAPI) | 8000 (interno; exposta no Compose) |
| **worker** | Fila de análises forenses (Celery) | — |
| **db** | PostgreSQL 15 | 5432 |
| **redis** | Broker Celery | 6379 |

Arquivos de evidência, derivados e resultados ficam em **volumes no disco** do host (`uploads/`, `results/`, `derivatives/`).

---

## 2. Requisitos de hardware e software

### Servidor mínimo (CPU, sem GPU)

- **SO:** Ubuntu 22.04 LTS ou 24.04 LTS (ou Debian 12 equivalente)
- **CPU:** 4 vCPU
- **RAM:** 16 GB
- **Disco:** SSD 100 GB+ (evidências forenses crescem rápido)
- **Rede:** IP fixo ou DNS; portas 80/443 abertas para usuários

### Servidor recomendado (análises pesadas / GPU)

- **RAM:** 32 GB+
- **GPU NVIDIA** com drivers + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- Use `docker-compose.gpu.yml` para worker dedicado à fila GPU (Detecção de imagens sintéticas, deepfake, etc.)

### Software no host

- Docker Engine 24+
- Docker Compose plugin v2+
- Git
- (Opcional) Certbot ou proxy TLS corporativo

---

## 3. Preparar o sistema operacional

Conecte-se ao servidor via SSH e execute:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl ca-certificates ufw
```

### Instalar Docker (método oficial)

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Saia e entre novamente na sessão SSH para o grupo `docker` valer.

Verifique:

```bash
docker --version
docker compose version
```

### Firewall básico

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**Não** exponha PostgreSQL (5432) nem Redis (6379) na internet pública.

---

## 4. Obter o código-fonte

```bash
sudo mkdir -p /opt/forensicauth
sudo chown $USER:$USER /opt/forensicauth
cd /opt/forensicauth

git clone <URL_DO_REPOSITORIO> .
# ou: git clone <URL do repositório público> .
```

---

## 5. Estrutura de diretórios persistentes

Crie pastas para dados que **não** podem ser perdidos ao recriar containers:

```bash
cd /opt/forensicauth
mkdir -p uploads results derivatives models secrets
chmod 750 uploads results derivatives models secrets
```

| Pasta | Conteúdo |
|-------|----------|
| `uploads/` | Evidências originais por caso |
| `results/` | Saída temporária de jobs de análise |
| `derivatives/` | Arquivos derivados salvos pelo perito |
| `models/` | Pesos de modelos ML (Detecção de imagens sintéticas, etc.), se aplicável |
| `secrets/` | Chaves Ed25519 de custódia (não versionar) |

---

## 6. Variáveis de ambiente (produção)

Copie o exemplo e edite com valores **fortes**:

```bash
cp .env.example .env
nano .env
```

Exemplo de `.env` para produção:

```env
DEBUG=false
SECRET_KEY=<gere-uma-string-aleatoria-longa-min-32-chars>

DATABASE_URL=postgresql+psycopg2://forensicauth_app:SENHA_FORTE_DB@db:5432/forensicauth

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

UPLOAD_DIR=/app/uploads
RESULTS_DIR=/app/results
DERIVATIVES_DIR=/app/derivatives
MODELS_DIR=/app/models

GPU_AVAILABLE=false

# Paralelismo interno por job (JPEG Ghosts, PRNU localizado) — não aparece na UI
JPEG_GHOSTS_N_JOBS=6
PRNU_LOCALIZED_N_JOBS=4

CUSTODY_SIGNING_KEY_ID=forensicauth-ed25519-v1
CUSTODY_SIGNING_PRIVATE_KEY=<base64-da-chave-privada>
CUSTODY_SIGNING_PUBLIC_KEY=<pem-opcional>
```

Gere `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Chaves Ed25519 da cadeia de custódia (obrigatório em produção)

Sem chave fixa, o backend gera chave **efêmera** a cada reinício — inválido para auditoria.

Em uma máquina com Python 3.11+ e dependências:

```bash
pip install cryptography
python3 scripts/generate_custody_signing_key.py
```

Copie os valores impressos para `.env`. Guarde `secrets/custody_ed25519_private.pem` em backup seguro **fora do Git**.

### Ajustar credenciais do PostgreSQL

Edite também `docker-compose.yml` (ou use um override) para que `POSTGRES_USER`, `POSTGRES_PASSWORD` e `DATABASE_URL` coincidam. **Nunca** use `postgres/postgres` em produção.

**Paralelismo CPU:** `JPEG_GHOSTS_N_JOBS` e `PRNU_LOCALIZED_N_JOBS` controlam workers joblib **dentro** de cada job. O worker Celery (`-c 4` no compose) limita quantos jobs rodam ao mesmo tempo. Regra prática em servidor ~48 núcleos: `-c 4` + `JPEG_GHOSTS_N_JOBS=6` → até ~24 núcleos em pico de Ghosts; reduza se vários usuários dispararem análises pesadas simultaneamente.

---

## 7. Ajustes recomendados antes do primeiro `up`

O repositório inclui um `Dockerfile` com `--reload` (desenvolvimento). Para produção, crie `docker-compose.override.yml`:

```yaml
# docker-compose.override.yml — não versionar se contiver segredos
services:
  app:
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
    environment:
      - DEBUG=false
      - DERIVATIVES_DIR=/app/derivatives
    volumes:
      - ./uploads:/app/uploads
      - ./results:/app/results
      - ./derivatives:/app/derivatives
      - ./models:/app/models
    env_file:
      - .env

  worker:
    volumes:
      - ./uploads:/app/uploads
      - ./results:/app/results
      - ./derivatives:/app/derivatives
      - ./models:/app/models
    env_file:
      - .env

  db:
    environment:
      POSTGRES_USER: forensicauth_app
      POSTGRES_PASSWORD: SENHA_FORTE_DB
      POSTGRES_DB: forensicauth
```

### Upload de pacotes Verification Case Package (VCP) grandes

Edite `src/frontend/nginx.conf` e adicione dentro do bloco `server`:

```nginx
client_max_body_size 1024m;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

Reconstrua a imagem do frontend após alterar.

---

## 8. Construir e iniciar os serviços

```bash
cd /opt/forensicauth
docker compose build
docker compose up -d
docker compose ps
```

Aguarde todos os serviços ficarem `healthy` / `running`:

```bash
docker compose logs -f app
```

Teste a API:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost/health
```

---

## 9. Criar o primeiro administrador

Com os containers em execução, execute o seed **a partir do host** (montando o código do repositório):

```bash
cd /opt/forensicauth
docker compose exec app pip install -q cryptography passlib bcrypt 2>/dev/null || true
docker compose run --rm \
  -v "$(pwd)/scripts:/scripts:ro" \
  -e DATABASE_URL=postgresql+psycopg2://forensicauth_app:SENHA_FORTE_DB@db:5432/forensicauth \
  app python /scripts/seed_users.py
```

Alternativa: instale `requirements.txt` no host, exporte `DATABASE_URL` apontando para `localhost:5432` (se o Postgres estiver publicado só em loopback) e rode `python scripts/seed_users.py`.

Edite `scripts/seed_users.py` antes se quiser alterar o username padrao do administrador.

Acesse a interface web → **Primeiro Acesso** → defina a senha do administrador.

---

## 10. HTTPS (TLS)

O container `frontend` serve HTTP na porta 80. Em produção, coloque um reverse proxy:

### Opção A — Caddy (simples)

```bash
sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```
forensicauth.exemplo.gov.br {
    reverse_proxy localhost:80
}
```

### Opção B — nginx no host

Proxy para `127.0.0.1:80` com certificado Let's Encrypt (`certbot --nginx`).

Atualize `CORS_ORIGINS` no backend para incluir `https://forensicauth.exemplo.gov.br`.

---

## 11. GPU (opcional)

Se tiver NVIDIA GPU:

```bash
# Instalar NVIDIA Container Toolkit conforme documentação oficial
docker compose -f docker-compose.gpu.yml up -d --build
```

Coloque modelos em `./models/` conforme documentação de cada técnica (Detecção de imagens sintéticas, etc.).

---

## 12. Backup e restauração

### Banco de dados (diário)

```bash
docker compose exec db pg_dump -U forensicauth_app forensicauth | gzip > backup/forensicauth_$(date +%F).sql.gz
```

### Arquivos forenses

```bash
tar czf backup/forensicauth_files_$(date +%F).tar.gz uploads results derivatives
```

### Chaves de custódia

Backup offline de `secrets/` e das variáveis `CUSTODY_SIGNING_*` no `.env`.

### Restauração

1. Restaurar volumes `uploads/`, `results/`, `derivatives/`
2. `gunzip -c backup.sql.gz | docker compose exec -T db psql -U forensicauth_app forensicauth`
3. Reiniciar `app` e `worker`

---

## 13. Atualização de versão

```bash
cd /opt/forensicauth
git pull
docker compose build
docker compose up -d
```

As migrações leves rodam automaticamente no startup da API (`app/main.py`).

---

## 14. Verificação pós-instalação

| Teste | Como |
|-------|------|
| Login | Acesse `https://seu-dominio/` |
| Upload | Crie caso, envie uma imagem/PDF |
| Análise | Execute uma técnica (ex.: metadados) |
| Worker | `docker compose logs worker` — job deve completar |
| Custódia | Aba Custódia → **Verificar cadeia** e **Verificação forense** |
| VCP (Verification Case Package) | Exporte e reimporte um caso de teste |

---

## 15. Solução de problemas

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| `Connection refused` na API | Container `app` parado | `docker compose logs app` |
| Análise fica em `pending` | Worker Celery parado | `docker compose up -d worker` |
| 502 no frontend | API não responde | Verificar `app:8000` na rede Docker |
| Assinaturas inválidas após restart | Chave Ed25519 não persistida | Configurar `CUSTODY_SIGNING_*` |
| Import VCP falha (413) | Limite nginx | Aumentar `client_max_body_size` |
| Disco cheio | Evidências acumuladas | Expandir volume ou política de retenção |

---

## 16. Dependências Python (referência)

O `requirements.txt` inclui, entre outros:

- **API:** FastAPI, Uvicorn, Pydantic, SQLAlchemy, psycopg2
- **Fila:** Celery, Redis
- **Auth:** python-jose, passlib
- **Forense:** OpenCV, PyMuPDF, jpegio, NumPy, SciPy, WeasyPrint
- **ML (opcional):** PyTorch, XGBoost — ver `requirements-gpu.txt` se existir

Tudo isso é instalado **dentro da imagem Docker**; não é necessário Python no host, exceto para scripts auxiliares (`seed_users.py`, geração de chaves).

---

## 17. Segurança operacional

- Troque **todas** as senhas padrão do Compose
- Restrinja SSH e use chaves públicas
- Faça backup criptografado de evidências
- Mantenha o SO e imagens Docker atualizados
- Em PostgreSQL, considere `REVOKE UPDATE, DELETE ON custody_records` para reforçar imutabilidade (ver documentação de custódia)
- Não publique `.env` nem `secrets/` no repositório

---

**Documentação relacionada:** [Arquitetura](arquitetura-forensicauth.html) · [Cadeia de custódia](CADEIA-CUSTODIA-E-VERIFICACAO-FORENSE.md) · [Verification Case Package](PACOTE-VERIFICATION-CASE-PACKAGE.md)
