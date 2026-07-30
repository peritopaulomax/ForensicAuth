import { describe, it, expect } from "vitest";
import { initialParameterValues } from "@/components/TechniqueParameterForm";
import type { TechniqueParameterDef } from "@/config/techniqueParameterTypes";
import { SCAFFOLDED_TECHNIQUES } from "@/config/scaffoldedTechniques";
import { applyScaffoldedImageGroups } from "@/config/scaffoldedImageGroups";
import { applyScaffoldedMediaGroups } from "@/config/scaffoldedMediaGroups";
import type { ImageAnalysisGroup } from "@/config/imageAnalysisGroups";
import type { MediaAnalysisGroup } from "@/config/mediaAnalysisGroups";

describe("technique scaffold frontend wiring", () => {
  it("starts with empty scaffolded techniques list", () => {
    expect(Array.isArray(SCAFFOLDED_TECHNIQUES)).toBe(true);
  });

  it("initialParameterValues fills defaults", () => {
    const defs: TechniqueParameterDef[] = [
      { name: "gain", type: "float", default: 1.5 },
      { name: "flag", type: "boolean" },
      { name: "mode", type: "enum", options: ["a", "b"] },
    ];
    expect(initialParameterValues(defs)).toEqual({
      gain: 1.5,
      flag: false,
      mode: "a",
    });
  });

  it("applyScaffoldedImageGroups is no-op with empty hooks", () => {
    const base: ImageAnalysisGroup[] = [
      {
        id: "g1",
        title: "G1",
        description: "d",
        techniques: [{ kind: "plugin", id: "ela" }],
      },
    ];
    const out = applyScaffoldedImageGroups(base);
    expect(out).toEqual(base);
    expect(out[0].techniques.map((t) => t.id)).toEqual(["ela"]);
  });

  it("applyScaffoldedMediaGroups is no-op with empty hooks", () => {
    const base: MediaAnalysisGroup[] = [
      {
        id: "audio-spoofing",
        title: "Spoofing",
        description: "d",
        techniques: [{ kind: "plugin", id: "audio_spoofing_detection" }],
      },
    ];
    const out = applyScaffoldedMediaGroups("audio", base);
    expect(out).toEqual(base);
  });
});
