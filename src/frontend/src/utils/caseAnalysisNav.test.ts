import { describe, expect, it, vi } from "vitest";
import {
  navigateToDedicatedAnalysis,
  techniqueHasDedicatedPage,
  ANALYSIS_ROUTE_META,
} from "./caseAnalysisNav";

describe("caseAnalysisNav distildire", () => {
  it("registers distildire as dedicated page", () => {
    expect(techniqueHasDedicatedPage("distildire")).toBe(true);
    expect(ANALYSIS_ROUTE_META.distildire?.technique).toBe("distildire");
  });

  it("navigates to distildire analysis route on card click", () => {
    const navigate = vi.fn();
    const ok = navigateToDedicatedAnalysis(navigate, "case-abc", "distildire");
    expect(ok).toBe(true);
    expect(navigate).toHaveBeenCalledWith("/cases/case-abc/analysis/distildire");
  });
});
