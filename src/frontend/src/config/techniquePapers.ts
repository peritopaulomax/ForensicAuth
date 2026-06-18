/** Técnicas com PDF local em docs/references/papers/imdl/ (manifest.json). */

export const TECHNIQUE_PAPER_IDS = new Set([
  "safire",
  "trufor",
  "cat_net",
  "sparse_vit",
  "mesorch",
  "dinov3_iml",
  "co_transformers",
]);

export function hasTechniquePaper(techniqueId: string | undefined): boolean {
  return Boolean(techniqueId && TECHNIQUE_PAPER_IDS.has(techniqueId));
}
