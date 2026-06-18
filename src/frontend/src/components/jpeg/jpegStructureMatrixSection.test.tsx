import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import JpegStructureMatrixSection from "@/components/jpeg/JpegStructureMatrixSection";
import type { Evidence } from "@/types/api";

vi.mock("@/services/evidence", () => ({
  listCaseReferences: vi.fn().mockResolvedValue({ groups: [] }),
  uploadJpegStructureReference: vi.fn(),
}));

vi.mock("@/hooks/useForensicJob", () => ({
  useForensicJob: () => ({
    running: false,
    error: null,
    progress: 0,
    progressLabel: "",
    runAnalysis: vi.fn(),
    reset: vi.fn(),
  }),
}));

const questioned: Evidence[] = [
  {
    id: "ev-a",
    case_id: "case-1",
    filename: "7.jpg",
    original_filename: "7.jpg",
    file_size: 1000,
    file_type: "imagem",
    mime_type: "image/jpeg",
    sha256: "a".repeat(64),
    extra_metadata: {},
    uploaded_by: "u1",
    created_at: "2026-06-09T00:00:00",
  },
  {
    id: "ev-b",
    case_id: "case-1",
    filename: "27.jpg",
    original_filename: "27.jpg",
    file_size: 1000,
    file_type: "imagem",
    mime_type: "image/jpeg",
    sha256: "b".repeat(64),
    extra_metadata: {},
    uploaded_by: "u1",
    created_at: "2026-06-09T00:00:00",
  },
];

describe("JpegStructureMatrixSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza secao de configuracao sem crash", async () => {
    render(
      <JpegStructureMatrixSection
        caseId="case-1"
        questionedEvidences={questioned}
        tab="with_reference"
        onTabChange={vi.fn()}
        selectedRefIds={new Set()}
        onSelectedRefIdsChange={vi.fn()}
      />
    );
    expect(await screen.findByText("Modo de comparação")).toBeTruthy();
    expect(screen.getByText("Com referência (padrões)")).toBeTruthy();
    expect(screen.getByText(/7\.jpg/)).toBeTruthy();
    expect(screen.queryByText("← Voltar as analises do caso")).toBeNull();
  });
});
