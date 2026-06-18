import { describe, expect, it } from "vitest";
import { buildCompareGridRowAliases, buildMatrixDisplayLabels } from "@/utils/jpegMatrixAliases";
import type { JpegComparePayload } from "@/utils/jpegStructureCompare";
import type { JpegStructureMatrixPayload } from "@/utils/jpegStructureMatrix";

describe("buildMatrixDisplayLabels", () => {
  it("usa R* e Q* no modo com referência", () => {
    const data: JpegStructureMatrixPayload = {
      mode: "with_reference",
      reference_count: 1,
      questioned_count: 2,
      matrix: {
        row_labels: ["padrao_longo_nome.jpg"],
        col_labels: ["7.jpg", "27.jpg"],
        rows: [
          {
            row_index: 0,
            evidence_id: "ref-1",
            label: "padrao_longo_nome.jpg",
            cells: [
              { col_index: 0, matches: true, questioned_evidence_id: "q1", questioned_label: "7.jpg" },
              { col_index: 1, matches: false, questioned_evidence_id: "q2", questioned_label: "27.jpg" },
            ],
          },
        ],
      },
    };
    const display = buildMatrixDisplayLabels(data);
    expect(display.rowAliases).toEqual(["R1"]);
    expect(display.colAliases).toEqual(["Q1", "Q2"]);
    expect(display.legend.find((e) => e.alias === "R1")?.label).toBe("padrao_longo_nome.jpg");
  });

  it("gera aliases R/Q para linhas da grade posicional", () => {
    const data: JpegComparePayload = {
      reference_index: 0,
      file_count: 3,
      max_positions: 1,
      all_match: true,
      structures: [],
      comparisons: [
        {
          is_reference: true,
          inactive_reference: true,
          row_section: "reference",
          evidence_id: "r1",
          label: "padrao.jpg",
          fully_matches: true,
          cells: [],
        },
        {
          is_reference: true,
          row_section: "reference",
          evidence_id: "r2",
          label: "ref.jpg",
          fully_matches: true,
          cells: [],
        },
        {
          is_reference: false,
          row_section: "questioned",
          evidence_id: "q1",
          label: "11.jpg",
          fully_matches: true,
          cells: [],
        },
      ],
    };
    expect(buildCompareGridRowAliases(data)).toEqual(["R1", "R2", "Q1"]);
  });
});
