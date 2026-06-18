import { lazy, type ComponentType } from "react";
import type { ImageTechniqueEntry } from "@/config/imageAnalysisGroups";

export type ImageTechniqueComponentProps = {
  embedMethodId?: string;
};

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
const NoiseprintAnalysis = lazy(() => import("@/pages/NoiseprintAnalysis"));
const SafireAnalysis = lazy(() => import("@/pages/SafireAnalysis"));
const SyntheticImageDetectionAnalysis = lazy(() => import("@/pages/SyntheticImageDetectionAnalysis"));
const DistilDireAnalysis = lazy(() => import("@/pages/DistilDireAnalysis"));
const ImdlMethodAnalysis = lazy(() => import("@/pages/ImdlMethodAnalysis"));

const PLUGIN_COMPONENTS: Record<string, ComponentType<ImageTechniqueComponentProps>> = {
  metadata: ImageMetadataAnalysis,
  jpeg_structure_compare: JpegStructureCompareAnalysis,
  jpeg_ghosts: JpegGhostsAnalysis,
  dct_quantization: DCTQuantization,
  double_compression: DoubleCompressionAnalysis,
  ela: ELAAnalysis,
  bag_extraction: BagExtractionAnalysis,
  zero_grid: ZeroGridAnalysis,
  resampling: ResamplingAnalysis,
  patchmatch: PatchMatchAnalysis,
  copy_move_pca: CopyMovePcaAnalysis,
  wavelet_noise_residue: WaveletNoiseResidueAnalysis,
  prnu: PRNUAnalysis,
  noiseprint: NoiseprintAnalysis,
  safire: SafireAnalysis,
  synthetic_image_detection: SyntheticImageDetectionAnalysis,
  distildire: DistilDireAnalysis,
};

export function resolveImageTechniqueComponent(
  entry: ImageTechniqueEntry,
): ComponentType<ImageTechniqueComponentProps> | null {
  if (entry.kind === "imdl") {
    return ImdlMethodAnalysis;
  }
  return PLUGIN_COMPONENTS[entry.id] ?? null;
}

export function techniqueComponentProps(entry: ImageTechniqueEntry): ImageTechniqueComponentProps {
  if (entry.kind === "imdl") {
    return { embedMethodId: entry.id };
  }
  return {};
}
