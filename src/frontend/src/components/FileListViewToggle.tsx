import type { CSSProperties } from "react";
import type { FileListViewMode } from "@/lib/fileListViewMode";

interface FileListViewToggleProps {
  mode: FileListViewMode;
  onChange: (mode: FileListViewMode) => void;
}

const btnBase: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 32,
  height: 32,
  padding: 0,
  border: "1px solid #d1d5db",
  background: "#fff",
  cursor: "pointer",
  color: "#374151",
};

function ListIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <rect x="1" y="2" width="14" height="2" rx="0.5" />
      <rect x="1" y="7" width="14" height="2" rx="0.5" />
      <rect x="1" y="12" width="14" height="2" rx="0.5" />
    </svg>
  );
}

function GridIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <rect x="1" y="1" width="6" height="6" rx="0.5" />
      <rect x="9" y="1" width="6" height="6" rx="0.5" />
      <rect x="1" y="9" width="6" height="6" rx="0.5" />
      <rect x="9" y="9" width="6" height="6" rx="0.5" />
    </svg>
  );
}

export default function FileListViewToggle({ mode, onChange }: FileListViewToggleProps) {
  return (
    <div
      role="group"
      aria-label="Modo de exibicao dos arquivos"
      style={{ display: "inline-flex", borderRadius: 6, overflow: "hidden" }}
    >
      <button
        type="button"
        title="Lista"
        aria-label="Lista"
        aria-pressed={mode === "list"}
        onClick={() => onChange("list")}
        style={{
          ...btnBase,
          borderRadius: "6px 0 0 6px",
          background: mode === "list" ? "#1a1a2e" : "#fff",
          color: mode === "list" ? "#fff" : "#374151",
          borderRight: "none",
        }}
      >
        <ListIcon />
      </button>
      <button
        type="button"
        title="Painéis"
        aria-label="Painéis"
        aria-pressed={mode === "grid"}
        onClick={() => onChange("grid")}
        style={{
          ...btnBase,
          borderRadius: "0 6px 6px 0",
          background: mode === "grid" ? "#1a1a2e" : "#fff",
          color: mode === "grid" ? "#fff" : "#374151",
        }}
      >
        <GridIcon />
      </button>
    </div>
  );
}
