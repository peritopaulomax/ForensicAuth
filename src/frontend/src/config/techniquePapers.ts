/** Técnicas com PDF local em docs/references/papers/imdl/ (manifest.json). */

import { SCAFFOLDED_TECHNIQUE_PAPER_IDS } from "@/config/scaffoldedTechniquePapers";

export const TECHNIQUE_PAPER_IDS = new Set([
  "jpeg_structure_compare",
  "jpeg_ghosts",
  "dct_quantization",
  "double_compression",
  "ela",
  "bag_extraction",
  "zero_grid",
  "resampling",
  "patchmatch",
  "copy_move_pca",
  "wavelet_noise_residue",
  "prnu",
  "presentation_attack_detection",
  "safire",
  "trufor",
  "cat_net",
  "sparse_vit",
  "mesorch",
  "dinov3_iml",
  "co_transformers",
  "miml_apscnet",
  ...SCAFFOLDED_TECHNIQUE_PAPER_IDS,
]);

export function hasTechniquePaper(techniqueId: string | undefined): boolean {
  return Boolean(techniqueId && TECHNIQUE_PAPER_IDS.has(techniqueId));
}
