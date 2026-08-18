import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import type { ForensicTechniqueMeta } from "@/config/forensicTechniqueMeta";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import type { MediaType } from "@/components/EvidenceSelectorFactory";
import type { TechniqueParameterDef } from "@/config/techniqueParameterTypes";
import type { ArtifactRole } from "@/config/artifactRoles";
import { ARTIFACT_ROLES } from "@/config/artifactRoles";
import type { MacroCategory } from "@/components/LrReferencePanels";
import { ANALYSIS_ROUTE_META } from "@/utils/caseAnalysisNav";
import { SCAFFOLDED_TECHNIQUES } from "@/config/scaffoldedTechniques";

/**
 * Família de página / padrão de UI da técnica.
 *
 * Scaffold automatizado: simple | medium | comparison | ensemble.
 * Roadmap: complex (hub permanece manual).
 */
export type TechniqueTemplate =
  | "simple"
  | "medium"
  | "comparison"
  | "complex"
  | "ensemble"
  | "hub";

export type ComparisonMode = "with_reference" | "all_pairs";

/** Config declarativa para páginas `GenericComparisonAnalysis` (scaffold). */
export interface ComparisonConfig {
  /** Modos disponíveis na UI (default: ambos). */
  modes?: ComparisonMode[];
  /**
   * De onde vêm as referências no modo with_reference.
   * - case_evidences: multi-select nas evidências normais do caso (default)
   * - case_references: referências **globais** do caso (`global_groups`),
   *   filtradas por tipo de mídia e escolhidas por rótulo
   */
  referenceSource?: "case_evidences" | "case_references";
  minQuestioned?: number;
  minReferences?: number;
}

/** Detector/modelo selecionável no formulário ensemble. */
export interface EnsembleDetectorDef {
  id: string;
  label: string;
}

/** Badges agregados (opcional) — chaves no JSON de resultado do job. */
export interface EnsembleScoreDisplay {
  positiveKey?: string;
  negativeKey?: string;
  labelKey?: string;
}

/**
 * Calibração LR com gestão de população (espelho áudio spoofing).
 * `mode: "result_only"` = só painel de resultado; `"calibrated"` = picker de bases + params de job.
 */
export interface EnsembleReferenceLrConfig {
  enabled?: boolean;
  /** result_only | calibrated (padrão: result_only). */
  mode?: "result_only" | "calibrated";
  /** Domínio sob reference_data/<domain>/ (obrigatório se calibrated). */
  domain?: string;
  /** GET JSON { categories: MacroCategory[], default_reference_items? } — opcional se macros inline. */
  catalogEndpoint?: string;
  /** Paths relativos a reference_data/<domain>/ (contrato para o pipeline / PoC). */
  scoresPath?: string;
  embeddingsPath?: string;
  /** detector_id → coluna de score na matriz publicada. */
  featureMap?: Record<string, string>;
  /** detector_id → id/coluna de embedding (opcional). */
  embeddingMap?: Record<string, string>;
  allowAugmented?: boolean;
  allowTypicality?: boolean;
  allowMetaClassifier?: boolean;
  enableSplitRoles?: boolean;
  defaultMetaClassifier?: string;
  populationUnitLabel?: string;
  lrPositiveLabel?: string;
  subgroupUnitLabel?: string;
  hypothesisHint?: string;
  /** Catálogo inline (MacroCategory[]) quando catalogEndpoint não está definido. */
  macros?: MacroCategory[];
  defaultReferenceItems?: { base_group: string; subgroup: string }[];
}

/** Config declarativa para `GenericEnsembleAnalysis` (scaffold). */
export interface EnsembleConfig {
  /** Lista de detectores/análises (checkboxes → selected_analyses). */
  detectors: EnsembleDetectorDef[];
  /** Cabeçalhos da tabela `individual_results` (tipicamente 6 colunas). */
  resultHeaders?: string[];
  /** Nome do parâmetro de job com a lista de ids selecionados (default selected_analyses). */
  selectedParam?: string;
  /** Badges de score agregados (ex.: spoof/bonafide). */
  scoreDisplay?: EnsembleScoreDisplay;
  /** LR: resultado apenas ou calibração com população. */
  referenceLr?: EnsembleReferenceLrConfig;
}

export type { TechniqueParameterDef } from "@/config/techniqueParameterTypes";
export type { ArtifactRole } from "@/config/artifactRoles";
export { ARTIFACT_ROLES };

