/** Metadados bibliográficos (ABNT), títulos e cards das técnicas forenses. */

export interface ForensicTechniqueMeta {
  /** Título exibido na página e no card (português; siglas mantidas). */
  title: string;
  /** Referência(s) bibliográfica(s) ABNT (parágrafos separados por linha em branco). */
  citation: string;
  /** Resumo breve no card da aba Análises. */
  cardSubtitle: string;
  /** Detalhamento técnico após a bibliografia na página da técnica. */
  detail: string;
  /** Resumo ampliado (técnicas DL com repositório). */
  summary?: string;
  license?: string;
  repoUrl?: string;
}

export const FORENSIC_TECHNIQUE_META: Record<string, ForensicTechniqueMeta> = {
  jpeg_structure_compare: {
    title: "Comparação de Estruturas JPEG",
    citation:
      "GLOE, Thomas. Forensic analysis of ordered data structures on the example of JPEG files. In: 2012 IEEE INTERNATIONAL WORKSHOP ON INFORMATION FORENSICS AND SECURITY (WIFS). 2012 IEEE International Workshop on Information Forensics and Security (WIFS). Costa Adeje - Tenerife, Spain: IEEE, dez. 2012. Disponível em: <http://ieeexplore.ieee.org/document/6412639/>. Acesso em: 18 nov. 2020.",
    cardSubtitle: "Marcadores JPEG ordenados · matriz de similaridade estrutural",
    detail:
      "Extrai a sequência ordenada de marcadores (SOI, APP, DQT, DHT, SOS…) e tabelas de quantização de cada evidência JPEG. Compara pares ou conjuntos (com referências ou todas × todas) produzindo matriz de similaridade e grade posicional de correspondência entre estruturas.",
  },
  jpeg_ghosts: {
    title: "JPEG Ghosts",
    citation:
      "FARID, H. Exposing Digital Forgeries From JPEG Ghosts. IEEE Transactions on Information Forensics and Security, v. 4, n. 1, p. 154–160, mar. 2009.",
    cardSubtitle: "Recompressão em múltiplas qualidades · fantasma de compressão",
    detail:
      "Recomprime a imagem em um intervalo de fatores de qualidade JPEG e mede o resíduo local (ghost) em blocos 8×8, com busca opcional de deslocamento de grade. Picos na métrica indicam regiões com histórico de compressão distinto do restante da imagem.",
  },
  dct_quantization: {
    title: "Inconsistência de Artefatos de Bloco (DCT)",
    citation:
      "YE, Shuiming; SUN, Qibin; CHANG, Ee-Chien. Detecting Digital Image Forgeries by Measuring Inconsistencies of Blocking Artifact. In: MULTIMEDIA AND EXPO, 2007 IEEE INTERNATIONAL CONFERENCE ON. Multimedia and Expo, 2007 IEEE International Conference on. Beijing, China: IEEE, jul. 2007. Disponível em: <http://ieeexplore.ieee.org/document/4284574/>. Acesso em: 30 ago. 2018.",
    cardSubtitle: "Matriz de quantização 8×8 · mapa de inconsistência de blocos",
    detail:
      "Estima ou aplica matrizes de quantização DCT (modo estimativa, referência jpegio ou matriz customizada) e gera mapa espacial das inconsistências de artefato de bloco 8×8 entre a evidência e a matriz de referência.",
  },
  double_compression: {
    title: "Dupla Compressão JPEG",
    citation:
      "POPESCU, Alin C.; FARID, Hany. Statistical Tools for Digital Forensics. In: FRIDRICH, Jessica (Org.). Information Hiding. Berlin, Heidelberg: Springer Berlin Heidelberg, 2004. v. 3200. p. 128–147.\n\nMAHDIAN, B.; SAIC, S. Detecting double compressed JPEG images. In: 3RD INTERNATIONAL CONFERENCE ON IMAGING FOR CRIME DETECTION AND PREVENTION (ICDP 2009). 3rd International Conference on Imaging for Crime Detection and Prevention (ICDP 2009). London, UK: IET, 2009. Disponível em: <https://digital-library.theiet.org/content/conferences/10.1049/ic.2009.0240>. Acesso em: 18 nov. 2020.",
    cardSubtitle: "Histogramas de coeficientes DCT · detecção de dupla compressão",
    detail:
      "Analisa a distribuição dos coeficientes DCT quantizados ao longo de um intervalo de índices, produzindo gráficos interativos (zoom/pan) por coeficiente. Padrões periódicos e descontinuidades nos histogramas sugerem dupla compressão JPEG.",
  },
  ela: {
    title: "Análise de Nível de Erro (ELA)",
    citation:
      "FARID, H. Exposing Digital Forgeries From JPEG Ghosts. IEEE Transactions on Information Forensics and Security, v. 4, n. 1, p. 154–160, mar. 2009.",
    cardSubtitle: "Diferença original × recompressão · mapa de nível de erro",
    detail:
      "Recomprime a evidência JPEG com qualidade e ganho configuráveis, subtrai do original e amplifica as diferenças por canal (RGB, Y ou crominância). Regiões editadas ou coladas tendem a apresentar níveis de erro distintos no heatmap resultante.",
  },
  bag_extraction: {
    title: "Extração de Grade de Artefatos de Bloco (BAG)",
    citation:
      "LI, Weihai; YUAN, Yuan; YU, Nenghai. DETECTING COPY-PASTE FORGERY OF JPEG IMAGE VIA BLOCK ARTIFACT GRID EXTRACTION. p. 6, [S.d.].",
    cardSubtitle: "Canal Y · mapa de desalinhamento da grade 8×8",
    detail:
      "Calcula, no canal de luminância, métricas de desalinhamento entre blocos JPEG adjacentes (BlockDiff) e gera mapa visual da grade de artefatos de bloco — base para análise de origem de grade e algoritmo ZERO.",
  },
  zero_grid: {
    title: "ZERO — Origem da Grade JPEG",
    citation:
      "NIKOUKHAH, Tina et al. ZERO: a Local JPEG Grid Origin Detector Based on the Number of DCT Zeros and its Applications in Image Forensics. Image Processing On Line, v. 11, p. 396–433, 16 dez. 2021.",
    cardSubtitle: "Zeros DCT + libzero · NFA e regiões de grade estrangeira",
    detail:
      "Conta coeficientes DCT nulos por pixel e agrega votos para estimar a origem da grade 8×8 (libzero). Entrega mapa de votos, grades globais com log-NFA e destaque de regiões com grade ausente ou inconsistente com o fundo.",
  },
  resampling: {
    title: "Detecção de Reamostragem",
    citation:
      "MAHDIAN, B.; SAIC, S. Blind Authentication Using Periodic Properties of Interpolation. IEEE Transactions on Information Forensics and Security, v. 3, n. 3, p. 529–538, set. 2008.",
    cardSubtitle: "2ª derivada + FFT · periodicidade de interpolação",
    detail:
      "Aplica segunda derivada na evidência (global ou em região selecionada) e analisa o espectro de frequência via FFT. Picos periódicos no espectro indicam reamostragem por interpolação (redimensionamento, rotação ou recorte com resize).",
  },
  patchmatch: {
    title: "Cópia e Colagem (PatchMatch)",
    citation:
      "COZZOLINO, Davide; POGGI, Giovanni; VERDOLIVA, Luisa. Efficient Dense-Field Copy–Move Forgery Detection. IEEE Transactions on Information Forensics and Security, v. 10, n. 11, p. 2284–2297, nov. 2015.",
    cardSubtitle: "PatchMatch + Zernike · correspondência densa interna",
    detail:
      "Busca correspondências densas de patches na própria imagem com PatchMatch acelerado por momentos de Zernike. Deslocamentos repetidos são agrupados e visualizados com setas coloridas ligando cada patch à sua região pareada.",
  },
  copy_move_pca: {
    title: "Cópia e Colagem (PCA)",
    citation:
      "POPESCU, Alin C.; FARID, Hany. Exposing Digital Forgeries by Detecting Duplicated Image Regions. [S.l.: s.n.], 2004.",
    cardSubtitle: "PCA + ordenação lexicográfica · método clássico Popescu & Farid",
    detail:
      "Detecta regiões duplicadas internas via redução PCA de blocos, quantização lexicográfica e agrupamento por vetor de deslocamento. Complementar ao PatchMatch; processa a imagem na resolução original. Use ROI opcional para focar numa região.",
  },
  wavelet_noise_residue: {
    title: "Resíduo de Ruído Wavelet",
    citation:
      "MAHDIAN, B.; SAIC, S. Using noise inconsistencies for blind image forensics. Image and Vision Computing, v. 27, n. 10, p. 1497–1503, set. 2009.",
    cardSubtitle: "DWT db8 + mediana HH · inconsistências de ruído",
    detail:
      "Extrai mapa de inconsistências de ruído via transformada wavelet (Daubechies), seleção de coeficientes HH e mediana por bloco. Visualização JET com pós-processamento opcional (distinto do denoising Wiener db4 usado no PRNU).",
  },
  prnu: {
    title: "PRNU — Impressão Digital do Sensor",
    citation:
      "FRIDRICH, Jessica. Digital Image Forensics Using Sensor Noise. p. 11, [S.d.].\n\nGOLJAN, Miroslav; FRIDRICH, Jessica; FILLER, Tomáš. Large scale test of sensor fingerprint camera identification. In: DELP III, Edward J. et al. (orgs.). IS&T/SPIE ELECTRONIC IMAGING. Anais... San Jose, CA: 5 fev. 2009. Disponível em: <http://proceedings.spiedigitallibrary.org/proceeding.aspx?doi=10.1117/12.805701>. Acesso em: 18 nov. 2020.\n\nGOLJAN, Miroslav; FRIDRICH, Jessica. Camera identification from cropped and scaled images. In: DELP III, Edward J. et al. (orgs.). ELECTRONIC IMAGING 2008. Anais... San Jose, CA: 14 fev. 2008. Disponível em: <http://proceedings.spiedigitallibrary.org/proceeding.aspx?doi=10.1117/12.766732>. Acesso em: 3 dez. 2020.",
    cardSubtitle: "Resíduo de sensor · correlação PCE e superfície C",
    detail:
      "Extrai o padrão de ruído de referência do sensor (fingerprint PRNU) a partir de imagens de referência ou derivados agregados, e correlaciona com a evidência questionada. Entrega PCE, mapa de correlação e superfície 3D de correlação cruzada.",
  },
  distildire: {
    title: "DistilDIRE — Detecção de Imagens Sintéticas por Difusão",
    citation:
      "LIM, Yewon et al. DistilDIRE: A Small, Fast, Cheap and Lightweight Diffusion Synthesized Deepfake Detection. In: ICML 2024 Workshop on Foundation Models in the Wild, 2024.",
    cardSubtitle: "DDIM 1 passo + ResNet-50 · reconstrucao DIRE leve",
    detail:
      "Reconstrói o ruido do primeiro passo DDIM (modelo ADM 256×256) e classifica imagem+ruido com DistilDIRE treinado. Indicado para imagens geradas por difusao (Stable Diffusion, DALL·E, etc.).",
    summary:
      "Entrega probabilidade de imagem sintetica, classificacao REAL/FAKE e mapa visual do epsilon DDIM.",
    license: "CC BY-NC 4.0",
    repoUrl: "https://github.com/miraflow/DistilDIRE",
  },
  safire: {
    title: "SAFIRE — Localização de Falsificação",
    citation:
      'KWON, M. et al. Segment Any Forged Image REgion (SAFIRE). In: AAAI CONFERENCE ON ARTIFICIAL INTELLIGENCE. AAAI, 2025.',
    cardSubtitle: "SAM + clustering forense · inconsistências de segmentação",
    detail:
      "Combina Segment Anything (SAM) com refinamento forense por prompts densos e clustering (k-means ou DBSCAN) para separar regiões autênticas de falsificadas.",
    summary:
      "Entrega heatmap de probabilidade de falsificação, overlay na evidência e, no modo multi-fonte, partição por cluster de origens distintas.",
    license: "MIT",
    repoUrl: "https://github.com/mjkwon2021/SAFIRE",
  },
  noiseprint: {
    title: "Noiseprint — Impressão Digital da Câmera",
    citation:
      "COZZOLINO, D.; VERDOLIVA, L. Noiseprint: A CNN-Based Camera Model Fingerprint. IEEE Transactions on Information Forensics and Security, v. 15, p. 144–159, 2020.",
    cardSubtitle: "CNN fingerprint · resíduo de modelo de câmera",
    detail:
      "Rede fully-convolutional treinada para extrair o fingerprint do modelo de câmera, suprimindo conteúdo semântico da cena.",
    summary:
      "Explora inconsistências de ruído entre regiões. Entrega mapa noiseprint, heatmap blind de localização, máscara valid e overlays de confiabilidade.",
    license: "Acadêmica / nonprofit (GRIP-UNINA)",
    repoUrl: "https://github.com/grip-unina/noiseprint",
  },
  trufor: {
    title: "TruFor — Localização de Manipulação",
    citation:
      "GUERA, D. et al. TruFor: Leveraging All-Round Clues for Trustworthy Image Forgery Localization and Detection. In: IEEE/CVF CONFERENCE ON COMPUTER VISION AND PATTERN RECOGNITION (CVPR). CVPR, 2023.",
    cardSubtitle: "Noiseprint++ + SegFormer-B2 · ruído, RGB e integridade full-res",
    detail:
      "Pipeline full-resolution com extrator Noiseprint++ e segmentador SegFormer (MIT-B2), sem resize destrutivo.",
    summary:
      "Explora pistas de ruído, RGB e alta frequência. Entrega heatmap, overlay, máscara binária, mapa de confiança e score global de integridade.",
    license: "AGPL-3.0",
    repoUrl: "https://github.com/grip-unina/TruFor",
  },
  objectformer: {
    title: "ObjectFormer — Protótipos de Objetos",
    citation:
      "WANG, J. et al. ObjectFormer for Image Manipulation Detection and Localization. In: IEEE/CVF CONFERENCE ON COMPUTER VISION AND PATTERN RECOGNITION (CVPR). CVPR, 2022.",
    cardSubtitle: "ViT-B/16 + alta frequência · protótipos de objetos",
    detail:
      "Encoder-decoder com protótipos aprendíveis sobre patches RGB e de alta frequência (FFT). Backbone ViT-B/16 processado para resolução 224×224 (reprodução IMDL-BenCo).",
    summary:
      "Explora inconsistências semânticas e traços de alta frequência. Entrega heatmap, overlay e máscara binária (inferência 224×224 com resize).",
    license: "Ver repositório",
    repoUrl: "https://github.com/wdrink/Objectformer",
  },
  cat_net: {
    title: "CAT-Net — Artefatos JPEG",
    citation:
      "KWON, M. et al. Learning JPEG Compression Artifacts for Image Manipulation Detection and Localization. International Journal of Computer Vision (IJCV), 2022.",
    cardSubtitle: "HRNet + DCT JPEG (jpegio) · artefatos de compressão 8×8",
    detail:
      "HRNet sobre coeficientes DCT quantizados via jpegio em resolução completa.",
    summary:
      "Explora inconsistências de blocos 8×8 e artefatos de compressão JPEG. Entrega mapa de manipulação, overlay e máscara de localização.",
    license: "MIT",
    repoUrl: "https://github.com/mjkwon2021/CAT-Net",
  },
  sparse_vit: {
    title: "Sparse-ViT — Detecção Não Semântica",
    citation:
      "CHEN, Y. et al. Sparse ViT: Non-Semantic Representation Learning for Image Manipulation Detection via Self-Supervised Sparse Attention. In: AAAI CONFERENCE ON ARTIFICIAL INTELLIGENCE. AAAI, 2025.",
    cardSubtitle: "Sparse-ViT + Uniformer · attention não semântica",
    detail:
      "ViT com attention esparsa auto-supervisionada e backbone Uniformer, focado em pistas de alta frequência.",
    summary:
      "Explora inconsistências locais não semânticas. Entrega heatmap de localização, overlay e máscara binária.",
    license: "Apache-2.0",
    repoUrl: "https://github.com/scu-zjz/SparseViT",
  },
  mesorch: {
    title: "Mesorch — Orquestração Multi-Escala",
    citation:
      "LIU, Y. et al. Mesorch: A Powerful Multiscale Forensic Orchistrator for Image Manipulation Detection and Localization. In: AAAI CONFERENCE ON ARTIFICIAL INTELLIGENCE. AAAI, 2025.",
    cardSubtitle: "ConvNeXt ∥ SegFormer · orquestração multi-escala",
    detail:
      "Ramo CNN (ConvNeXt) e ramo Transformer (SegFormer) em paralelo, com variantes Mesorch e Mesorch-P.",
    summary:
      "Explora pistas multi-escala em RGB. Entrega heatmap, overlay e máscara (inferência 512×512 com pós-processamento).",
    license: "Apache-2.0",
    repoUrl: "https://github.com/scu-zjz/Mesorch",
  },
  dinov3_iml: {
    title: "DINOv3-IML — Foundation Model Forense",
    citation:
      "YU, J. et al. DINOv3 Beats Specialized Detectors: A Simple Foundation Model Baseline for Image Forensics. arXiv:2604.16083, 2026.",
    cardSubtitle: "ViT-L + LoRA r=32 · backbone DINOv3 congelado",
    detail:
      "Backbone DINOv3 ViT-L congelado com adaptadores LoRA (rank 32) nas projeções QKV e cabeça convolucional leve para máscara pixel a pixel. Treinado no protocolo CAT (CASIA-v2 + FantasticReality + IMD2020 + TampCOCO).",
    summary:
      "Baseline de localização IML com ~9M parâmetros treináveis. Entrega heatmap de probabilidade, overlay e máscara binária (inferência 512×512).",
    license: "MIT",
    repoUrl: "https://github.com/Irennnne/DINOv3-IML",
  },
  co_transformers: {
    title: "Co-Transformers — Localização IML Colaborativa",
    citation:
      "ZHANG, J. et al. Collaborative Transformers with Multi-Level Forensic Attention for Image Manipulation Localization. AAAI, 2026.",
    cardSubtitle: "HES-Transformer + CTE-Transformer · atenção forense multi-nível",
    detail:
      "Framework dual-Transformer que modela inconsistências semânticas macroscópicas (Hierarchical Edge-Supervised Transformer com SegFormer-B3) e traços forenses microscópicos (Cross-trace Extraction Transformer sobre Noiseprint). Multi-Level Forensic Attention melhora robustez a pós-processamento.",
    summary:
      "Estado da arte em benchmarks IMDL-BenCo. Entrega heatmap, overlay e máscara binária (inferência 512×512 com padding e edge mask width 7).",
    license: "Ver repositório",
    repoUrl: "https://github.com/ProgrameThinking/Co-Transformers",
  },
  videofact: {
    title: "VideoFACT — Edições e Deepfake em Vídeo",
    citation:
      "NGUYEN, T. D.; FANG, S.; STAMM, M. C. VideoFACT: Detecting Video Forgeries Using Attention, Scene Context, and Forensic Traces. In: WINTER CONFERENCE ON APPLICATIONS OF COMPUTER VISION (WACV), 2024.",
    cardSubtitle: "WACV 2024 · amostragem automática de frames · mapas de localização",
    detail:
      "Processa o vídeo diretamente (decord): amostra frames, aplica modelos Xfer (edições) e/ou Deepfake (DF) com scores e heatmaps por frame. Não exige extração manual de frames.",
    summary: "Demo oficial em Gradio também opera sobre arquivo de vídeo com amostragem interna de frames.",
    license: "CC BY-NC 4.0",
    repoUrl: "https://github.com/ductai199x/videofact-wacv-2024",
  },
  stil_video_detection: {
    title: "STIL — Deepfake por Inconsistência Espaço-Temporal",
    citation:
      "GU, Z. et al. Spatiotemporal Inconsistency Learning for DeepFake Video Detection. In: ACM MULTIMEDIA, 2021.",
    cardSubtitle: "ACM MM 2021 · clips temporais · rostos por frame",
    detail:
      "Amostra frames do vídeo, recorta rostos e alimenta o bloco STIL (SCNet + módulos SIM/TIM/ISM) em clips de 8 frames para score de falsificação facial.",
    license: "Ver Tencent/TFace",
    repoUrl: "https://github.com/wizyoung/STIL-DeepFake-Video-Detection",
  },
  lowres_fake_video: {
    title: "Low-Res Fake Video Detection (TUM)",
    citation:
      "MITTERMAIR, A.; HOELLEIN, L. Low-Resolution Fake Video Detection. Projeto ADL4CV, TU Munich.",
    cardSubtitle: "Baseline Xception temporal · vídeos comprimidos/baixa resolução",
    detail:
      "Amostra frames com detecção de rosto e classifica cada frame com baseline Xception treinada no FaceForensics++, agregando scores temporais para decisão do vídeo.",
    repoUrl: "https://github.com/lukasHoel/fake-video-detection",
  },
};

