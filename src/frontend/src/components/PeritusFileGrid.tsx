import type { CSSProperties, ReactNode } from "react";
import PeritusFilePreview from "@/components/PeritusFilePreview";
import type { PeritusFileEntry } from "@/services/peritus";
import { fileGridContainerStyle, scrollableListStyle } from "@/styles/listHeights";

interface Props {
  caseId: string;
  items: PeritusFileEntry[];
  selectedPath?: string | null;
  onSelect: (file: PeritusFileEntry) => void;
  renderFooter?: (file: PeritusFileEntry) => ReactNode;
  maxHeight?: number | string;
  thumbSize?: number;
  style?: CSSProperties;
}

export default function PeritusFileGrid({
  caseId,
  items,
  selectedPath,
  onSelect,
  renderFooter,
  maxHeight,
  thumbSize = 72,
  style,
}: Props) {
  return (
    <div
      style={{
        ...scrollableListStyle,
        ...(maxHeight != null ? { maxHeight } : {}),
        ...fileGridContainerStyle,
        ...style,
      }}
    >
      {items.map((file) => {
        const isSelected = selectedPath === file.path;
        return (
          <button
            key={file.path}
            type="button"
            onClick={() => onSelect(file)}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "stretch",
              gap: "0.4rem",
              padding: "0.6rem",
              border: `1px solid ${isSelected ? "#a5b4fc" : "#e5e7eb"}`,
              borderRadius: 8,
              background: isSelected ? "#eef2ff" : "#fff",
              cursor: "pointer",
              textAlign: "left",
              minWidth: 0,
            }}
          >
            <PeritusFilePreview
              caseId={caseId}
              path={file.path}
              fileType={file.file_type}
              filename={file.filename}
              size={thumbSize}
              showPlayBadge={file.file_type === "video"}
            />
            <span
              style={{
                fontSize: "0.78rem",
                fontWeight: 500,
                color: "#1a1a2e",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={file.filename}
            >
              {file.filename}
            </span>
            {renderFooter?.(file)}
          </button>
        );
      })}
    </div>
  );
}
