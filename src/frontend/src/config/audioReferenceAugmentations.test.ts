import { describe, expect, it } from "vitest";
import {
  AUDIO_REFERENCE_AUGMENTATIONS,
  describeAudioAugmentations,
  orderedAudioAugmentations,
} from "./audioReferenceAugmentations";

describe("audioReferenceAugmentations", () => {
  it("preserva a ordem do catalogo ao selecionar fora de ordem", () => {
    expect(orderedAudioAugmentations(["noise_snr_15", "mp3_128k"])).toEqual([
      "mp3_128k",
      "noise_snr_15",
    ]);
  });

  it("rotula ids conhecidos", () => {
    expect(AUDIO_REFERENCE_AUGMENTATIONS.map((item) => item.id)).toEqual([
      "mp3_128k",
      "opus_32k",
      "noise_snr_20",
      "noise_snr_15",
    ]);
    expect(describeAudioAugmentations(["mp3_128k", "opus_32k"])).toBe(
      "MP3 128 kbps, Opus / OGG 32 kbps"
    );
  });
});
