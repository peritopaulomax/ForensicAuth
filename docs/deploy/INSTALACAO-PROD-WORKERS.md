# Roteiro passo a passo — ForensicAuth em produção (2 máquinas × 2 GPUs)

**Objetivo:** pegar o código do GitHub + arquivos extras/desenvolvimento (pesos, `reference_data`, etc.) e deixar o ForensicAuth rodando em produção, com:

- **Máquina PRINCIPAL (PROD-1):** banco PostgreSQL, Redis, API, frontend, worker CPU + **duas GPUs** (RTX 3090 24 GB + Ada 2000 16 GB)
- **Máquina WORKER (PROD-2):** só workers (CPU e/ou GPU), **sem banco próprio**, ligadas na LAN; também **duas GPUs** (3090 + Ada 2000)
- Filas Celery para distribuir carga entre as GPUs

**Contexto:** Sistema já está rodando em protótipo em uma máquina de desenvolvimento (DEV/MAQ) 

**Repositório GitHub:**

```text
https://github.com/peritopaulomax/ForensicAuth.git
```

**Sistema operacional alvo deste roteiro:** Ubuntu 22.04/24.04/26.04 LTS em ambas as máquinas de produção.

---

## 0. Leia antes de qualquer coisa

### 0.1 O que o GitHub **não** traz (e você **precisa** copiar de outras fontes/máquina de DEV/terceiros)

| Pasta / arquivo | Por quê |
|---------------|---------|
| `models/` | Pesos ML (dezenas de GB) |
| `reference_data/` | Catálogos LR, scores, embeddings, macros (GB) |
| `vendor/` | Código de terceiros; se estiver em clone do Git completo, ótimo; se faltar pasta, copiar da fonte |
| `.env` / senhas / chaves Ed25519 | **Nunca** vão no Git — gera na PROD |

### 0.2 Nomes que usaremos neste roteiro

| Apelido | Significado | Exemplo (não é real) |
|---------|-------------|---------|
| **DEV/MAQ** | Máquina de desenvolvimento (onde já roda versão de teste, podssui os modelos) | IP `192.168.1.10` |
| **PROD-1** | Máquina principal de produção (banco + site + API) | IP `192.168.1.20` |
| **PROD-2** | Segunda máquina (só workers GPU/CPU) | IP `192.168.1.21` |
| **USUARIO** | Seu login Linux | `perito` |
| **REPO** | Pasta do projeto | `/opt/forensicauth` |

**Antes de começar, anote numa folha:**

```text
IP da DEV/MAQ      = ________________
IP da PROD-1   = ________________
IP da PROD-2   = ________________
Usuario Linux  = ________________
```

Sempre que o roteiro disser `<IP_PROD1>`, troque pelo número real (ex.: `192.168.1.20`).

### 0.3 Como a carga GPU funciona neste projeto (importante)

- Jobs pesados de ML vão para a fila Celery chamada **`gpu`**.
- Jobs leves (metadados, muitos parsers) vão para a fila **`celery`** (worker CPU).
- Existe um **cadeado Redis** (`GPU_LOCK_KEY`). Se **todos** os workers usarem a **mesma** chave, **só 1 job GPU roda no cluster inteiro** por vez (os outros esperam na fila — isso é seguro, mas não usa as 4 GPUs ao mesmo tempo).
- Para **usar várias GPUs em paralelo**, cada worker GPU deve ter:
  - `CUDA_VISIBLE_DEVICES` apontando para **uma** placa (0 ou 1), e
  - `GPU_LOCK_KEY` **diferente** por placa (ex.: `forensicauth:gpu:prod1-0`, `forensicauth:gpu:prod1-1`, …).

Assim o Celery entrega o próximo job da fila `gpu` para qualquer worker livre, e até **4 jobs GPU** podem rodar juntos (1 por placa).

**Limite realista:** a Ada 2000 (16 GB) pode falhar (OOM) em técnicas muito pesadas (ex.: alguns caminhos IMDL/TruFor full-res). A 3090 (24 GB) aguenta mais. Se um job estourar na Ada, rode de novo; se for frequente, use só as 3090 para essas técnicas (veja seção 11).

**Política de fallback GPU (desde ago/2026):** em OOM o pipeline faz **purge dos modelos residentes → re-tenta na mesma GPU → se persistir, devolve o job à fila** para outro worker GPU livre (até 3 tentativas). **Nunca cai para CPU** por padrão (`GPU_ALLOW_CPU_FALLBACK=false`). Além disso, o worker só aceita o job se a VRAM livre ≥ `GPU_MIN_FREE_MB`.

### 0.4 Arquitetura que vamos montar

```text
                    [Usuários na LAN]
                           |
                      http://IP_PROD1
                           |
        +------------------+------------------+
        |              PROD-1                 |
        |  Docker: frontend, API, Postgres,   |
        |          Redis, worker-CPU          |
        |  Conda: worker-GPU-3090 (device 0)  |
        |  Conda: worker-GPU-Ada  (device 1)  |
        |  Disco: models/, reference_data/,   |
        |         data/uploads|results|...    |
        |  NFS exporta esses discos --------+ |
        +-----------------------------------|-+
                                            |
                         NFS + Redis + DB   |
                                            v
        +-----------------------------------+-+
        |              PROD-2                 |
        |  Monta NFS nos mesmos caminhos      |
        |  Conda: worker-GPU-3090 (device 0)  |
        |  Conda: worker-GPU-Ada  (device 1)  |
        |  (opcional) worker-CPU              |
        |  SEM Postgres próprio               |
        +-------------------------------------+
```

---

## 1. Na máquina DEV — descobrir IPs e preparar o pacote mais pesado

Faça **todos** os comandos desta seção na máquina onde o sistema **já** funciona e onde estão `models/` e `reference_data/`.

### Passo 1.1 — Abrir um terminal

No Ubuntu: teclas `Ctrl+Alt+T` (ou procure “Terminal” no menu).

### Passo 1.2 — Descobrir o IP da DEV na LAN

```bash
hostname -I
```

Anote o primeiro IP (ex.: `192.168.1.10`). Esse é `<IP_DEV>`.

### Passo 1.3 — Ir até a pasta do projeto na DEV

Se o projeto estiver em `/home/SEU_USUARIO/VA` (como nesta máquina de exemplo):

```bash
cd "/home/$USER/VA"
pwd
ls
```

Você deve ver pastas como `src`, `models`, `reference_data`, `docker-compose.yml`.  
Se o caminho for outro, use o caminho real daqui para frente (chame-o de pasta do projeto DEV).

### Passo 1.4 — Ver o tamanho do que será copiado (pode demorar)

```bash
du -sh models reference_data vendor data 2>/dev/null
```

Espere ter **espaço livre maior** que essa soma na PROD-1 (recomendado: disco SSD com 200 GB+ livres).

### Passo 1.5 — Garantir que o código no GitHub está atualizado (opcional mas recomendado)

Na DEV, se você tem commits locais que ainda não foram enviados:

```bash
cd "/home/$USER/VA Suite"
git status
git log -3 --oneline
```

