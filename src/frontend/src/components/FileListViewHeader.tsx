import type { CSSProperties, ReactNode } from "react";
import FileListViewToggle from "@/components/FileListViewToggle";
import type { FileListViewMode } from "@/lib/fileListViewMode";

interface FileListViewHeaderProps {
  viewMode: FileListViewMode;
  onViewModeChange: (mode: FileListViewMode) => void;
  children?: ReactNode;
  trailing?: ReactNode;
  style?: CSSProperties;
}

export default function FileListViewHeader({
  viewMode,
  onViewModeChange,
  children,
  trailing,
  style,
}: FileListViewHeaderProps) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "0.75rem",
        marginBottom: "0.5rem",
        flexWrap: "wrap",
        ...style,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
      <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
        {trailing}
        <FileListViewToggle mode={viewMode} onChange={onViewModeChange} />
      </div>
    </div>
  );
}
