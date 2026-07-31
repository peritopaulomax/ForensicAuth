import type { AudioTechnicalMetadata } from "@/types/api";

export function formatAudioDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function formatAudioSampleRate(hz: number | null | undefined): string {
  if (hz == null) return "—";
  return `${hz.toLocaleString("pt-BR")} Hz`;
}

export function formatAudioBitDepth(bits: number | null | undefined): string {
  if (bits == null) return "—";
  return `${bits}-bit`;
}

export function formatAudioCodec(codec: string | null | undefined): string {
  if (!codec) return "—";
  return codec;
}

export function audioMetaFromEvidence(extra: Record<string, unknown> | undefined): Partial<AudioTechnicalMetadata> {
  const stored = extra?.audio_technical;
  if (!stored || typeof stored !== "object") return {};
  const m = stored as Record<string, unknown>;
  return {
    sample_rate_hz: typeof m.sample_rate_hz === "number" ? m.sample_rate_hz : null,
    duration_sec: typeof m.duration_sec === "number" ? m.duration_sec : null,
    bit_depth: typeof m.bit_depth === "number" ? m.bit_depth : null,
    codec: typeof m.codec === "string" ? m.codec : null,
    channels: typeof m.channels === "number" ? m.channels : null,
  };
}

export function mergeAudioMeta(
  fromApi: AudioTechnicalMetadata | undefined,
  fromEvidence: Partial<AudioTechnicalMetadata>
): Partial<AudioTechnicalMetadata> {
  if (fromApi) return fromApi;
  return fromEvidence;
}