Se `git status` mostrar commits “à frente” do `origin`, envie-os.  
Se o push falhar (sem permissão), **não trave**: na PROD-1 você pode clonar o GitHub e depois **sobrescrever** com `rsync` da DEV.

### Passo 1.6 — Anotar o caminho absoluto da DEV

```bash
cd "/home/$USER/VA Suite"
pwd
```

Exemplo de saída: `/home/bfl-pcf/VA Suite`  
Anote como `<CAMINHO_DEV>`.

---

## 2. Na PROD-1 — preparar o sistema operacional

Faça estes passos **na máquina principal de produção**, com um usuário que possa usar `sudo`.

### Passo 2.1 — Atualizar o Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
```

Se pedir confirmação, digite `S` ou `Y` e Enter.

### Passo 2.2 — Instalar ferramentas básicas

```bash
sudo apt install -y git curl ca-certificates ufw rsync openssh-server nfs-kernel-server
```

### Passo 2.3 — Instalar Docker 

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

**Saia da sessão e entre de novo** (logout/login ou feche o SSH e reconecte). Sem isso o Docker reclama de permissão.

Teste:

```bash
docker --version
docker compose version
```

Os dois comandos devem mostrar números de versão (sem erro).

### Passo 2.3.1 — Proxy corporativo (se a rede exigir, ex.: órgãos públicos)

Se a sua rede sai para a internet via proxy, o Docker **não** herda isso do shell — o build falha com `403 Forbidden` no `apt-get` dentro do container. Configure uma vez:

```bash
mkdir -p ~/.docker
cat > ~/.docker/config.json <<'EOF'
{
  "proxies": {
    "default": {
      "httpProxy": "http://SEU_PROXY:PORTA",
      "httpsProxy": "http://SEU_PROXY:PORTA",
      "noProxy": "localhost,127.0.0.1,::1"
    }
  }
}
EOF
```

Troque `SEU_PROXY:PORTA` pelo proxy real (nas máquinas da PF: `proxy.ditec.pf.gov.br:3128`). Isso vale para builds e containers deste usuário, sem tocar em Dockerfile nem no repo. O `pip`/`conda` no shell usam as variáveis `http_proxy`/`https_proxy` normais.

### Passo 2.4 — Drivers NVIDIA + CUDA + Container Toolkit (passo a passo)

**Faça esta seção inteira na PROD-1 e, depois, repita na PROD-2.**  
Sem driver NVIDIA funcionando, o ForensicAuth **não** usa as GPUs.

#### 2.4.0 — Resumo

| Peça | Para quê serve |
|------|----------------|
| **Driver NVIDIA** | O sistema “vê” as placas (`nvidia-smi`). **Obrigatório.** |
| **CUDA Toolkit** (`nvcc`, libs no `/usr/local/cuda`) | Compilar/usar ferramentas CUDA no host. **Recomendado.** |
| **CUDA tazido pelo PyTorch** | O `pip install torch ... cu124` já embute runtime CUDA. Mesmo assim o **driver** do host precisa ser novo o bastante. |
| **NVIDIA Container Toolkit** | Permite que o **Docker** use a GPU (`--gpus all`). Útil; neste roteiro os workers GPU rodam em **conda**, mas o toolkit ajuda a testar. |

Meta deste roteiro: **driver ≥ 550** (melhor 560+) e **CUDA Toolkit 12.4 ou 12.6/12.8** no host, alinhado ao PyTorch `cu124` / `cu126`.

#### 2.4.1 — Ver se já está instalado (pode pular instalação)

```bash
lspci | grep -i nvidia
nvidia-smi
```

- Se `lspci` listar as duas GPUs e `nvidia-smi` mostrar tabela com Driver Version e as duas placas → **pule para 2.4.7** (anotar índices) e depois 2.4.8 / 2.4.9.
- Se `nvidia-smi: command not found` ou erro de módulo → continue a instalação abaixo.

#### 2.4.2 — Preparar o sistema (headers do kernel, etc.)

```bash
sudo apt update
sudo apt install -y build-essential dkms curl wget ca-certificates
sudo apt install -y linux-headers-$(uname -r)
sudo apt install -y ubuntu-drivers-common
```

Confira a versão do Ubuntu (vai decidir o repositório CUDA):

```bash
. /etc/os-release
echo "$UBUNTU_CODENAME  $VERSION_ID"
uname -r
```

Anote: `22.04` → usar `ubuntu2204` nos links; `24.04` → usar `ubuntu2404`.

#### 2.4.3 — Remover restos quebrados (só se já tentou instalar e falhou)

**Não rode isto na primeira instalação limpa**, a menos que `nvidia-smi` esteja quebrado.

```bash
sudo apt purge -y 'nvidia-*' 'libnvidia-*' 'cuda-*' 2>/dev/null || true
sudo apt autoremove -y
sudo reboot
```

Depois do reboot, volte neste ponto e continue do 2.4.2.

#### 2.4.4 — Instalar o **driver** (método mais fácil — Ubuntu)

Este é o caminho recomendado :

```bash
ubuntu-drivers devices
```

Leia a saída. Procure a linha `recommended`. Exemplo:

```text
driver   : nvidia-driver-570 - distro non-free recommended
```

Instale o recomendado automaticamente:

```bash
sudo ubuntu-drivers autoinstall
```

**OU** instale um número específico (troque `570` pelo recomendado na sua tela):

```bash
sudo apt install -y nvidia-driver-570
```

> Para RTX 3090 + Ada 2000 em Ubuntu recente, drivers da família **550 / 560 / 570** costumam funcionar. Prefira o que o `ubuntu-drivers` marcar como `recommended`.

Reinicie **obrigatoriamente**:

```bash
sudo reboot
```

Após voltar o PC, abra o terminal e rode:

```bash
nvidia-smi
```

Você **deve** ver algo assim (números variam):

```text
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 570.xx       Driver Version: 570.xx       CUDA Version: 12.x     |
|-------------------------------+----------------------+----------------------+
|   0  NVIDIA GeForce RTX 3090 ...                                                |
|   1  NVIDIA RTX 2000 Ada ...                                                    |
+-----------------------------------------------------------------------------+
```

Se ainda falhar, use o **método B** (2.4.5). Se funcionar, vá para **2.4.6 (CUDA Toolkit)**.

#### 2.4.5 — Instalar o **driver** (método B — repositório oficial NVIDIA)

Use só se o `ubuntu-drivers` falhou.

**No Ubuntu 26.04:**

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2604/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y cuda-drivers
sudo reboot
```
**No Ubuntu 24.04:**

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y cuda-drivers
sudo reboot
```

**No Ubuntu 22.04:**

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y cuda-drivers
sudo reboot
```

Depois:

```bash
nvidia-smi
```

Documentação oficial (se a URL do `.deb` mudar no futuro):  
https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/index.html

#### 2.4.6 — Instalar o **CUDA Toolkit** no host (`nvcc`)

O ForensicAuth (PyTorch via pip) **não obriga** ter o toolkit completo no sistema, mas instalar evita surpresas e permite `nvcc --version`.

**Passo A — repositório NVIDIA** (se ainda não fez no 2.4.5):

