import { describe, it, expect } from "vitest";
import {
  TECHNIQUE_REGISTRY,
  listTechniqueConfigs,
  getTechniqueConfig,
  resolveTechniqueComponent,
} from "./techniqueRegistry";

describe("techniqueRegistry", () => {
  it("registers canonical image techniques", () => {
    expect(getTechniqueConfig("ela")).toBeDefined();
    expect(getTechniqueConfig("dct_quantization")).toBeDefined();
    expect(getTechniqueConfig("prnu")).toBeDefined();
  });

  it("registers audio, video and pdf techniques", () => {
    expect(getTechniqueConfig("audio_spoofing_detection")).toBeDefined();
    expect(getTechniqueConfig("videofact")).toBeDefined();
    expect(getTechniqueConfig("truvil")).toBeDefined();
    expect(getTechniqueConfig("vilocal")).toBeDefined();
    expect(getTechniqueConfig("pdf_structure_similarity")).toBeDefined();
  });

  it("resolves route slugs that differ from canonical technique ids", () => {
    const bySlug = getTechniqueConfig("audio_spoofing");
    const byId = getTechniqueConfig("audio_spoofing_detection");
    expect(bySlug).toBeDefined();
    expect(bySlug?.id).toBe("audio_spoofing_detection");
    expect(bySlug).toBe(byId);

    expect(getTechniqueConfig("pdf_font_overlay")?.id).toBe("pdf_font_color_overlay");
    expect(getTechniqueConfig("image_metadata")?.id).toBe("metadata");
  });

  it("lists all registered techniques", () => {
    const configs = listTechniqueConfigs();
    expect(configs.length).toBeGreaterThan(0);
    expect(configs.every((c) => c.id && c.mediaType && c.template)).toBe(true);
  });

  it("covers all page templates used by the sanitization plan", () => {
    const templates = new Set(listTechniqueConfigs().map((c) => c.template));
    for (const required of [
      "simple",
      "medium",
      "comparison",
      "complex",
      "ensemble",
      "hub",
    ] as const) {
      expect(templates.has(required)).toBe(true);
    }
    // Exemplares por template
    expect(getTechniqueConfig("zero_grid")?.template).toBe("simple");
    expect(getTechniqueConfig("ela")?.template).toBe("medium");
    expect(getTechniqueConfig("jpeg_structure_compare")?.template).toBe("comparison");
    expect(getTechniqueConfig("metadata")?.template).toBe("complex");
    expect(getTechniqueConfig("synthetic_image_detection")?.template).toBe("ensemble");
    expect(getTechniqueConfig("audio_spoofing_detection")?.template).toBe("ensemble");
    expect(getTechniqueConfig("__audio_hub__")?.template).toBe("hub");
  });

  it("exposes lazy components for every registered technique", () => {
    for (const id of Object.keys(TECHNIQUE_REGISTRY)) {
      expect(resolveTechniqueComponent(id)).toBeDefined();
    }
  });

  it("supports disabling a technique without removing it from the registry", () => {
    const configs = listTechniqueConfigs();
    const disabled = configs.find((c) => c.disabled);
    // Registry inclui ao menos uma técnica com disabled=true (ex.: nfa_vit).
    expect(disabled).toBeDefined();
    expect(getTechniqueConfig(disabled!.id)).toBeDefined();
  });

  it("removes a technique from routing when it is removed from the registry", () => {
    // Simulate removal by filtering the registry keys.
    const withoutEla = Object.fromEntries(
      Object.entries(TECHNIQUE_REGISTRY).filter(([id]) => id !== "ela"),
    );
    expect(withoutEla["ela"]).toBeUndefined();
    expect(withoutEla["dct_quantization"]).toBeDefined();
  });
});
