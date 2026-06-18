import { describe, expect, it } from "vitest";
import { buildRefVsQuestionedCompare } from "@/utils/jpegStructureCompare";
import type { JpegStructureDump } from "@/utils/jpegStructureCompare";

const refA: JpegStructureDump = {
  available: true,
  evidence_id: "ref-a",
  label: "padrao_a.jpg",
  comparison_markers: [
    { name: "SOI", display_name: "SOI" },
    { name: "EOI", display_name: "EOI" },
  ],
};

const refB: JpegStructureDump = {
  available: true,
  evidence_id: "ref-b",
  label: "padrao_b.jpg",
  comparison_markers: [
    { name: "SOI", display_name: "SOI" },
    { name: "DQT", display_name: "DQT" },
    { name: "EOI", display_name: "EOI" },
  ],
};

const quest: JpegStructureDump = {
  available: true,
  evidence_id: "quest-1",
  label: "7.jpg",
  comparison_markers: [
    { name: "SOI", display_name: "SOI" },
    { name: "EOI", display_name: "EOI" },
  ],
};

describe("buildRefVsQuestionedCompare", () => {
  it("coloca padrões no topo e questionados embaixo", () => {
    const payload = buildRefVsQuestionedCompare([refA, refB], [quest], "ref-a");
    expect(payload.comparisons).toHaveLength(3);
    expect(payload.comparisons[0].row_section).toBe("reference");
    expect(payload.comparisons[1].row_section).toBe("reference");
    expect(payload.comparisons[2].row_section).toBe("questioned");
  });

  it("marca padrões inativos e compara pelo ativo", () => {
    const payload = buildRefVsQuestionedCompare([refA, refB], [quest], "ref-a");
    expect(payload.comparisons[0].is_reference).toBe(true);
    expect(payload.comparisons[0].inactive_reference).toBeFalsy();
    expect(payload.comparisons[1].inactive_reference).toBe(true);
    expect(payload.comparisons[2].fully_matches).toBe(true);
  });

  it("recalcula ao trocar padrão ativo", () => {
    const payload = buildRefVsQuestionedCompare([refA, refB], [quest], "ref-b");
    expect(payload.comparisons[1].inactive_reference).toBeFalsy();
    expect(payload.comparisons[0].inactive_reference).toBe(true);
    expect(payload.comparisons[2].fully_matches).toBe(false);
  });
});
