/** IDs must match `AUGMENTATION_CATALOG` in `audio_spoofing_lr_reference.py`. */
export const AUDIO_REFERENCE_AUGMENTATIONS = [
  { id: "mp3_128k", label: "MP3 128 kbps" },
  { id: "opus_32k", label: "Opus / OGG 32 kbps" },
  { id: "noise_snr_20", label: "Ruído ambiente 20 dB SNR" },
  { id: "noise_snr_15", label: "Ruído ambiente 15 dB SNR" },
] as const;

export type AudioReferenceAugmentationId =
  (typeof AUDIO_REFERENCE_AUGMENTATIONS)[number]["id"];

export function orderedAudioAugmentations(
  selected: Iterable<string>
): AudioReferenceAugmentationId[] {
  const set = new Set(selected);
  return AUDIO_REFERENCE_AUGMENTATIONS.map((item) => item.id).filter((id) =>
    set.has(id)
  );
}

export function describeAudioAugmentations(ids: string[] | undefined): string {
  if (!ids?.length) return "";
  const labels = ids.map(
    (id) => AUDIO_REFERENCE_AUGMENTATIONS.find((item) => item.id === id)?.label ?? id
  );
  return labels.join(", ");
}
