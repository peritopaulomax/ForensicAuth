import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import JpegMatrixLegendCompact from "@/components/jpeg/JpegMatrixLegendCompact";
import type { MatrixLegendEntry } from "@/utils/jpegMatrixAliases";

const legend: MatrixLegendEntry[] = [
  { alias: "R1", label: "padrao_a.jpg", role: "reference" },
  { alias: "R2", label: "padrao_b.jpg", role: "reference" },
  ...Array.from({ length: 20 }, (_, i) => ({
    alias: `Q${i + 1}`,
    label: `file_${i + 1}.jpg`,
    role: "questioned" as const,
  })),
];

describe("JpegMatrixLegendCompact", () => {
  it("renderiza seções compactas com scroll", () => {
    render(<JpegMatrixLegendCompact legend={legend} />);
    expect(screen.getByTestId("jpeg-matrix-legend")).toBeTruthy();
    expect(screen.getByText(/Padrões/)).toBeTruthy();
    expect(screen.getByText(/Questionados/)).toBeTruthy();
    expect(screen.getByText("R1")).toBeTruthy();
    expect(screen.getByText("Q20")).toBeTruthy();
  });
});
