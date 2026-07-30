/**
 * Técnicas geradas por ``scripts/technique/scaffold_technique.py``.
 * Não edite entradas à mão — rode o scaffold (ou remova a técnica pelo script).
 */
import { lazy } from "react";
import type { TechniqueConfig } from "@/config/techniqueRegistry";
import { SCAFFOLDED_TECHNIQUE_META } from "@/config/scaffoldedTechniqueMeta";

const GenericTechniqueAnalysis = lazy(() => import("@/pages/GenericTechniqueAnalysis"));
const GenericComparisonAnalysis = lazy(() => import("@/pages/GenericComparisonAnalysis"));
const GenericEnsembleAnalysis = lazy(() => import("@/pages/GenericEnsembleAnalysis"));

/** Preenchido automaticamente pelo scaffold (simple/medium/comparison/ensemble). */
export const SCAFFOLDED_TECHNIQUES: TechniqueConfig[] = [
  // --- scaffold:techniques:start ---
// --- scaffold:techniques:end ---
];

/** Helper usado pelos templates do scaffold (evita import circular de meta). */
export function scaffoldMeta(id: string) {
  return SCAFFOLDED_TECHNIQUE_META[id];
}

export { GenericTechniqueAnalysis, GenericComparisonAnalysis, GenericEnsembleAnalysis };
