import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { type ComponentProps } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import CaseAnalysisPanels from "@/components/CaseAnalysisPanels";
import type { Evidence } from "@/types/api";

vi.mock("@/services/api", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
  },
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: (sel: (s: { user: { role: string } }) => unknown) =>
    sel({ user: { role: "perito" } }),
}));

function makeEvidence(partial: Partial<Evidence> & { id: string; file_type: string }): Evidence {
  return {
    case_id: "case-1",
    filename: `${partial.id}.bin`,
    original_filename: `${partial.id}.bin`,
    file_size: 100,
    mime_type: "application/octet-stream",
    sha256: "a".repeat(64),
    uploaded_by: "1",
    created_at: "2026-07-28T00:00:00Z",
    ...partial,
  };
}

function renderPanels(
  props: Partial<ComponentProps<typeof CaseAnalysisPanels>> = {},
) {
  return render(
    <MemoryRouter initialEntries={["/cases/case-1?tab=analises"]}>
      <Routes>
        <Route
          path="/cases/:caseId"
          element={<CaseAnalysisPanels evidences={[]} {...props} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CaseAnalysisPanels media tabs from refs/derivatives", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("opens imagem tab when only global image references exist", async () => {
    renderPanels({
      globalReferenceTypes: ["imagem"],
      globalReferenceCounts: { imagem: 2 },
    });
    const tab = await screen.findByTestId("media-tab-imagem");
    expect(tab).toBeInTheDocument();
    expect(tab).toHaveTextContent("2");
    expect(screen.queryByTestId("media-tab-audio")).not.toBeInTheDocument();
  });

  it("opens audio/video/pdf tabs from derivatives of those types", async () => {
    renderPanels({
      derivativeTypes: ["audio", "video", "pdf"],
      derivativeCounts: { audio: 1, video: 3, pdf: 2 },
    });
    expect(await screen.findByTestId("media-tab-audio")).toBeInTheDocument();
    expect(screen.getByTestId("media-tab-video")).toBeInTheDocument();
    expect(screen.getByTestId("media-tab-pdf")).toBeInTheDocument();
  });

  it("unions evidences with references and derivatives", async () => {
    renderPanels({
      evidences: [makeEvidence({ id: "e1", file_type: "imagem" })],
      globalReferenceTypes: ["audio"],
      globalReferenceCounts: { audio: 1 },
      derivativeTypes: ["pdf"],
      derivativeCounts: { pdf: 4 },
    });
    expect(await screen.findByTestId("media-tab-imagem")).toBeInTheDocument();
    expect(screen.getByTestId("media-tab-audio")).toBeInTheDocument();
    expect(screen.getByTestId("media-tab-pdf")).toBeInTheDocument();
  });
});