Ubuntu 26.04:

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2604/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
```

Ubuntu 24.04:

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
```

Ubuntu 22.04:

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
```

**Passo B — instalar o toolkit 12.x** (escolha **uma** linha; 12-4 combina bem com PyTorch `cu124`):

```bash
# Opção recomendada para este projeto (alinha com wheel cu124):
sudo apt install -y cuda-toolkit-12-4
```

Se `cuda-toolkit-12-4` não existir no apt, tente na ordem:

```bash
sudo apt install -y cuda-toolkit-12-6
# ou
sudo apt install -y cuda-toolkit-12-8
# ou o meta-pacote genérico:
sudo apt install -y cuda-toolkit
```

**Passo C — colocar CUDA no PATH** (para o terminal achar `nvcc`):

```bash
nano ~/.bashrc
```

Cole **no final** do arquivo (ajuste `12.4` se instalou outra versão; confira com `ls /usr/local/cuda*`):

```bash
# CUDA (ForensicAuth)
export PATH=/usr/local/cuda-12.4/bin${PATH:+:${PATH}}
export LD_LIBRARY_PATH=/usr/local/cuda-12.4/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
```

Se existir o atalho `/usr/local/cuda` (link simbólico), pode usar assim em vez da versão fixa:

```bash
export PATH=/usr/local/cuda/bin${PATH:+:${PATH}}
export LD_LIBRARY_PATH=/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
```

Salve (`Ctrl+O`, Enter, `Ctrl+X`) e recarregue:

```bash
source ~/.bashrc
nvcc --version
nvidia-smi
```

`nvcc` deve imprimir `release 12.x`.  
A linha **CUDA Version** do `nvidia-smi` é a **máxima** que o driver aceita — pode ser ≥ à do toolkit.

#### 2.4.7 — Anotar o índice de cada GPU

```bash
nvidia-smi -L
```

Exemplo:

```text
GPU 0: NVIDIA GeForce RTX 3090 (UUID: ...)
GPU 1: NVIDIA RTX 2000 Ada Generation (UUID: ...)
```

Neste roteiro:

- **device 0** = 3090 (24 GB) → trabalhos mais pesados  
- **device 1** = Ada 2000 (16 GB) → trabalhos médios  

Se na sua máquina estiver **diferente**, troque `CUDA_VISIBLE_DEVICES=0/1` na seção 7 (e o equivalente na PROD-2).

#### 2.4.8 — NVIDIA Container Toolkit (Docker enxergar GPU)

Só depois de `nvidia-smi` funcionar no host.

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Teste:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Deve listar as **duas** GPUs.  
Se falhar, os workers **conda** deste roteiro ainda funcionam desde que `nvidia-smi` no host esteja OK — corrija o toolkit depois com calma.

Documentação: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

#### 2.4.9 — Checklist rápido “GPU pronta”

Marque mentalmente:

```bash
nvidia-smi                          # 2 GPUs, sem erro
nvcc --version                      # 12.x (se instalou toolkit)
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi   # opcional Docker
```

Só então continue o roteiro (firewall, clone, etc.).

#### 2.4.10 — Problemas comuns na instalação NVIDIA/CUDA

| Sintoma | O que fazer |
|---------|-------------|
| `nvidia-smi` → *Failed to initialize NVML* / *Driver/library version mismatch* | Reinicie (`sudo reboot`). Se persistir: `sudo apt install --reinstall nvidia-driver-XXX` com o mesmo XXX do pacote instalado. |
| Tela preta após instalar driver | No GRUB, tente modo recovery ou `nomodeset` temporário; depois `sudo apt purge nvidia-*` e reinstale com `ubuntu-drivers autoinstall`. |
| `nvcc: command not found` | Faltou `source ~/.bashrc` ou PATH errado; confira `ls /usr/local/cuda*`. |
| Secure Boot impede o módulo | Desative Secure Boot na BIOS, ou assine o módulo (avançado). Para sistema interno, desativar Secure Boot costuma ser o caminho mais simples. |
| Duas GPUs no `lspci`, só uma no `nvidia-smi` | Cabo de energia / slot PCIe / GPU desabilitada na BIOS. |
| Nouveau conflitante | `echo 'blacklist nouveau' \| sudo tee /etc/modprobe.d/blacklist-nouveau.conf` e `sudo update-initramfs -u && sudo reboot` — depois reinstale o driver. |

### Passo 2.5 — Firewall da PROD-1 (LAN)

**Atenção:** as portas do Postgres e Redis só devem ficar abertas para a **rede local**, nunca para a internet pública.

Descubra sua rede (exemplo `192.168.1.0/24`):

```bash
ip -4 route | awk '/default/ {print $3}' 
hostname -I
```

Se seus IPs são `192.168.1.x`, a rede costuma ser `192.168.1.0/24`. Ajuste se for outra.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# Só da LAN — TROQUE a rede se a sua for diferente:
sudo ufw allow from 192.168.1.0/24 to any port 5432 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 6379 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 2049
sudo ufw enable
sudo ufw status
```

### Passo 2.6 — Criar pasta do projeto

```bash
sudo mkdir -p /opt/forensicauth
sudo chown $USER:$USER /opt/forensicauth
cd /opt/forensicauth
```

---

## 3. Na PROD-1 — baixar o código do GitHub

### Passo 3.1 — Clonar

```bash
cd /opt/forensicauth
git clone https://github.com/peritopaulomax/ForensicAuth.git .
```

Se a pasta não estiver vazia e o `git clone` reclamar, use:

```bash
cd /opt
sudo rm -rf forensicauth
sudo mkdir -p forensicauth
sudo chown $USER:$USER forensicauth
cd /opt/forensicauth
git clone https://github.com/peritopaulomax/ForensicAuth.git .
```

### Passo 3.2 — Conferir que clonou

```bash
cd /opt/forensicauth
ls
git log -1 --oneline
```

Deve aparecer `src`, `docs`, `docker-compose.yml`, etc.

### Passo 3.3 — Criar pastas de dados

```bash
cd /opt/forensicauth
mkdir -p data/uploads data/results data/derivatives data/peritus_cases models reference_data secrets backup
chmod 750 data data/uploads data/results data/derivatives data/peritus_cases models reference_data secrets
```

---

## 4. Copiar da DEV para a PROD-1 os arquivos que não estão no Git (ou copiar de outros repositórios/terceiros)

Os modelos de terceiros em /models/ (pré treinados) devem ser copiados. A máquina de DEV se já os tiver pode ser a forma mais rápida. 

O mesmo pode ser dito para a pasta /reference_data/ já com o reusltado da ingestão dos datasets ingeridos para funcionar como população de referência, e /vendor/ com códigos distribuidos por terceiros.

Faça estes comandos **na máquina DEV** (ela empurra os arquivos para a PROD-1).

### Passo 4.1 — Testar SSH até a PROD-1

Na DEV:

```bash
ssh USUARIO@<IP_PROD1>
```

Troque `USUARIO` e `<IP_PROD1>`. Na primeira vez digite `yes` e a senha.  
Depois digite `exit` para voltar à DEV.

