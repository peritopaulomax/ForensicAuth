# Scripts de contribuidores (tooling de desenvolvimento)

| Pasta / arquivo | Uso |
|-------|-----|
| `diagnose_gpu.py` | Diagnóstico GPU / deps pesadas / pesos (`MODELS_DIR`) |
| `technique/` | Scaffold de novas técnicas forenses (simple/medium/comparison/ensemble) |
| `ingest_synthetic_image_reference.py` | Ingestão de base de imagens sintéticas na população de referência LR |
| `ingest_audio_spoofing_reference.py` | Ingestão de base de spoofing de áudio na população de referência LR |

## Ingestão de base sintética (população de referência)

Protocolo CSV (`image_path,base_id,subgroup,y_fake`):

```bash
conda activate forensicauth
cd "/path/to/VA Suite"
PYTHONPATH=src/backend python scripts/ingest_synthetic_image_reference.py \
  --protocol scripts/examples/synthetic_image_reference_protocol.example.csv \
  --media-root /path/to/images \
  --dataset-id MyNewBench \
  --base-group MyNewBench \
  --macro-id other_neural \
  --register-catalog
```

Ordem: materializa em `va-reference_build` → gera augs → scores/embeddings em `reference_data/`.  
Flags úteis: `--skip-scoring`, `--skip-augment`, `--limit N`.

## Ingestão de base de spoofing de áudio (população de referência)

Protocolo CSV (`audio_path,base_id,subgroup,y_spoof`):

```bash
conda activate forensicauth
cd "/path/to/VA Suite"
PYTHONPATH=src/backend python scripts/ingest_audio_spoofing_reference.py \
  --protocol scripts/examples/audio_spoofing_reference_protocol.example.csv \
  --media-root /path/to/audio \
  --dataset-id MyAudioBench \
  --base-group MyAudioBench \
  --macro-id deepfake_challenges \
  --register-catalog
```

Ordem: materializa em `va-reference_build` → augs (mp3/opus/noise) → scores/embeddings.  
Requer `ffmpeg` para `mp3_128k` / `opus_32k`. Flags: `--skip-scoring`, `--skip-augment`, `--limit N`.

## Nova técnica (simple / medium / comparison / ensemble)

```bash
# a partir da raiz do repositório, com o conda do projeto ativo
python scripts/technique/scaffold_technique.py scripts/technique/examples/simple.yaml --dry-run
python scripts/technique/scaffold_technique.py scripts/technique/examples/comparison.yaml --dry-run
python scripts/technique/scaffold_technique.py scripts/technique/examples/ensemble.yaml --dry-run
python scripts/technique/scaffold_technique.py path/to/meu_manifest.yaml
```

Depois edite **apenas** `src/backend/forensics/<id>/pipeline.py` (função `run`).

Documentação: `docs/developer/03-scaffold-technique.md`  
(§5 = IDs dos cards; §9 = ensemble; apêndice A = todos os campos YAML).  
Tutoriais: `04` mediana · `05` aHash · `06` ensemble.
