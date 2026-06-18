import type { ReactNode } from "react";
import PeritusFileGrid from "@/components/PeritusFileGrid";
import PeritusFilePreview from "@/components/PeritusFilePreview";
import FileListViewHeader from "@/components/FileListViewHeader";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import type { PeritusFileEntry } from "@/services/peritus";
import { imageSelectorListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / k ** i).toFixed(1))} ${sizes[i]}`;
}

interface Props {
  caseId: string;
  files: PeritusFileEntry[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
  radioName: string;
  emptyMessage?: string;
  disabled?: boolean;
  showToggle?: boolean;
  headerLeft?: ReactNode;
}

export default function SelectablePeritusFileList({
  caseId,
  files,
  selectedPath,
  onSelect,
  radioName,
  emptyMessage = "Nenhum arquivo Peritus deste tipo.",
  disabled = false,
  showToggle = true,
  headerLeft,
}: Props) {
  const [viewMode, setViewMode] = useFileListViewMode();

  if (files.length === 0) {
    return <p style={{ color: "#9ca3af", fontSize: "0.85rem", margin: 0 }}>{emptyMessage}</p>;
  }

  const listBody = (
    <div
      style={{
        ...scrollableListStyle,
        maxHeight: imageSelectorListMaxHeight,
        display: "flex",
        flexDirection: "column",
        gap: "0.4rem",
      }}
    >
      {files.map((f) => {
        const selected = selectedPath === f.path;
        return (
          <label
            key={f.path}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.5rem 0.75rem",
              background: selected ? "#eef2ff" : "#fff",
              border: `1px solid ${selected ? "#a5b4fc" : "#e5e7eb"}`,
              borderRadius: 6,
              cursor: disabled ? "wait" : "pointer",
              fontSize: "0.85rem",
              color: "#1a1a2e",
              opacity: disabled && !selected ? 0.65 : 1,
            }}
          >
            <input
              type="radio"
              name={radioName}
              checked={selected}
              disabled={disabled}
              onChange={() => onSelect(f.path)}
            />
            <PeritusFilePreview
              caseId={caseId}
              path={f.path}
              fileType={f.file_type}
              filename={f.filename}
              size={40}
              showPlayBadge={f.file_type === "video"}
            />
            <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
              {f.filename}
            </span>
            <span style={{ fontSize: "0.75rem", color: "#6b7280", whiteSpace: "nowrap" }}>
              {f.folder} · {formatBytes(f.size)}
            </span>
          </label>
        );
      })}
    </div>
  );

  const gridBody = (
    <PeritusFileGrid
      caseId={caseId}
      items={files}
      selectedPath={selectedPath}
      onSelect={(f) => !disabled && onSelect(f.path)}
      maxHeight={imageSelectorListMaxHeight}
      renderFooter={(f) => (
        <span style={{ fontSize: "0.68rem", color: "#9ca3af" }}>
          {f.folder} · {formatBytes(f.size)}
        </span>
      )}
    />
  );

  if (!showToggle) {
    return viewMode === "grid" ? gridBody : listBody;
  }

  return (
    <div>
      <FileListViewHeader viewMode={viewMode} onViewModeChange={setViewMode}>
        {headerLeft}
      </FileListViewHeader>
      {viewMode === "grid" ? gridBody : listBody}
    </div>
  );
}
