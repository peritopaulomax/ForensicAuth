# reference_data — populações publicadas (LR / tipicidade)

Ativos **leves/versionáveis** + features publicadas. Staging pesado (WAVs
aumentados) em ``$FORENSICAUTH_REFERENCE_BUILD_DIR``, fora do git.

Ver (clone local, não versionado): `DOCS_DEV_NOGIT/calibration/REFERENCE-DATA-LIFECYCLE.md`

Paths canônicos de código: `src/backend/core/reference_data/paths.py`.

**Calibração LR / typicality:** em **`reference_data/`** (catalog, populations, features, macros). Não depende de pasta `ops/` nem de YAMLs de protocolo em `config/`. Staging pesado (WAVs aumentados etc.) pode usar `$FORENSICAUTH_REFERENCE_BUILD_DIR` fora do git.


## Layout (publish)

- `*/catalog/macros.yaml` — **fonte dos checkboxes** da UI
- `*/populations/` — defaults / presets
- `*/features/` — scores + embeddings (runtime)
- `cache/` — joblib LR (regenerável)

## Roots

```bash
export FORENSICAUTH_BASES_ROOT=/mnt/bases
export FORENSICAUTH_REFERENCE_BUILD_DIR=$HOME/va-reference_build
export FORENSICAUTH_REFERENCE_DATA_DIR=$PWD/reference_data
```

Não existe `scripts/reference_pipeline.py` no repositório. Paths canônicos:
`src/backend/core/reference_data/paths.py`. Ingestão de populações usa os
scripts versionados em `scripts/` (ver `scripts/README.md`):

- `ingest_synthetic_image_reference.py`
- `ingest_audio_spoofing_reference.py`
