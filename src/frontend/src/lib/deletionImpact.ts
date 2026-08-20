/** Regras de apresentacao da confirmacao destrutiva de evidencias/derivados. */

import type { DependentDerivative, EvidenceDeletionPreview } from "@/types/api";

/** Acima deste total, a confirmacao exige digitacao para evitar clique automatico. */
export const TYPED_CONFIRMATION_THRESHOLD = 10;

export const TYPED_CONFIRMATION_WORD = "EXCLUIR";

export type DeletionScope = "targets_only" | "with_dependents";

export function totalToDelete(
  preview: EvidenceDeletionPreview | null,
  scope: DeletionScope
): number {
  if (!preview) return 0;
  const base = preview.targets.length;
  return scope === "with_dependents" ? base + preview.cascade_count : base;
}

export function requiresTypedConfirmation(total: number): boolean {
  return total > TYPED_CONFIRMATION_THRESHOLD;
}

export function typedConfirmationSatisfied(total: number, typed: string): boolean {
  if (!requiresTypedConfirmation(total)) return true;
  return typed.trim().toUpperCase() === TYPED_CONFIRMATION_WORD;
}

/** Nomes visiveis + quantos ficaram de fora, para nao estourar a altura do modal. */
export function summarizeNames(
  names: string[],
  maxNames = 5
): { visible: string[]; hidden: number } {
  return {
    visible: names.slice(0, maxNames),
    hidden: Math.max(0, names.length - maxNames),
  };
}

export interface DependentPackage {
  group_id: string;
  label: string;
  items: DependentDerivative[];
}

export function groupDependentsByPackage(
  dependents: DependentDerivative[]
): DependentPackage[] {
  const buckets = new Map<string, DependentDerivative[]>();
  for (const item of dependents) {
    const list = buckets.get(item.derivation_group_id) || [];
    list.push(item);
    buckets.set(item.derivation_group_id, list);
  }
  return Array.from(buckets.entries()).map(([group_id, items]) => ({
    group_id,
    label: packageLabel(items),
    items,
  }));
}

function packageLabel(items: DependentDerivative[]): string {
  const technique = items.find((item) => item.technique)?.technique;
  const base = technique ? technique.toUpperCase() : "Derivados";
  return items.length > 1 ? `${base} · ${items.length} artefatos` : base;
}
