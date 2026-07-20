# Calibração LR — Spoofing de Áudio (POC)

Pipeline espelhando a calibração de imagens sintéticas (`synthetic_lr_reference.py`):

1. **Seleção versionada de bases** por dataset/subset (gerador ou condição de codec)
2. **Amostragem balanceada** bonafide/spoof (150+150 na POC)
3. **Extração de escores** com DF Arena 1B, SLS XLS-R, WeDefense
4. **Meta-classificador** (logit dos três detectores → score descalibrado)
5. **Bi-Gaussianized LR** (Morrison/EER) → LR calibrada favorecendo bonafide

## Pré-requisitos

- Ambiente conda `va-suite` ativo
- Pesos dos três detectores instalados localmente
- `protocolo_unificado.csv` na raiz do projeto (metadados das bases)
- Bases de áudio montadas na LAN (ajustar prefixos em `config/audio_lr_protocolo.yaml`)

### Montar bases na LAN

Copie o exemplo e ajuste o prefixo remoto → local:

```bash
cp config/audio_lr_protocolo.example.yaml config/audio_lr_protocolo.yaml
```

Exemplo quando o HD estiver montado em `/mnt/bases`:

```yaml
path_prefixes:
  - remote: /media/paulopmgir/HD10T-Bases
    local: /mnt/bases
```

Alternativas comuns:

- **NFS:** `mount servidor:/media/paulopmgir/HD10T-Bases /mnt/bases`
- **SSHFS:** `sshfs paulopmgir@maquina-bases:/media/paulopmgir/HD10T-Bases /mnt/bases`
- **SMB/CIFS:** montar share Windows/Linux na mesma LAN

Verificar acesso:

```bash
conda activate va-suite
python scripts/sync_audio_lr_samples.py \
  --manifest outputs/lr_calibration/audio_spoofing/poc/CodecFake_C1/manifest.csv \
  --check-only
```

## Passo a passo (POC 150+150)

### 1. Explorar bases disponíveis

```bash
python scripts/sample_audio_spoofing_lr.py --summary-only
```

Subsets balanceados sugeridos para POC:

| Dataset | Subset | Bonafide | Spoof |
|---------|--------|----------|-------|
| CodecFake | C1 | 13228 | 13228 |
| ADD2022 | track1test | 31334 | 77865 |

### 2. Amostrar manifest (sem copiar arquivos)

```bash
python scripts/sample_audio_spoofing_lr.py \
  --subset CodecFake/C1 \
  --with-splits \
  --out-dir outputs/lr_calibration/audio_spoofing/poc/CodecFake_C1
```

Splits: 75 train / 38 calib / 37 test **por classe** (bonafide e spoof).

### 3. Sincronizar áudios (quando montados)

```bash
python scripts/sync_audio_lr_samples.py \
  --manifest outputs/lr_calibration/audio_spoofing/poc/CodecFake_C1/manifest.csv \
  --out-dir outputs/lr_calibration/audio_spoofing/poc/CodecFake_C1
```

### 4. Extrair escores dos detectores

```bash
python scripts/run_audio_spoofing_score_matrix.py \
  --manifest outputs/lr_calibration/audio_spoofing/poc/CodecFake_C1/manifest.csv \
  --out outputs/lr_calibration/audio_spoofing/poc/CodecFake_C1/score_matrix.csv \
  --resume
```

### 5. Treinar meta-classificador + bi-Gauss LR

```bash
python scripts/run_audio_bigaussianized_lr_poc.py \
  --score-matrix outputs/lr_calibration/audio_spoofing/poc/CodecFake_C1/score_matrix.csv \
  --out-dir outputs/lr_calibration/audio_spoofing/poc/CodecFake_C1/calibration
```

Saídas: `lr_reference_report.json`, Tippett, distribuição, modelo `.joblib`.

### Pipeline completo (um comando)

```bash
python scripts/run_audio_spoofing_lr_poc_pipeline.py --subset CodecFake/C1
```

## Processamento remoto na máquina das bases

Se a GPU está nesta máquina mas os áudios estão na outra:

1. **Nesta máquina:** gerar manifest (`sample_audio_spoofing_lr.py`) — só metadados
2. **Na máquina das bases:** montar nada; paths originais do CSV já apontam para `/media/paulopmgir/...`
3. **Copiar manifest** via `scp` ou compartilhamento
4. **Rodar score matrix na máquina das bases** (com GPU e pesos)
5. **Copiar `score_matrix.csv` de volta** e rodar calibração aqui

Ou montar o HD10T via NFS/SSHFS nesta máquina e rodar tudo localmente.

## Módulo runtime (integração futura)

`src/backend/core/audio_spoofing_lr_reference.py` expõe:

- `reference_macro_catalog()` — categorias versionadas para UI
- `compute_reference_lr()` — LR calibrada a partir de matriz de scores

## Notas forenses

- **Convenção LR:** positivo favorece **bonafide** (H1 = áudio autêntico)
- **Features:** logit de `bonafide_prob` por detector (mesma direção do pipeline de imagens)
- **Janelas 4s:** escores agregados por média de logits; diferente do protocolo single-clip dos autores
- **Amostragem:** exige contagem igual bonafide/spoof **por subgrupo selecionado**
