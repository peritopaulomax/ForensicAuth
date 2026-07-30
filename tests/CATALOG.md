# Catálogo dos testes Python

Lista cada arquivo de teste e, em uma frase, **o que ele verifica**.

Alguns testes só rodam com modelos baixados ou GPU. No dia a dia use:

`pytest … -m "not weights and not gpu"`

---

## Pasta `unit/` (65 arquivos)

| Arquivo | O que esse teste verifica |
|---|---|
| `test_audio_lr_cache_hit.py` | Se o cache do cálculo LR de áudio é lido de volta corretamente |
| `test_audio_plot_snapshot.py` | Se as imagens PNG de gráficos de áudio batem com o esperado |
| `test_audio_plot_traces.py` | Se os gráficos interativos de áudio são enviados certos para a tela |
| `test_audio_plugins.py` | Se as técnicas de áudio rodam e geram os arquivos de resultado |
| `test_audio_prepare.py` | Se o sistema prepara o arquivo de áudio temporário sem erro |
| `test_audio_probe.py` | Se o sistema lê duração, formato e outros dados do áudio |
| `test_audio_representations.py` | Se IDs e arquivos de “assinatura” de áudio são montados e corrigidos certo |
| `test_auth.py` | Login, token de sessão e permissões de usuário |
| `test_case_access.py` | Quem pode ver cada caso (dono / responsável) |
| `test_case_deletion.py` | Se apagar um caso não quebra o histórico de custódia |
| `test_case_lifecycle.py` | Fechar e reabrir caso com as assinaturas necessárias |
| `test_case_shares.py` | Compartilhar caso com outro usuário e controlar o acesso |
| `test_case_transfer.py` | Exportar e importar um caso completo (pacote VCP) |
| `test_copy_move_pca.py` | Detecção de cópia-e-cola em imagem (técnica Copy-Move) |
| `test_core.py` | Peças centrais do motor (registro básico do sistema) |
| `test_custody.py` | Cadeia de custódia: registros, assinatura digital e relatório em texto |
| `test_custody_integration.py` | Do upload da evidência até o registro na custódia |
| `test_data_runtime.py` | Se arquivos de trabalho ficam em `data/`, fora do código |
| `test_dct_reference_submit.py` | Se o job DCT com imagem de referência recebe os parâmetros certos |
| `test_derivation_lineage.py` | Se o sistema monta o “parentesco” entre evidências derivadas |
| `test_derivative_api.py` | Pela API: salvar resultado como evidência derivada e ver a linhagem |
| `test_derivative_service.py` | Por dentro: transformar resultado de análise em evidência derivada |
| `test_evidence.py` | Envio e consulta de evidências |
| `test_evidence_references.py` | Diferença entre evidência do caso e material só de referência |
| `test_forensic_integrity.py` | Se o caso ainda está íntegro (hashes e assinaturas batem) |
| `test_forensic_metadata_insights.py` | Alertas automáticos a partir de metadados (sem repetir o mesmo aviso) |
| `test_gpu_runtime.py` | Uso da GPU: fila, trava, memória e fallback para CPU |
| `test_image_plugins.py` | Técnicas de imagem (ex.: ELA) via plugins |
| `test_imdlbenco.py` | Pacote IMDL-BenCo: métodos disponíveis e se os pesos existem |
| `test_isom.py` | Estrutura de vídeo MP4/ISO e comparação entre dois arquivos |
| `test_job_dispatch.py` | Se o job vai para a fila certa (CPU ou GPU) |
| `test_job_preview_reproducibility.py` | Preview rápido e depois resultado “oficial” reproduzível |
| `test_jobs.py` | Criar, acompanhar e concluir jobs de análise |
| `test_jpeg_structure_compare.py` | Comparar a estrutura interna de JPEGs (tabelas, marcadores, grade) |
| `test_jpeg_structure_compare_integration.py` | Mesma comparação JPEG pelo plugin, no formato que a tela espera |
| `test_latent_typicality.py` | Cálculo de “quão típico” um embedding é em relação a exemplos reais/falsos |
| `test_legacy_plugins.py` | Técnicas clássicas: PRNU, DCT, JPEG Ghosts, resampling, grade ZERO |
| `test_lfv.py` | Detecção de vídeo deepfake em baixa resolução (LFV) |
| `test_metadata_extractor.py` | Extração de metadados da imagem (EXIF etc.) |
| `test_metadata_hints.py` | Textos de ajuda explicando o que cada campo de metadado significa |
| `test_moe_ffd.py` | Detector facial MoE-FFD (com simulação, sem precisar de peso) |
| `test_pdf_forensic_extract.py` | Extrair versões e conteúdo forense de PDF |
| `test_pdf_signatures.py` | Assinaturas digitais PDF (cadeia, validação, plugin E2E) |
| `test_pdf_plugins.py` | Técnicas de PDF oferecidas na interface |
| `test_pdf_structure_graph.py` | Desenho do grafo da estrutura do PDF |
| `test_pdf_structure_similarity.py` | Comparar a estrutura de dois PDFs |
| `test_peritus_bridge.py` | Importar/exportar pacote no formato Peritus |
| `test_plugin_contracts.py` | Regras para cadastrar ou remover uma técnica no sistema |
| `test_presentation_attack_detection.py` | Detecção de ataque de apresentação (foto/tela no lugar do rosto) |
| `test_preview_cleanup.py` | Limpeza de previews (layout nested + legado + scheduler) |
| `test_preview_effective.py` | Parâmetros usados de fato no preview e na geração do resultado |
| `test_provenance_contract.py` | Formato padrão dos dados de origem/proveniência |
| `test_reference_data_paths.py` | Caminhos dos dados de referência LR (só a pasta publicada, não o staging) |
| `test_repo_forbidden_names.py` | Impede que pastas antigas/proibidas voltem na raiz do projeto |
| `test_reproducibility.py` | Manifesto de execução e hashes para poder repetir a análise |
| `test_safire.py` | SAFIRE: achar região provavelmente adulterada na imagem |
| `test_score_matrix_hash_sidecar.py` | Hash rápido da planilha de scores (acelera o cache LR) |
| `test_spectrogram.py` | Espectrograma de áudio: cálculo, redução, PNG e dados para a tela |
| `test_synthetic_image_detection.py` | Conjunto de detectores de imagem gerada por IA |
| `test_synthetic_image_embeddings.py` | Extração de vetores (embeddings) desses detectores — precisa de pesos |
| `test_synthetic_lr_cache_key_stability.py` | Cache LR de imagem não quebra se o caminho absoluto da pasta mudar |
| `test_thumbnail.py` | Miniatura da evidência |
| `test_videofact.py` | Integração VideoFACT (vídeo) |
| `test_wavelet_noise_residue.py` | Análise de ruído por wavelets (técnica clássica Peritus) |
| `test_xmp_packet.py` | Leitura do bloco XMP da imagem |
| `test_xmp_structural_tree.py` | Árvore completa do XMP (campos um dentro do outro) |

