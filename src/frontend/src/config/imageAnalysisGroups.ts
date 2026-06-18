/** Agrupamento visual dos cards na aba Imagem (Análises do caso). */

import { FORENSIC_TECHNIQUE_META } from "./forensicTechniqueMeta";

export type ImageTechniqueEntry =
  | { kind: "plugin"; id: string; adminOnly?: boolean; disabled?: boolean }
  | { kind: "imdl"; id: string; disabled?: boolean; adminOnly?: boolean };

export interface ImageAnalysisGroup {
  id: string;
  title: string;
  description: string;
  techniques: ImageTechniqueEntry[];
  /** Aba extra "executar todas" (somente DL manipulação por enquanto). */
  batchTab?: boolean;
}

export const IMAGE_ANALYSIS_GROUPS: ImageAnalysisGroup[] = [
  {
    id: "estrutura-arquivo",
    title: "Estrutura de arquivo",
    description:
      "Metadados incorporados, estrutura de contêiner e comparação estrutural entre evidências JPEG — útil para rastrear origem, software e consistência interna do arquivo.",
    techniques: [
      { kind: "plugin", id: "metadata" },
      { kind: "plugin", id: "jpeg_structure_compare" },
    ],
  },
  {
    id: "classicas-compressao",
    title: "Clássicas: Artefatos de compressão",
    description:
      "Técnicas baseadas em artefatos JPEG e DCT: ghosts, dupla compressão, ELA, grade de blocos (BAG), origem de grade (ZERO) e inconsistências de quantização.",
    techniques: [
      { kind: "plugin", id: "jpeg_ghosts" },
      { kind: "plugin", id: "dct_quantization" },
      { kind: "plugin", id: "double_compression" },
      { kind: "plugin", id: "ela" },
      { kind: "plugin", id: "bag_extraction" },
      { kind: "plugin", id: "zero_grid" },
    ],
  },
  {
    id: "classicas-correlacao",
    title: "Clássicas: Correlações entre pixels",
    description:
      "Detecção de reamostragem, copy-move (PatchMatch e PCA), e resíduo de ruído wavelet — exploram inconsistências espaciais e estatísticas entre pixels vizinhos.",
    techniques: [
      { kind: "plugin", id: "resampling" },
      { kind: "plugin", id: "patchmatch" },
      { kind: "plugin", id: "copy_move_pca" },
      { kind: "plugin", id: "wavelet_noise_residue" },
    ],
  },
  {
    id: "classicas-aquisicao",
    title: "Clássicas: Características de aquisição",
    description:
      "PRNU (pegada do sensor) e Noiseprint (resíduo de câmera/modelo) — comparam padrões de ruído de aquisição entre imagens e referências.",
    techniques: [
      { kind: "plugin", id: "prnu" },
      { kind: "plugin", id: "noiseprint" },
    ],
  },
  {
    id: "dl-manipulacao",
    title: "Deep Learning: Detecção e Localização de Manipulações em Imagens",
    description:
      "Localizadores baseados em deep learning (SAFIRE, TruFor, CAT-Net, Mesorch, Sparse-ViT e ecossistema IMDL-BenCo) — mapas de suspeita, overlays e máscaras por pixel.",
    techniques: [
      { kind: "imdl", id: "cat_net" },
      { kind: "imdl", id: "trufor" },
      { kind: "plugin", id: "safire" },
      { kind: "imdl", id: "sparse_vit" },
      { kind: "imdl", id: "mesorch" },
      { kind: "imdl", id: "dinov3_iml" },
      { kind: "imdl", id: "co_transformers" },
      { kind: "imdl", id: "miml_apscnet", adminOnly: true },
      { kind: "imdl", id: "nfa_vit", adminOnly: true, disabled: true },
    ],
    batchTab: true,
  },
  {
    id: "dl-sintetico",
    title: "Deep Learning: Detecção de Imagens Sintéticas",
    description:
      "Ensemble de detectores de imagens geradas por IA (CNN + Effort + SAFE + IAPL) e DistilDIRE para difusão — veredito global e mapas auxiliares.",
    techniques: [
      { kind: "plugin", id: "synthetic_image_detection" },
      { kind: "plugin", id: "distildire" },
    ],
  },
];

export const IMAGE_BATCH_TAB_ID = "__executar_todas__";

export function getImageAnalysisGroup(groupId: string): ImageAnalysisGroup | undefined {
  return IMAGE_ANALYSIS_GROUPS.find((g) => g.id === groupId);
}

export function findImageGroupForTechnique(techniqueKey: string): {
  group: ImageAnalysisGroup;
  tabId: string;
} | null {
  for (const group of IMAGE_ANALYSIS_GROUPS) {
    for (const entry of group.techniques) {
      const tabId = techniqueEntryKey(entry);
      if (tabId === techniqueKey) {
        return { group, tabId };
      }
    }
  }
  return null;
}

