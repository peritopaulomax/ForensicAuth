import { describe, expect, it } from "vitest";
import {
  TYPED_CONFIRMATION_THRESHOLD,
  groupDependentsByPackage,
  requiresTypedConfirmation,
  summarizeNames,
  totalToDelete,
  typedConfirmationSatisfied,
} from "@/lib/deletionImpact";
import type { DependentDerivative, EvidenceDeletionPreview } from "@/types/api";

function dependent(
  id: string,
  overrides: Partial<DependentDerivative> = {}
): DependentDerivative {
  return {
    evidence_id: id,
    original_filename: `${id}.png`,
    file_type: "imagem",
    is_derived: true,
    technique: "ela",
    artifact_role: null,
    derivation_group_id: "job-1",
    exclusive: true,
    parents: [],
    retained_parents: [],
    ...overrides,
  };
}

function preview(overrides: Partial<EvidenceDeletionPreview> = {}): EvidenceDeletionPreview {
  return {
    case_id: "case-1",
    targets: [
      {
        evidence_id: "ev-1",
        original_filename: "q.jpg",
        file_type: "imagem",
        is_derived: false,
        technique: null,
        artifact_role: null,
        derivation_group_id: "ev-1",
      },
    ],
    dependents: [],
    dependent_count: 0,
    cascade_count: 0,
    retained_count: 0,
    package_count: 0,
    ...overrides,
  };
}

describe("totalToDelete", () => {
  it("counts only targets when cascade is off", () => {
    expect(totalToDelete(preview({ cascade_count: 3 }), "targets_only")).toBe(1);
  });

  it("adds cascade count when cascade is on", () => {
    expect(totalToDelete(preview({ cascade_count: 3 }), "with_dependents")).toBe(4);
  });

  it("returns zero without preview", () => {
    expect(totalToDelete(null, "with_dependents")).toBe(0);
  });
});

describe("typed confirmation", () => {
  it("is not required at the threshold", () => {
    expect(requiresTypedConfirmation(TYPED_CONFIRMATION_THRESHOLD)).toBe(false);
  });

  it("is required above the threshold", () => {
    expect(requiresTypedConfirmation(TYPED_CONFIRMATION_THRESHOLD + 1)).toBe(true);
  });

  it("passes automatically for small batches", () => {
    expect(typedConfirmationSatisfied(2, "")).toBe(true);
  });

  it("requires the exact word for large batches, ignoring case and spaces", () => {
    expect(typedConfirmationSatisfied(50, "")).toBe(false);
    expect(typedConfirmationSatisfied(50, "excluir ")).toBe(true);
    expect(typedConfirmationSatisfied(50, "apagar")).toBe(false);
  });
});

describe("summarizeNames", () => {
  it("truncates long lists and reports the remainder", () => {
    const result = summarizeNames(["a", "b", "c", "d", "e", "f", "g"]);
    expect(result.visible).toHaveLength(5);
    expect(result.hidden).toBe(2);
  });

  it("hides nothing when the list fits", () => {
    expect(summarizeNames(["a", "b"])).toEqual({ visible: ["a", "b"], hidden: 0 });
  });
});

describe("groupDependentsByPackage", () => {
  it("groups by derivation group and labels multi-artifact packages", () => {
    const packages = groupDependentsByPackage([
      dependent("d1"),
      dependent("d2"),
      dependent("d3", { derivation_group_id: "job-2", technique: "prnu" }),
    ]);

    expect(packages).toHaveLength(2);
    expect(packages[0].label).toBe("ELA · 2 artefatos");
    expect(packages[1].label).toBe("PRNU");
  });

  it("falls back to a generic label without technique", () => {
    const packages = groupDependentsByPackage([dependent("d1", { technique: null })]);
    expect(packages[0].label).toBe("Derivados");
  });
});
