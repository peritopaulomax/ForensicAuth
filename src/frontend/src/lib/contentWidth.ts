import { useCallback, useEffect, useState } from "react";

export type ContentWidthMode = "auto" | "compact" | "wide";

const STORAGE_KEY = "forensicauth-content-width";

export function isAnalysisPath(pathname: string): boolean {
  return /\/cases\/[^/]+\/analysis(?:\/|$)/.test(pathname);
}

export function resolveContentWidth(mode: ContentWidthMode, pathname: string): "compact" | "wide" {
  if (mode === "compact") return "compact";
  if (mode === "wide") return "wide";
  return isAnalysisPath(pathname) ? "wide" : "compact";
}

export function readContentWidthMode(): ContentWidthMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "compact" || raw === "wide" || raw === "auto") return raw;
  } catch {
    /* ignore */
  }
  return "auto";
}

export function writeContentWidthMode(mode: ContentWidthMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function useContentWidthMode() {
  const [mode, setModeState] = useState<ContentWidthMode>(() => readContentWidthMode());

  const setMode = useCallback((next: ContentWidthMode) => {
    setModeState(next);
    writeContentWidthMode(next);
  }, []);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) {
        setModeState(readContentWidthMode());
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return { mode, setMode };
}
