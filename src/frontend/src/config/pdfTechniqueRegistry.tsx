import { lazy, type ComponentType } from "react";

export interface PdfTechniqueEntry {
  id: string;
  kind: "plugin";
  adminOnly?: boolean;
  disabled?: boolean;
}

const PDFForensicExtractAnalysis = lazy(() => import("@/pages/PDFForensicExtractAnalysis"));
const PDFStructureMetricsAnalysis = lazy(() => import("@/pages/PDFStructureMetricsAnalysis"));
const PDFStructureSimilarityAnalysis = lazy(() => import("@/pages/PDFStructureSimilarityAnalysis"));
const PDFFontColorAnalysis = lazy(() => import("@/pages/PDFFontColorAnalysis"));

const PDF_TECHNIQUE_COMPONENTS: Record<string, ComponentType<Record<string, unknown>>> = {
  pdf_forensic_extract: PDFForensicExtractAnalysis,
  pdf_structure_metrics: PDFStructureMetricsAnalysis,
  pdf_structure_similarity: PDFStructureSimilarityAnalysis,
  pdf_font_color_overlay: PDFFontColorAnalysis,
};

export function resolvePdfTechniqueComponent(
  techniqueId: string
): ComponentType<Record<string, unknown>> | null {
  return PDF_TECHNIQUE_COMPONENTS[techniqueId] ?? null;
}
