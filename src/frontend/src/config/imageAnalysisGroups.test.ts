import { describe, it, expect } from "vitest";
import {
  IMAGE_ANALYSIS_GROUPS,
  isImageTechniqueVisible,
  findImageTechniqueEntry,
  getImageAnalysisGroup,
  resolveImageGroupId,
  resolveTechniqueTabLabel,
} from "./imageAnalysisGroups";
import { TECHNIQUE_REGISTRY } from "./techniqueRegistry";

describe("isImageTechniqueVisible", () => {
  it("labels metadata tab as Metadados", () => {
    const entry = findImageTechniqueEntry("metadata");
    expect(entry).toBeDefined();
    expect(resolveTechniqueTabLabel(entry!)).toBe("Metadados");
  });

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

  it("exposes only CAT-Net, TruFor and MIML APSC-Net in dl-manipulacao for perito", () => {
    const group = IMAGE_ANALYSIS_GROUPS.find((g) => g.id === "dl-manipulacao");
    expect(group).toBeDefined();
    const visibleToPerito = group!.techniques
      .filter((t) => isImageTechniqueVisible(t, "perito"))
      .map((t) => t.id);
    expect(visibleToPerito).toEqual(["cat_net", "trufor", "miml_apscnet"]);
  });

  it("exposes admin-only localization methods in dl-manipulacao for admin", () => {
    const group = IMAGE_ANALYSIS_GROUPS.find((g) => g.id === "dl-manipulacao");
    expect(group).toBeDefined();
    const visibleToAdmin = group!.techniques
      .filter((t) => isImageTechniqueVisible(t, "admin"))
      .map((t) => t.id);
    expect(visibleToAdmin).toContain("safire");
    expect(visibleToAdmin).toContain("mesorch");
    expect(visibleToAdmin).toContain("dinov3_iml");
    expect(visibleToAdmin).toEqual(
      expect.arrayContaining(["cat_net", "trufor", "miml_apscnet", "safire"]),
    );
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

  it("maps every grouped image technique to a registered technique", () => {
    for (const group of IMAGE_ANALYSIS_GROUPS) {
      for (const entry of group.techniques) {
        expect(TECHNIQUE_REGISTRY[entry.id]).toBeDefined();
      }
    }
  });

  it("hides a technique when its group entry is removed", () => {
    const group = IMAGE_ANALYSIS_GROUPS.find((g) => g.id === "classicas-compressao");
    expect(group).toBeDefined();
    const withoutDct = group!.techniques.filter((t) => t.id !== "dct_quantization");
    expect(withoutDct.some((t) => t.id === "dct_quantization")).toBe(false);
    expect(withoutDct.some((t) => t.id === "ela")).toBe(true);
  });
});
