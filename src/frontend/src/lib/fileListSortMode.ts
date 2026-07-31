import { useCallback, useSyncExternalStore } from "react";

export type FileListSortMode = "upload" | "name";

export const FILE_LIST_SORT_MODE_STORAGE_KEY = "forensicauth:fileListSortMode";

const DEFAULT_MODE: FileListSortMode = "upload";

const listeners = new Set<() => void>();

let cachedMode: FileListSortMode | null = null;

function parseStoredMode(raw: string | null): FileListSortMode | null {
  if (raw === "upload" || raw === "name") return raw;
  return null;
}

function readModeFromStorage(): FileListSortMode {
  try {
    const parsed = parseStoredMode(localStorage.getItem(FILE_LIST_SORT_MODE_STORAGE_KEY));
    if (parsed) return parsed;
  } catch {
    /* ignore */
  }
  return DEFAULT_MODE;
}

function getSnapshot(): FileListSortMode {
  if (cachedMode === null) {
    cachedMode = readModeFromStorage();
  }
  return cachedMode;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notifyListeners(): void {
  listeners.forEach((listener) => listener());
}

function setGlobalMode(mode: FileListSortMode): void {
  cachedMode = mode;
  try {
    localStorage.setItem(FILE_LIST_SORT_MODE_STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
  notifyListeners();
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key !== FILE_LIST_SORT_MODE_STORAGE_KEY) return;
    cachedMode = parseStoredMode(event.newValue) ?? DEFAULT_MODE;
    notifyListeners();
  });
}

export function useFileListSortMode(): [FileListSortMode, (mode: FileListSortMode) => void] {
  const mode = useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_MODE);

  const setMode = useCallback((next: FileListSortMode) => {
    setGlobalMode(next);
  }, []);

  return [mode, setMode];
}