export interface ArtifactManifestItem {
  filename: string;
  label: string;
  /**
   * Papel do artefato para a UI genérica.
   * Ver `artifactRoles.ts` e docs/developer/03-scaffold-technique.md.
   */
  role?: ArtifactRole;
}

export interface TechniqueConfig {
  /** ID canônico da técnica (igual ao nome do plugin backend). */
  id: string;
  /** Tipo de mídia para seleção de evidência. */
  mediaType: MediaType;
  /** Template de página a ser usado (ver TechniqueTemplate). */
  template: TechniqueTemplate;
  /** Componente React lazy da página. */
  component: LazyExoticComponent<ComponentType<Record<string, unknown>>>;
  /** Metadados bibliográficos e textuais. */
  meta: ForensicTechniqueMeta;
  /** Timeout estimado em ms para feedback de progresso (null = default). */
  timeout?: number | null;
  /** Se a técnica requer GPU/fila GPU. */
  gpu?: boolean;
  /** Parâmetros default ao abrir a página. */
  defaultParameters?: Record<string, unknown>;
  /** Definições de formulário (técnicas scaffolded). */
  parameterDefs?: TechniqueParameterDef[];
  /** Artefatos esperados para renderização genérica (quando aplicável). */
  artifactManifest?: ArtifactManifestItem[];
  /** Opções do template comparison (scaffold). */
  comparisonConfig?: ComparisonConfig;
  /** Opções do template ensemble (scaffold). */
  ensembleConfig?: EnsembleConfig;
  /** Se true, a técnica aparece no catálogo mas pode estar desabilitada. */
  disabled?: boolean;
  /** Se true, apenas administradores veem. */
  adminOnly?: boolean;
}

// --- Lazy page components (explicit imports required by Vite) ---

const ImageMetadataAnalysis = lazy(() => import("@/pages/ImageMetadataAnalysis"));
const JpegStructureCompareAnalysis = lazy(() => import("@/pages/JpegStructureCompareAnalysis"));
const JpegGhostsAnalysis = lazy(() => import("@/pages/JpegGhostsAnalysis"));
const DCTQuantization = lazy(() => import("@/pages/DCTQuantization"));
const DoubleCompressionAnalysis = lazy(() => import("@/pages/DoubleCompressionAnalysis"));
const ELAAnalysis = lazy(() => import("@/pages/ELAAnalysis"));
const BagExtractionAnalysis = lazy(() => import("@/pages/BagExtractionAnalysis"));
const ZeroGridAnalysis = lazy(() => import("@/pages/ZeroGridAnalysis"));
const ResamplingAnalysis = lazy(() => import("@/pages/ResamplingAnalysis"));
const PatchMatchAnalysis = lazy(() => import("@/pages/PatchMatchAnalysis"));
const CopyMovePcaAnalysis = lazy(() => import("@/pages/CopyMovePcaAnalysis"));
const WaveletNoiseResidueAnalysis = lazy(() => import("@/pages/WaveletNoiseResidueAnalysis"));
const PRNUAnalysis = lazy(() => import("@/pages/PRNUAnalysis"));
const SafireAnalysis = lazy(() => import("@/pages/SafireAnalysis"));
const SyntheticImageDetectionAnalysis = lazy(() => import("@/pages/SyntheticImageDetectionAnalysis"));
const PresentationAttackDetectionAnalysis = lazy(() => import("@/pages/PresentationAttackDetectionAnalysis"));
const MoeFfdAnalysis = lazy(() => import("@/pages/MoeFfdAnalysis"));
const ImdlMethodAnalysis = lazy(() => import("@/pages/ImdlMethodAnalysis"));

const AudioSpoofingAnalysis = lazy(() => import("@/pages/AudioSpoofingAnalysis"));
const AudioForensicsHub = lazy(() => import("@/pages/AudioForensicsHub"));
const AudioContainerParserAnalysis = lazy(() => import("@/pages/AudioContainerParserAnalysis"));
const AudioMetadataAnalysis = lazy(() => import("@/pages/AudioMetadataAnalysis"));

const VideoFactAnalysis = lazy(() => import("@/pages/VideoFactAnalysis"));
const StilVideoAnalysis = lazy(() => import("@/pages/StilVideoAnalysis"));
const LowResFakeVideoAnalysis = lazy(() => import("@/pages/LowResFakeVideoAnalysis"));
const TruVilAnalysis = lazy(() => import("@/pages/TruVilAnalysis"));
const ViLocalAnalysis = lazy(() => import("@/pages/ViLocalAnalysis"));
const IsoMediaStructureAnalysis = lazy(() => import("@/pages/IsoMediaStructureAnalysis"));
const IsoMediaSimilarityAnalysis = lazy(() => import("@/pages/IsoMediaSimilarityAnalysis"));
const VideoMetadataAnalysis = lazy(() => import("@/pages/VideoMetadataAnalysis"));

