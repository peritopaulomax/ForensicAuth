import type { Evidence } from "@/types/api";

/** Evidencia criada a partir do workspace Peritus (nao aparece na aba Evidencias ForensicAuth). */
export function isPeritusImportEvidence(ev: Evidence): boolean {
  return Boolean(ev.extra_metadata?.peritus_import);
}

export function filterForensicAuthEvidences(evidences: Evidence[]): Evidence[] {
  return evidences.filter((e) => !isPeritusImportEvidence(e));
}
