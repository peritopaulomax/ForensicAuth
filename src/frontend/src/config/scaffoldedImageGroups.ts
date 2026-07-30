/**
 * Hooks de grupo de imagem (compatibilidade).
 * Scaffolds novos gravam em `scaffoldedMediaGroups.ts` (campo `media`).
 * Wrapper no-op quando a lista de hooks está vazia.
 */
import type { ImageAnalysisGroup, ImageTechniqueEntry } from "@/config/imageAnalysisGroups";

export interface ScaffoldedImageGroupHook {
  /** Grupo existente em IMAGE_ANALYSIS_GROUPS, ou id novo. */
  groupId: string;
  /** Se o grupo não existir, criar com estes campos. */
  newGroup?: {
    title: string;
    description: string;
  };
  entry: ImageTechniqueEntry;
}

/** Preenchido pelo scaffold. */
export const SCAFFOLDED_IMAGE_GROUP_HOOKS: ScaffoldedImageGroupHook[] = [
  // --- scaffold:image-groups:start ---
// --- scaffold:image-groups:end ---
];

/** Aplica hooks scaffolded sobre a lista canônica de grupos (imutável na origem). */
export function applyScaffoldedImageGroups(
  groups: ImageAnalysisGroup[],
): ImageAnalysisGroup[] {
  if (!SCAFFOLDED_IMAGE_GROUP_HOOKS.length) return groups;

  const cloned: ImageAnalysisGroup[] = groups.map((g) => ({
    ...g,
    techniques: [...g.techniques],
  }));

  for (const hook of SCAFFOLDED_IMAGE_GROUP_HOOKS) {
    let group = cloned.find((g) => g.id === hook.groupId);
    if (!group) {
      if (!hook.newGroup) continue;
      group = {
        id: hook.groupId,
        title: hook.newGroup.title,
        description: hook.newGroup.description,
        techniques: [],
      };
      cloned.push(group);
    }
    const key = hook.entry.id;
    if (!group.techniques.some((t) => t.id === key)) {
      group.techniques.push(hook.entry);
    }
  }
  return cloned;
}
