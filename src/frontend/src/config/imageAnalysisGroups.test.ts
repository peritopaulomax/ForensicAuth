import { describe, it, expect } from "vitest";
import {
  IMAGE_ANALYSIS_GROUPS,
  isImageTechniqueVisible,
  findImageTechniqueEntry,
  getImageAnalysisGroup,
  resolveImageGroupId,
} from "./imageAnalysisGroups";

describe("isImageTechniqueVisible", () => {
  it("shows synthetic_image_detection for admin", () => {
    const entry = findImageTechniqueEntry("synthetic_image_detection");
    expect(entry).toBeDefined();
    expect(isImageTechniqueVisible(entry!, "admin")).toBe(true);
  });

  it("shows synthetic_image_detection for perito", () => {
    const entry = findImageTechniqueEntry("synthetic_image_detection");
    expect(isImageTechniqueVisible(entry!, "perito")).toBe(true);
  });

  it("shows synthetic_image_detection for unauthenticated users", () => {
    const entry = findImageTechniqueEntry("synthetic_image_detection");
    expect(isImageTechniqueVisible(entry!, undefined)).toBe(true);
  });

  it("exposes only synthetic_image_detection in the dl-sintetico group for non-admins", () => {
    const group = IMAGE_ANALYSIS_GROUPS.find((g) => g.id === "dl-sintetico");
    expect(group).toBeDefined();
    const visibleToPerito = group!.techniques.filter((t) =>
      isImageTechniqueVisible(t, "perito"),
    );
    const visibleToNone = group!.techniques.filter((t) =>
      isImageTechniqueVisible(t, undefined),
    );
    expect(visibleToPerito.map((t) => t.id)).toEqual(["synthetic_image_detection"]);
    expect(visibleToNone.map((t) => t.id)).toEqual(["synthetic_image_detection"]);
  });

  it("exposes only synthetic_image_detection in the dl-sintetico group for admins", () => {
    const group = IMAGE_ANALYSIS_GROUPS.find((g) => g.id === "dl-sintetico");
    expect(group).toBeDefined();
    const visibleToAdmin = group!.techniques.filter((t) =>
      isImageTechniqueVisible(t, "admin"),
    );
    expect(visibleToAdmin.map((t) => t.id)).toEqual(["synthetic_image_detection"]);
  });

  it("exposes PAD and MoE-FFD in the dl-facial-spoofing group for admins", () => {
    const group = IMAGE_ANALYSIS_GROUPS.find((g) => g.id === "dl-facial-spoofing");
    expect(group).toBeDefined();
    expect(group!.title).toMatch(/Manipulação e Spoofing Facial/i);
    const visibleToAdmin = group!.techniques.filter((t) => isImageTechniqueVisible(t, "admin"));
    expect(visibleToAdmin.map((t) => t.id)).toEqual([
      "presentation_attack_detection",
      "moe_ffd",
    ]);
    const visibleToPerito = group!.techniques.filter((t) => isImageTechniqueVisible(t, "perito"));
    expect(visibleToPerito).toHaveLength(0);
  });

  it("resolves legacy biometria-facial group id", () => {
    expect(resolveImageGroupId("biometria-facial")).toBe("dl-facial-spoofing");
    expect(getImageAnalysisGroup("biometria-facial")?.id).toBe("dl-facial-spoofing");
  });
});
