/** Metadados bibliográficos (ABNT), títulos e cards das técnicas forenses. */

import { SCAFFOLDED_TECHNIQUE_META } from "./scaffoldedTechniqueMeta";

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

const _BASE_FORENSIC_TECHNIQUE_META: Record<string, ForensicTechniqueMeta> = {
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
      "Analisa a distribuição dos coeficientes DCT quantizados ao longo de um intervalo de índices, produzindo gráficos interativos (zoom/pan) por coeficiente. Padrões periódicos nos histogramas sugerem dupla compressão JPEG.",
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
      "Calcula, no canal de luminância, métricas de desalinhamento entre blocos JPEG adjacentes (BlockDiff) e gera mapa visual da grade de artefatos de bloco.",
  },
  zero_grid: {
    title: "ZERO — Origem da Grade JPEG",
    citation:
      "NIKOUKHAH, Tina et al. ZERO: a Local JPEG Grid Origin Detector Based on the Number of DCT Zeros and its Applications in Image Forensics. Image Processing On Line, v. 11, p. 396–433, 16 dez. 2021.",
    cardSubtitle: "Zeros DCT + libzero · NFA e regiões de grade estrangeira",
    detail:
      "Conta coeficientes DCT nulos, por pixel, para cada um dos 64 posicionamentos de grade possível, e agrega votos para estimar a origem da grade 8×8 (libzero). Entrega mapa de votos e destaque de regiões com grade ausente ou inconsistente com o fundo.",
  },
  resampling: {
    title: "Detecção de Reamostragem",
    citation:
      "MAHDIAN, B.; SAIC, S. Blind Authentication Using Periodic Properties of Interpolation. IEEE Transactions on Information Forensics and Security, v. 3, n. 3, p. 529–538, set. 2008.",
    cardSubtitle: "2ª derivada + FFT · periodicidade de interpolação",
    detail:
      "Aplica segunda derivada na função autocorrelação de diferentes projeções Radon da imagem questionada. Padrões periódicos nesta segunda derivada são detectados por meio de picos em sua FFT. O gráfico mostrado corresponde ao empilhamento max-hold de todas as FFT, nas diferentes direções da transformada Radon. Periodicidade indica reamostragem por interpolação (redimensionamento, rotação ou recorte com resize).",
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
      "Detecta regiões duplicadas internas via redução PCA de blocos, quantização lexicográfica e agrupamento por vetor de deslocamento. Processa a imagem na resolução original. Use ROI opcional para focar numa região.",
  },
  wavelet_noise_residue: {
    title: "Resíduo de Ruído Wavelet",
    citation:
      "MAHDIAN, B.; SAIC, S. Using noise inconsistencies for blind image forensics. Image and Vision Computing, v. 27, n. 10, p. 1497–1503, set. 2009.",
    cardSubtitle: "DWT db8 + mediana HH · inconsistências de ruído",
    detail:
      "Extrai mapa de inconsistências de ruído via transformada wavelet (Daubechies), seleção de coeficientes HH e mediana por bloco.",
  },
  prnu: {
    title: "PRNU — Impressão Digital do Sensor",
    citation:
      "FRIDRICH, Jessica. Digital Image Forensics Using Sensor Noise. p. 11, [S.d.].\n\nGOLJAN, Miroslav; FRIDRICH, Jessica; FILLER, Tomáš. Large scale test of sensor fingerprint camera identification. In: DELP III, Edward J. et al. (orgs.). IS&T/SPIE ELECTRONIC IMAGING. Anais... San Jose, CA: 5 fev. 2009. Disponível em: <http://proceedings.spiedigitallibrary.org/proceeding.aspx?doi=10.1117/12.805701>. Acesso em: 18 nov. 2020.\n\nGOLJAN, Miroslav; FRIDRICH, Jessica. Camera identification from cropped and scaled images. In: DELP III, Edward J. et al. (orgs.). ELECTRONIC IMAGING 2008. Anais... San Jose, CA: 14 fev. 2008. Disponível em: <http://proceedings.spiedigitallibrary.org/proceeding.aspx?doi=10.1117/12.766732>. Acesso em: 3 dez. 2020.",
    cardSubtitle: "Resíduo de sensor · correlação PCE e superfície C",
    detail:
      "Extrai o padrão de ruído de referência do sensor (fingerprint PRNU) a partir de imagens de referência ou derivados agregados, e correlaciona com a evidência questionada. Entrega PCE, mapa de correlação e superfície 3D de correlação cruzada.",
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
  miml_apscnet: {
    title: "MIML APSC-Net — Localização de Manipulação",
    citation:
      "QU, Chenfan; ZHONG, Yiwu; LIU, Chongyu; XU, Guitao; PENG, Dezhi; GUO, Fengjun; JIN, Lianwen. Towards Modern Image Manipulation Localization: A Large-Scale Dataset and Novel Methods. In: IEEE/CVF CONFERENCE ON COMPUTER VISION AND PATTERN RECOGNITION (CVPR). 2024. p. 10781–10790. Disponível em: <https://github.com/qcf-568/MIML>. Acesso em: 28 jul. 2026.",
    cardSubtitle: "CVPR 2024 · APSC-Net · Adaptive Perception + Self-Calibration",
    detail:
      "APSC-Net (Adaptive Perception + Self-Calibration) do ecossistema MIML: fusiona pistas multi-visão com pesos adaptativos e refina a máscara com kernel aprendido. Treinado no dataset MIML (~123 mil imagens forjadas manualmente), voltado a edições modernas do tipo Photoshop/web.",
    summary:
      "Localização single-image de regiões manipuladas. Entrega heatmap de probabilidade, overlay na evidência e máscara binária (inferência 512×512).",
    license: "CC BY-NC 4.0",
    repoUrl: "https://github.com/qcf-568/MIML",
  },
  videofact: {
    title: "VideoFACT — Edições e Deepfake em Vídeo",
    citation:
      "NGUYEN, T. D.; FANG, S.; STAMM, M. C. VideoFACT: Detecting Video Forgeries Using Attention, Scene Context, and Forensic Traces. In: WINTER CONFERENCE ON APPLICATIONS OF COMPUTER VISION (WACV), 2024.",
    cardSubtitle: "WACV 2024 · amostragem automática de frames · mapas de localização",
    detail:
      "Processa o vídeo diretamente (decord): amostra frames, aplica modelos Xfer (edições) e/ou Deepfake (DF) com scores e heatmaps por frame. Não exige extração manual de frames.",
    summary: "Processa o arquivo de vídeo com amostragem interna de frames (sem extração manual prévia).",
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
  truvil: {
    title: "TruVIL — Localização de Inpainting em Vídeo",
    citation:
      "LOU, Z. et al. Trusted Video Inpainting Localization via Deep Attentive Noise Learning. IEEE Transactions on Dependable and Secure Computing, 2025.",
    cardSubtitle: "IEEE TDSC 2025 · clips 5 frames · HP3D + atenção cross-modal",
    detail:
      "Localiza regiões de inpainting em vídeo via ruído 3D atento (HP3D) e fusão cross-modal. Protocolo oficial: 5 frames em 240×432; devolve máscara, heatmap e overlay sem rótulo autenticidade.",
    license: "CC BY-NC 4.0",
    repoUrl: "https://github.com/multimediaFor/TruVIL",
  },
  vilocal: {
    title: "ViLocal — Localização de Inpainting em Vídeo",
    citation:
      "LOU, Z.; CAO, G.; LIN, M. Video Inpainting Localization with Contrastive Learning. IEEE Signal Processing Letters, 2025.",
    cardSubtitle: "IEEE SPL 2025 · clips 5 frames · contrastive encoder + decoder",
    detail:
      "Localiza regiões de inpainting em vídeo com aprendizado contrastivo (encoder) e supervisão de localização (decoder). Protocolo oficial: 5 frames em 240×432; devolve máscara, heatmap e overlay sem rótulo autenticidade.",
    license: "CC BY-NC 4.0",
    repoUrl: "https://github.com/multimediaFor/ViLocal",
  },
  presentation_attack_detection: {
    title: "Detecção de Ataques de Apresentação",
    citation:
      "Baseado em multi-scale CNN + frequency supervision, inspirada pela linha de auxiliary supervision:\n\nLIU, Yaojie; JOURABLOO, Amin; LIU, Xiaoming. Learning Deep Models for Face Anti-Spoofing: Binary or Auxiliary Supervision. In: IEEE/CVF CONFERENCE ON COMPUTER VISION AND PATTERN RECOGNITION (CVPR). 2018.\n\nWANG, Guoqing et al. Deep Spatial Gradient and Temporal Depth Learning for Face Anti-spoofing. In: IEEE/CVF CONFERENCE ON COMPUTER VISION AND PATTERN RECOGNITION (CVPR). 2020.\n\nGEORGE, Anjith; MARCEL, Sébastien. Bi-FPNFAS: Bi-Directional Feature Pyramid Network for Pixel-Wise Face Anti-Spoofing by Leveraging Fourier Spectra. Sensors, 2021.\n\nSilent-Face-Anti-Spoofing. Minivision AI, 2020. Disponível em: <https://github.com/minivision-ai/Silent-Face-Anti-Spoofing>. Acesso em: 22 jun. 2026.",
    cardSubtitle: "MiniFASNet + RetinaFace · multi-scale CNN + frequency supervision",
    detail:
      "Técnica baseada no repositório open-source MiniVision Silent-Face-Anti-Spoofing, que implementa detecção passiva de vivacidade facial com arquitetura leve MiniFASNet e supervisão auxiliar em domínio de frequência. Detecta a face principal com RetinaFace e classifica recortes multi-escala para distinguir rostos reais de ataques de apresentação (foto impressa, tela de dispositivo, máscara). Retorna label, score de confiança e bounding box sobreposto na imagem.",
    summary:
      "Execução 100% local. Fila GPU com fallback CPU. Apenas face principal no v0.",
    license: "Apache-2.0",
    repoUrl: "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing",
  },
  moe_ffd: {
    title: "MoE-FFD (Face Forgery Detection)",
    citation:
      "KONG, Chenqi; LUO, Anwei; BAO, Peijun; YU, Yi; LI, Haoliang; ZHENG, Zengwei; WANG, Shiqi; KOT, Alex C. MoE-FFD: Mixture of Experts for Generalized and Parameter-Efficient Face Forgery Detection. IEEE Transactions on Dependable and Secure Computing, 2025.\n\nCódigo: <https://github.com/LoveSiameseCat/MoE-FFD>. Pesos: <https://huggingface.co/luobo91/MoE-FFD>.",
    cardSubtitle: "ViT-B/16 + Mixture-of-Experts · deepfake / face swap",
    detail:
      "Detecta manipulação facial (deepfake, FaceSwap, Face2Face, NeuralTextures) com ViT-B/16 + MoE (LoRA/Adapter). Pré-processamento: RetinaFace → crop 1.3× → albumentations 224. Softmax classe 1 = fake. IMPORTANTE: o MoE-FFD.tar publicado no Hugging Face (jul/2026) é um checkpoint mid-training com gates MoE zerados e é rejeitado pelo runtime; é necessário o model_params_best_*.pkl dos autores.",
    summary:
      "Exige vendor + RetinaFace PAD + checkpoint com gates MoE treinados (best.pkl). HF MoE-FFD.tar atual é inválido para uso forense.",
    license: "MIT",
    repoUrl: "https://github.com/LoveSiameseCat/MoE-FFD",
  },
  audio_spectrogram: {
    title: "Análise Forense de Áudio",
    citation: "",
    cardSubtitle: "Espectrograma, ENF, LTAS, níveis e DC local",
    detail:
      "Hub unificado de análises forenses de áudio. Oferece espectrograma interativo (comparação de evidências, " +
      "escalas de cor e decimação), análise ENF (frequência nominal da rede elétrica), LTAS (Long-Term Average Spectrum), " +
      "histograma de níveis de quantização e variação DC local por janela temporal.",
  },
  audio_enf: {
    title: "Análise ENF",
    citation:
      "GRIGORAS, C. et al. ENF-based forensic authentication of digital audio recordings. In: AUDIO ENGINEERING SOCIETY CONVENTION. AES, 2005.",
    cardSubtitle: "Frequência nominal da rede · 50/60 Hz",
    detail:
      "Extrai a componente de frequência nominal da rede elétrica (ENF) do sinal de áudio via filtragem FIR passa-faixa " +
      "e demodulação de Hilbert. Permite comparar múltiplas evidências sobrepostas para verificar consistência temporal ou geográfica.",
  },
  audio_ltas: {
    title: "LTAS — Long-Term Average Spectrum",
    citation:
      "Baken, R. J.; Orlikoff, R. F. Clinical Measurement of Speech and Voice. 2. ed. San Diego: Singular, 2000.",
    cardSubtitle: "Espectro médio de longo prazo · Welch",
    detail:
      "Calcula o espectro médio de longo prazo (LTAS) via método de Welch em quatro condições: normal, " +
      "compensação 6 dB/oitava, ordenado por frequência e derivada ordenada. Útil para caracterizar " +
      "perfis espectrais e detectar inconsistências entre gravações.",
  },
  audio_levels: {
    title: "Histograma de Níveis de Quantização",
    citation:
      "Rec. ITU-R BS.468-4. Measurement of audio-frequency noise voltage level in sound broadcasting.",
    cardSubtitle: "Distribuição de amplitudes PCM · 8/16/24/32 bits",
    detail:
      "Exibe o histograma dos níveis de quantização PCM da evidência de áudio. " +
      "Anomalias no histograma (picos, lacunas ou repetibilidade) podem indicar processamento, " +
      "conversão de bit-depth ou sinais sintéticos.",
  },
  audio_dc_local: {
    title: "Nível DC Local",
    citation:
      "Pohlmann, K. C. Principles of Digital Audio. 6. ed. New York: McGraw-Hill, 2010.",
    cardSubtitle: "Média DC por janela temporal",
    detail:
      "Calcula a média do nível DC em janelas deslizantes ao longo do tempo. " +
      "Variações abruptas ou padrões inesperados de offset DC podem revelar edições, " +
      "cortes ou concatenação de trechos de origens distintas.",
  },
  audio_spoofing_detection: {
    title: "Detecção de Spoofing de Áudio",
    citation:
      "SPEECH-ARENA-2025. DF Arena 1B V1 — antispoofing com Wav2Vec2 XLS-R-1B + Conformer. Modelo HuggingFace: Speech-Arena-2025/DF_Arena_1B_V_1. Disponível em: <https://huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1>. Acesso em: 4 jul. 2026.\n\n" +
      "KULKARNI, Ajinkya; DOWERAH, Sandipana; KULKARNI, Atharva; ALUMÄE, Tanel; MAGIMAI DOSS, Mathew. Audio Deepfake Detection with Self-supervised XLS-R and SLS classifier. In: ACM MULTIMEDIA (ACM MM), 2024. Repositório: <https://github.com/QiShanZhang/SLSforASVspoof-2021-DF>. Acesso em: 4 jul. 2026.\n\n" +
      "ZHANG, Lin et al. WeDefense: A Toolkit to Defend Against Fake Audio. arXiv:2601.15240, 2025. Disponível em: <https://arxiv.org/abs/2601.15240>. Checkpoint ASVspoof 2025: <https://huggingface.co/JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning>. Acesso em: 29 jul. 2026.\n\n" +
      "KULKARNI, Ajinkya; DOWERAH, Sandipana; KULKARNI, Atharva; ALUMÄE, Tanel; MAGIMAI DOSS, Mathew. Do Compact SSL Backbones Matter for Audio Deepfake Detection? A Controlled Study with RAPTOR. arXiv:2603.06164, 2026.",
    cardSubtitle: "DF Arena 1B + SLS XLS-R + WeDefense · meta-classificador LR",
    detail:
      "Hub multi-detector de spoofing de áudio com calibração LR por população de referência versionada. " +
      "DF Arena 1B (Wav2Vec2 XLS-R-1B + Conformer), SLS XLS-R (ACM MM 2024) e WeDefense WavLM+MHFA (ASVspoof 2025) " +
      "analisam janelas de 4 segundos; os logits bonafide alimentam meta-classificador e bi-Gaussianized LR. " +
      "Opcionalmente, tipicidade latente (k-NN nos embeddings, sistema D) enriquece a fusão. " +
      "LR positiva favorece H1 = bonafide (áudio autêntico). População padrão: clonagem comercial "
      + "(StyleTTS2, NaturalSpeech2, xTTS, PromptTTS2, VoiceBox), ASVspoof 5 e In-The-Wild "
      + "(distribuição via redes/mensageiros). CodecFake permanece opcional no catálogo.",
    summary:
      "Processamento local com GPU/CPU. Selecione detectores e subgrupos de calibração; artefatos: detector_scores.txt e gráficos LR.",
    license: "Non-commercial (ver LICENSE.txt de cada modelo)",
    repoUrl: "https://huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1",
  },
  mp3_parser: {
    title: "Parser MP3",
    citation:
      "ISO/IEC 11172-3 / 13818-3. Coding of moving pictures and associated audio — Part 3: Audio. " +
      "ID3v2 Informal Standard. Disponível em: <https://id3.org/>.",
    cardSubtitle: "Frames MPEG · ID3 · Xing/VBRI · encoder",
    detail:
      "Análise estrutural binária de arquivos MP3: headers de frame, tags ID3v1/ID3v2, headers VBR (Xing/VBRI), " +
      "assinatura de encoder e inconsistências (bitrate misto, versões MPEG misturadas, ausência de tags).",
  },
  opus_parser: {
    title: "Parser Ogg/Opus",
    citation:
      "RFC 6716. Definition of the Opus Audio Codec. IETF, 2012. " +
      "RFC 7845. Ogg Encapsulation for the Opus Audio Codec. IETF, 2016.",
    cardSubtitle: "Páginas Ogg · OpusHead/Tags · TOC · origem",
    detail:
      "Análise forense de containers Ogg/Opus: estrutura de páginas, OpusHead/OpusTags, TOC do bitstream, " +
      "serial number e pistas de plataforma/origem (ex.: pre-skip típico de apps de mensagem).",
  },
  audio_metadata: {
    title: "Metadados de Áudio",
    citation:
      "Harvey, Phil. ExifTool — Read, Write and Edit Meta Information. Disponível em: <https://exiftool.org/>. " +
      "ID3v2 Informal Standard. Disponível em: <https://id3.org/>.",
    cardSubtitle: "ExifTool · ID3 · Vorbis · RIFF · QuickTime · XMP · C2PA",
    detail:
      "Extração unificada de metadados de áudio via ExifTool (ID3, Vorbis/Opus/FLAC, RIFF/WAV, QuickTime/M4A, XMP), " +
      "Content Credentials (C2PA) via c2pa-python com validação criptográfica, " +
      "e probe técnico complementar (codec, taxa, canais, duração).",
  },
  video_metadata: {
    title: "Metadados de Vídeo",
    citation:
      "Harvey, Phil. ExifTool — Read, Write and Edit Meta Information. Disponível em: <https://exiftool.org/>. " +
      "FFmpeg / ffprobe. Disponível em: <https://ffmpeg.org/>. " +
      "ISO/IEC 14496-12. ISO base media file format.",
    cardSubtitle: "ExifTool -ee · ffprobe · ISO BMFF · GPS · MakerNotes",
    detail:
      "Extração profunda de metadados de vídeo: ExifTool com grupos, tags desconhecidas e embutidos (-ee); " +
      "ffprobe (format/streams/capítulos); resumo estrutural ISO BMFF (timestamps, trilhas). " +
      "Famílias QuickTime, GPS, câmera/MakerNotes, codec, XMP e container — com insights forenses automáticos.",
  },
  synthetic_image_detection: {
    title: "Detecção de Imagens Sintéticas",
    citation:
      "CORVI, Riccardo et al. On The Detection of Synthetic Images Generated by Diffusion Models. In: IEEE ICASSP, 2023. Disponível em: <https://arxiv.org/abs/2211.00680>. Código: <https://github.com/grip-unina/DMimageDetection>.\n\n" +
      "GUILLARO, Fabrizio et al. A Bias-Free Training Paradigm for More General AI-generated Image Detection. In: IEEE/CVF CVPR, 2025. Disponível em: <https://arxiv.org/abs/2412.17671>. Código: <https://github.com/grip-unina/B-Free>.\n\n" +
      "LI, Ouxiang et al. Improving Synthetic Image Detection Towards Generalization: An Image Transformation Perspective. In: ACM KDD, 2025. Disponível em: <https://arxiv.org/abs/2408.06741>. Código: <https://github.com/Ouxiang-Li/SAFE>.\n\n" +
      "Modelos Hugging Face do ensemble: haywoodsloan/ai-image-detector-deploy; cmckinle/sdxl-flux-detector_v1.1.",
    cardSubtitle: "Ensemble HF + B-Free + Corvi2023 + SAFE · calibração LR",
    detail:
      "Hub multi-detector para classificação real vs sintético com calibração LR por população de referência. " +
      "Inclui dois classificadores Hugging Face (ai-image-detector-deploy e sdxl-flux-detector v1.1), " +
      "B-Free (CVPR 2025), DMImageDetection/Corvi2023 (ICASSP 2023, tiles 1024px) e SAFE (KDD 2025). " +
      "Scores alimentam meta-classificador (logistic/XGBoost) e LR; tipicidade latente opcional via embeddings.",
    summary:
      "Selecione detectores e subgrupos de calibração na UI. Artefatos: scores individuais, gráficos Tippett/distribuição LR e resíduos forenses opcionais.",
    license: "Ver LICENSE de cada detector / vendor",
    repoUrl: "https://github.com/grip-unina/B-Free",
  },
};

export const FORENSIC_TECHNIQUE_META: Record<string, ForensicTechniqueMeta> = {
  ..._BASE_FORENSIC_TECHNIQUE_META,
  ...SCAFFOLDED_TECHNIQUE_META,
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

/** Rótulos de fallback para técnicas sem entrada em FORENSIC_TECHNIQUE_META. */
export const LEGACY_TECHNIQUE_LABELS: Record<string, string> = {
  metadata: "Metadados",
  synthetic_image_detection: "Detecção de Imagens Sintéticas",
  mp3_parser: "Parser MP3",
  opus_parser: "Parser Opus",
  audio_metadata: "Metadados",
  video_metadata: "Metadados de vídeo",
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
  truvil: "Vídeo — TruVIL (inpainting localization)",
  vilocal: "Vídeo — ViLocal (inpainting localization)",
};

export function resolveTechniqueLabel(techniqueId: string): string {
  return getTechniqueTitle(techniqueId, LEGACY_TECHNIQUE_LABELS[techniqueId]);
}
