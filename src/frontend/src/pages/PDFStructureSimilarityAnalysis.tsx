import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import EvidenceDropZone from "@/components/EvidenceDropZone";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import EvidenceFilePreview from "@/components/EvidenceFilePreview";
import FileListViewHeader from "@/components/FileListViewHeader";
import PeritusMultiFilePicker from "@/components/PeritusMultiFilePicker";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import { useForensicJob } from "@/hooks/useForensicJob";
import {
  listCaseEvidences,
  listCaseReferences,
  saveDerivative,
  uploadPdfStructureReference,
  type ReferenceGroup,
} from "@/services/evidence";
import type { Evidence } from "@/types/api";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import { imageSelectorListMaxHeight, prnuRefListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

type TabMode = "with_reference" | "all_pairs";

export default function PDFStructureSimilarityAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabMode>("with_reference");

  const [refGroups, setRefGroups] = useState<ReferenceGroup[]>([]);
  const [selectedRotulo, setSelectedRotulo] = useState("__new__");
  const [newRotulo, setNewRotulo] = useState("");
  const [selectedRefIds, setSelectedRefIds] = useState<Set<string>>(new Set());
  const [uploadingRefs, setUploadingRefs] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [refUploadMessage, setRefUploadMessage] = useState<{ type: "ok" | "err"; text: string } | null>(
    null
  );
  const [refViewMode, setRefViewMode] = useFileListViewMode();

  const [casePdfs, setCasePdfs] = useState<Evidence[]>([]);
  const [selectedQuestIds, setSelectedQuestIds] = useState<Set<string>>(new Set());
  const [questViewMode, setQuestViewMode] = useFileListViewMode();

  const [jaccardUrl, setJaccardUrl] = useState<string | null>(null);
  const [wlUrl, setWlUrl] = useState<string | null>(null);
  const [savingDerivative, setSavingDerivative] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  const rotuloOptions = useMemo(() => refGroups.map((g) => g.group_label), [refGroups]);

  const refPdfs = useMemo(() => {
    if (selectedRotulo === "__new__") return [];
    return refGroups.find((g) => g.group_label === selectedRotulo)?.files ?? [];
  }, [refGroups, selectedRotulo]);

  const activeRotulo = useMemo(() => {
    if (selectedRotulo === "__new__") return newRotulo.trim();
    return selectedRotulo.trim();
  }, [selectedRotulo, newRotulo]);

  const loadRefGroups = useCallback(async (activateRotulo?: string) => {
    if (!caseId) return;
    try {
      const data = await listCaseReferences(caseId);
      const groups = data.groups.filter((g) => g.technique === "pdf_structure_similarity");
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
  }, [caseId]);

  useEffect(() => {
    if (selectedRotulo === "__new__") {
      setSelectedRefIds(new Set());
      return;
    }
    setSelectedRefIds((prev) => {
      const valid = new Set(refPdfs.map((r) => r.id));
      if (prev.size > 0) {
        return new Set([...prev].filter((id) => valid.has(id)));
      }
      return valid;
    });
  }, [selectedRotulo, refPdfs]);

  const loadCasePdfs = useCallback(async () => {
    if (!caseId) return;
    try {
      const evs = await listCaseEvidences(caseId);
      const pdfs = filterForensicAuthEvidences(evs).filter((e) => e.file_type === "pdf");
      setCasePdfs(pdfs);
      setSelectedQuestIds((prev) => {
        const valid = new Set(pdfs.map((p) => p.id));
        return new Set([...prev].filter((id) => valid.has(id)));
      });
    } catch {
      setCasePdfs([]);
    }
  }, [caseId]);

  useEffect(() => {
    loadRefGroups();
    loadCasePdfs();
  }, [loadRefGroups, loadCasePdfs]);

  useEffect(
    () => () => {
      if (jaccardUrl) URL.revokeObjectURL(jaccardUrl);
      if (wlUrl) URL.revokeObjectURL(wlUrl);
    },
    [jaccardUrl, wlUrl]
  );

  function clearResults() {
    reset();
    if (jaccardUrl) URL.revokeObjectURL(jaccardUrl);
    if (wlUrl) URL.revokeObjectURL(wlUrl);
    setJaccardUrl(null);
    setWlUrl(null);
    setSaveMessage(null);
  }

  async function handleSaveDerivative(artifactFilename: string, label: string) {
    if (!currentJobId) return;
    setSavingDerivative(artifactFilename);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: artifactFilename,
        label,
      });
      setSaveMessage({
        type: "ok",
        text: `${res.message} «${res.evidence.original_filename}». SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setSaveMessage({ type: "err", text: detail || "Erro ao salvar derivado" });
    } finally {
      setSavingDerivative(null);
    }
  }

  function renderDerivativeActions(
    artifactFilename: string,
    label: string,
    buttonLabel = "Salvar em derivados"
  ) {
    if (!currentJobId) return null;
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
        <button
          type="button"
          onClick={() => handleSaveDerivative(artifactFilename, label)}
          disabled={!!savingDerivative}
          style={btnPrimary}
        >
          {savingDerivative === artifactFilename ? "Salvando…" : buttonLabel}
        </button>
        <button type="button" onClick={() => navigate(`/cases/${caseId}?tab=derivados`)} style={btnSecondary}>
          Abrir derivados
        </button>
      </div>
    );
  }

  async function handleRefUpload(files: FileList | File[]) {
    if (!caseId) return;
    const rotulo = activeRotulo;
    if (!rotulo) {
      setRefUploadMessage({
        type: "err",
        text: "Informe o nome do rotulo antes de enviar os PDFs de referencia.",
      });
      return;
    }
    setUploadingRefs(true);
    setRefUploadMessage(null);
    const list = Array.from(files).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (list.length === 0) {
      setRefUploadMessage({ type: "err", text: "Envie apenas arquivos PDF." });
      setUploadingRefs(false);
      return;
    }

    const uploaded: Evidence[] = [];
    for (const file of list) {
      setUploadProgress((p) => ({ ...p, [file.name]: 0 }));
      try {
        const ev = await uploadPdfStructureReference(caseId, file, rotulo, (pct) => {
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
      setSelectedRefIds((prev) => {
        const next = new Set(prev);
        uploaded.forEach((u) => next.add(u.id));
        return next;
      });
      setRefUploadMessage({
        type: "ok",
        text: `${uploaded.length} PDF(s) no grupo PDF estrutura - ${rotulo} (cadeia de custodia).`,
      });
    }

    setUploadingRefs(false);
  }

  function toggleRef(id: string) {
    setSelectedRefIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleQuest(id: string) {
    setSelectedQuestIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function process() {
    clearResults();
    setSaveMessage(null);
    const questIds = [...selectedQuestIds];
    try {
    if (tab === "with_reference") {
      const refIds = [...selectedRefIds];
      if (refIds.length === 0 || questIds.length === 0) return;
      const anchor = questIds[0];
      await runAnalysis(
        anchor,
        "pdf_structure_similarity",
        {
          mode: "with_reference",
          case_id: caseId,
          reference_evidence_ids: refIds,
          questioned_evidence_ids: questIds,
        },
        {
          onArtifactsLoaded: async (jobId) => {
            const j = await fetchImage(jobId, "similarity_jaccard.png");
            const w = await fetchImage(jobId, "similarity_wl_kernel.png");
            if (jaccardUrl) URL.revokeObjectURL(jaccardUrl);
            if (wlUrl) URL.revokeObjectURL(wlUrl);
            setJaccardUrl(j);
            setWlUrl(w);
          },
        }
      );
    } else {
      if (questIds.length < 2) return;
      await runAnalysis(
        questIds[0],
        "pdf_structure_similarity",
        {
          mode: "all_pairs",
          case_id: caseId,
          questioned_evidence_ids: questIds,
        },
        {
          onArtifactsLoaded: async (jobId) => {
            const j = await fetchImage(jobId, "similarity_jaccard.png");
            const w = await fetchImage(jobId, "similarity_wl_kernel.png");
            if (jaccardUrl) URL.revokeObjectURL(jaccardUrl);
            if (wlUrl) URL.revokeObjectURL(wlUrl);
            setJaccardUrl(j);
            setWlUrl(w);
          },
        }
      );
    }
    } catch {
      /* hook */
    }
  }

  const canProcess =
    tab === "with_reference"
      ? selectedRefIds.size > 0 && selectedQuestIds.size > 0
      : selectedQuestIds.size >= 2;

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="PDF — Similaridade estrutural (grafos)"
      subtitle="Matriz de similaridade Jaccard e kernel WL entre estruturas de objetos PDF."
    >
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={() => {
            setTab("with_reference");
            clearResults();
          }}
          style={tab === "with_reference" ? tabActive : tabIdle}
        >
          Com referencia
        </button>
        <button
          type="button"
          onClick={() => {
            setTab("all_pairs");
            clearResults();
          }}
          style={tab === "all_pairs" ? tabActive : tabIdle}
        >
          Sem referencia (todas x todas)
        </button>
      </div>

      {tab === "with_reference" && (
        <AnalysisPanel title="Referencias PDF (por rotulo)">
          <p style={hintStyle}>
            Envie PDFs de referencia agrupados por rotulo (como PRNU). O grupo ativo define quais entram na matriz.
          </p>
          <RotuloPicker
            rotuloOptions={rotuloOptions}
            selectedRotulo={selectedRotulo}
            newRotulo={newRotulo}
            onRotuloChange={(v) => {
              setSelectedRotulo(v);
              setSelectedRefIds(new Set());
              setRefUploadMessage(null);
            }}
            onNewRotuloChange={(v) => {
              setNewRotulo(v);
              setRefUploadMessage(null);
            }}
            prefix="PDF estrutura"
          />
          <EvidenceDropZone
            inputId="pdf-struct-ref-upload"
            accept="application/pdf,.pdf"
            multiple
            uploading={uploadingRefs}
            disabled={selectedRotulo === "__new__" && !newRotulo.trim()}
            hint="Clique ou arraste PDFs de referencia"
            subHint={
              activeRotulo
                ? `Grupo: PDF estrutura - ${activeRotulo}`
                : "Informe o nome do rotulo acima antes de enviar arquivos"
            }
            onFiles={handleRefUpload}
          />
          {refUploadMessage && <MessageBox type={refUploadMessage.type} text={refUploadMessage.text} />}
          {Object.keys(uploadProgress).length > 0 && (
            <UploadProgressList progress={uploadProgress} />
          )}
          <ReferenceFileList
            items={refPdfs}
            selectedIds={selectedRefIds}
            viewMode={refViewMode}
            onViewModeChange={setRefViewMode}
            onToggle={toggleRef}
            onSelectAll={() => setSelectedRefIds(new Set(refPdfs.map((r) => r.id)))}
            onClear={() => setSelectedRefIds(new Set())}
            activeLabel={activeRotulo}
          />
        </AnalysisPanel>
      )}

      <AnalysisPanel title={tab === "with_reference" ? "Evidencias PDF questionadas" : "Evidencias PDF"}>
        <p style={hintStyle}>
          {tab === "with_reference"
            ? "Selecione os PDFs do caso a comparar com o grupo de referencia ativo."
            : "Selecione ao menos 2 PDFs; a matriz compara todos contra todos."}
        </p>
        <QuestionedFileList
          items={casePdfs}
          selectedIds={selectedQuestIds}
          viewMode={questViewMode}
          onViewModeChange={setQuestViewMode}
          onToggle={toggleQuest}
          onSelectAll={() => setSelectedQuestIds(new Set(casePdfs.map((p) => p.id)))}
          onClear={() => setSelectedQuestIds(new Set())}
        />
        <PeritusMultiFilePicker
          caseId={caseId!}
          fileType="pdf"
          selectedEvidenceIds={selectedQuestIds}
          onToggleEvidenceId={toggleQuest}
        />
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!canProcess}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Calcular matrizes"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Resultado">
          <p style={{ margin: 0, fontSize: "0.88rem" }}>
            Modo: {String(result.mode)} · Referencias: {Number(result.reference_count)} · Questionados:{" "}
            {Number(result.questioned_count)}
          </p>
        </AnalysisPanel>
      )}

      {jaccardUrl && (
        <AnalysisPanel title="Matriz Jaccard">
          <img src={jaccardUrl} alt="Matriz Jaccard" style={{ width: "100%", maxWidth: 1100 }} />
          {renderDerivativeActions(
            "similarity_jaccard.png",
            "pdf_structure_similarity_jaccard",
            "Salvar matriz Jaccard em derivados"
          )}
        </AnalysisPanel>
      )}
      {wlUrl && (
        <AnalysisPanel title="Matriz WL (kernel normalizado)">
          <img src={wlUrl} alt="Matriz WL" style={{ width: "100%", maxWidth: 1100 }} />
          {renderDerivativeActions(
            "similarity_wl_kernel.png",
            "pdf_structure_similarity_wl",
            "Salvar matriz WL em derivados"
          )}
        </AnalysisPanel>
      )}

      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
    </AnalysisPageShell>
  );
}

function RotuloPicker({
  rotuloOptions,
  selectedRotulo,
  newRotulo,
  onRotuloChange,
  onNewRotuloChange,
  prefix,
}: {
  rotuloOptions: string[];
  selectedRotulo: string;
  newRotulo: string;
  onRotuloChange: (v: string) => void;
  onNewRotuloChange: (v: string) => void;
  prefix: string;
}) {
  return (
    <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-end", marginBottom: "1rem" }}>
      <label style={fieldStyle}>
        Rotulo do grupo
        <select value={selectedRotulo} onChange={(e) => onRotuloChange(e.target.value)} style={{ ...inputStyle, minWidth: 200 }}>
          {rotuloOptions.map((r) => (
            <option key={r} value={r}>
              {prefix} - {r}
            </option>
          ))}
          <option value="__new__">+ Novo rotulo…</option>
        </select>
      </label>
      {selectedRotulo === "__new__" && (
        <label style={fieldStyle}>
          Novo rotulo
          <input
            type="text"
            value={newRotulo}
            onChange={(e) => onNewRotuloChange(e.target.value)}
            placeholder="Ex.: Lote_A, Fabricante_X"
            style={inputStyle}
          />
        </label>
      )}
    </div>
  );
}

function UploadProgressList({ progress }: { progress: Record<string, number> }) {
  return (
    <div style={{ marginTop: "0.75rem" }}>
      {Object.entries(progress).map(([name, pct]) => (
        <div key={name} style={{ fontSize: "0.8rem", color: "#374151", marginBottom: 4 }}>
          {name}: {pct}%
        </div>
      ))}
    </div>
  );
}

function ReferenceFileList({
  items,
  selectedIds,
  viewMode,
  onViewModeChange,
  onToggle,
  onSelectAll,
  onClear,
  activeLabel,
}: {
  items: Evidence[];
  selectedIds: Set<string>;
  viewMode: "list" | "grid";
  onViewModeChange: (m: "list" | "grid") => void;
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
  activeLabel: string;
}) {
  if (items.length === 0) return null;
  return (
    <div style={{ marginTop: "1rem" }}>
      <FileListViewHeader viewMode={viewMode} onViewModeChange={onViewModeChange}>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button type="button" onClick={onSelectAll} style={btnSmall}>
            Marcar todas
          </button>
          <button type="button" onClick={onClear} style={btnSmall}>
            Desmarcar
          </button>
          <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
            {selectedIds.size} de {items.length} · grupo {activeLabel || "?"}
          </span>
        </div>
      </FileListViewHeader>
      {viewMode === "grid" ? (
        <EvidenceFileGrid
          items={items}
          selected={(ev) => selectedIds.has(ev.id)}
          onSelect={(ev) => onToggle(ev.id)}
          maxHeight={prnuRefListMaxHeight}
          thumbSize={56}
        />
      ) : (
        <PdfCheckboxList items={items} selectedIds={selectedIds} onToggle={onToggle} maxHeight={prnuRefListMaxHeight} />
      )}
    </div>
  );
}

function QuestionedFileList({
  items,
  selectedIds,
  viewMode,
  onViewModeChange,
  onToggle,
  onSelectAll,
  onClear,
}: {
  items: Evidence[];
  selectedIds: Set<string>;
  viewMode: "list" | "grid";
  onViewModeChange: (m: "list" | "grid") => void;
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  if (items.length === 0) {
    return <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Nenhum PDF no caso.</p>;
  }
  return (
    <>
      <FileListViewHeader viewMode={viewMode} onViewModeChange={onViewModeChange}>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button type="button" onClick={onSelectAll} style={btnSmall}>
            Marcar todas
          </button>
          <button type="button" onClick={onClear} style={btnSmall}>
            Desmarcar
          </button>
          <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
            {selectedIds.size} de {items.length} selecionada(s)
          </span>
        </div>
      </FileListViewHeader>
      {viewMode === "grid" ? (
        <EvidenceFileGrid
          items={items}
          selected={(ev) => selectedIds.has(ev.id)}
          onSelect={(ev) => onToggle(ev.id)}
          maxHeight={imageSelectorListMaxHeight}
          thumbSize={64}
        />
      ) : (
        <PdfCheckboxList items={items} selectedIds={selectedIds} onToggle={onToggle} maxHeight={imageSelectorListMaxHeight} />
      )}
    </>
  );
}

function PdfCheckboxList({
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
    <div
      style={{
        ...scrollableListStyle,
        maxHeight,
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        padding: 8,
      }}
    >
      {items.map((ev) => (
        <label
          key={ev.id}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontSize: "0.85rem",
            marginBottom: 8,
            cursor: "pointer",
            background: selectedIds.has(ev.id) ? "#eff6ff" : "transparent",
            padding: "4px 6px",
            borderRadius: 4,
          }}
        >
          <input type="checkbox" checked={selectedIds.has(ev.id)} onChange={() => onToggle(ev.id)} />
          <EvidenceFilePreview evidenceId={ev.id} fileType={ev.file_type} size={40} />
          <span>{ev.original_filename}</span>
        </label>
      ))}
    </div>
  );
}

const hintStyle = { fontSize: "0.82rem", color: "#6b7280", marginTop: 0 } as const;
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

const btnSecondary = {
  padding: "0.45rem 0.9rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
} as const;

const btnPrimary = {
  padding: "0.45rem 0.9rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
  fontWeight: 500,
} as const;