### Passo 4.2 — Copiar `models/` (demora; GB)

Na DEV (ajuste os caminhos):

```bash
rsync -avh --progress \
  "/home/$USER/VA Suite/models/" \
  USUARIO@<IP_PROD1>:/opt/forensicauth/models/
```

> Isso inclui **também os modelos baixados do HuggingFace** (o cache HF do projeto vive em `models/synthetic_image_detection/huggingface/` — ex.: os detectores do ensemble SID e o backbone `wav2vec2-xls-r-1b` do DF Arena de áudio). Nenhum passo extra de download é necessário: a regra geral vale para todos — vem tudo na cópia de `models/`. Se algum dia faltar um modelo numa máquina, a tabela do README indica a fonte oficial de cada um.

### Passo 4.3 — Copiar `reference_data/` (demora, são as bases de população de referência já ingeridas em DEV)

```bash
rsync -avh --progress \
  "/home/$USER/VA Suite/reference_data/" \
  USUARIO@<IP_PROD1>:/opt/forensicauth/reference_data/
```

> **Após o rsync — reescrever os caminhos absolutos da DEV nos CSVs.** Os CSVs de escores/embeddings carregam caminhos absolutos da máquina de origem; sem esta etapa a calibração LR por tipicidade falha ("nenhuma linha com embeddings completos no disco"). Na PROD-1:
>
> ```bash
> cd /opt/forensicauth/reference_data
> grep -rl "/home/bfl-pcf" --include="*.csv" . | while read f; do
>   sed -i 's|/home/bfl-pcf/VA Suite/reference_data|/opt/forensicauth/reference_data|g' "$f"
> done
> ```
>
> (ajuste o prefixo de origem conforme o caminho real da DEV; colunas `image_path`/`audio_path` com caminhos de datasets crus, ex. `/mnt/bases/...`, não são lidas em runtime — podem ficar)

### Passo 4.4 — Copiar `vendor/` (recomendado se for grande / incompleto no Git)

```bash
rsync -avh --progress \
  "/home/$USER/VA Suite/vendor/" \
  USUARIO@<IP_PROD1>:/opt/forensicauth/vendor/
```

### Passo 4.5 — (Opcional) Sincronizar o código inteiro da DEV por cima do clone

Use se a DEV tem commits/local mais novos que o GitHub:

```bash
rsync -avh --progress \
  --exclude '.git' \
  --exclude 'data/uploads' \
  --exclude 'data/results' \
  --exclude 'data/derivatives' \
  --exclude 'data/db' \
  --exclude 'data/postgres' \
  --exclude 'src/frontend/node_modules' \
  --exclude '__pycache__' \
  --exclude '.env' \
  --exclude 'src/backend/.env' \
  "/home/$USER/VA Suite/" \
  USUARIO@<IP_PROD1>:/opt/forensicauth/
```

### Passo 4.6 — Conferir na PROD-1

Entre na PROD-1:

```bash
ssh USUARIO@<IP_PROD1>
cd /opt/forensicauth
du -sh models reference_data vendor
ls models
ls reference_data
```

`models` e `reference_data` devem ter dezenas de GB.

---

## 5. Na PROD-1 — gerar segredos e arquivo `.env.production`

Ainda na PROD-1.

### Passo 5.1 — Instalar Miniconda (para gerar chaves e depois rodar workers GPU)

```bash
cd /tmp
curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o miniconda.sh
bash miniconda.sh -b -p $HOME/miniconda3
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda init bash
```

Feche e abra o terminal (ou `source ~/.bashrc`).

### Passo 5.2 — Criar ambiente conda do projeto

```bash
cd /opt/forensicauth
conda env create -f environment.yml
conda activate forensicauth
pip install -r requirements.txt
pip install -r requirements-gpu.txt
```

> **Notas aprendidas em produção (ago/2026):**
>
> - Se o build do `mmcv==1.7.2` falhar com `No module named 'pkg_resources'`: rode `pip install "setuptools<81" wheel` e depois `pip install mmcv==1.7.2 --no-build-isolation`, e repita o requirements-gpu.
> - Se o pip "travar" por muitos minutos resolvendo versões: é o resolvedor antigo em backtracking — `pip install --upgrade pip` antes ajuda muito.
> - Se `dlib` for necessário em outra máquina: precisa de `cmake` (`pip install cmake`) e, sem gcc ≤13 com CUDA 12.x, compile com `DLIB_USE_CUDA=OFF` (CPU).
> - O repositório traz `constraints.txt` com as versões validadas; os builds Docker já o usam. Se alterar `requirements*.txt`, regenere com `pip freeze | grep -v ' @ file://' > constraints.txt` antes de commitar.

> A instalação GPU pode demorar muito. Se o PyTorch não enxergar CUDA, instale o wheel CUDA adequado (exemplo CUDA 12.4):

