import { describe, expect, it } from "vitest";
import { dqtFlatToMatrix8x8, normalizeDqtMatrix } from "@/utils/jpegDqtMatrix";

describe("jpegDqtMatrix", () => {
  it("converte vetor zigzag de 64 coeficientes sem lançar erro", () => {
    const flat = Array.from({ length: 64 }, (_, i) => i + 1);
    const matrix = dqtFlatToMatrix8x8(flat);
    expect(matrix).toHaveLength(8);
    expect(matrix[0][0]).toBe(1);
    expect(matrix[7][7]).toBe(64);
  });

  it("aceita matriz 8x8 já espacial", () => {
    const raw = Array.from({ length: 8 }, (_, r) =>
      Array.from({ length: 8 }, (_, c) => r * 8 + c + 1)
    );
    const matrix = normalizeDqtMatrix(raw);
    expect(matrix[0][0]).toBe(1);
    expect(matrix[7][7]).toBe(64);
  });
});
