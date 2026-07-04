import { describe, it, expect } from "vitest";
import {
  IMAGE_ANALYSIS_GROUPS,
  isImageTechniqueVisible,
  findImageTechniqueEntry,
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
});