const PDFFontColorAnalysis = lazy(() => import("@/pages/PDFFontColorAnalysis"));
const PDFStructureMetricsAnalysis = lazy(() => import("@/pages/PDFStructureMetricsAnalysis"));
const PDFForensicExtractAnalysis = lazy(() => import("@/pages/PDFForensicExtractAnalysis"));
const PDFStructureSimilarityAnalysis = lazy(() => import("@/pages/PDFStructureSimilarityAnalysis"));

// --- Imagens ---

const imageTechniques: TechniqueConfig[] = [
  {
    id: "metadata",
    mediaType: "imagem",
    template: "complex",
    component: ImageMetadataAnalysis,
    meta: {
      title: "Metadados",
      citation: "",
      cardSubtitle: "EXIF, IPTC, XMP, ICC, MakerNotes, C2PA, JPEG markers",
      detail:
        "Relatório estruturado de metadados, Content Credentials (C2PA) e estrutura do arquivo JPEG.",
    },
  },
  {
    id: "jpeg_structure_compare",
    mediaType: "imagem",
    template: "comparison",
    component: JpegStructureCompareAnalysis,
    meta: FORENSIC_TECHNIQUE_META.jpeg_structure_compare,
  },
  {
    id: "jpeg_ghosts",
    mediaType: "imagem",
    template: "medium",
    component: JpegGhostsAnalysis,
    meta: FORENSIC_TECHNIQUE_META.jpeg_ghosts,
  },
  {
    id: "dct_quantization",
    mediaType: "imagem",
    template: "medium",
    component: DCTQuantization,
    meta: FORENSIC_TECHNIQUE_META.dct_quantization,
  },
  {
    id: "double_compression",
    mediaType: "imagem",
    template: "simple",
    component: DoubleCompressionAnalysis,
    meta: FORENSIC_TECHNIQUE_META.double_compression,
  },
  {
    id: "ela",
    mediaType: "imagem",
    template: "medium",
    component: ELAAnalysis,
    meta: FORENSIC_TECHNIQUE_META.ela,
  },
  {
    id: "bag_extraction",
    mediaType: "imagem",
    template: "simple",
    component: BagExtractionAnalysis,
    meta: FORENSIC_TECHNIQUE_META.bag_extraction,
  },
  {
    id: "zero_grid",
    mediaType: "imagem",
    template: "simple",
    component: ZeroGridAnalysis,
    meta: FORENSIC_TECHNIQUE_META.zero_grid,
  },
  {
    id: "resampling",
    mediaType: "imagem",
    template: "medium",
    component: ResamplingAnalysis,
    meta: FORENSIC_TECHNIQUE_META.resampling,
  },
  {
    id: "patchmatch",
    mediaType: "imagem",
    template: "medium",
    component: PatchMatchAnalysis,
    meta: FORENSIC_TECHNIQUE_META.patchmatch,
  },
  {
    id: "copy_move_pca",
    mediaType: "imagem",
    template: "medium",
    component: CopyMovePcaAnalysis,
    meta: FORENSIC_TECHNIQUE_META.copy_move_pca,
  },
  {
    id: "wavelet_noise_residue",
    mediaType: "imagem",
    template: "medium",
    component: WaveletNoiseResidueAnalysis,
    meta: FORENSIC_TECHNIQUE_META.wavelet_noise_residue,
  },
  {
    id: "prnu",
    mediaType: "imagem",
    template: "complex",
    component: PRNUAnalysis,
    meta: FORENSIC_TECHNIQUE_META.prnu,
    gpu: true,
  },
  {
    id: "safire",
    mediaType: "imagem",
    template: "medium",
    component: SafireAnalysis,
    meta: FORENSIC_TECHNIQUE_META.safire,
    gpu: true,
    adminOnly: true,
  },
  {
    id: "synthetic_image_detection",
    mediaType: "imagem",
    template: "ensemble",
    component: SyntheticImageDetectionAnalysis,
    meta: FORENSIC_TECHNIQUE_META.synthetic_image_detection,
    gpu: true,
  },
  {
    id: "presentation_attack_detection",
    mediaType: "imagem",
    template: "medium",
    component: PresentationAttackDetectionAnalysis,
    meta: FORENSIC_TECHNIQUE_META.presentation_attack_detection,
    gpu: true,
    adminOnly: true,
  },
  {
    id: "moe_ffd",
    mediaType: "imagem",
    template: "medium",
    component: MoeFfdAnalysis,
    meta: FORENSIC_TECHNIQUE_META.moe_ffd,
    gpu: true,
    adminOnly: true,
  },
];

