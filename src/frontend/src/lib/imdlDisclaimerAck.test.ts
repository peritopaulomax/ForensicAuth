import { describe, expect, it } from "vitest";
import {
  IMDL_DISCLAIMER_GROUP_ID,
  IMDL_DISCLAIMER_STORAGE_KEY,
  hasImdlDisclaimerAckToday,
  localDateKey,
  markImdlDisclaimerAckToday,
  needsImdlDisclaimer,
} from "./imdlDisclaimerAck";
import { SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY } from "./syntheticLrPopulationDisclaimer";
import { hasDailyAck, markDailyAck } from "./dailyAck";

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(initial));
  return {
    get length() {
      return map.size;
    },
    clear() {
      map.clear();
    },
    getItem(key: string) {
      return map.has(key) ? map.get(key)! : null;
    },
    key(index: number) {
      return [...map.keys()][index] ?? null;
    },
    removeItem(key: string) {
      map.delete(key);
    },
    setItem(key: string, value: string) {
      map.set(key, value);
    },
  };
}

describe("imdlDisclaimerAck", () => {
  it("formats local date as YYYY-MM-DD", () => {
    expect(localDateKey(new Date(2026, 8, 2))).toBe("2026-09-02");
  });

  it("needs disclaimer only for dl-manipulacao without today's ack", () => {
    const storage = memoryStorage();
    const now = new Date(2026, 8, 2);
    expect(hasImdlDisclaimerAckToday(storage, now)).toBe(false);
    expect(IMDL_DISCLAIMER_GROUP_ID).toBe("dl-manipulacao");

    markImdlDisclaimerAckToday(storage, now);
    expect(storage.getItem(IMDL_DISCLAIMER_STORAGE_KEY)).toBe("2026-09-02");
    expect(hasImdlDisclaimerAckToday(storage, now)).toBe(true);
    expect(hasImdlDisclaimerAckToday(storage, new Date(2026, 8, 3))).toBe(false);
  });

  it("needsImdlDisclaimer is false for other groups", () => {
    expect(needsImdlDisclaimer("dl-sintetico")).toBe(false);
    expect(needsImdlDisclaimer("classicas-compressao")).toBe(false);
  });
});

describe("syntheticLrPopulationDisclaimer", () => {
  it("tracks once-per-day ack on dedicated key", () => {
    const storage = memoryStorage();
    const now = new Date(2026, 8, 2);
    expect(hasDailyAck(SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY, storage, now)).toBe(false);
    markDailyAck(SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY, storage, now);
    expect(hasDailyAck(SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY, storage, now)).toBe(true);
    expect(
      hasDailyAck(SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY, storage, new Date(2026, 8, 3))
    ).toBe(false);
  });
});
