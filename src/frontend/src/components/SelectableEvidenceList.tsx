import { useMemo, type ReactNode } from "react";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import EvidenceFilePreview from "@/components/EvidenceFilePreview";
import FileListSortToggle from "@/components/FileListSortToggle";
import FileListViewHeader from "@/components/FileListViewHeader";
import { useFileListSortMode } from "@/lib/fileListSortMode";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import { sortEvidenceItems } from "@/lib/sortEvidenceItems";
import type { Evidence } from "@/types/api";
import { imageSelectorListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / k ** i).toFixed(1))} ${sizes[i]}`;
}

export interface SelectableEvidenceListProps {
  sectionId: string;
  items: Evidence[];
  selectedId: string | null;
  selectionSource: string;
  source: "original" | "derivative";
  onSelect: (id: string, source: "original" | "derivative") => void;
  radioName: string;
  badge?: string;
  emptyMessage?: string;
  showToggle?: boolean;
  showSort?: boolean;
  headerLeft?: ReactNode;
}

export default function SelectableEvidenceList({
  sectionId: _sectionId,
  items,
  selectedId,
  selectionSource,
  source,
  onSelect,
  radioName,
  badge,
  emptyMessage = "Nenhum item.",
  showToggle = true,
  showSort = true,
  headerLeft,
}: SelectableEvidenceListProps) {
  const [viewMode, setViewMode] = useFileListViewMode();
  const [sortMode, setSortMode] = useFileListSortMode();
  const sortedItems = useMemo(
    () => (showSort ? sortEvidenceItems(items, sortMode) : items),
    [items, showSort, sortMode],
  );

  if (items.length === 0) {
    return <p style={{ color: "#9ca3af", fontSize: "0.85rem", margin: 0 }}>{emptyMessage}</p>;
  }

  const isSelected = (ev: Evidence) => selectedId === ev.id && selectionSource === source;

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
      {sortedItems.map((ev) => {
        const selected = isSelected(ev);
        const meta = ev.extra_metadata || {};
        const procedure = meta.procedure_summary as string | undefined;
        return (
          <label
            key={`${source}-${ev.id}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.5rem 0.75rem",
              background: selected ? "#e0f2fe" : "#fff",
              border: `1px solid ${selected ? "#7dd3fc" : "#e5e7eb"}`,
              borderRadius: 6,
              cursor: "pointer",
              fontSize: "0.85rem",
              color: "#1a1a2e",
            }}
          >
            <input
              type="radio"
              name={radioName}
              value={ev.id}
              checked={selected}
              onChange={() => onSelect(ev.id, source)}
            />
            <EvidenceFilePreview
              evidenceId={ev.id}
              fileType={ev.file_type}
              filename={ev.original_filename}
              mimeType={ev.mime_type}
              size={36}
            />
            <span style={{ minWidth: 0, flex: 1 }}>
              {ev.original_filename}
              {badge && (
                <span style={{ marginLeft: "0.35rem", fontSize: "0.7rem", color: "#6b7280" }}>
                  ({badge})
                </span>
              )}
              {source === "derivative" && procedure && (
                <span style={{ display: "block", fontSize: "0.7rem", color: "#9ca3af" }}>{procedure}</span>
              )}
            </span>
            <span style={{ color: "#9ca3af", fontSize: "0.75rem", flexShrink: 0 }}>
              {formatBytes(ev.file_size ?? 0)}
            </span>
          </label>
        );
      })}
    </div>
  );

  const gridBody = (
    <EvidenceFileGrid
      items={sortedItems}
      selected={(ev) => isSelected(ev as Evidence)}
      onSelect={(ev) => onSelect(ev.id, source)}
      maxHeight={imageSelectorListMaxHeight}
      renderFooter={(ev) => {
        const meta = ev.extra_metadata || {};
        const procedure = meta.procedure_summary as string | undefined;
        return (
          <>
            {badge && (
              <span style={{ fontSize: "0.68rem", color: "#6b7280" }}>{badge}</span>
            )}
            {source === "derivative" && procedure && (
              <span style={{ fontSize: "0.68rem", color: "#9ca3af" }}>{procedure}</span>
            )}
            <span style={{ fontSize: "0.68rem", color: "#9ca3af" }}>{formatBytes(ev.file_size ?? 0)}</span>
          </>
        );
      }}
      showPlayBadge={(ev) => ev.file_type === "video"}
    />
  );

  if (!showToggle) {
    return viewMode === "grid" ? gridBody : listBody;
  }

  return (
    <div>
      <FileListViewHeader
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        trailing={showSort ? <FileListSortToggle mode={sortMode} onChange={setSortMode} /> : undefined}
      >
        {headerLeft}
      </FileListViewHeader>
      {viewMode === "grid" ? gridBody : listBody}
    </div>
  );
}
