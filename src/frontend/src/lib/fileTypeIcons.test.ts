import { describe, expect, it } from "vitest";
import { isVisualImageEvidence } from "./fileTypeIcons";

describe("isVisualImageEvidence", () => {
  it("rejects json by extension even when mime is image/jpeg (legado)", () => {
    expect(
      isVisualImageEvidence("imagem", "jpeg_structure_matrix.json", "image/jpeg"),
    ).toBe(false);
  });

  it("accepts jpeg originals", () => {
    expect(isVisualImageEvidence("imagem", "foto.jpg", "image/jpeg")).toBe(true);
  });

  it("accepts png derivatives", () => {
    expect(isVisualImageEvidence("imagem", "heatmap.png", "image/png")).toBe(true);
  });

  it("rejects documento type", () => {
    expect(isVisualImageEvidence("documento", "report.json", "application/json")).toBe(false);
  });
});
