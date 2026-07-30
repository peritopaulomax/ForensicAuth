import { lazy, type ComponentType } from "react";

export interface AudioTechniqueEntry {
  id: string;
  kind: "plugin" | "hub";
  adminOnly?: boolean;
  disabled?: boolean;
}

const AudioForensicsHub = lazy(() => import("@/pages/AudioForensicsHub"));
const AudioSpoofingAnalysis = lazy(() => import("@/pages/AudioSpoofingAnalysis"));

const AUDIO_TECHNIQUE_COMPONENTS: Record<string, ComponentType<Record<string, unknown>>> = {
  audio_hub: AudioForensicsHub,
  audio_spoofing_detection: AudioSpoofingAnalysis,
};

export function resolveAudioTechniqueComponent(
  techniqueId: string
): ComponentType<Record<string, unknown>> | null {
  return AUDIO_TECHNIQUE_COMPONENTS[techniqueId] ?? null;
}
