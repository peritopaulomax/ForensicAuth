import type { FileListSortMode } from "@/lib/fileListSortMode";
import type { Evidence } from "@/types/api";

function compareByName(a: Evidence, b: Evidence): number {
  return a.original_filename.localeCompare(b.original_filename, "pt-BR", {
    sensitivity: "base",
    numeric: true,
  });
}

function compareByUpload(a: Evidence, b: Evidence): number {
  const ta = Date.parse(a.created_at);
  const tb = Date.parse(b.created_at);
  if (!Number.isNaN(ta) && !Number.isNaN(tb) && ta !== tb) {
    return ta - tb;
  }
  return compareByName(a, b);
}

export function sortEvidenceItems(items: Evidence[], mode: FileListSortMode): Evidence[] {
  if (items.length <= 1) return items;
  const sorted = [...items];
  sorted.sort(mode === "name" ? compareByName : compareByUpload);
  return sorted;
}
