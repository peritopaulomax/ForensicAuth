/**
 * Agrupamento visual dos cards nas abas Áudio / Vídeo / PDF (Análises do caso).
 * Imagem permanece em `imageAnalysisGroups.ts` (com batch IMDL e sessão de evidência).
 */
import { FORENSIC_TECHNIQUE_META } from "./forensicTechniqueMeta";
import { applyScaffoldedMediaGroups } from "./scaffoldedMediaGroups";

export type AnalysisMedia = "imagem" | "audio" | "video" | "pdf";

export type MediaTechniqueEntry =
  | { kind: "plugin"; id: string; adminOnly?: boolean; disabled?: boolean }
  | { kind: "imdl"; id: string; disabled?: boolean; adminOnly?: boolean };

export interface MediaAnalysisGroup {
  id: string;
  title: string;
  description: string;
  techniques: MediaTechniqueEntry[];
  batchTab?: boolean;
}

const _AUDIO_ANALYSIS_GROUPS_BASE: MediaAnalysisGroup[] = [
  {
    id: "audio-forense",
    title: "Análise forense de áudio",
    description:
      "Espectrograma, ENF, LTAS, níveis e DC local — hub unificado de inspeção tempo/frequência e envelope.",
    techniques: [{ kind: "plugin", id: "__audio_hub__" }],
  },
  {
    id: "audio-estrutura",
    title: "Metadados e parsers de container",
    description:
      "Metadados (ExifTool) e análise estrutural MP3 / Ogg-Opus — tags, frames, páginas Ogg, TOC e assinaturas de origem.",
    techniques: [
      { kind: "plugin", id: "audio_metadata" },
      { kind: "plugin", id: "mp3_parser" },
      { kind: "plugin", id: "opus_parser" },
    ],
  },
  {
    id: "audio-spoofing",
    title: "Deep Learning: Spoofing / deepfake de áudio",
    description:
      "Detectores de síntese e spoofing de áudio (ensemble / tipicidade latente quando calibrado).",
    techniques: [{ kind: "plugin", id: "audio_spoofing_detection" }],
  },
];

/** URLs antigas dos dois cards → card único. */
const AUDIO_GROUP_ID_ALIASES: Record<string, string> = {
  "audio-espectral": "audio-forense",
  "audio-niveis": "audio-forense",
};

const _VIDEO_ANALYSIS_GROUPS_BASE: MediaAnalysisGroup[] = [
  {
    id: "video-estrutura",
    title: "Metadados e estrutura de container",
    description:
      "Metadados profundos (ExifTool + ffprobe + ISO BMFF) e parser/comparação estrutural de containers MP4/MOV.",
    techniques: [
      { kind: "plugin", id: "video_metadata" },
      { kind: "plugin", id: "isomedia_parser" },
      { kind: "plugin", id: "isomedia_compare" },
    ],
  },
  {
    id: "video-manipulacao",
    title: "Deep Learning: Manipulação e deepfake de vídeo",
    description:
      "Localização e classificação de manipulações / deepfakes em vídeo (VideoFact, STIL, LowRes, TruVIL, ViLocal).",
    techniques: [
      { kind: "plugin", id: "videofact", adminOnly: true },
      { kind: "plugin", id: "stil_video_detection", adminOnly: true },
      { kind: "plugin", id: "lowres_fake_video", adminOnly: true },
      { kind: "plugin", id: "truvil", adminOnly: true },
      { kind: "plugin", id: "vilocal", adminOnly: true },
    ],
  },
];

const _PDF_ANALYSIS_GROUPS_BASE: MediaAnalysisGroup[] = [
  {
    id: "pdf-estrutura",
    title: "Estrutura e similaridade",
    description:
      "Métricas estruturais, grafo de objetos e comparação estrutural entre documentos PDF.",
    techniques: [
      { kind: "plugin", id: "pdf_structure_metrics" },
      { kind: "plugin", id: "pdf_structure_similarity" },
    ],
  },
  {
    id: "pdf-conteudo",
    title: "Conteúdo e extração forense",
    description:
      "Overlay por fonte/cor e extração incremental de artefatos forenses do PDF.",
    techniques: [
      { kind: "plugin", id: "pdf_font_color_overlay" },
      { kind: "plugin", id: "pdf_forensic_extract" },
    ],
  },
];

export const AUDIO_ANALYSIS_GROUPS: MediaAnalysisGroup[] = applyScaffoldedMediaGroups(
  "audio",
  _AUDIO_ANALYSIS_GROUPS_BASE,
);

