import { describe, expect, it } from "vitest";
import {
  DEFAULT_LIBJPEG_QUALITY,
  LIBJPEG_LUMA_BASE,
  clampJpegQuality,
  libjpegLumaQuantizationMatrix,
  libjpegQualityScale,
} from "@/utils/libjpegQuantizationMatrix";

describe("libjpegQuantizationMatrix", () => {
  it("clampa qualidade em 1–100", () => {
    expect(clampJpegQuality(0)).toBe(1);
    expect(clampJpegQuality(101)).toBe(100);
    expect(clampJpegQuality(80.4)).toBe(80);
  });

  it("usa escala libjpeg clássica", () => {
    expect(libjpegQualityScale(50)).toBe(100);
    expect(libjpegQualityScale(80)).toBe(40);
    expect(libjpegQualityScale(90)).toBe(20);
    expect(libjpegQualityScale(25)).toBe(200);
  });

  it("em Q50 devolve a tabela base de luminância", () => {
    expect(libjpegLumaQuantizationMatrix(50)).toEqual(
      LIBJPEG_LUMA_BASE.map((row) => [...row])
    );
  });

  it("default Q80 bate com libjpeg luminância", () => {
    expect(DEFAULT_LIBJPEG_QUALITY).toBe(80);
    expect(libjpegLumaQuantizationMatrix(80)).toEqual([
      [6, 4, 4, 6, 10, 16, 20, 24],
      [5, 5, 6, 8, 10, 23, 24, 22],
      [6, 5, 6, 10, 16, 23, 28, 22],
      [6, 7, 9, 12, 20, 35, 32, 25],
      [7, 9, 15, 22, 27, 44, 41, 31],
      [10, 14, 22, 26, 32, 42, 45, 37],
      [20, 26, 31, 35, 41, 48, 48, 40],
      [29, 37, 38, 39, 45, 40, 41, 40],
    ]);
  });

  it("Q100 não zera coeficientes", () => {
    const m = libjpegLumaQuantizationMatrix(100);
    expect(m.flat().every((v) => v >= 1 && v <= 255)).toBe(true);
  });
});