// --- IMDL métodos dedicados (sub-tecnicas de imagem) ---

const imdlDedicatedMethods: TechniqueConfig[] = [
  { id: "trufor", mediaType: "imagem", template: "medium", component: ImdlMethodAnalysis, meta: FORENSIC_TECHNIQUE_META.trufor, gpu: true },
  { id: "cat_net", mediaType: "imagem", template: "medium", component: ImdlMethodAnalysis, meta: FORENSIC_TECHNIQUE_META.cat_net, gpu: true },
  { id: "miml_apscnet", mediaType: "imagem", template: "medium", component: ImdlMethodAnalysis, meta: FORENSIC_TECHNIQUE_META.miml_apscnet, gpu: true },
  { id: "sparse_vit", mediaType: "imagem", template: "medium", component: ImdlMethodAnalysis, meta: FORENSIC_TECHNIQUE_META.sparse_vit, gpu: true, adminOnly: true },
  { id: "mesorch", mediaType: "imagem", template: "medium", component: ImdlMethodAnalysis, meta: FORENSIC_TECHNIQUE_META.mesorch, gpu: true, adminOnly: true },
  { id: "dinov3_iml", mediaType: "imagem", template: "medium", component: ImdlMethodAnalysis, meta: FORENSIC_TECHNIQUE_META.dinov3_iml, gpu: true, adminOnly: true },
  { id: "co_transformers", mediaType: "imagem", template: "medium", component: ImdlMethodAnalysis, meta: FORENSIC_TECHNIQUE_META.co_transformers, gpu: true, adminOnly: true },
  { id: "nfa_vit", mediaType: "imagem", template: "medium", component: ImdlMethodAnalysis, meta: FORENSIC_TECHNIQUE_META.objectformer, gpu: true, adminOnly: true, disabled: true },
];

// --- Áudio ---

const audioTechniques: TechniqueConfig[] = [
  {
    id: "audio_spoofing_detection",
    mediaType: "audio",
    template: "ensemble",
    component: AudioSpoofingAnalysis,
    meta: FORENSIC_TECHNIQUE_META.audio_spoofing_detection,
    gpu: true,
  },
  {
    id: "audio_metadata",
    mediaType: "audio",
    template: "simple",
    component: AudioMetadataAnalysis,
    meta: FORENSIC_TECHNIQUE_META.audio_metadata,
  },
  {
    id: "mp3_parser",
    mediaType: "audio",
    template: "simple",
    component: AudioContainerParserAnalysis,
    meta: FORENSIC_TECHNIQUE_META.mp3_parser,
  },
  {
    id: "opus_parser",
    mediaType: "audio",
    template: "simple",
    component: AudioContainerParserAnalysis,
    meta: FORENSIC_TECHNIQUE_META.opus_parser,
  },
  {
    id: "__audio_hub__",
    mediaType: "audio",
    template: "hub",
    component: AudioForensicsHub,
    meta: {
      title: "Análise forense de Áudio",
      citation: "",
      cardSubtitle: "Espectrograma, níveis, ENF, LTAS e DC local",
      detail: "Hub de técnicas forenses de áudio.",
    },
  },
];

// --- Vídeo ---

