import { FORENSIC_TECHNIQUE_META, LEGACY_TECHNIQUE_LABELS } from "@/config/forensicTechniqueMeta";
import { findImageGroupForTechnique } from "@/config/imageAnalysisGroups";

/** Mapeamento slug da rota → meta (técnica e mídia). */
export const ANALYSIS_ROUTE_META: Record<string, { technique: string; media: string; title?: string }> = {
  ela: { technique: "ela", media: "imagem", title: FORENSIC_TECHNIQUE_META.ela.title },
  image_metadata: { technique: "metadata", media: "imagem", title: LEGACY_TECHNIQUE_LABELS.metadata },
  dct_quantization: { technique: "dct_quantization", media: "imagem", title: FORENSIC_TECHNIQUE_META.dct_quantization.title },
  resampling: { technique: "resampling", media: "imagem", title: FORENSIC_TECHNIQUE_META.resampling.title },
  patchmatch: { technique: "patchmatch", media: "imagem", title: FORENSIC_TECHNIQUE_META.patchmatch.title },
  copy_move_pca: { technique: "copy_move_pca", media: "imagem", title: FORENSIC_TECHNIQUE_META.copy_move_pca.title },
  wavelet_noise_residue: {
    technique: "wavelet_noise_residue",
    media: "imagem",
    title: FORENSIC_TECHNIQUE_META.wavelet_noise_residue.title,
  },
  double_compression: { technique: "double_compression", media: "imagem", title: FORENSIC_TECHNIQUE_META.double_compression.title },
  bag_extraction: { technique: "bag_extraction", media: "imagem", title: FORENSIC_TECHNIQUE_META.bag_extraction.title },
  jpeg_ghosts: { technique: "jpeg_ghosts", media: "imagem", title: FORENSIC_TECHNIQUE_META.jpeg_ghosts.title },
  zero_grid: { technique: "zero_grid", media: "imagem", title: FORENSIC_TECHNIQUE_META.zero_grid.title },
  synthetic_image_detection: {
    technique: "synthetic_image_detection",
    media: "imagem",
    title: LEGACY_TECHNIQUE_LABELS.synthetic_image_detection,
  },
  safire: { technique: "safire", media: "imagem", title: FORENSIC_TECHNIQUE_META.safire.title },
  noiseprint: { technique: "noiseprint", media: "imagem", title: FORENSIC_TECHNIQUE_META.noiseprint.title },
  prnu: { technique: "prnu", media: "imagem", title: FORENSIC_TECHNIQUE_META.prnu.title },
  audio: { technique: "audio_forensics", media: "audio", title: "Audio forense" },
  audio_spoofing: { technique: "audio_spoofing_detection", media: "audio", title: FORENSIC_TECHNIQUE_META.audio_spoofing_detection.title },
  pdf_font_overlay: { technique: "pdf_font_color_overlay", media: "pdf", title: "PDF overlay por fonte" },
  pdf_structure_metrics: { technique: "pdf_structure_metrics", media: "pdf", title: "PDF estrutura (grafo)" },
  pdf_structure_similarity: { technique: "pdf_structure_similarity", media: "pdf", title: "PDF similaridade estrutural" },
  pdf_forensic_extract: { technique: "pdf_forensic_extract", media: "pdf", title: "PDF extracao forense" },
  isomedia_parser: { technique: "isomedia_parser", media: "video", title: "Parser ISO BMFF" },
  isomedia_compare: { technique: "isomedia_compare", media: "video", title: "Similaridade ISO BMFF" },
  videofact: { technique: "videofact", media: "video", title: FORENSIC_TECHNIQUE_META.videofact.title },
  stil_video_detection: {
    technique: "stil_video_detection",
    media: "video",
    title: FORENSIC_TECHNIQUE_META.stil_video_detection.title,
  },
  lowres_fake_video: {
    technique: "lowres_fake_video",
    media: "video",
    title: FORENSIC_TECHNIQUE_META.lowres_fake_video.title,
  },
  jpeg_structure_compare: {
    technique: "jpeg_structure_compare",
    media: "imagem",
    title: FORENSIC_TECHNIQUE_META.jpeg_structure_compare.title,
  },
};

/** Tecnicas de audio espectral com pagina unificada /analysis/audio */
export const AUDIO_FORENSICS_TECHNIQUES = new Set([
  "audio_spectrogram",
  "audio_enf",
  "audio_ltas",
  "audio_levels",
  "audio_dc_local",
  "audio_forensics",
]);

const AUDIO_NAV_TECHNIQUES = new Set([
  "__audio_hub__",
  "__audio_spectral__",
  "__audio_levels__",
  ...AUDIO_FORENSICS_TECHNIQUES,
]);

const IMDL_DEDICATED_ROUTE_TECHNIQUES = [
  "trufor",
  "cat_net",
  "sparse_vit",
  "mesorch",
  "nfa_vit",
  "dinov3_iml",
  "co_transformers",
] as const;

/** Tecnicas com pagina dedicada nao usam o painel inline "Executar" na aba Análises. */
export const DEDICATED_ANALYSIS_TECHNIQUES = new Set([
  ...Object.values(ANALYSIS_ROUTE_META).map((m) => m.technique),
  ...AUDIO_FORENSICS_TECHNIQUES,
  ...IMDL_DEDICATED_ROUTE_TECHNIQUES,
]);

