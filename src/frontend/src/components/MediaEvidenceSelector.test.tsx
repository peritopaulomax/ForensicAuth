import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import MediaEvidenceSelector from "@/components/MediaEvidenceSelector";
import type { Evidence } from "@/types/api";

vi.mock("@/services/evidence", () => ({
  listCaseEvidences: vi.fn(),
  listCaseDerivatives: vi.fn(),
  listCaseReferences: vi.fn(),
}));

vi.mock("@/services/cases", () => ({
  getCase: vi.fn().mockResolvedValue({ storage_mode: "local" }),
}));

vi.mock("@/services/peritus", () => ({
  resolvePeritusFileForAnalysis: vi.fn(),
  listPeritusFiles: vi.fn().mockResolvedValue({ files: [], file_count: 0 }),
}));

import { listCaseDerivatives, listCaseEvidences, listCaseReferences } from "@/services/evidence";

function makeEv(partial: Partial<Evidence> & Pick<Evidence, "id" | "file_type" | "original_filename">): Evidence {
  return {
    case_id: "c1",
    filename: partial.original_filename,
    file_size: 10,
    mime_type: null,
    sha256: "abc",
    extra_metadata: {},
    uploaded_by: "u1",
    created_at: "2026-01-01T00:00:00Z",
    ...partial,
  };
}

describe("MediaEvidenceSelector refs/derivatives", () => {
  beforeEach(() => {
    vi.mocked(listCaseEvidences).mockReset();
    vi.mocked(listCaseDerivatives).mockReset();
    vi.mocked(listCaseReferences).mockReset();
    vi.mocked(listCaseReferences).mockResolvedValue({ groups: [], global_groups: [] } as never);
  });

  it("shows collapsed global references and pdf derivatives of matching type", async () => {
    vi.mocked(listCaseEvidences).mockResolvedValue([
      makeEv({ id: "e1", file_type: "pdf", original_filename: "doc.pdf" }),
    ]);
    vi.mocked(listCaseDerivatives).mockResolvedValue([
      makeEv({ id: "d1", file_type: "pdf", original_filename: "version_001.pdf" }),
      makeEv({ id: "d2", file_type: "imagem", original_filename: "page.png" }),
      makeEv({ id: "d3", file_type: "documento", original_filename: "report.txt" }),
    ]);
    vi.mocked(listCaseReferences).mockResolvedValue({
      groups: [],
      global_groups: [
        {
          reference_type: "pdf",
          group_label: "padrao",
          display_label: "Padrao PDF",
          files: [makeEv({ id: "r1", file_type: "pdf", original_filename: "ref.pdf" })],
        },
        {
          reference_type: "audio",
          group_label: "aud",
          display_label: "Audio",
          files: [makeEv({ id: "r2", file_type: "audio", original_filename: "a.wav" })],
        },
      ],
    } as never);

    render(
      <MediaEvidenceSelector
        caseId="c1"
        fileType="pdf"
        selectedId={null}
        onSelect={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Referencias globais")).toBeInTheDocument();
      expect(screen.getByText("Derivados (evidencias derivadas)")).toBeInTheDocument();
    });

    expect(screen.queryByText("a.wav")).not.toBeInTheDocument();
    expect(screen.queryByText("page.png")).not.toBeInTheDocument();
    expect(screen.getAllByText("1").length).toBeGreaterThanOrEqual(1);
  });

  it("hides derivatives section when no matching mime/type derivatives exist", async () => {
    vi.mocked(listCaseEvidences).mockResolvedValue([
      makeEv({ id: "e1", file_type: "video", original_filename: "clip.mp4" }),
    ]);
    vi.mocked(listCaseDerivatives).mockResolvedValue([
      makeEv({ id: "d1", file_type: "imagem", original_filename: "frame.png" }),
    ]);

    const { container } = render(
      <MediaEvidenceSelector
        caseId="c-video"
        fileType="video"
        selectedId={null}
        onSelect={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/clip\.mp4/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(vi.mocked(listCaseDerivatives)).toHaveBeenCalled();
    });

    expect(container.textContent).not.toContain("Derivados (evidencias derivadas)");
    expect(container.textContent).not.toContain("Referencias globais");
  });

  it("keeps derivative selected when parent passes selectionSource=derivative", async () => {
    const onSelect = vi.fn();
    vi.mocked(listCaseEvidences).mockResolvedValue([
      makeEv({ id: "e1", file_type: "pdf", original_filename: "doc.pdf" }),
    ]);
    vi.mocked(listCaseDerivatives).mockResolvedValue([
      makeEv({ id: "d1", file_type: "pdf", original_filename: "version_001.pdf" }),
    ]);

    render(
      <MediaEvidenceSelector
        caseId="c1"
        fileType="pdf"
        selectedId="d1"
        selectionSource="derivative"
        onSelect={onSelect}
      />,
    );

    // forceOpen expands the derivatives section when a derivative is selected
    await waitFor(() => {
      expect(screen.getByText("version_001.pdf")).toBeInTheDocument();
    });
  });
});
