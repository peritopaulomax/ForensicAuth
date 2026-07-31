import { describe, expect, it } from "vitest";
import { filterPeritusAnalyzable } from "./peritusAnalysis";
import type { PeritusFileEntry } from "@/services/peritus";

function entry(partial: Partial<PeritusFileEntry> & Pick<PeritusFileEntry, "path" | "file_type">): PeritusFileEntry {
  return {
    filename: partial.path.split("/").pop() ?? partial.path,
    folder: "(raiz)",
    size: 100,
    mime_type: null,
    sha256: null,
    peritus_uuid: null,
    is_derived: false,
    is_xml: false,
    ...partial,
  };
}

describe("filterPeritusAnalyzable", () => {
  it("includes derived-files when media type is analyzable", () => {
    const files = [
      entry({ path: "Imagem1.jpg", file_type: "imagem" }),
      entry({
        path: "derived-files/thumb_1.jpg",
        file_type: "imagem",
        is_derived: true,
        folder: "derived-files",
      }),
      entry({
        path: "derived-files/audio.wav",
        file_type: "audio",
        is_derived: true,
        folder: "derived-files",
      }),
    ];
    const result = filterPeritusAnalyzable(files);
    expect(result.map((f) => f.path)).toEqual([
      "Imagem1.jpg",
      "derived-files/thumb_1.jpg",
      "derived-files/audio.wav",
    ]);
  });

  it("excludes xml and outros", () => {
    const files = [
      entry({ path: "peritusCase.xml", file_type: "xml", is_xml: true }),
      entry({ path: "derived-files/hashes.txt", file_type: "outros", is_derived: true }),
      entry({ path: "doc.pdf", file_type: "pdf" }),
    ];
    const result = filterPeritusAnalyzable(files);
    expect(result.map((f) => f.path)).toEqual(["doc.pdf"]);
  });

  it("filters by fileType when provided", () => {
    const files = [
      entry({ path: "a.jpg", file_type: "imagem" }),
      entry({ path: "derived-files/b.jpg", file_type: "imagem", is_derived: true }),
      entry({ path: "c.mp4", file_type: "video" }),
    ];
    expect(filterPeritusAnalyzable(files, "imagem").map((f) => f.path)).toEqual([
      "a.jpg",
      "derived-files/b.jpg",
    ]);
  });
});
