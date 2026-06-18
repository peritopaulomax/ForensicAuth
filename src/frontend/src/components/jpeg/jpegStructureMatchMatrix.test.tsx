import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import JpegStructureMatchMatrix from "@/components/jpeg/JpegStructureMatchMatrix";
import type { JpegStructureMatrixPayload } from "@/utils/jpegStructureMatrix";

const fixture: JpegStructureMatrixPayload = {
  mode: "with_reference",
  reference_count: 1,
  questioned_count: 2,
  matrix: {
    row_labels: ["padrao.jpg"],
    col_labels: ["7.jpg", "27.jpg"],
    rows: [
      {
        row_index: 0,
        label: "padrao.jpg",
        cells: [
          { col_index: 0, matches: true },
          { col_index: 1, matches: false, reason: "divergência em DQT" },
        ],
      },
    ],
  },
};

describe("JpegStructureMatchMatrix", () => {
  it("renderiza células verde e vermelha com aliases", () => {
    render(<JpegStructureMatchMatrix data={fixture} />);
    const cells = screen.getAllByTestId("jpeg-matrix-cell");
    expect(cells).toHaveLength(2);
    expect(cells[0].textContent).toBe("✓");
    expect(cells[1].textContent).toBe("✗");
    expect(cells[0].className).toContain("jpeg-matrix__cell--match");
    expect(cells[1].className).toContain("jpeg-matrix__cell--diverge");
    expect(screen.getAllByText("R1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Q1").length).toBeGreaterThan(0);
    expect(screen.getByTestId("jpeg-matrix-legend")).toBeTruthy();
  });
});
