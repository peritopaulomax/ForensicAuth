# Critical Paths — ForensicAuth

**Atualizado:** 2026-07-04

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

## Path 3: Análise Spoofing Áudio (Tier 1) — **NOVO**

```text
POST /analysis (technique=audio_spoofing_detection)
  → fila CPU → AudioSpoofingAdapter
      → df_arena / sls / wedefense (selecionáveis)
      → janelas 4s, agregação média logits
  → detector_scores.txt, plot_by_detector JSON
```

**Riscos:** detectores discordam; pesos locais obrigatórios; ≠ protocolo autores em áudio longo.

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

## Priorização

1. Upload | 2. Análise (imagem/spoofing) | 3. Login | 4. Verificação | 5. Derivado | 6. Fechamento

## O que para o sistema

- PostgreSQL → tudo
- Redis → jobs GPU lock
- FS → evidências + modelos locais
- Pesos ausentes → técnica ML indisponível (runtime_status)