---

## Pasta `integration/` (7 arquivos)

| Arquivo | O que esse teste verifica |
|---|---|
| `test_audio_spoofing_multi.py` | Pela API: vários detectores de áudio falso (voz sintética) |
| `test_case_shares_api.py` | Pela API: compartilhar caso |
| `test_imdlbenco_methods_roles.py` | Quais métodos IMDL cada perfil de usuário pode usar |
| `test_moe_ffd_api.py` | Pela API: criar job MoE-FFD |
| `test_presentation_attack_detection_api.py` | Pela API: criar job de detecção facial anti-spoof |
| `test_synthetic_new_detectors_smoke.py` | Teste rápido dos detectores novos de imagem sintética (pesos + GPU) |
| `test_video_ml_e2e.py` | Fluxo quase completo do VideoFACT (simulado) |

---

## Outros arquivos (não são “um teste”)

| Arquivo / pasta | Função |
|---|---|
| `unit/derivative_support.py` | Funções auxiliares usadas pelos testes de derivação |
| `conftest.py` | Dados e ambiente comuns a todos os testes (usuário, caso, banco…) |
| `specs/*.md` | Descrição do que *deveria* ser testado (texto, não roda sozinho) |
| `fixtures/` | Imagens e arquivos usados como entrada dos testes |

Mais sobre como rodar a suite: [`README.md`](./README.md).
