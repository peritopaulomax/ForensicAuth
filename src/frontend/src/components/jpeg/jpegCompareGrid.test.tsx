import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import DqtMatrixTooltipLayer from "@/components/jpeg/DqtMatrixTooltipLayer";
import JpegCompareGrid from "@/components/jpeg/JpegCompareGrid";
import legacyFixture from "@/test-fixtures/jpegCompareLegacyResult.json";
import { normalizeComparePayload } from "@/utils/jpegComparePayload";
import { useDqtTooltip } from "@/hooks/useDqtTooltip";

function Harness() {
  const dqt = useDqtTooltip();
  const data = normalizeComparePayload(legacyFixture as Record<string, unknown>);
  if (!data) return <div data-testid="parse-failed" />;
  return (
    <>
      <DqtMatrixTooltipLayer
        state={dqt.state}
        onMouseEnter={dqt.onTooltipEnter}
        onMouseLeave={dqt.onTooltipLeave}
      />
      <JpegCompareGrid
        data={data}
        expandedThumbs={new Set()}
        onPromoteReference={vi.fn()}
        onToggleThumb={vi.fn()}
        dqtHover={dqt.handlers}
      />
    </>
  );
}

describe("JpegCompareGrid + DQT tooltip", () => {
  it("renderiza grade com alias na primeira coluna e nomes de arquivo", () => {
    render(<Harness />);
    expect(screen.getByText("Q1")).toBeTruthy();
    expect(screen.getByText("Q2")).toBeTruthy();
    expect(screen.getByText("ref.jpg")).toBeTruthy();
    expect(screen.getByText("b.jpg")).toBeTruthy();
    expect(screen.queryByTestId("jpeg-grid-legend")).toBeNull();
    expect(screen.getAllByTestId("dqt-cell").length).toBeGreaterThan(0);
  });

  it("exibe tooltip com matriz ao passar o mouse no DQT", async () => {
    render(<Harness />);

    const dqtCells = screen.getAllByTestId("dqt-cell");
    fireEvent.mouseEnter(dqtCells[0]);

    const tooltip = await screen.findByTestId("dqt-tooltip");
    expect(tooltip).toBeTruthy();
    expect(tooltip.textContent).toContain("Matrizes de quantização");
    expect(tooltip.textContent).toContain("Q0");
    expect(tooltip.textContent).toContain("8");

    fireEvent.mouseLeave(dqtCells[0]);
    await waitFor(
      () => {
        expect(screen.queryByTestId("dqt-tooltip")).toBeNull();
      },
      { timeout: 500 }
    );
  });

  it("não deixa tabela HTML aninhada na grade (evita crash de DOM)", () => {
    const { container } = render(<Harness />);
    const outerTables = container.querySelectorAll("table.jpeg-compare-grid");
    expect(outerTables).toHaveLength(1);
    const nestedTables = container.querySelector("table.jpeg-compare-grid table");
    expect(nestedTables).toBeNull();
  });
});
