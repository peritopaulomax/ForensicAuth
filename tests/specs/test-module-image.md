# test-module-image.md - Especificacao de Testes: Imagem

## Dados de Teste

- `tests/fixtures/images/`
  - `original.jpg` — JPEG nativo sem adulteracao
  - `double_compressed.jpg` — JPEG com dupla compressao
  - `spliced.jpg` — Imagem com regiao colada de outra fonte
  - `copymove.jpg` — Copy-move forgery
  - `resampled.jpg` — Imagem reamostrada (resize)
  - `deepfake_sample.jpg` — Face sintetica (para deepfake/sepael)
  - `camera_fingerprint.prnu` — Fingerprint PRNU de camera padrao

## Testes Unitarios

### TU-IMG-001: JPEG DCT Artifacts - Deteccao de adulteracao
- **Adapter**: `DCTArtifactsAdapter`
- **Entrada**: `tests/fixtures/images/spliced.jpg`
- **Setup**: Matriz de quantizacao extraida do proprio arquivo
- **Saida esperada**: success=true, metrics com mapa de inconsistencias
- **Verificacoes**:
  - Valores de BMat nao sao todos zero
  - Regioes com alto residuo indicam possivel manipulacao
  - Artefato `bmat_heatmap.png` gerado

### TU-IMG-002: JPEG Ghosts - Deteccao de dupla qualidade
- **Adapter**: `JPEGGhostsAdapter`
- **Entrada**: `tests/fixtures/images/double_compressed.jpg`
- **Parametros**: Qmin=50, Qmax=100, step=5
- **Saida esperada**: success=true
- **Verificacoes**:
  - Metrica `ghost_regions` > 0
  - Heatmap mostra discrepancia em pelo menos uma qualidade

### TU-IMG-003: PRNU - Identificacao de camera
- **Adapter**: `PRNUAdapter`
- **Entrada**: `tests/fixtures/images/original.jpg`
- **Parametros**: fingerprint_path="tests/fixtures/images/camera_fingerprint.prnu"
- **Saida esperada**: success=true
- **Verificacoes**:
  - PCE > threshold (ex: 50)
  - p_value < 0.01
  - Artefato de correlacao gerado

### TU-IMG-004: PRNU - Imagem de camera diferente
- **Entrada**: `tests/fixtures/images/spliced.jpg` (de outra camera)
- **Parametros**: mesmo fingerprint
- **Saida esperada**: success=true
- **Verificacoes**:
  - PCE baixo (indicativo de nao-match)
  - p_value alto

### TU-IMG-005: PatchMatch - Copy-move detection
- **Adapter**: `PatchMatchAdapter`
- **Entrada**: `tests/fixtures/images/copymove.jpg`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Mascara binaria gerada (`mask.png`)
  - Pelo menos 2 componentes conectadas grandes detectadas
  - F-score alto se ground truth disponivel

### TU-IMG-005: PatchMatch - Copy-move detection
- **Adapter**: `PatchMatchAdapter`
- **Entrada**: `tests/fixtures/images/copymove.jpg`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Mascara binaria gerada (`mask.png`)
  - Pelo menos 2 componentes conectadas grandes detectadas
  - F-score alto se ground truth disponivel

### TU-IMG-005b: Copy-Move PCA (Popescu & Farid)
- **Adapter**: `CopyMovePcaPlugin`
- **Entrada**: `tests/fixtures/images/copymove.jpg`
- **Parametros**: defaults Peritus (`b=7`, `n_comp=0.75`, `nf=128`, `nd=16`)
- **Saida esperada**: success=true
- **Verificacoes**:
  - Mascara e overlay gerados (`mask.png`, `overlay.png`)
  - Area mascarada > 0 em copy-move sintetico
  - Reexecucao deterministica (hash identico da mascara com mesmos params)
  - ROI reduz `nb_blocks` vs imagem inteira

### TU-IMG-006: Detecção de imagens sintéticas - Deteccao de IA
- **Adapter**: `Detecção de imagens sintéticasAdapter`
- **Entrada**: `tests/fixtures/images/deepfake_sample.jpg`
- **Setup**: Modelos carregados (mock ou real se disponivel)
- **Saida esperada**: success=true
- **Verificacoes**:
  - Score agregado indica "AI" ou "Real"
  - Todos os modelos individuais retornaram scores
  - Visualizacoes de residuo e FFT geradas

### TU-IMG-007: BAG - Desalinhamento de grid
- **Adapter**: `BAGAdapter`
- **Entrada**: `tests/fixtures/images/spliced.jpg`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Mapa de calor mostra regioes com alto desalinhamento

### TU-IMG-008: ZERO - Origem do grid JPEG
- **Adapter**: `ZEROAdapter`
- **Entrada**: `tests/fixtures/images/original.jpg`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Grid global detectado
  - LNFA do grid principal e significativo
  - Sem forjarias detectadas em imagem original

### TU-IMG-009: Estimativa de Quantizacao
- **Adapter**: `QuantizationEstimationAdapter`
- **Entrada**: `tests/fixtures/images/double_compressed.jpg`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Matriz 8x8 estimada gerada
  - Fatores de quantizacao dentro de range razoavel (1-100)

### TU-IMG-010: Reamostragem
- **Adapter**: `ResamplingAdapter`
- **Entrada**: `tests/fixtures/images/resampled.jpg`
- **Saida esperada**: success=true
- **Verificacoes**:
  - Picos periodicos detectados no espectro FFT da autocovariancia

## Testes de Integracao

### TI-IMG-001: Pipeline de imagem completo
- **Fluxo**:
  1. Upload de imagem
  2. Submissao de 3 jobs: PRNU, JPEG Ghosts, Detecção de imagens sintéticas
  3. Todos completam com sucesso
  4. Resultados acessiveis via API
  5. Cadeia de custodia verificavel

## Mocks/Stubs

- Mock de modelos PyTorch/InsightFace para Detecção de imagens sintéticas/Deepfake (evita carregamento pesado em testes)
- Mock de GPU lock
- Arquivos de teste pequenos (<< 1MB)
