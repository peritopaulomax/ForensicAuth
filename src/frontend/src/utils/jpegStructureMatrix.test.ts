import { describe, expect, it } from "vitest";
import { parseJpegStructureMatrix } from "@/utils/jpegStructureMatrix";

describe("parseJpegStructureMatrix", () => {
  it("aceita payload de matriz com referência", () => {
    const parsed = parseJpegStructureMatrix({
      mode: "with_reference",
      reference_count: 1,
      questioned_count: 2,
      matrix: {
        row_labels: ["ref.jpg"],
        col_labels: ["7.jpg", "27.jpg"],
        rows: [
          {
            row_index: 0,
            label: "ref.jpg",
            cells: [
              { col_index: 0, matches: true },
              { col_index: 1, matches: false, reason: "matriz DQT diferente" },
            ],
          },
        ],
      },
    });
    expect(parsed?.matrix?.rows).toHaveLength(1);
    expect(parsed?.matrix?.rows[0].cells[1].matches).toBe(false);
  });

  it("rejeita modo positional", () => {
    expect(parseJpegStructureMatrix({ mode: "positional", matrix: { rows: [], col_labels: [] } })).toBeNull();
  });
});