const videoTechniques: TechniqueConfig[] = [
  {
    id: "video_metadata",
    mediaType: "video",
    template: "simple",
    component: VideoMetadataAnalysis,
    meta: FORENSIC_TECHNIQUE_META.video_metadata,
  },
  { id: "videofact", mediaType: "video", template: "medium", component: VideoFactAnalysis, meta: FORENSIC_TECHNIQUE_META.videofact, gpu: true, adminOnly: true },
  { id: "stil_video_detection", mediaType: "video", template: "simple", component: StilVideoAnalysis, meta: FORENSIC_TECHNIQUE_META.stil_video_detection, gpu: true, adminOnly: true },
  { id: "lowres_fake_video", mediaType: "video", template: "simple", component: LowResFakeVideoAnalysis, meta: FORENSIC_TECHNIQUE_META.lowres_fake_video, gpu: true, adminOnly: true },
  { id: "truvil", mediaType: "video", template: "simple", component: TruVilAnalysis, meta: FORENSIC_TECHNIQUE_META.truvil, gpu: true, adminOnly: true },
  { id: "vilocal", mediaType: "video", template: "simple", component: ViLocalAnalysis, meta: FORENSIC_TECHNIQUE_META.vilocal, gpu: true, adminOnly: true },
  {
    id: "isomedia_parser",
    mediaType: "video",
    template: "complex",
    component: IsoMediaStructureAnalysis,
    meta: {
      title: "Vídeo — Parser ISO BMFF",
      citation: "",
      cardSubtitle: "Estrutura de container ISO BMFF/MP4",
      detail: "Análise estrutural de containers de vídeo ISO BMFF.",
    },
  },
  {
    id: "isomedia_compare",
    mediaType: "video",
    template: "comparison",
    component: IsoMediaSimilarityAnalysis,
    meta: {
      title: "Vídeo — Similaridade ISO BMFF",
      citation: "",
      cardSubtitle: "Comparação estrutural entre containers",
      detail: "Comparação lado a lado de containers ISO BMFF.",
    },
  },
];

// --- PDF ---

const pdfTechniques: TechniqueConfig[] = [
  {
    id: "pdf_font_color_overlay",
    mediaType: "pdf",
    template: "simple",
    component: PDFFontColorAnalysis,
    meta: {
      title: "PDF — Overlay por fonte",
      citation: "",
      cardSubtitle: "Sobreposição de fonte/cor em PDF",
      detail: "Visualização de overlay de fonte e cor em documentos PDF.",
    },
  },
  {
    id: "pdf_structure_metrics",
    mediaType: "pdf",
    template: "simple",
    component: PDFStructureMetricsAnalysis,
    meta: {
      title: "PDF — Estrutura e métricas (grafo)",
      citation: "",
      cardSubtitle: "Métricas estruturais e grafo de objetos PDF",
      detail: "Análise de estrutura e métricas de documentos PDF.",
    },
  },
  {
    id: "pdf_forensic_extract",
    mediaType: "pdf",
    template: "complex",
    component: PDFForensicExtractAnalysis,
    meta: {
      title: "PDF — Extração forense",
      citation: "",
      cardSubtitle: "Extração incremental de artefatos PDF",
      detail: "Extração incremental de múltiplos artefatos forenses de PDF.",
    },
  },
  {
    id: "pdf_structure_similarity",
    mediaType: "pdf",
    template: "comparison",
    component: PDFStructureSimilarityAnalysis,
    meta: {
      title: "PDF — Similaridade estrutural",
      citation: "",
      cardSubtitle: "Comparação estrutural entre documentos PDF",
      detail: "Comparação estrutural lado a lado entre documentos PDF.",
    },
  },
];

const ALL_TECHNIQUES: TechniqueConfig[] = [
  ...imageTechniques,
  ...imdlDedicatedMethods,
  ...audioTechniques,
  ...videoTechniques,
  ...pdfTechniques,
  ...SCAFFOLDED_TECHNIQUES,
];

export const TECHNIQUE_REGISTRY: Readonly<Record<string, TechniqueConfig>> = Object.freeze(
  Object.fromEntries(ALL_TECHNIQUES.map((t) => [t.id, t]))
);

/**
 * Resolve alias de slug de URL (ex.: ``audio_spoofing``, ``pdf_font_overlay``)
 * para o id canônico do registry (ex.: ``audio_spoofing_detection``).
 */
export function resolveCanonicalTechniqueId(techniqueIdOrSlug: string): string {
  const fromRoute = ANALYSIS_ROUTE_META[techniqueIdOrSlug]?.technique;
  if (fromRoute && TECHNIQUE_REGISTRY[fromRoute]) {
    return fromRoute;
  }
  return techniqueIdOrSlug;
}

export function getTechniqueConfig(techniqueId: string): TechniqueConfig | undefined {
  const canonical = resolveCanonicalTechniqueId(techniqueId);
  return TECHNIQUE_REGISTRY[canonical] ?? TECHNIQUE_REGISTRY[techniqueId];
}

export function listTechniqueConfigs(): TechniqueConfig[] {
  return Object.values(TECHNIQUE_REGISTRY);
}

export function resolveTechniqueMediaType(techniqueId: string): MediaType | undefined {
  return getTechniqueConfig(techniqueId)?.mediaType;
}

export function resolveTechniqueComponent(
  techniqueId: string
): LazyExoticComponent<ComponentType<Record<string, unknown>>> | undefined {
  return getTechniqueConfig(techniqueId)?.component;
}
