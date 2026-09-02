import { hasDailyAck, markDailyAck } from "@/lib/dailyAck";

export const SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY =
  "forensicauth:synthetic-lr-population-disclaimer-ack-date";

export const SYNTHETIC_LR_POPULATION_DISCLAIMER_TITLE =
  "Atenção — população de referência LR";

export const SYNTHETIC_LR_POPULATION_DISCLAIMER_BODY =
  "Os resultados da LR numérica são fortemente dependentes da escolha apropriada da população de referência.\n\nA seleção default de população de referência engloba modelos open-source de geração sintética mais recentes, e os modelos comerciais atuais.";

export function needsSyntheticLrPopulationDisclaimer(now: Date = new Date()): boolean {
  return !hasDailyAck(SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY, localStorage, now);
}

export function markSyntheticLrPopulationDisclaimerAck(now: Date = new Date()): void {
  markDailyAck(SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY, localStorage, now);
}
