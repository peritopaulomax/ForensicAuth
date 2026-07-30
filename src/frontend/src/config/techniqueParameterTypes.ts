/** Tipos compartilhados para formulários declarativos de técnicas (scaffold simple/medium). */

export type TechniqueParamType = "int" | "float" | "boolean" | "string" | "enum";

/**
 * Widget de UI. Se omitido:
 * - int/float → number
 * - enum → select
 * - boolean → checkbox
 * - string → text
 */
export type TechniqueParamWidget = "number" | "slider" | "select" | "radio" | "checkbox" | "text";

export interface TechniqueParameterDef {
  name: string;
  type: TechniqueParamType;
  /** Controle visual; ver TechniqueParamWidget. */
  widget?: TechniqueParamWidget;
  label?: string;
  default?: number | string | boolean;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  description?: string;
}
