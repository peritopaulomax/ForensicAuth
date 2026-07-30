/**
 * Hooks de grupo por mídia para técnicas scaffolded.
 * Cada entrada adiciona a técnica a um grupo existente (ou declara um grupo novo).
 */
import type { MediaAnalysisGroup, MediaTechniqueEntry } from "@/config/mediaAnalysisGroups";

export type ScaffoldMedia = "imagem" | "audio" | "video" | "pdf";

export interface ScaffoldedMediaGroupHook {
  media: ScaffoldMedia;
  /** Grupo existente no catálogo da mídia, ou id novo. */
  groupId: string;
  /** Se o grupo não existir, criar com estes campos. */
  newGroup?: {
    title: string;
    description: string;
  };
  entry: MediaTechniqueEntry;
}

/** Preenchido pelo scaffold (`card.mode` existing|new). */
export const SCAFFOLDED_MEDIA_GROUP_HOOKS: ScaffoldedMediaGroupHook[] = [
  // --- scaffold:media-groups:start ---
  // --- scaffold:media-groups:end ---
];

/** Aplica hooks scaffolded sobre a lista canônica de grupos de uma mídia. */
export function applyScaffoldedMediaGroups(
  media: ScaffoldMedia,
  groups: MediaAnalysisGroup[],
): MediaAnalysisGroup[] {
  const hooks = SCAFFOLDED_MEDIA_GROUP_HOOKS.filter((h) => h.media === media);
  if (!hooks.length) return groups;

  const cloned: MediaAnalysisGroup[] = groups.map((g) => ({
    ...g,
    techniques: [...g.techniques],
  }));

  for (const hook of hooks) {
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
