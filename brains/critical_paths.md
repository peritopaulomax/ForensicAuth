# Critical Paths — ForensicAuth

**Atualizado:** 2026-07-08

## Path 1: Upload (Tier 0)

```text
POST /evidences/upload
  → EvidenceService.upload_evidence (SHA-256, FS)
  → CustodyService.create_record("evidence_upload")
```

## Path 2: Análise Imagem Sintética (Tier 0)

```text
POST /analysis (technique=synthetic_image_detection)
  → fila GPU → SyntheticImageDetectionAdapter
      → HF detectors + B-Free + Corvi2023 (+ SAFE tiles)
      → optional: synthetic_lr_reference (LR calibrado)
  → model_scores.txt, plots, LR artifacts
```

## Path 3: Análise Spoofing Áudio (Tier 1) — **EXPANDIDO**

```text
POST /analysis (technique=audio_spoofing_detection)
  → fila CPU → AudioSpoofingAdapter
      → df_arena / sls / wedefense (selecionáveis)
      → janelas 4s, agregação média logits, embeddings opcionais
      → optional: compute_reference_lr
          → score matrix original (logits) ou representations.csv (scores+embeddings)
          → amostra estratificada por subgrupo/classe
          → split train_logreg / calibration_bigauss / test_bigauss
          → meta-classificador → calibração bi-Gaussiana EER
          → tipicidade latente opcional (k-NN sistema D)
  → detector_scores.txt, audio_spoofing_details.json, plot temporal JSON
  → LR: lr_reference_report.json, lr_reference_summary.txt,
        lr_reference_tippett.png, lr_reference_distribution.png,
        lr_reference_identity.png, lr_reference_model.joblib,
        lr_reference_test_scored.csv
```

**Riscos:** detectores discordam; pesos locais obrigatórios; LR exige score matrix/representations gerados offline; primeira calibração com tipicidade pode demorar minutos.

## Path 4: Análise Genérica (Tier 0)

```text
POST /analysis → JobService → Celery/thread → plugin.analyze
  → stage artifacts → result.json (sem CustodyRecord)
```

## Path 5: Derivado (Tier 1)

```text
POST /evidences/derivatives → DerivativeService → CustodyRecord
```

## Path 6: Verificação Forense (Tier 0)

```text
GET /audit/verify-case-forensic/{case_id} → ForensicIntegrityService
```

## Path 7: Login (Tier 0)

```text
POST /auth/login → JWT HS256
```

## Path 8: Fechamento (Tier 1)

```text
POST /cases/{id}/close → manifesto assinado → CustodyRecord
```

## Path 9: Catálogo de Referência de Spoofing de Áudio (Tier 1)

```text
GET /analysis/audio-spoofing-reference-catalog
  → audio_spoofing_lr_reference.reference_macro_catalog
  → macro categorias: asv_classic, codec_conditions, deepfake_challenges, in_the_wild
  → detector_eer_catalog_metadata (EER por gerador, labels dos detectores)
  → frontend: ReferencePopulationSelector com split treino/calibração vs teste
```

## Path 10: Tipicidade Latente (Tier 2)

```text
scripts/audio_lr_*.py → matriz de representações (scores + embeddings .npy)
  → core/latent_typicality/:
      config.py: sistema D, cosine, k=5
      typicality.py: k-NN real/spoof, CDF empírica, distâncias r_R/r_S
      features.py: sistemas A/B/C/D
          A: S_* (logits)
          B: A + T_R_*, T_S_*
          C: B + OOD_*
          D: C + Delta_r_*, rho_*
      representations_utils.py: sample_id, embedding I/O, parent_source_id
  → compute_reference_lr com use_latent_typicality=true carrega representations.csv,
    constrói bancos k-NN no split train_logreg, materializa features em batches
```

## Path 11: População de Referência Aumentada (Tier 2)

```text
scripts/audio_lr_augmentation.py
  → mp3_128k, opus_32k, noise_snr_20, noise_snr_15
  → multiplicador = 1 + 4 = 5 amostras por classe/subgrupo
scripts/audio_lr_completion_gate.py + audio_lr_disk_verify.py
  → gate de completude: WAV + embeddings 3/3 + scores para originais e augmentações
  → audit em outputs/lr_calibration/audio_spoofing/inventory/
```

## Priorização

1. Upload | 2. Análise (imagem/spoofing) | 3. Login | 4. Verificação | 5. Derivado | 6. Fechamento | 7. Catálogo LR áudio | 8. Tipicidade/aumentação

## O que para o sistema

- PostgreSQL → tudo
- Redis → jobs GPU lock
- FS → evidências + modelos locais
- Pesos ausentes → técnica ML indisponível (runtime_status)
- Score matrix / representations.csv ausentes → LR de áudio indisponível
- Cache SHA-256 de calibração LR em `outputs/lr_calibration/cache/` (.joblib)

## Controles de LR e Tipicidade no Frontend

- `AudioSpoofingAnalysis.tsx`: seleção de detectores, `ReferencePopulationSelector` (split fit/test), meta-classificador, checkbox de população aumentada e tipicidade latente, painel `ReferenceLrPanel` com Tippett/distribuição/identidade, botões de salvar derivados.
