import { hasDailyAck, localDateKey, markDailyAck } from "@/lib/dailyAck";

export const IMDL_DISCLAIMER_GROUP_ID = "dl-manipulacao";

export const IMDL_DISCLAIMER_STORAGE_KEY = "forensicauth:imdl-disclaimer-ack-date";

export const IMDL_DISCLAIMER_TITLE = "Atenção — interpretação de resultados IMDL";

export const IMDL_DISCLAIMER_BODY =
  "Os modelos de detecção e localização de manipulações em imagens (IMDL) podem apresentar falsos positivos, a depender das características e das circunstâncias de aquisição e processamento da imagem analisada. Os resultados também podem sofrer influência de aspectos semânticos do conteúdo, e não apenas de artefatos técnicos relacionados à manipulação. Cada caso deve ser avaliado individualmente, considerando suas características, as circunstâncias envolvidas e o conjunto das demais evidências e referências disponíveis.";

export { localDateKey };

export function hasImdlDisclaimerAckToday(
  storage: Pick<Storage, "getItem"> = localStorage,
  now: Date = new Date()
): boolean {
  return hasDailyAck(IMDL_DISCLAIMER_STORAGE_KEY, storage, now);
}

export function markImdlDisclaimerAckToday(
  storage: Pick<Storage, "setItem"> = localStorage,
  now: Date = new Date()
): void {
  markDailyAck(IMDL_DISCLAIMER_STORAGE_KEY, storage, now);
}

export function needsImdlDisclaimer(groupId: string, now: Date = new Date()): boolean {
  if (groupId !== IMDL_DISCLAIMER_GROUP_ID) return false;
  return !hasImdlDisclaimerAckToday(localStorage, now);
}