```bash
conda activate forensicauth
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

Teste:

```bash
conda activate forensicauth
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count()); print([torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])"
```

Deve mostrar `True`, `2` e os nomes das duas placas.

### Passo 5.3 — Gerar SECRET_KEY

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie a linha impressa (guarde).

### Passo 5.4 — Gerar chaves Ed25519 de custódia

```bash
conda activate forensicauth
python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; from cryptography.hazmat.primitives import serialization; import base64; k=Ed25519PrivateKey.generate(); print('PRIVATE='+base64.b64encode(k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode()); print('PUBLIC='+base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())"
```

Copie `PRIVATE=...` e `PUBLIC=...` (guarde backup offline; **nunca** no Git).

### Passo 5.5 — Escolher senha forte do Postgres

Invente uma senha forte. Anote como `<SENHA_DB>`.

### Passo 5.6 — Criar o arquivo `.env.production`

```bash
cd /opt/forensicauth
cp .env.production.example .env.production
nano .env.production
```

Apague o conteúdo e cole o bloco abaixo, **substituindo** os valores entre `<>` :

```env
ENVIRONMENT=production
DEBUG=false

SECRET_KEY=<COLE_AQUI_O_SECRET_KEY>
CUSTODY_SIGNING_PRIVATE_KEY=<COLE_AQUI_SO_O_VALOR_DEPOIS_DE_PRIVATE=>
CUSTODY_SIGNING_PUBLIC_KEY=<COLE_AQUI_SO_O_VALOR_DEPOIS_DE_PUBLIC=>

POSTGRES_USER=forensicauth
POSTGRES_PASSWORD=<SENHA_DB>
POSTGRES_DB=forensicauth
DATABASE_URL=postgresql+psycopg2://forensicauth:<SENHA_DB>@db:5432/forensicauth

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

UPLOAD_DIR=/app/uploads
RESULTS_DIR=/app/results
DERIVATIVES_DIR=/app/derivatives
PERITUS_CASES_DIR=/app/peritus_cases
MODELS_DIR=/app/models
REFERENCE_DATA_DIR=/app/reference_data
FORENSICAUTH_REFERENCE_DATA_DIR=/app/reference_data
HF_HUB_CACHE=/app/models/synthetic_image_detection/huggingface
TRANSFORMERS_OFFLINE=1

FORENSICAUTH_PROCESS_ROLE=api
FORENSICAUTH_WORKER_QUEUE=
GPU_AVAILABLE=false
ML_WARMUP_ON_STARTUP=false
GPU_DISTRIBUTED_LOCK=true
# Política GPU (desde ago/2026): em OOM o sistema faz purge→retry→re-enfileira
# em outra GPU. CPU nunca é usada como fallback, a menos que você ligue:
# GPU_ALLOW_CPU_FALLBACK=false

# OBRIGATÓRIO em produção: origens reais do frontend (o validador rejeita localhost).
# Formato JSON. Ajuste para o IP/hostname da PROD-1:
CORS_ORIGINS=["http://<IP_PROD1>"]

JPEG_GHOSTS_N_JOBS=12
PRNU_LOCALIZED_N_JOBS=8
COPY_MOVE_PCA_N_JOBS=0

JOB_PREVIEW_RETENTION_DAYS=0
JOB_PREVIEW_DAILY_CLEANUP=true
JOB_PREVIEW_CLEANUP_HOUR=2
```

No `nano`: `Ctrl+O` Enter para salvar, `Ctrl+X` para sair.

### Passo 5.7 — Ajustar o Compose de produção para expor DB/Redis na LAN e aceitar senha

O arquivo `docker-compose.prod.yml` usa `env_file` no `db`. Confirme que as portas estão publicadas. Se `db` ou `redis` **não** tiverem `ports:`, crie um override:

```bash
cd /opt/forensicauth
nano docker-compose.override.yml
```

Cole:

```yaml
services:
  db:
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: forensicauth
      POSTGRES_PASSWORD: <SENHA_DB>
      POSTGRES_DB: forensicauth

  redis:
    ports:
      - "6379:6379"

  app:
    environment:
      DATABASE_URL: postgresql+psycopg2://forensicauth:<SENHA_DB>@db:5432/forensicauth
      REFERENCE_DATA_DIR: /app/reference_data
      FORENSICAUTH_REFERENCE_DATA_DIR: /app/reference_data
      MODELS_DIR: /app/models

  worker:
    environment:
      DATABASE_URL: postgresql+psycopg2://forensicauth:<SENHA_DB>@db:5432/forensicauth
      REFERENCE_DATA_DIR: /app/reference_data
      FORENSICAUTH_REFERENCE_DATA_DIR: /app/reference_data
      MODELS_DIR: /app/models
    command: celery -A app.celery_app worker -Q celery -c 4 -n cpu-prod1@%h --loglevel=info
```

Salve (`Ctrl+O`, Enter, `Ctrl+X`).

> Troque `<SENHA_DB>` pelos caracteres reais da senha (iguais ao `.env.production`).
>
> **Importante:** use senha **URL-safe** (só letras, números, `-._~`). Senha com `%`, `#` etc. quebra o YAML do compose ("found character that cannot start any token") e/ou a URL do `DATABASE_URL` (`#` vira fragmento de URL). Gere uma boa com:
>
> ```bash
> openssl rand -base64 48 | tr -dc 'A-Za-z0-9._~-' | head -c 30; echo
> ```

---

## 6. Na PROD-1 — subir API + banco + Redis + frontend + worker CPU

### Passo 6.1 — Construir e iniciar

```bash
cd /opt/forensicauth
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml --env-file .env.production up -d --build
```

### Passo 6.2 — Esperar e olhar status

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml ps
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml logs -f app
```

Quando a API subir, saia dos logs com `Ctrl+C`.

### Passo 6.3 — Testar saúde

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1/health
```

Deve aparecer JSON com `"status":"ok"` (ou similar).

### Passo 6.4 — Criar o primeiro administrador

```bash
cd /opt/forensicauth
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml exec app python -c "
from uuid import uuid4
from app.database import SessionLocal
from models.user import User
from services.user_service import unset_password_hash

db = SessionLocal()
user = User(
    id=uuid4(),
    username='admin',
    email='admin@localhost',
    hashed_password=unset_password_hash(),
    password_set=False,
    role='admin',
    is_active=True,
)
db.add(user)
db.commit()
print('provisionado:', user.username)
db.close()
"
```

No navegador de outro PC da LAN abra:

```text
http://<IP_PROD1>/
```

Use **Primeiro Acesso**, username `admin`, defina senha (mín. 8 caracteres, 1 maiúscula, 1 número).

---

## 7. Na PROD-1 — ligar as DUAS GPUs locais (workers conda)

A API/Docker **não** precisa “segurar” a GPU. Os workers conda consomem a fila `gpu`.

### Passo 7.1 — Arquivo de ambiente do worker GPU (base)

```bash
cd /opt/forensicauth
mkdir -p run
nano run/env-gpu-common.env
```

Cole (troque senha e IP — aqui o worker fala com Postgres/Redis **no host**, então use `127.0.0.1`):

```env
FORENSICAUTH_PROCESS_ROLE=worker-gpu
FORENSICAUTH_WORKER_QUEUE=gpu
GPU_AVAILABLE=true
ML_WARMUP_ON_STARTUP=true
EFFORT_WARMUP_ON_STARTUP=true
SYNTHETIC_KEEP_RESIDENT=true
GPU_RESIDENT_TECHNIQUES=synthetic,effort,safe
GPU_DISTRIBUTED_LOCK=true
GPU_MIN_FREE_MB=1500
GPU_RESERVED_FUTURE_MB=4000

DATABASE_URL=postgresql+psycopg2://forensicauth:<SENHA_DB>@127.0.0.1:5432/forensicauth
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

UPLOAD_DIR=/opt/forensicauth/data/uploads
RESULTS_DIR=/opt/forensicauth/data/results
DERIVATIVES_DIR=/opt/forensicauth/data/derivatives
PERITUS_CASES_DIR=/opt/forensicauth/data/peritus_cases
MODELS_DIR=/opt/forensicauth/models
REFERENCE_DATA_DIR=/opt/forensicauth/reference_data
FORENSICAUTH_REFERENCE_DATA_DIR=/opt/forensicauth/reference_data
HF_HUB_CACHE=/opt/forensicauth/models/synthetic_image_detection/huggingface
TRANSFORMERS_OFFLINE=1

# Obrigatório: o console script do celery não coloca o cwd no sys.path dos
# processos filhos — sem isto o warmup falha com "No module named 'forensics'".
PYTHONPATH=/opt/forensicauth/src/backend
# Reduz fragmentação do alocador CUDA (OOM de TruFor com VRAM reservada-não-alocada).
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

SECRET_KEY=<MESMO_SECRET_KEY_DO_.env.production>
DEBUG=false
```

Salve.

### Passo 7.2 — Env específico da 3090 (device 0)

```bash
nano /opt/forensicauth/run/env-gpu-prod1-3090.env
```

Cole:

```env
CUDA_VISIBLE_DEVICES=0
GPU_LOCK_KEY=forensicauth:gpu:prod1-3090
```

### Passo 7.3 — Env específico da Ada (device 1)

```bash
nano /opt/forensicauth/run/env-gpu-prod1-ada.env
```

Cole:

```env
CUDA_VISIBLE_DEVICES=1
GPU_LOCK_KEY=forensicauth:gpu:prod1-ada
```

### Passo 7.4 — Scripts para subir cada worker

```bash
nano /opt/forensicauth/run/start-gpu-prod1-3090.sh
```

Cole:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/forensicauth/src/backend
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda activate forensicauth
set -a
source /opt/forensicauth/run/env-gpu-common.env
source /opt/forensicauth/run/env-gpu-prod1-3090.env
set +a
exec celery -A app.celery_app worker -Q gpu -c 1 -n gpu-prod1-3090@%h --loglevel=info
```

```bash
nano /opt/forensicauth/run/start-gpu-prod1-ada.sh
```

Cole:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/forensicauth/src/backend
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda activate forensicauth
set -a
source /opt/forensicauth/run/env-gpu-common.env
source /opt/forensicauth/run/env-gpu-prod1-ada.env
set +a
exec celery -A app.celery_app worker -Q gpu -c 1 -n gpu-prod1-ada@%h --loglevel=info
```

Torne executáveis:

```bash
chmod +x /opt/forensicauth/run/start-gpu-prod1-3090.sh /opt/forensicauth/run/start-gpu-prod1-ada.sh
```

### Passo 7.4.1 — Symlink de compatibilidade de caminhos (workers GPU no host)

O `file_path` das evidências é gravado no banco como caminho absoluto do **container** (`/app/uploads/<uuid>.<ext>`). Os workers GPU no host leem esse campo e procuram o arquivo em `/app/uploads` — que não existe no host. Crie o symlink uma vez:

```bash
sudo mkdir -p /app
sudo ln -sfn /opt/forensicauth/data/uploads /app/uploads
```

### Passo 7.5 — Testar manualmente (duas janelas de terminal)

**Terminal A:**

```bash
/opt/forensicauth/run/start-gpu-prod1-3090.sh
```

**Terminal B:**

```bash
/opt/forensicauth/run/start-gpu-prod1-ada.sh
```

Deixe os dois rodando. Se der erro de import/CUDA, leia a mensagem e corrija antes de continuar.

### Passo 7.6 — (Recomendado) systemd para subir sozinho no boot

```bash
sudo nano /etc/systemd/system/forensicauth-gpu-prod1-3090.service
```

Cole:

```ini
[Unit]
Description=ForensicAuth Celery GPU worker PROD1 3090
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=USUARIO
Group=USUARIO
WorkingDirectory=/opt/forensicauth/src/backend
ExecStart=/opt/forensicauth/run/start-gpu-prod1-3090.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo nano /etc/systemd/system/forensicauth-gpu-prod1-ada.service
```

Cole o mesmo, trocando o nome e o `ExecStart` para `...-ada.sh`.

Ative (troque `USUARIO` nos arquivos antes):

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now forensicauth-gpu-prod1-3090.service
sudo systemctl enable --now forensicauth-gpu-prod1-ada.service
sudo systemctl status forensicauth-gpu-prod1-3090.service --no-pager
sudo systemctl status forensicauth-gpu-prod1-ada.service --no-pager
```

### Passo 7.7 — Diagnóstico GPU

```bash
cd /opt/forensicauth
conda activate forensicauth
python scripts/diagnose_gpu.py
```

Corrija tudo que aparecer como `FAIL` crítico.

---

## 8. Na PROD-1 — exportar pastas via NFS (para a PROD-2 ver os mesmos arquivos)

Os workers da PROD-2 **precisam** enxergar os **mesmos caminhos** de evidências e modelos.

### Passo 8.1 — Configurar exports

```bash
sudo nano /etc/exports
```

Adicione **no final** (troque a rede se precisar):

```text
/opt/forensicauth/data/uploads      192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
/opt/forensicauth/data/results      192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
/opt/forensicauth/data/derivatives  192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
/opt/forensicauth/data/peritus_cases 192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
/opt/forensicauth/models            192.168.1.0/24(ro,sync,no_subtree_check,no_root_squash)
/opt/forensicauth/reference_data    192.168.1.0/24(ro,sync,no_subtree_check,no_root_squash)
```

Aplique:

```bash
sudo exportfs -ra
sudo systemctl enable --now nfs-kernel-server
sudo exportfs -v
```

---

## 9. Na PROD-2 — preparar a segunda máquina (workers)

Faça na **PROD-2**.

### Passo 9.1 — Pacotes base + Docker (Docker opcional aqui) + NFS client + conda

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git curl ca-certificates ufw rsync openssh-server nfs-common
```

**Drivers NVIDIA + CUDA:** repita **toda a seção 2.4** nesta máquina (2.4.1 → 2.4.9), até `nvidia-smi` mostrar as duas GPUs.  
Instale Miniconda (igual seção 5.1).

Firewall (só SSH da LAN, se quiser):

```bash
sudo ufw allow OpenSSH
sudo ufw enable
```

### Passo 9.2 — Mesma pasta `/opt/forensicauth`

```bash
sudo mkdir -p /opt/forensicauth
sudo chown $USER:$USER /opt/forensicauth
cd /opt/forensicauth
git clone https://github.com/peritopaulomax/ForensicAuth.git .
```

Ou `rsync` do código a partir da PROD-1 / DEV (como no passo 4.5), apontando para a PROD-2.

### Passo 9.3 — Criar pontos de montagem NFS (mesmos caminhos!)

```bash
sudo mkdir -p \
  /opt/forensicauth/data/uploads \
  /opt/forensicauth/data/results \
  /opt/forensicauth/data/derivatives \
  /opt/forensicauth/data/peritus_cases \
  /opt/forensicauth/models \
  /opt/forensicauth/reference_data
```

### Passo 9.4 — Testar montagem NFS

```bash
sudo mount -t nfs <IP_PROD1>:/opt/forensicauth/models /opt/forensicauth/models
ls /opt/forensicauth/models | head
```

Se listar pastas (`sepael`, `bfree`, …), está certo. Desmonte o teste:

```bash
sudo umount /opt/forensicauth/models
```

### Passo 9.5 — Montagem permanente no boot (`/etc/fstab`)

```bash
sudo nano /etc/fstab
```

Adicione (uma linha por recurso):

```text
<IP_PROD1>:/opt/forensicauth/data/uploads       /opt/forensicauth/data/uploads       nfs defaults,_netdev 0 0
<IP_PROD1>:/opt/forensicauth/data/results       /opt/forensicauth/data/results       nfs defaults,_netdev 0 0
<IP_PROD1>:/opt/forensicauth/data/derivatives   /opt/forensicauth/data/derivatives   nfs defaults,_netdev 0 0
<IP_PROD1>:/opt/forensicauth/data/peritus_cases /opt/forensicauth/data/peritus_cases nfs defaults,_netdev 0 0
<IP_PROD1>:/opt/forensicauth/models             /opt/forensicauth/models             nfs defaults,_netdev 0 0
<IP_PROD1>:/opt/forensicauth/reference_data     /opt/forensicauth/reference_data     nfs defaults,_netdev 0 0
```

Monte tudo:

```bash
sudo mount -a
df -h | grep forensicauth
```

### Passo 9.6 — Ambiente conda + deps na PROD-2

```bash
cd /opt/forensicauth
conda env create -f environment.yml
conda activate forensicauth
pip install -r requirements.txt
pip install -r requirements-gpu.txt
# se precisar:
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

### Passo 9.7 — Env dos workers apontando para o **IP da PROD-1**

```bash
mkdir -p /opt/forensicauth/run
nano /opt/forensicauth/run/env-gpu-common.env
```

Cole (note o IP da PROD-1, **não** 127.0.0.1):

```env
FORENSICAUTH_PROCESS_ROLE=worker-gpu
FORENSICAUTH_WORKER_QUEUE=gpu
GPU_AVAILABLE=true
ML_WARMUP_ON_STARTUP=true
EFFORT_WARMUP_ON_STARTUP=true
SYNTHETIC_KEEP_RESIDENT=true
GPU_RESIDENT_TECHNIQUES=synthetic,effort,safe
GPU_DISTRIBUTED_LOCK=true
GPU_MIN_FREE_MB=1500
GPU_RESERVED_FUTURE_MB=4000

DATABASE_URL=postgresql+psycopg2://forensicauth:<SENHA_DB>@<IP_PROD1>:5432/forensicauth
REDIS_URL=redis://<IP_PROD1>:6379/0
CELERY_BROKER_URL=redis://<IP_PROD1>:6379/0
CELERY_RESULT_BACKEND=redis://<IP_PROD1>:6379/0

UPLOAD_DIR=/opt/forensicauth/data/uploads
RESULTS_DIR=/opt/forensicauth/data/results
DERIVATIVES_DIR=/opt/forensicauth/data/derivatives
PERITUS_CASES_DIR=/opt/forensicauth/data/peritus_cases
MODELS_DIR=/opt/forensicauth/models
REFERENCE_DATA_DIR=/opt/forensicauth/reference_data
FORENSICAUTH_REFERENCE_DATA_DIR=/opt/forensicauth/reference_data
HF_HUB_CACHE=/opt/forensicauth/models/synthetic_image_detection/huggingface
TRANSFORMERS_OFFLINE=1

# Obrigatório: o console script do celery não coloca o cwd no sys.path dos
# processos filhos — sem isto o warmup falha com "No module named 'forensics'".
PYTHONPATH=/opt/forensicauth/src/backend
# Reduz fragmentação do alocador CUDA (OOM de TruFor com VRAM reservada-não-alocada).
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

SECRET_KEY=<MESMO_SECRET_KEY_DO_PROD1>
DEBUG=false
```

Arquivos por GPU:

```bash
nano /opt/forensicauth/run/env-gpu-prod2-3090.env
```

```env
CUDA_VISIBLE_DEVICES=0
GPU_LOCK_KEY=forensicauth:gpu:prod2-3090
```

```bash
nano /opt/forensicauth/run/env-gpu-prod2-ada.env
```

```env
CUDA_VISIBLE_DEVICES=1
GPU_LOCK_KEY=forensicauth:gpu:prod2-ada
```

Scripts (iguais aos da PROD-1, só mudando nomes):

```bash
nano /opt/forensicauth/run/start-gpu-prod2-3090.sh
```

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/forensicauth/src/backend
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda activate forensicauth
set -a
source /opt/forensicauth/run/env-gpu-common.env
source /opt/forensicauth/run/env-gpu-prod2-3090.env
set +a
exec celery -A app.celery_app worker -Q gpu -c 1 -n gpu-prod2-3090@%h --loglevel=info
```

```bash
nano /opt/forensicauth/run/start-gpu-prod2-ada.sh
```

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/forensicauth/src/backend
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda activate forensicauth
set -a
source /opt/forensicauth/run/env-gpu-common.env
source /opt/forensicauth/run/env-gpu-prod2-ada.env
set +a
exec celery -A app.celery_app worker -Q gpu -c 1 -n gpu-prod2-ada@%h --loglevel=info
```

```bash
chmod +x /opt/forensicauth/run/start-gpu-prod2-*.sh
```

Suba (manual ou systemd, espelhando a seção 7.6).

### Passo 9.8 — (Opcional) worker CPU na PROD-2 para aliviar a PRINCIPAL

```bash
nano /opt/forensicauth/run/start-cpu-prod2.sh
```

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/forensicauth/src/backend
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda activate forensicauth
export FORENSICAUTH_PROCESS_ROLE=worker-cpu
export FORENSICAUTH_WORKER_QUEUE=celery
export GPU_AVAILABLE=false
export ML_WARMUP_ON_STARTUP=false
export DATABASE_URL=postgresql+psycopg2://forensicauth:<SENHA_DB>@<IP_PROD1>:5432/forensicauth
export REDIS_URL=redis://<IP_PROD1>:6379/0
export CELERY_BROKER_URL=redis://<IP_PROD1>:6379/0
export CELERY_RESULT_BACKEND=redis://<IP_PROD1>:6379/0
export UPLOAD_DIR=/opt/forensicauth/data/uploads
export RESULTS_DIR=/opt/forensicauth/data/results
export DERIVATIVES_DIR=/opt/forensicauth/data/derivatives
export PERITUS_CASES_DIR=/opt/forensicauth/data/peritus_cases
export MODELS_DIR=/opt/forensicauth/models
export REFERENCE_DATA_DIR=/opt/forensicauth/reference_data
export FORENSICAUTH_REFERENCE_DATA_DIR=/opt/forensicauth/reference_data
export SECRET_KEY=<MESMO_SECRET_KEY_DO_PROD1>
exec celery -A app.celery_app worker -Q celery -c 2 -n cpu-prod2@%h --loglevel=info
```

```bash
chmod +x /opt/forensicauth/run/start-cpu-prod2.sh
/opt/forensicauth/run/start-cpu-prod2.sh
```

---

## 10. Verificação final (checklist “funcionou”)

Faça na PROD-1, com conda ativo:

### Passo 10.1 — Workers enxergam a fila `gpu`

```bash
cd /opt/forensicauth/src/backend
conda activate forensicauth
export REDIS_URL=redis://127.0.0.1:6379/0
export CELERY_BROKER_URL=redis://127.0.0.1:6379/0
celery -A app.celery_app inspect active_queues
```

Você deve ver nomes como:

- `gpu-prod1-3090@...`
- `gpu-prod1-ada@...`
- `gpu-prod2-3090@...`
- `gpu-prod2-ada@...`

todos com a fila `gpu`.

### Passo 10.2 — Teste na interface

1. Abra `http://<IP_PROD1>/` e faça login.
2. Crie um caso e envie uma imagem de teste.
3. Rode uma análise **leve** (metadados) → deve completar via worker CPU.
4. Rode **Detecção de imagens sintéticas** (ou outra técnica GPU).
5. Enquanto roda, na PROD-1:

```bash
nvidia-smi
```

e na PROD-2 o mesmo. A VRAM deve subir em **alguma** das placas.

6. Dispare **várias** análises GPU seguidas: elas devem ir para workers diferentes (até 4 em paralelo se `GPU_LOCK_KEY` forem distintos).

### Passo 10.3 — Endpoint de fila GPU (se autenticado na API)

Na UI ou via API autenticada, consulte a fila GPU documentada em `docs/07-operacao-e-setup.md` (`GET /api/v1/analysis/gpu-queue`).

---

## 11. Balanceamento de carga

| Situação | O que acontece |
|----------|----------------|
| 1 job GPU | Qualquer um dos 4 workers livres pega |
| 4 jobs GPU juntos | Idealmente 1 por placa (locks diferentes) |
| 5º job GPU | Fica **esperando** na fila Redis/Celery |
| Job CPU | Vai para workers `-Q celery` (PROD-1 e/ou PROD-2) |

**Dica operacional para Ada 16 GB:** deixe warmup mais enxuto na Ada (`SYNTHETIC_KEEP_RESIDENT=false` só no env da Ada) para sobrar VRAM. Nas 3090 pode manter `true`.

**Nunca** use `-c` maior que `1` no worker GPU (risco de OOM / briga pela mesma placa).

---

## 12. Atualizar o sistema depois

### No GitHub → PROD-1

```bash
cd /opt/forensicauth
git pull
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml --env-file .env.production up -d --build
# O nginx guarda o IP do app na subida: ao recriar o app, reinicie o frontend
# para evitar 502 por IP obsoleto:
docker restart forensicauth-frontend-prod
sudo systemctl restart forensicauth-gpu-prod1-3090.service forensicauth-gpu-prod1-ada.service
```

### PROD-2 (código)

```bash
cd /opt/forensicauth
git pull
# ou rsync a partir da PROD-1
sudo systemctl restart forensicauth-gpu-prod2-3090.service forensicauth-gpu-prod2-ada.service
```

Se atualizar **pesos** na DEV, rode de novo o `rsync` de `models/` e `reference_data/` para a PROD-1 (a PROD-2 vê via NFS).

---

## 13. Backup (faça desde o primeiro dia)

Na PROD-1:

```bash
mkdir -p /opt/forensicauth/backup
cd /opt/forensicauth

# Banco
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml exec -T db \
  pg_dump -U forensicauth forensicauth | gzip > backup/db_$(date +%F).sql.gz

# Evidências (pode ser enorme)
tar czf backup/files_$(date +%F).tar.gz data/uploads data/derivatives

# Segredos (guarde offline também)
cp -a .env.production secrets backup/secrets_$(date +%F)/ 2>/dev/null || mkdir -p backup/secrets_$(date +%F) && cp .env.production backup/secrets_$(date +%F)/
```

---

## 14. Problemas comuns

| Sintoma | O que fazer |
|---------|-------------|
| Análise fica `pending` para sempre | Nenhum worker na fila certa. Veja `celery inspect active_queues` e `systemctl status` dos workers. |
| `FileNotFoundError` no worker remoto | NFS não montou ou caminho diferente. `df -h` e `ls` do path na PROD-2. |
| `password authentication failed` no Postgres | Senha do `.env` ≠ `POSTGRES_PASSWORD` do container. Alinhe e `docker compose ... up -d`. |
| GPU não aparece no PyTorch | Refaça a seção 2.4; confira `nvidia-smi` e `python -c "import torch; print(torch.cuda.is_available())"`. Reinstale torch com `--index-url .../cu124` se preciso. |
| `nvidia-smi` quebrou após update do kernel | `sudo apt install --reinstall linux-headers-$(uname -r) nvidia-driver-XXX` e reboot. |
| OOM na GPU | Job pesado demais para VRAM. Use VRAM maior ou reduza residency. |
| Só 1 GPU trabalha no cluster | Todos os workers com o **mesmo** `GPU_LOCK_KEY`. Corrija para chaves distintas por placa. |
| Página/site não abre de outro PC | Firewall / IP errado. `curl http://<IP_PROD1>/` na PROD-1 e no cliente. |
| Login ok, análise ML “indisponível” | Falta pasta em `models/` ou worker GPU parado. |
| `403 Forbidden` no `apt-get` durante o build Docker | Rede exige proxy. Configure `~/.docker/config.json` (seção 2.3.1). |
| `pip install` “trava” baixando metadata de muitas versões | Resolvedor antigo em backtracking. Na imagem já há constraints; manualmente: `pip install --upgrade pip` antes. |
| `No module named 'pkg_resources'` ao compilar `mmcv` | `pip install "setuptools<81" wheel` e reinstale o mmcv com `--no-build-isolation`. |
| 502 logo após recriar o container `app` | O nginx guardou o IP antigo. `docker restart forensicauth-frontend-prod`. |
| PatchMatch nunca termina (100% CPU por horas) | `min_dn` maior que o deslocamento máximo possível da imagem (imagens pequenas). O sistema agora falha rápido informando o máximo viável — reduza o `min_dn`. |
| Análise ML “lenta demais” (minutos) que antes era segundos | Verifique se não caiu em fallback de política (log do worker GPU) e se o governor da CPU está em `performance` (`cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`). |
| “Nenhuma linha com embeddings completos” na calibração LR | Caminhos absolutos da máquina de origem nos CSVs de `reference_data/` — rode a reescrita do passo 4.3. |

Logs úteis:

```bash
# Docker
cd /opt/forensicauth
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml logs -f app worker

# Workers GPU (systemd)
sudo journalctl -u forensicauth-gpu-prod1-3090.service -f
```

---

## 15. Ordem rápida 

1. DEV: anotar IPs; medir tamanho de `models` + `reference_data`.  
2. PROD-1: Ubuntu + Docker + **driver NVIDIA + CUDA Toolkit (seção 2.4)** + Container Toolkit + clone GitHub.  
3. DEV→PROD-1: `rsync` de `models/`, `reference_data/`, `vendor/`.  
4. PROD-1: conda, secrets, `.env.production`, `docker compose ... up`.  
5. PROD-1: admin + login na web.  
6. PROD-1: 2 workers GPU (3090 + Ada) com locks diferentes.  
7. PROD-1: NFS export.  
8. PROD-2: mount NFS + conda + 2 workers GPU apontando Redis/DB da PROD-1.  
9. `celery inspect active_queues` → 4 workers na fila `gpu`.  
10. Testar job leve + job sintético + vários jobs juntos.  
11. Backup.

---

## 16. Documentação oficial no repositório

Dentro de `/opt/forensicauth`:

- `docs/public/INSTALACAO-PRODUCAO-LINUX.md`
- `docs/deploy/WORKER-REMOTE.md`
- `docs/deploy/MIGRATION-GPU.md`
- `docs/deploy/ENV-PRODUCTION-TEMPLATE.md`
- `docs/07-operacao-e-setup.md`
- `docs/09-ml-e-artefatos.md`

Este arquivo é o **roteiro operacional completo** para o seu cenário de 2 máquinas × 2 GPUs, agora versionado em `docs/deploy/INSTALACAO-PROD-WORKERS.md`; os docs do repo são a referência técnica.

---

**Fim do roteiro.** Se um comando falhar, copie a mensagem de erro inteira antes de mudar mais de uma coisa por vez.

