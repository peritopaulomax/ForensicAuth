// Ambient declaration: plotly.js-dist-min ships no TypeScript types.
// Must live in a non-module .d.ts (no top-level import/export) so TS treats
// it as an ambient module declaration, not a module augmentation.
declare module "plotly.js-dist-min";
