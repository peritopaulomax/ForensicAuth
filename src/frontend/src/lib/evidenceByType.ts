import type { Evidence } from "@/types/api";

export const EVIDENCE_TYPE_ORDER = ["imagem", "video", "audio", "pdf"] as const;

export const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  imagem: "Imagens",
  video: "Videos",
  audio: "Audio",
  pdf: "Documentos PDF",
};

export function groupEvidencesByType(evidences: Evidence[]): {
  grouped: Record<string, Evidence[]>;
  types: string[];
} {
  const grouped = evidences.reduce<Record<string, Evidence[]>>((acc, ev) => {
    const t = ev.file_type || "outros";
    if (!acc[t]) acc[t] = [];
    acc[t].push(ev);
    return acc;
  }, {});

  const types = [
    ...EVIDENCE_TYPE_ORDER.filter((t) => grouped[t]?.length),
    ...Object.keys(grouped).filter((t) => !EVIDENCE_TYPE_ORDER.includes(t as (typeof EVIDENCE_TYPE_ORDER)[number])),
  ];

  return { grouped, types };
}
