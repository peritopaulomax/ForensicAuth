import { useCallback, useEffect, useMemo, useState } from "react";
import { AnalysisPanel, MessageBox } from "@/components/AnalysisPageShell";
import EvidenceDropZone from "@/components/EvidenceDropZone";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import FileListViewHeader from "@/components/FileListViewHeader";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import {
  listCaseReferences,
  uploadJpegStructureReference,
  type ReferenceGroup,
} from "@/services/evidence";
import type { Evidence } from "@/types/api";
import { prnuRefListMaxHeight } from "@/styles/listHeights";

export type MatrixTab = "with_reference" | "all_pairs";

const JPEG_EXTS = [".jpg", ".jpeg", ".jfif"];

export default function JpegStructureMatrixSection({
  caseId,
  questionedEvidences,
  tab,
  onTabChange,
  selectedRefIds,
  onSelectedRefIdsChange,
}: {
  caseId: string;
  questionedEvidences: Evidence[];
  tab: MatrixTab;
  onTabChange: (tab: MatrixTab) => void;
  selectedRefIds: Set<string>;
  onSelectedRefIdsChange: (ids: Set<string>) => void;
}) {
  const [refGroups, setRefGroups] = useState<ReferenceGroup[]>([]);
  const [selectedRotulo, setSelectedRotulo] = useState("__new__");
  const [newRotulo, setNewRotulo] = useState("");
  const [uploadingRefs, setUploadingRefs] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [refUploadMessage, setRefUploadMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [refViewMode, setRefViewMode] = useFileListViewMode();

  const rotuloOptions = useMemo(() => refGroups.map((g) => g.group_label), [refGroups]);
  const refImages = useMemo(() => {
    if (selectedRotulo === "__new__") return [];
    return refGroups.find((g) => g.group_label === selectedRotulo)?.files ?? [];
  }, [refGroups, selectedRotulo]);

  const activeRotulo = useMemo(() => {
    if (selectedRotulo === "__new__") return newRotulo.trim();
    return selectedRotulo.trim();
  }, [selectedRotulo, newRotulo]);

  const loadRefGroups = useCallback(
    async (activateRotulo?: string) => {
      try {
        const data = await listCaseReferences(caseId);
        const groups = data.groups.filter((g) => g.technique === "jpeg_structure_compare");
        setRefGroups(groups);
        const labels = groups.map((g) => g.group_label);
        setSelectedRotulo((prev) => {
          const preferred = activateRotulo?.trim();
          if (preferred && labels.includes(preferred)) return preferred;
          if (prev && (prev === "__new__" || labels.includes(prev))) return prev;
          return labels[0] || "__new__";
        });
      } catch {
        setRefGroups([]);
      }
    },
    [caseId]
  );

  useEffect(() => {
    loadRefGroups();
  }, [loadRefGroups]);

  useEffect(() => {
    if (selectedRotulo === "__new__") {
      onSelectedRefIdsChange(new Set());
      return;
    }
    const valid = new Set(refImages.map((r) => r.id));
    const kept = [...selectedRefIds].filter((id) => valid.has(id));
    if (kept.length > 0) {
      onSelectedRefIdsChange(new Set(kept));
    } else {
      onSelectedRefIdsChange(valid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync when rotulo/ref list changes
  }, [selectedRotulo, refImages]);

  function toggleRef(id: string) {
    const next = new Set(selectedRefIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedRefIdsChange(next);
  }

  async function handleRefUpload(files: FileList | File[]) {
    const rotulo = activeRotulo;
    if (!rotulo) {
      setRefUploadMessage({ type: "err", text: "Informe o rótulo antes de enviar padrões JPEG." });
      return;
    }
    setUploadingRefs(true);
    setRefUploadMessage(null);
    const list = Array.from(files).filter((f) =>
      JPEG_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext))
    );
    if (list.length === 0) {
      setRefUploadMessage({ type: "err", text: "Envie imagens .jpg, .jpeg ou .jfif." });
      setUploadingRefs(false);
      return;
    }

    const uploaded: Evidence[] = [];
    for (const file of list) {
      setUploadProgress((p) => ({ ...p, [file.name]: 0 }));
      try {
        const ev = await uploadJpegStructureReference(caseId, file, rotulo, (pct) => {
          setUploadProgress((p) => ({ ...p, [file.name]: pct }));
        });
        uploaded.push(ev);
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          `Falha ao enviar ${file.name}`;
        setRefUploadMessage({ type: "err", text: String(msg) });
      }
      setUploadProgress((p) => {
        const next = { ...p };
        delete next[file.name];
        return next;
      });
    }

    if (uploaded.length > 0) {
      await loadRefGroups(rotulo);
      const next = new Set(selectedRefIds);
      uploaded.forEach((u) => next.add(u.id));
      onSelectedRefIdsChange(next);
      setRefUploadMessage({
        type: "ok",
        text: `${uploaded.length} padrão(ões) no grupo JPEG estrutura — ${rotulo}.`,
      });
    }
    setUploadingRefs(false);
  }

  const questionedLabels = questionedEvidences.map((e) => e.original_filename).join(", ");

  return (
    <AnalysisPanel title="Modo de comparação" className="jpeg-structure-matrix-section">
      <p style={{ fontSize: "0.85rem", color: "#6b7280", margin: "0 0 0.75rem" }}>
        <strong>{questionedEvidences.length}</strong> evidência(s) questionada(s) selecionada(s)
        {questionedEvidences.length > 0 ? `: ${questionedLabels}` : ""}. Use <strong>Calcular</strong> para
        gerar a matriz e a grade de estruturas.
      </p>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={() => onTabChange("with_reference")}
          style={tab === "with_reference" ? tabActive : tabIdle}
        >
          Com referência (padrões)
        </button>
        <button
          type="button"
          onClick={() => onTabChange("all_pairs")}
          style={tab === "all_pairs" ? tabActive : tabIdle}
        >
          Sem referência (todas × todas)
        </button>
      </div>

      {tab === "with_reference" && (
        <>
          <RotuloPicker
            rotuloOptions={rotuloOptions}
            selectedRotulo={selectedRotulo}
            newRotulo={newRotulo}
            onRotuloChange={(v) => {
              setSelectedRotulo(v);
              onSelectedRefIdsChange(new Set());
              setRefUploadMessage(null);
            }}
            onNewRotuloChange={setNewRotulo}
          />
          <EvidenceDropZone
            inputId="jpeg-structure-ref-upload"
            accept="image/jpeg,.jpg,.jpeg,.jfif"
            multiple
            uploading={uploadingRefs}
            disabled={selectedRotulo === "__new__" && !newRotulo.trim()}
            hint="Clique ou arraste padrões JPEG de referência"
            subHint={
              activeRotulo
                ? `Grupo: JPEG estrutura — ${activeRotulo}`
                : "Informe o rótulo acima antes de enviar"
            }
            onFiles={handleRefUpload}
          />
          {refUploadMessage && <MessageBox type={refUploadMessage.type} text={refUploadMessage.text} />}
          {Object.keys(uploadProgress).length > 0 && (
            <div style={{ marginTop: "0.75rem", fontSize: "0.8rem" }}>
              {Object.entries(uploadProgress).map(([name, pct]) => (
                <div key={name}>
                  {name}: {pct}%
                </div>
              ))}
            </div>
          )}
          {refImages.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <FileListViewHeader viewMode={refViewMode} onViewModeChange={setRefViewMode}>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={() => onSelectedRefIdsChange(new Set(refImages.map((r) => r.id)))}
                    style={btnSmall}
                  >
                    Marcar todas
                  </button>
                  <button type="button" onClick={() => onSelectedRefIdsChange(new Set())} style={btnSmall}>
                    Desmarcar
                  </button>
                  <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
                    {selectedRefIds.size} de {refImages.length} padrão(ões)
                  </span>
                </div>
              </FileListViewHeader>
              {refViewMode === "grid" ? (
                <EvidenceFileGrid
                  items={refImages}
                  selected={(ev) => selectedRefIds.has(ev.id)}
                  onSelect={(ev) => toggleRef(ev.id)}
                  maxHeight={prnuRefListMaxHeight}
                  thumbSize={56}
                />
              ) : (
                <JpegRefCheckboxList
                  items={refImages}
                  selectedIds={selectedRefIds}
                  onToggle={toggleRef}
                  maxHeight={prnuRefListMaxHeight}
                />
              )}
            </div>
          )}
        </>
      )}
    </AnalysisPanel>
  );
}

function RotuloPicker({
  rotuloOptions,
  selectedRotulo,
  newRotulo,
  onRotuloChange,
  onNewRotuloChange,
}: {
  rotuloOptions: string[];
  selectedRotulo: string;
  newRotulo: string;
  onRotuloChange: (v: string) => void;
  onNewRotuloChange: (v: string) => void;
}) {
  return (
    <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-end", marginBottom: "1rem" }}>
      <label style={fieldStyle}>
        Rótulo do grupo de padrões
        <select
          value={selectedRotulo}
          onChange={(e) => onRotuloChange(e.target.value)}
          style={{ ...inputStyle, minWidth: 200 }}
        >
          {rotuloOptions.map((r) => (
            <option key={r} value={r}>
              JPEG estrutura — {r}
            </option>
          ))}
          <option value="__new__">+ Novo rótulo…</option>
        </select>
      </label>
      {selectedRotulo === "__new__" && (
        <label style={fieldStyle}>
          Novo rótulo
          <input
            type="text"
            value={newRotulo}
            onChange={(e) => onNewRotuloChange(e.target.value)}
            placeholder="Ex.: Câmera_X, Lote_A"
            style={inputStyle}
          />
        </label>
      )}
    </div>
  );
}

function JpegRefCheckboxList({
  items,
  selectedIds,
  onToggle,
  maxHeight,
}: {
  items: Evidence[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  maxHeight: number | string;
}) {
  return (
    <div className="jpeg-compare-select-list" style={{ maxHeight }}>
      {items.map((ev) => (
        <label key={ev.id} className="jpeg-compare-select-item">
          <input type="checkbox" checked={selectedIds.has(ev.id)} onChange={() => onToggle(ev.id)} />
          <span className="jpeg-compare-select-item__name">{ev.original_filename}</span>
        </label>
      ))}
    </div>
  );
}

const fieldStyle = { display: "flex", flexDirection: "column" as const, gap: 4, fontSize: "0.82rem" };
const inputStyle = { padding: "0.45rem", borderRadius: 6, border: "1px solid #d1d5db" };
const btnSmall = {
  padding: "0.35rem 0.7rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.8rem",
} as const;
const tabActive = {
  padding: "0.5rem 1rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontWeight: 600,
} as const;
const tabIdle = {
  padding: "0.5rem 1rem",
  background: "#f3f4f6",
  color: "#374151",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
} as const;
