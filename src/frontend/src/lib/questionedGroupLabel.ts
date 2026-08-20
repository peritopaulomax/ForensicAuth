/** Group questioned evidences by questioned_group_label (UI helper). */

import type { Evidence } from "@/types/api";

export const DEFAULT_QUESTIONED_LABEL = "Sem rotulo";

export function questionedGroupLabel(ev: Evidence): string {
  const fromApi = (ev as Evidence & { group_label?: string }).group_label;
  if (typeof fromApi === "string" && fromApi.trim()) return fromApi.trim();
  const meta = ev.extra_metadata || {};
  const label = meta.questioned_group_label;
  if (typeof label === "string" && label.trim()) return label.trim();
  return DEFAULT_QUESTIONED_LABEL;
}

export function groupQuestionedByLabel(evidences: Evidence[] | null | undefined): {
  group_label: string;
  display_label: string;
  files: Evidence[];
}[] {
  const buckets = new Map<string, Evidence[]>();
  for (const ev of evidences ?? []) {
    const label = questionedGroupLabel(ev);
    const list = buckets.get(label) || [];
    list.push(ev);
    buckets.set(label, list);
  }
  const labels = Array.from(buckets.keys()).sort((a, b) => {
    if (a === DEFAULT_QUESTIONED_LABEL) return 1;
    if (b === DEFAULT_QUESTIONED_LABEL) return -1;
    return a.localeCompare(b, "pt-BR", { sensitivity: "base" });
  });
  return labels.map((label) => ({
    group_label: label,
    display_label: label,
    files: buckets.get(label) || [],
  }));
}

export function uniqueQuestionedLabels(evidences: Evidence[]): string[] {
  const set = new Set<string>();
  for (const ev of evidences) {
    const label = questionedGroupLabel(ev);
    if (label !== DEFAULT_QUESTIONED_LABEL) set.add(label);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b, "pt-BR", { sensitivity: "base" }));
}
