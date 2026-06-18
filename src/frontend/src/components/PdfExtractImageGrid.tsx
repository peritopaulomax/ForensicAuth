import type { CSSProperties, ReactNode } from "react";
import JobArtifactImageThumb from "@/components/JobArtifactImageThumb";
import { fileGridContainerStyle, scrollableListStyle } from "@/styles/listHeights";

export interface PdfExtractImageItem {
  id: string;
  filename: string;
  label: string;
}

interface PdfExtractImageGridProps {
  jobId: string;
  items: PdfExtractImageItem[];
  fetchBlobUrl: (jobId: string, filename: string) => Promise<string | null>;
  selected?: (item: PdfExtractImageItem) => boolean;
  onSelect: (item: PdfExtractImageItem) => void;
  renderFooter?: (item: PdfExtractImageItem) => ReactNode;
  maxHeight?: number | string;
  thumbSize?: number;
  style?: CSSProperties;
}

export default function PdfExtractImageGrid({
  jobId,
  items,
  fetchBlobUrl,
  selected,
  onSelect,
  renderFooter,
  maxHeight,
  thumbSize = 72,
  style,
}: PdfExtractImageGridProps) {
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
              <JobArtifactImageThumb
                jobId={jobId}
                filename={item.filename}
                fetchBlobUrl={fetchBlobUrl}
                size={thumbSize}
                alt={item.label}
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
              title={item.label}
            >
              {item.label}
            </span>
            {renderFooter?.(item)}
          </button>
        );
      })}
    </div>
  );
}
