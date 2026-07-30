import { lazy, type ComponentType } from "react";

export interface VideoTechniqueEntry {
  id: string;
  kind: "plugin";
  adminOnly?: boolean;
  disabled?: boolean;
}

const VideoFactAnalysis = lazy(() => import("@/pages/VideoFactAnalysis"));
const StilVideoAnalysis = lazy(() => import("@/pages/StilVideoAnalysis"));
const LowResFakeVideoAnalysis = lazy(() => import("@/pages/LowResFakeVideoAnalysis"));
const TruVilAnalysis = lazy(() => import("@/pages/TruVilAnalysis"));
const ViLocalAnalysis = lazy(() => import("@/pages/ViLocalAnalysis"));
const IsoMediaStructureAnalysis = lazy(() => import("@/pages/IsoMediaStructureAnalysis"));
const IsoMediaSimilarityAnalysis = lazy(() => import("@/pages/IsoMediaSimilarityAnalysis"));

const VIDEO_TECHNIQUE_COMPONENTS: Record<string, ComponentType<Record<string, unknown>>> = {
  videofact: VideoFactAnalysis,
  stil_video_detection: StilVideoAnalysis,
  lowres_fake_video: LowResFakeVideoAnalysis,
  truvil: TruVilAnalysis,
  vilocal: ViLocalAnalysis,
  isomedia_parser: IsoMediaStructureAnalysis,
  isomedia_compare: IsoMediaSimilarityAnalysis,
};

export function resolveVideoTechniqueComponent(
  techniqueId: string
): ComponentType<Record<string, unknown>> | null {
  return VIDEO_TECHNIQUE_COMPONENTS[techniqueId] ?? null;
}
