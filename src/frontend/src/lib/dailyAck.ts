/** Aceite diário genérico em localStorage (YYYY-MM-DD). */

export function localDateKey(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function hasDailyAck(
  storageKey: string,
  storage: Pick<Storage, "getItem"> = localStorage,
  now: Date = new Date()
): boolean {
  try {
    return storage.getItem(storageKey) === localDateKey(now);
  } catch {
    return false;
  }
}

export function markDailyAck(
  storageKey: string,
  storage: Pick<Storage, "setItem"> = localStorage,
  now: Date = new Date()
): void {
  try {
    storage.setItem(storageKey, localDateKey(now));
  } catch {
    // Storage bloqueado: o aviso pode reaparecer — aceitável.
  }
}
