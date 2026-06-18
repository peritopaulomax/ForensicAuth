import { describe, expect, it } from "vitest";
import { slimStructuresList } from "@/utils/jpegComparePayload";
import { buildRefVsQuestionedCompare } from "@/utils/jpegStructureCompare";

describe("comparação ignora conteúdo DHT", () => {
  it("diferença nas tabelas Huffman não impede match", () => {
    const raw = [
      {
        available: true,
        evidence_id: "ref",
        label: "ref.jpg",
        comparison_markers: [
          { name: "SOI", display_name: "SOI" },
          {
            name: "DHT",
            display_name: "DHT",
            dht_tables: [
              {
                table_class: 0,
                table_id: 0,
                counts: [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                values: [5],
              },
            ],
          },
          { name: "EOI", display_name: "EOI" },
        ],
      },
      {
        available: true,
        evidence_id: "quest",
        label: "q.jpg",
        comparison_markers: [
          { name: "SOI", display_name: "SOI" },
          {
            name: "DHT",
            display_name: "DHT",
            dht_tables: [
              {
                table_class: 0,
                table_id: 0,
                counts: [0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                values: [9, 10],
              },
            ],
          },
          { name: "EOI", display_name: "EOI" },
        ],
      },
    ];

    const [ref, cand] = slimStructuresList(raw);
    const cmp = buildRefVsQuestionedCompare([ref], [cand], "ref");
    expect(cmp.comparisons[1].fully_matches).toBe(true);
  });
});
