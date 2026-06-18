import type { CSSProperties } from "react";

/** Alturas max. de listas rolaveis (~linhas visiveis), alinhadas ao padding/thumb atuais. */

export const EVIDENCE_LIST_MAX_LINES = 20;
export const PRNU_REF_LIST_MAX_LINES = 6;

const CASE_EVIDENCE_ROW_PX = 58;
const SELECTOR_ROW_PX = 50;
const PRNU_REF_ROW_PX = 54;

export const caseEvidenceListMaxHeight = CASE_EVIDENCE_ROW_PX * EVIDENCE_LIST_MAX_LINES;
export const imageSelectorListMaxHeight = SELECTOR_ROW_PX * EVIDENCE_LIST_MAX_LINES;
export const referenceGroupListMaxHeight = CASE_EVIDENCE_ROW_PX * EVIDENCE_LIST_MAX_LINES;
export const prnuRefListMaxHeight = PRNU_REF_ROW_PX * PRNU_REF_LIST_MAX_LINES;

export const scrollableListStyle: CSSProperties = {
  overflowY: "auto",
  overflowX: "hidden",
};

export const fileGridContainerStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
  gap: "0.75rem",
};
