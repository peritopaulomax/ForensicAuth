import { describe, expect, it } from "vitest";
import { sortEvidenceItems } from "@/lib/sortEvidenceItems";
import type { Evidence } from "@/types/api";

function ev(id: string, name: string, createdAt: string): Evidence {
  return {
    id,
    case_id: "case-1",
    filename: name,
    original_filename: name,
    file_size: 100,
    file_type: "imagem",
    mime_type: "image/jpeg",
    sha256: id,
    extra_metadata: {},
    uploaded_by: "u1",
    created_at: createdAt,
  };
}

describe("sortEvidenceItems", () => {
  const items = [
    ev("c", "charlie.jpg", "2026-01-03T10:00:00Z"),
    ev("a", "alpha.jpg", "2026-01-01T10:00:00Z"),
    ev("b", "bravo.jpg", "2026-01-02T10:00:00Z"),
  ];

  it("keeps upload order by created_at", () => {
    const sorted = sortEvidenceItems(items, "upload");
    expect(sorted.map((i) => i.id)).toEqual(["a", "b", "c"]);
  });

  it("sorts by filename when mode is name", () => {
    const sorted = sortEvidenceItems(items, "name");
    expect(sorted.map((i) => i.original_filename)).toEqual([
      "alpha.jpg",
      "bravo.jpg",
      "charlie.jpg",
    ]);
  });
});
