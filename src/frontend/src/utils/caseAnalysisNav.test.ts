import { describe, expect, it, vi } from "vitest";
import {
  navigateToDedicatedAnalysis,
  techniqueHasDedicatedPage,
  ANALYSIS_ROUTE_META,
} from "./caseAnalysisNav";

describe("caseAnalysisNav removed synthetic tabs", () => {
  it("does not register distildire as dedicated page", () => {
    expect(techniqueHasDedicatedPage("distildire")).toBe(false);
    expect(ANALYSIS_ROUTE_META.distildire).toBeUndefined();
  });

  it("does not navigate to removed distildire analysis route", () => {
    const navigate = vi.fn();
    const ok = navigateToDedicatedAnalysis(navigate, "case-abc", "distildire");
    expect(ok).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });
});
