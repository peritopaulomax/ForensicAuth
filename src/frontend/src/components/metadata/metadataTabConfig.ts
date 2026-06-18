export type MetadataTabId =
  | "overview"
  | "exif"
  | "iptc"
  | "xmp"
  | "icc"
  | "makernotes"
  | "adobe"
  | "jpeg"
  | "other";

export type MetadataTabGroupId = "overview" | "capture" | "edition" | "color" | "technical" | "other";

export interface MetadataTabDef {
  id: MetadataTabId;
  label: string;
  icon: string;
  group: MetadataTabGroupId;
  accentColor: string;
}

export const METADATA_TAB_GROUPS: { id: MetadataTabGroupId; label: string }[] = [
  { id: "overview", label: "Painel" },
  { id: "capture", label: "Captura" },
  { id: "edition", label: "Edição" },
  { id: "color", label: "Cor" },
  { id: "technical", label: "Técnico" },
  { id: "other", label: "Outros" },
];

export const METADATA_TABS: MetadataTabDef[] = [
  { id: "overview", label: "Visão geral", icon: "◉", group: "overview", accentColor: "#0369a1" },
  { id: "exif", label: "EXIF", icon: "⌗", group: "capture", accentColor: "#0f766e" },
  { id: "makernotes", label: "MakerNotes", icon: "⚙", group: "capture", accentColor: "#0f766e" },
  { id: "xmp", label: "XMP", icon: "⎇", group: "edition", accentColor: "#7c3aed" },
  { id: "adobe", label: "Adobe", icon: "◧", group: "edition", accentColor: "#7c3aed" },
  { id: "iptc", label: "IPTC", icon: "✎", group: "edition", accentColor: "#7c3aed" },
  { id: "icc", label: "ICC", icon: "◐", group: "color", accentColor: "#b45309" },
  { id: "jpeg", label: "Estrutura JPEG", icon: "#", group: "technical", accentColor: "#1e40af" },
  { id: "other", label: "Outros", icon: "…", group: "other", accentColor: "#6b7280" },
];

export function tabDefById(id: MetadataTabId): MetadataTabDef {
  return METADATA_TABS.find((t) => t.id === id) ?? METADATA_TABS[0];
}
