import { useCallback, useSyncExternalStore } from "react";

export type FileListViewMode = "list" | "grid";

export const FILE_LIST_VIEW_MODE_STORAGE_KEY = "forensicauth:fileListViewMode";

const DEFAULT_MODE: FileListViewMode = "grid";

const listeners = new Set<() => void>();

let cachedMode: FileListViewMode | null = null;

function parseStoredMode(raw: string | null): FileListViewMode | null {
  if (raw === "list" || raw === "grid") return raw;
  return null;
}

function readModeFromStorage(): FileListViewMode {
  try {
    const parsed = parseStoredMode(localStorage.getItem(FILE_LIST_VIEW_MODE_STORAGE_KEY));
    if (parsed) return parsed;
  } catch {
    /* ignore */
  }
  return DEFAULT_MODE;
}

function getSnapshot(): FileListViewMode {
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

function setGlobalMode(mode: FileListViewMode): void {
  cachedMode = mode;
  try {
    localStorage.setItem(FILE_LIST_VIEW_MODE_STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
  notifyListeners();
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key !== FILE_LIST_VIEW_MODE_STORAGE_KEY) return;
    cachedMode = parseStoredMode(event.newValue) ?? DEFAULT_MODE;
    notifyListeners();
  });
}

export function loadFileListViewMode(): FileListViewMode {
  return getSnapshot();
}

export function saveFileListViewMode(mode: FileListViewMode): void {
  setGlobalMode(mode);
}

export function useFileListViewMode(): [FileListViewMode, (mode: FileListViewMode) => void] {
  const mode = useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_MODE);

  const setMode = useCallback((next: FileListViewMode) => {
    setGlobalMode(next);
  }, []);

  return [mode, setMode];
}