export function techniqueEntryKey(entry: ImageTechniqueEntry): string {
  return entry.kind === "imdl" ? entry.id : entry.id;
}

/** Rótulos curtos das abas do grupo DL manipulação (com ano de publicação). */
export const DL_MANIPULATION_TAB_LABELS: Record<string, { name: string; year: number }> = {
  cat_net: { name: "CAT-Net", year: 2022 },
  trufor: { name: "TruFor", year: 2023 },
  safire: { name: "SAFIRE", year: 2025 },
  sparse_vit: { name: "Sparse-ViT", year: 2025 },
  mesorch: { name: "Mesorch", year: 2025 },
  dinov3_iml: { name: "DINOv3-IML", year: 2026 },
  co_transformers: { name: "Co-Transformers", year: 2026 },
  miml_apscnet: { name: "MIML APSC-Net", year: 2026 },
};

export function resolveTechniqueTabLabel(entry: ImageTechniqueEntry): string {
  const key = techniqueEntryKey(entry);
  const dlTab = DL_MANIPULATION_TAB_LABELS[key];
  if (dlTab) {
    return `${dlTab.name} (${dlTab.year})`;
  }
  if (entry.kind === "imdl") {
    return IMDL_METHOD_LABELS[entry.id] || entry.id;
  }
  const meta = FORENSIC_TECHNIQUE_META[entry.id];
  if (meta?.title) return meta.title;
  return entry.id;
}

/** Métodos IMDL com página dedicada (fora do hub). */
export const IMDL_DEDICATED_METHOD_IDS = new Set([
  "trufor",
  "cat_net",
  "sparse_vit",
  "mesorch",
  "nfa_vit",
  "dinov3_iml",
  "co_transformers",
  "miml_apscnet",
]);

/** Métodos IMDL visíveis apenas para administradores (ex.: pesos ainda pendentes). */
export const IMDL_ADMIN_ONLY_METHOD_IDS = new Set(["nfa_vit", "miml_apscnet"]);

export function isImageTechniqueVisible(
  entry: ImageTechniqueEntry,
  role: "admin" | "perito" | undefined,
): boolean {
  if (entry.adminOnly && role !== "admin") {
    return false;
  }
  return true;
}

export function isImageTechniqueDisabled(entry: ImageTechniqueEntry): boolean {
  return Boolean(entry.disabled);
}

/** Técnicas elegíveis para a aba "Executar todas" (exclui incompletas/desabilitadas). */
export function isImageTechniqueBatchEligible(entry: ImageTechniqueEntry): boolean {
  return !isImageTechniqueDisabled(entry);
}

export function findImageTechniqueEntry(techniqueKey: string): ImageTechniqueEntry | undefined {
  for (const group of IMAGE_ANALYSIS_GROUPS) {
    for (const entry of group.techniques) {
      if (techniqueEntryKey(entry) === techniqueKey) return entry;
    }
  }
  return undefined;
}

export function isImageTechniqueDisabledById(techniqueId: string): boolean {
  const entry = findImageTechniqueEntry(techniqueId);
  return entry ? isImageTechniqueDisabled(entry) : false;
}

export const IMDL_METHOD_LABELS: Record<string, string> = {
  trufor: FORENSIC_TECHNIQUE_META.trufor.title,
  cat_net: FORENSIC_TECHNIQUE_META.cat_net.title,
  sparse_vit: FORENSIC_TECHNIQUE_META.sparse_vit.title,
  mesorch: FORENSIC_TECHNIQUE_META.mesorch.title,
  dinov3_iml: "DINOv3-IML",
  co_transformers: "Co-Transformers",
  nfa_vit: "NFA-ViT",
  miml_apscnet: "MIML APSC-Net",
};

export const IMDL_METHOD_SUBTITLES: Record<string, string> = {
  trufor: FORENSIC_TECHNIQUE_META.trufor.cardSubtitle,
  cat_net: FORENSIC_TECHNIQUE_META.cat_net.cardSubtitle,
  sparse_vit: FORENSIC_TECHNIQUE_META.sparse_vit.cardSubtitle,
  mesorch: FORENSIC_TECHNIQUE_META.mesorch.cardSubtitle,
  nfa_vit: "Noise-guided forgery amplification (BR-Gen)",
  dinov3_iml: "ViT-L + LoRA r=32 · foundation model forense",
  co_transformers: "Dual-Transformer · atenção forense multi-nível (AAAI'26)",
  miml_apscnet: "APSC-Net oficial MIML · localização single-image",
};
