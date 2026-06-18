import type { CSSProperties, ReactNode } from "react";
import EvidenceFilePreview from "@/components/EvidenceFilePreview";
import { fileGridContainerStyle, scrollableListStyle } from "@/styles/listHeights";

export interface EvidenceGridItem {
  id: string;
  original_filename: string;
  file_type?: string;
  mime_type?: string | null;
  file_size?: number;
  sha256?: string;
  extra_metadata?: Record<string, unknown>;
}

interface EvidenceFileGridProps<T extends EvidenceGridItem> {
  items: T[];
  selected?: (item: T) => boolean;
  onSelect: (item: T) => void;
  renderFooter?: (item: T) => ReactNode;
  showPlayBadge?: (item: T) => boolean;
  maxHeight?: number | string;
  thumbSize?: number;
  style?: CSSProperties;
}

export default function EvidenceFileGrid<T extends EvidenceGridItem>({
  items,
  selected,
  onSelect,
  renderFooter,
  showPlayBadge,
  maxHeight,
  thumbSize = 72,
  style,
}: EvidenceFileGridProps<T>) {
  return (
    <div
      style={{
        ...scrollableListStyle,
        ...(maxHeight != null ? { maxHeight } : {}),
        ...fileGridContainerStyle,
        ...style,
      }}
    >
      {items.map((item) => {
        const isSelected = selected?.(item) ?? false;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item)}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "stretch",
              gap: "0.4rem",
              padding: "0.6rem",
              border: `1px solid ${isSelected ? "#7dd3fc" : "#e5e7eb"}`,
              borderRadius: 8,
              background: isSelected ? "#e0f2fe" : "#fff",
              cursor: "pointer",
              textAlign: "left",
              minWidth: 0,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                minHeight: thumbSize,
                background: "#f9fafb",
                borderRadius: 6,
                overflow: "hidden",
              }}
            >
              <EvidenceFilePreview
                evidenceId={item.id}
                fileType={item.file_type}
                filename={item.original_filename}
                mimeType={item.mime_type}
                size={thumbSize}
                showPlayBadge={showPlayBadge?.(item)}
              />
            </div>
            <span
              style={{
                fontSize: "0.78rem",
                fontWeight: 500,
                color: "#1a1a2e",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={item.original_filename}
            >
              {item.original_filename}
            </span>
            {renderFooter?.(item)}
          </button>
        );
      })}
    </div>
  );
}
