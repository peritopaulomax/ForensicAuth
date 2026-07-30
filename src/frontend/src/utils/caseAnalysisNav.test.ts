import { describe, expect, it, vi } from "vitest";
import {
  navigateToDedicatedAnalysis,
  techniqueHasDedicatedPage,
  ANALYSIS_ROUTE_META,
} from "./caseAnalysisNav";

describe("caseAnalysisNav purged techniques", () => {
  const purged = ["distildire", "fakevlm", "clipbased_synthetic", "deepfake_similarity"] as const;

  it.each(purged)("does not register %s as dedicated page", (technique) => {
    expect(techniqueHasDedicatedPage(technique)).toBe(false);
    expect(ANALYSIS_ROUTE_META[technique as keyof typeof ANALYSIS_ROUTE_META]).toBeUndefined();
  });

  it.each(purged)("does not navigate to removed %s analysis route", (technique) => {
    const navigate = vi.fn();
    const ok = navigateToDedicatedAnalysis(navigate, "case-abc", technique);
    expect(ok).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });
});