export function getForensicTechniqueMeta(techniqueId: string): ForensicTechniqueMeta | undefined {
  return FORENSIC_TECHNIQUE_META[techniqueId];
}

export function getTechniqueTitle(techniqueId: string, fallback?: string): string {
  return FORENSIC_TECHNIQUE_META[techniqueId]?.title ?? fallback ?? techniqueId;
}

export function getTechniqueCardSubtitle(techniqueId: string): string | undefined {
  return FORENSIC_TECHNIQUE_META[techniqueId]?.cardSubtitle;
}

/** Rótulos legados para técnicas sem entrada em FORENSIC_TECHNIQUE_META. */
export const LEGACY_TECHNIQUE_LABELS: Record<string, string> = {
  metadata: "Metadados e estrutura JPEG",
  synthetic_image_detection: "Detecção de Imagens Sintéticas",
  mock_technique: "Técnica de Teste",
  mp3_parser: "Áudio forense (hub)",
  opus_parser: "Áudio forense (hub)",
  audio_forensics: "Análise forense de Áudio",
  __audio_hub__: "Análise forense de Áudio",
  __audio_spectral__: "Análise espectral (áudio)",
  __audio_levels__: "Análise de níveis (áudio)",
  audio_spectrogram: "Análise forense de Áudio",
  audio_enf: "Análise forense de Áudio",
  audio_ltas: "Análise forense de Áudio",
  audio_levels: "Análise forense de Áudio",
  audio_dc_local: "Análise forense de Áudio",
  wav_ima_adpcm: "WAV IMA ADPCM",
  pdf_font_color_overlay: "PDF — Overlay por fonte",
  pdf_structure_metrics: "PDF — Estrutura e métricas (grafo)",
  pdf_structure_similarity: "PDF — Similaridade estrutural",
  pdf_forensic_extract: "PDF — Extração forense",
  isomedia_parser: "Vídeo — Parser ISO BMFF",
  isomedia_compare: "Vídeo — Similaridade ISO BMFF",
  videofact: "Vídeo — VideoFACT (edições/deepfake)",
  stil_video_detection: "Vídeo — STIL deepfake",
  lowres_fake_video: "Vídeo — Low-Res fake video (TUM)",
};

export function resolveTechniqueLabel(techniqueId: string): string {
  return getTechniqueTitle(techniqueId, LEGACY_TECHNIQUE_LABELS[techniqueId]);
}