export const VIDEO_ANALYSIS_GROUPS: MediaAnalysisGroup[] = applyScaffoldedMediaGroups(
  "video",
  _VIDEO_ANALYSIS_GROUPS_BASE,
);

export const PDF_ANALYSIS_GROUPS: MediaAnalysisGroup[] = applyScaffoldedMediaGroups(
  "pdf",
  _PDF_ANALYSIS_GROUPS_BASE,
);

/** IDs canônicos de grupo por mídia (base + aliases). Fonte para docs e validação do scaffold. */
export const MEDIA_GROUP_CATALOG: Record<
  Exclude<AnalysisMedia, "imagem">,
  { id: string; title: string }[]
> = {
  audio: _AUDIO_ANALYSIS_GROUPS_BASE.map((g) => ({ id: g.id, title: g.title })),
  video: _VIDEO_ANALYSIS_GROUPS_BASE.map((g) => ({ id: g.id, title: g.title })),
  pdf: _PDF_ANALYSIS_GROUPS_BASE.map((g) => ({ id: g.id, title: g.title })),
};

export function getMediaAnalysisGroups(media: AnalysisMedia): MediaAnalysisGroup[] {
  if (media === "audio") return AUDIO_ANALYSIS_GROUPS;
  if (media === "video") return VIDEO_ANALYSIS_GROUPS;
  if (media === "pdf") return PDF_ANALYSIS_GROUPS;
  return [];
}

export function getMediaAnalysisGroup(
  media: AnalysisMedia,
  groupId: string,
): MediaAnalysisGroup | undefined {
  const canonical =
    media === "audio" ? AUDIO_GROUP_ID_ALIASES[groupId] ?? groupId : groupId;
  return getMediaAnalysisGroups(media).find((g) => g.id === canonical);
}

export function mediaTechniqueEntryKey(entry: MediaTechniqueEntry): string {
  return entry.id;
}

export function resolveMediaTechniqueTabLabel(entry: MediaTechniqueEntry): string {
  if (entry.id === "__audio_hub__") return "Hub forense (espectral + níveis)";
  if (entry.id === "__audio_spectral__") return "Espectrograma, ENF e LTAS";
  if (entry.id === "__audio_levels__") return "Níveis e DC local";
  // Rótulos curtos de aba (paridade com imagem)
  const short: Record<string, string> = {
    pdf_structure_metrics: "Estrutura e métricas",
    pdf_structure_similarity: "Similaridade estrutural",
    pdf_font_color_overlay: "Overlay por fonte",
    pdf_forensic_extract: "Extração forense",
    isomedia_parser: "Parser ISO BMFF",
    isomedia_compare: "Similaridade ISO BMFF",
    video_metadata: "Metadados",
    videofact: "VideoFact",
    stil_video_detection: "STIL",
    lowres_fake_video: "LowRes Fake",
    truvil: "TruVIL",
    vilocal: "ViLocal",
    audio_spoofing_detection: "Spoofing / deepfake",
    audio_metadata: "Metadados",
    mp3_parser: "Parser MP3",
    opus_parser: "Parser Opus",
  };
  if (short[entry.id]) return short[entry.id];
  const meta = FORENSIC_TECHNIQUE_META[entry.id];
  if (meta?.title) return meta.title;
  return entry.id;
}

export function isMediaTechniqueVisible(
  entry: MediaTechniqueEntry,
  role: "admin" | "perito" | undefined,
): boolean {
  if (entry.adminOnly && role !== "admin") return false;
  return true;
}

export function isMediaTechniqueDisabled(entry: MediaTechniqueEntry): boolean {
  return Boolean(entry.disabled);
}

export function findMediaGroupForTechnique(techniqueKey: string): {
  media: Exclude<AnalysisMedia, "imagem">;
  group: MediaAnalysisGroup;
  tabId: string;
} | null {
  const audioHubKeys = new Set([
    "__audio_hub__",
    "__audio_spectral__",
    "__audio_levels__",
    "audio_spectrogram",
    "audio_enf",
    "audio_ltas",
    "audio_levels",
    "audio_dc_local",
    "audio_forensics",
  ]);
  if (audioHubKeys.has(techniqueKey)) {
    const group = getMediaAnalysisGroup("audio", "audio-forense");
    if (group) {
      return { media: "audio", group, tabId: "__audio_hub__" };
    }
  }
  for (const media of ["audio", "video", "pdf"] as const) {
    for (const group of getMediaAnalysisGroups(media)) {
      for (const entry of group.techniques) {
        const tabId = mediaTechniqueEntryKey(entry);
        if (tabId === techniqueKey) {
          return { media, group, tabId };
        }
      }
    }
  }
  return null;
}