export function techniqueHasDedicatedPage(technique: string): boolean {
  return DEDICATED_ANALYSIS_TECHNIQUES.has(technique);
}

/** Tecnicas registradas mas ocultas na UI da aba Imagem (hub substituido por cards/metodos dedicados). */
export const HIDDEN_IMAGE_TECHNIQUES = new Set(["imdlbenco"]);

/** Tecnicas registradas mas ocultas na UI da aba PDF. */
export const HIDDEN_PDF_TECHNIQUES = new Set<string>([]);

/** Tecnicas registradas mas ocultas na UI da aba Audio. */
export const HIDDEN_AUDIO_TECHNIQUES = new Set([
  "mp3_parser",
  "opus_parser",
  "wav_ima_adpcm",
]);

export function isTechniqueHiddenInMediaTab(technique: string, media: string): boolean {
  if (media === "imagem" && HIDDEN_IMAGE_TECHNIQUES.has(technique)) return true;
  if (media === "pdf" && HIDDEN_PDF_TECHNIQUES.has(technique)) return true;
  if (media === "audio" && HIDDEN_AUDIO_TECHNIQUES.has(technique)) return true;
  return false;
}

export function buildImageGroupUrl(caseId: string, groupId: string, tabId?: string): string {
  const params = tabId ? `?tab=${encodeURIComponent(tabId)}` : "";
  return `/cases/${caseId}/analysis/image-group/${groupId}${params}`;
}

export function buildReturnToCaseAnalysesUrl(caseId: string, pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  const groupIdx = parts.indexOf("image-group");
  if (groupIdx >= 0 && parts[groupIdx + 1]) {
    return buildCaseAnalysesUrl(caseId, "imagem");
  }
  const slug = parts.pop() || "";
  const meta = ANALYSIS_ROUTE_META[slug];
  if (!meta) {
    return `/cases/${caseId}?tab=analises`;
  }
  const params = new URLSearchParams({
    tab: "analises",
    media: meta.media,
  });
  return `/cases/${caseId}?${params.toString()}`;
}

export function parseAnalysesSearchParams(searchParams: URLSearchParams): {
  media: string | null;
  technique: string | null;
} {
  return {
    media: searchParams.get("media"),
    technique: searchParams.get("technique"),
  };
}

export function getAnalysisRouteSlug(pathname: string): string {
  return pathname.split("/").filter(Boolean).pop() || "";
}

export function getAnalysisRouteMeta(pathname: string) {
  return ANALYSIS_ROUTE_META[getAnalysisRouteSlug(pathname)] ?? null;
}

export type NavigateFn = (path: string) => void;

/** Navega para pagina dedicada da tecnica; retorna true se navegou. */
export function navigateToDedicatedAnalysis(
  navigate: NavigateFn,
  caseId: string,
  technique: string,
  options?: { audioTab?: string }
): boolean {
  if (AUDIO_NAV_TECHNIQUES.has(technique)) {
    let tab = options?.audioTab || "spectrogram";
    let group: "spectral" | "levels" = "spectral";
    if (technique === "__audio_spectral__" || technique === "__audio_hub__") {
      tab = tab === "levels" || tab === "dc" ? "spectrogram" : tab;
      group = "spectral";
    } else if (technique === "__audio_levels__") {
      tab = "levels";
      group = "levels";
    } else if (technique === "audio_levels" || technique === "audio_dc_local") {
      group = "levels";
    } else if (
      technique === "audio_enf" ||
      technique === "audio_ltas" ||
      technique === "audio_spectrogram"
    ) {
      group = "spectral";
    }
    if (technique === "audio_enf") tab = "enf";
    if (technique === "audio_ltas") tab = "ltas";
    if (technique === "audio_levels") tab = "levels";
    if (technique === "audio_dc_local") tab = "dc";
    navigate(`/cases/${caseId}/analysis/audio?tab=${tab}&group=${group}`);
    return true;
  }

  const imageGroup = findImageGroupForTechnique(technique);
  if (imageGroup) {
    navigate(buildImageGroupUrl(caseId, imageGroup.group.id, imageGroup.tabId));
    return true;
  }

  const routes: Record<string, string> = {
    audio_spoofing_detection: `/cases/${caseId}/analysis/audio_spoofing`,
    pdf_font_color_overlay: `/cases/${caseId}/analysis/pdf_font_overlay`,
    pdf_structure_metrics: `/cases/${caseId}/analysis/pdf_structure_metrics`,
    pdf_structure_similarity: `/cases/${caseId}/analysis/pdf_structure_similarity`,
    pdf_forensic_extract: `/cases/${caseId}/analysis/pdf_forensic_extract`,
    isomedia_parser: `/cases/${caseId}/analysis/isomedia_parser`,
    isomedia_compare: `/cases/${caseId}/analysis/isomedia_compare`,
    videofact: `/cases/${caseId}/analysis/videofact`,
    stil_video_detection: `/cases/${caseId}/analysis/stil_video_detection`,
    lowres_fake_video: `/cases/${caseId}/analysis/lowres_fake_video`,
  };

  const path = routes[technique];
  if (!path) return false;
  navigate(path);
  return true;
}

export function buildCaseAnalysesUrl(caseId: string, media: string): string {
  const params = new URLSearchParams({ tab: "analises", media });
  return `/cases/${caseId}?${params.toString()}`;
}
