import { describe, it, expect } from "vitest";
import { hasTechniquePaper, TECHNIQUE_PAPER_IDS } from "@/config/techniquePapers";
import { SCAFFOLDED_TECHNIQUE_PAPER_IDS } from "@/config/scaffoldedTechniquePapers";

describe("techniquePapers scaffold merge", () => {
  it("exposes base paper ids", () => {
    expect(hasTechniquePaper("ela")).toBe(true);
    expect(TECHNIQUE_PAPER_IDS.has("ela")).toBe(true);
  });

  it("starts with empty scaffolded paper set", () => {
    expect(SCAFFOLDED_TECHNIQUE_PAPER_IDS.size).toBe(0);
  });
});
