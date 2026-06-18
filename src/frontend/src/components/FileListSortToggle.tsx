import type { CSSProperties } from "react";
import type { FileListSortMode } from "@/lib/fileListSortMode";

interface FileListSortToggleProps {
  mode: FileListSortMode;
  onChange: (mode: FileListSortMode) => void;
}

const selectStyle: CSSProperties = {
  fontSize: "0.75rem",
  color: "#374151",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  padding: "0.35rem 0.5rem",
  background: "#fff",
  cursor: "pointer",
};

export default function FileListSortToggle({ mode, onChange }: FileListSortToggleProps) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
      <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>Ordenar</span>
      <select
        aria-label="Ordenacao dos arquivos"
        value={mode}
        onChange={(e) => onChange(e.target.value as FileListSortMode)}
        style={selectStyle}
      >
        <option value="upload">Upload</option>
        <option value="name">Nome</option>
      </select>
    </label>
  );
}
