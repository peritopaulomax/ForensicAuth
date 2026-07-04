import { useState, useEffect, useRef, useCallback, useMemo, type CSSProperties } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  closeCase,
  getCase,
  getClosureStatus,
  reopenCase,
  type ClosureStatus,
} from "@/services/cases";
import CaseExportVcpModal from "@/components/CaseExportVcpModal";
import CaseExportPeritusModal from "@/components/CaseExportPeritusModal";
import PeritusFilesPanel from "@/components/PeritusFilesPanel";
import { listPeritusFiles, type PeritusFileEntry } from "@/services/peritus";
import { filterPeritusAnalyzable } from "@/lib/peritusAnalysis";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import CaseSharePanel from "@/components/CaseSharePanel";
import { useAuthStore } from "@/store/authStore";
import {
  downloadEvidenceFile,
  listCaseEvidences,
  listCaseDerivatives,
  listCaseReferences,
  listCaseAudioMetadata,
  uploadEvidence,
} from "@/services/evidence";
import CaseAnalysisPanels from "@/components/CaseAnalysisPanels";
import CustodyPanel from "@/components/CustodyPanel";
import DerivativesPanel from "@/components/DerivativesPanel";
import CaseReferencesPanel from "@/components/CaseReferencesPanel";
import EvidenceFilePreview from "@/components/EvidenceFilePreview";
import FileListViewHeader from "@/components/FileListViewHeader";
import { fileTypeIcon } from "@/lib/fileTypeIcons";
import { EVIDENCE_TYPE_LABELS, groupEvidencesByType } from "@/lib/evidenceByType";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import api from "@/services/api";
import type { CaseDetail, Evidence, AudioTechnicalMetadata } from "@/types/api";
import {
  audioMetaFromEvidence,
  formatAudioBitDepth,
  formatAudioCodec,
  formatAudioDuration,
  formatAudioSampleRate,
  mergeAudioMeta,
} from "@/lib/audioMetadataFormat";
import { techniqueHasDedicatedPage } from "@/utils/caseAnalysisNav";
import {
  caseEvidenceListMaxHeight,
  fileGridContainerStyle,
  scrollableListStyle,
} from "@/styles/listHeights";

const statusLabels: Record<string, string> = {
  aberto: "Aberto",
  em_andamento: "Aberto",
  fechamento_pendente: "Fechamento pendente",
  fechado: "Fechado",
};

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function uploadFailureMessage(reason: unknown): string {
  const maybeAxios = reason as { response?: { data?: { detail?: string } } };
  return maybeAxios.response?.data?.detail || "Erro ao fazer upload";
}

function matchesUploadedFile(evidence: Evidence, files: File[]): boolean {
  return files.some((file) => (
    evidence.original_filename === file.name && evidence.file_size === file.size
  ));
}

export default function CaseDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const user = useAuthStore((s) => s.user);
  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [showCloseModal, setShowCloseModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showExportPeritusModal, setShowExportPeritusModal] = useState(false);
  const closeExportModal = useCallback(() => setShowExportModal(false), []);
  const closeExportPeritusModal = useCallback(() => setShowExportPeritusModal(false), []);
  const [closing, setClosing] = useState(false);
  const [closureStatus, setClosureStatus] = useState<ClosureStatus | null>(null);
  const [evidences, setEvidences] = useState<Evidence[]>([]);
  const [derivativesCount, setDerivativesCount] = useState(0);
  const [derivativesRefreshKey, setDerivativesRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [dragOver, setDragOver] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [bulkDownloading, setBulkDownloading] = useState(false);
  const [activeTab, setActiveTab] = useState<
    "evidencias" | "peritus_arquivos" | "analises" | "derivados" | "custodia"
  >("evidencias");
  const [peritusFileCount, setPeritusFileCount] = useState(0);
  const [peritusFiles, setPeritusFiles] = useState<PeritusFileEntry[]>([]);
  const [evidenceSubview, setEvidenceSubview] = useState<"lista" | "referencias">("lista");
  const [referencesRefreshKey, setReferencesRefreshKey] = useState(0);
  const [referencesCount, setReferencesCount] = useState(0);
  const [custodyFilterEvidenceId, setCustodyFilterEvidenceId] = useState<string | null>(null);
  const [audioMetaById, setAudioMetaById] = useState<Record<string, AudioTechnicalMetadata>>({});
  const [evidenceViewMode, setEvidenceViewMode] = useFileListViewMode();

  const { types: evidenceTypes, grouped: evidencesByType } = useMemo(
    () => groupEvidencesByType(evidences),
    [evidences]
  );

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (
      tab === "derivados" ||
      tab === "analises" ||
      tab === "custodia" ||
      tab === "evidencias" ||
      tab === "peritus_arquivos"
    ) {
      setActiveTab(tab);
    }
    if (tab === "derivados" && searchParams.get("graph") && caseId) {
      setDerivativesRefreshKey((k) => k + 1);
    }
    const technique = searchParams.get("technique");
    if (tab === "analises" && technique && techniqueHasDedicatedPage(technique)) {
      const next = new URLSearchParams(searchParams);
      next.delete("technique");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const loadAll = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    setError("");
    try {
      const [c, evs, derivatives, refs, closure] = await Promise.all([
        getCase(caseId),
        listCaseEvidences(caseId),
        listCaseDerivatives(caseId),
        listCaseReferences(caseId),
        getClosureStatus(caseId).catch(() => null),
      ]);
      setCaseData(c);
      setClosureStatus(closure);
      setEvidences(filterForensicAuthEvidences(evs));
      setDerivativesCount(derivatives.length);
      setReferencesCount(refs.groups.reduce((n, g) => n + g.files.length, 0));
      if (c.storage_mode === "peritus") {
        listPeritusFiles(caseId)
          .then((listing) => {
            setPeritusFileCount(listing.file_count);
            setPeritusFiles(filterPeritusAnalyzable(listing.files));
          })
          .catch(() => {
            setPeritusFileCount(0);
            setPeritusFiles([]);
          });
      } else {
        setPeritusFileCount(0);
        setPeritusFiles([]);
      }
      if (filterForensicAuthEvidences(evs).some((e) => e.file_type === "audio")) {
        try {
          const items = await listCaseAudioMetadata(caseId);
          const map: Record<string, AudioTechnicalMetadata> = {};
          for (const item of items) map[item.evidence_id] = item;
          setAudioMetaById(map);
        } catch {
          setAudioMetaById({});
        }
      } else {
        setAudioMetaById({});
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao carregar caso");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  function switchTab(tab: "evidencias" | "peritus_arquivos" | "analises" | "derivados" | "custodia") {
    setActiveTab(tab);
    setSearchParams(tab === "evidencias" ? {} : { tab }, { replace: true });
    if (tab === "derivados" && caseId) {
      setDerivativesRefreshKey((k) => k + 1);
      listCaseDerivatives(caseId).then((d) => setDerivativesCount(d.length));
    }
  }

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const isFullyClosed = caseData?.status === "fechado";
  const isClosurePending = caseData?.status === "fechamento_pendente";
  const isLocked = isFullyClosed || isClosurePending;
  const isPeritusCase = caseData?.storage_mode === "peritus";
  const canManageCase =
    user &&
    (user.role === "admin" || (caseData && caseData.created_by === user.id));
  const canSignClosure =
    closureStatus?.current_user_must_sign ||
    closureStatus?.current_user_can_initiate;
  const closeButtonLabel = closureStatus?.current_user_must_sign
    ? "Assinar fechamento"
    : closureStatus?.closure_pending
      ? "Assinar fechamento"
      : "Fechar caso";

  async function handleCloseCase() {
    if (!caseId) return;
    setClosing(true);
    try {
      const result = await closeCase(caseId, "system");
      setClosureStatus(result.closure_status);
      await loadAll();
      setShowCloseModal(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao fechar caso");
    } finally {
      setClosing(false);
    }
  }

  async function handleReopenCase() {
    if (!caseId || !confirm("Reabrir este caso para novas alteracoes?")) return;
    try {
      await reopenCase(caseId);
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao reabrir caso");
    }
  }

  async function handleUploadFiles(files: FileList | null) {
    if (!files || !caseId || isLocked) return;
    const fileArray = Array.from(files);
    const previousEvidenceIds = new Set(evidences.map((evidence) => evidence.id));
    setUploading(true);
    setError("");
    const newProgress: Record<string, number> = {};
    fileArray.forEach((f) => (newProgress[f.name] = 0));
    setUploadProgress(newProgress);

    try {
      const settled = await Promise.allSettled(
        fileArray.map(async (file) => {
          const ev = await uploadEvidence(caseId, file, (percent) => {
            setUploadProgress((prev) => ({ ...prev, [file.name]: percent }));
          });
          return { file, evidence: ev };
        })
      );
      const successful = settled
        .filter((item): item is PromiseFulfilledResult<{ file: File; evidence: Evidence }> => (
          item.status === "fulfilled"
        ))
        .map((item) => item.value);
      const failed = settled.filter((item): item is PromiseRejectedResult => item.status === "rejected");

      if (successful.length > 0) {
        setEvidences((prev) => [...successful.map((item) => item.evidence), ...prev]);
      }

      if (failed.length === 0) {
        setError("");
      } else if (successful.length > 0) {
        setError(
          `${successful.length} arquivo(s) enviado(s), ${failed.length} falharam. ` +
            uploadFailureMessage(failed[0].reason)
        );
      } else {
        const latest = filterForensicAuthEvidences(await listCaseEvidences(caseId));
        const recovered = latest.filter((evidence) => (
          !previousEvidenceIds.has(evidence.id) && matchesUploadedFile(evidence, fileArray)
        ));
        setEvidences(latest);
        setError(recovered.length > 0 ? "" : uploadFailureMessage(failed[0].reason));
      }
    } catch (err: unknown) {
      setError(uploadFailureMessage(err));
    } finally {
      setUploading(false);
      setUploadProgress({});
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    handleUploadFiles(e.dataTransfer.files);
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedIds.size === evidences.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(evidences.map((e) => e.id)));
    }
  }

  async function handleDeleteSelected() {
    if (!confirm(`Excluir ${selectedIds.size} evidencia(s)?`)) return;
    try {
      for (const id of selectedIds) {
        await api.delete(`/evidences/${id}`);
      }
      setEvidences((prev) => prev.filter((e) => !selectedIds.has(e.id)));
      setSelectedIds(new Set());
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao excluir");
    }
  }

  async function handleDownloadEvidence(ev: Evidence) {
    setDownloadingId(ev.id);
    setError("");
    try {
      await downloadEvidenceFile(ev.id, ev.original_filename);
    } catch {
      setError(`Erro ao baixar "${ev.original_filename}"`);
    } finally {
      setDownloadingId(null);
    }
  }

  async function handleDownloadSelected() {
    const selected = evidences.filter((e) => selectedIds.has(e.id));
    if (selected.length === 0) return;
    setBulkDownloading(true);
    setError("");
    try {
      for (const ev of selected) {
        await downloadEvidenceFile(ev.id, ev.original_filename);
      }
    } catch {
      setError("Erro ao baixar uma ou mais evidencias selecionadas");
    } finally {
      setBulkDownloading(false);
    }
  }

  if (loading) {
    return (
      <div style={{ padding: "2rem" }}>
        <p style={{ color: "#666" }}>Carregando...</p>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div style={{ padding: "2rem" }}>
        <p style={{ color: "#666" }}>Caso nao encontrado.</p>
        <button
          onClick={() => navigate("/")}
          style={{
            marginTop: "1rem",
            padding: "0.5rem 1rem",
            background: "#1a1a2e",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Voltar
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: "2rem" }}>
      {/* Header do Caso */}
      <div style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
          <button
            onClick={() => navigate("/")}
            style={{
              background: "none",
              border: "none",
              color: "#6b7280",
              cursor: "pointer",
              fontSize: "0.9rem",
              padding: 0,
            }}
          >
            ← Voltar
          </button>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div>
            <h1 style={{ margin: "0 0 0.4rem 0", fontSize: "1.6rem", color: "#1a1a2e" }}>
              {caseData.title}
            </h1>
            <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", color: "#6b7280", fontSize: "0.85rem" }}>
              <span>Protocolo: <strong style={{ color: "#374151" }}>{caseData.protocol_number}</strong></span>
              {caseData.inquiry_number && (
                <span>Inquerito: <strong style={{ color: "#374151" }}>{caseData.inquiry_number}</strong></span>
              )}
              {caseData.process_number && (
                <span>Processo: <strong style={{ color: "#374151" }}>{caseData.process_number}</strong></span>
              )}
              <span
                style={{
                  padding: "0.15rem 0.5rem",
                  borderRadius: "4px",
                  background:
                    caseData.status === "aberto"
                      ? "#e0f2fe"
                      : caseData.status === "fechamento_pendente"
                      ? "#ffedd5"
                      : "#fee2e2",
                  color:
                    caseData.status === "aberto"
                      ? "#0369a1"
                      : caseData.status === "fechamento_pendente"
                      ? "#c2410c"
                      : "#991b1b",
                  fontWeight: 600,
                  fontSize: "0.75rem",
                  textTransform: "uppercase",
                }}
              >
                {statusLabels[caseData.status]}
              </span>
              {isPeritusCase && (
                <span
                  style={{
                    padding: "0.15rem 0.5rem",
                    borderRadius: "4px",
                    background: "#eef2ff",
                    color: "#4338ca",
                    fontWeight: 600,
                    fontSize: "0.75rem",
                    textTransform: "uppercase",
                  }}
                >
                  Peritus Desktop
                </span>
              )}
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {!isLocked && (
              <button
                onClick={() => navigate(`/cases/${caseId}/edit`)}
                style={{
                  padding: "0.5rem 1rem",
                  background: "#f3f4f6",
                  color: "#374151",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                }}
              >
                Editar Caso
              </button>
            )}
            <button
              type="button"
              disabled={showExportModal}
              onClick={() => setShowExportModal(true)}
              title="Pacote portavel para outra instancia ForensicAuth"
              style={{
                padding: "0.5rem 1rem",
                background: showExportModal ? "#9ca3af" : "#0f766e",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: showExportModal ? "wait" : "pointer",
                fontSize: "0.85rem",
              }}
            >
              {showExportModal ? "Exportando…" : "Exportar VCP"}
            </button>
            <button
              type="button"
              disabled={showExportPeritusModal}
              onClick={() => setShowExportPeritusModal(true)}
              title={
                isPeritusCase
                  ? "ZIP nativo Peritus (identico ao importado se nao modificado)"
                  : "Gera ZIP legivel pelo Peritus (XML sem assinatura ICP — requer re-assinatura no Peritus)"
              }
              style={{
                padding: "0.5rem 1rem",
                background: showExportPeritusModal ? "#9ca3af" : "#4338ca",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: showExportPeritusModal ? "wait" : "pointer",
                fontSize: "0.85rem",
              }}
            >
              {showExportPeritusModal ? "Exportando…" : "Exportar Peritus"}
            </button>
            {canSignClosure && !isFullyClosed && (
              <button
                type="button"
                onClick={() => setShowCloseModal(true)}
                style={{
                  padding: "0.5rem 1rem",
                  background: isClosurePending ? "#c2410c" : "#1a1a2e",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                }}
              >
                {closeButtonLabel}
              </button>
            )}
            {canManageCase && isFullyClosed && (
              <button
                type="button"
                onClick={handleReopenCase}
                style={{
                  padding: "0.5rem 1rem",
                  background: "#fef3c7",
                  color: "#b45309",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                }}
              >
                Reabrir caso
              </button>
            )}
          </div>
        </div>
        {closureStatus && (isClosurePending || closureStatus.required_signers.length > 1) && (
          <div
            style={{
              marginTop: "0.75rem",
              padding: "0.75rem 1rem",
              background: isClosurePending ? "#fff7ed" : "#f0f9ff",
              border: `1px solid ${isClosurePending ? "#fed7aa" : "#bae6fd"}`,
              borderRadius: "8px",
              fontSize: "0.85rem",
              color: isClosurePending ? "#9a3412" : "#0369a1",
            }}
          >
            <strong style={{ display: "block", marginBottom: "0.35rem" }}>
              {isClosurePending ? "Fechamento bilateral em andamento" : "Fechamento bilateral"}
            </strong>
            <p style={{ margin: "0 0 0.5rem", lineHeight: 1.5 }}>{closureStatus.message}</p>
            <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
              {closureStatus.required_signers.map((s) => (
                <li key={s.user_id}>
                  {s.username || s.user_id.slice(0, 8)}
                  {s.is_current_user ? " (voce)" : ""} —{" "}
                  {s.signed ? (
                    <span style={{ color: "#059669", fontWeight: 600 }}>assinado</span>
                  ) : (
                    <span style={{ color: "#b45309", fontWeight: 600 }}>pendente</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {isFullyClosed && (
          <p
            style={{
              marginTop: "0.75rem",
              padding: "0.6rem 1rem",
              background: "#fef2f2",
              color: "#991b1b",
              borderRadius: "6px",
              fontSize: "0.85rem",
            }}
          >
            Caso encerrado — todas as assinaturas obrigatorias registradas. Uploads e derivados
            bloqueados; leitura e verificacao forense permitidas.
          </p>
        )}
        {caseId && (
          <CaseSharePanel
            caseId={caseId}
            canManage={!!canManageCase}
            caseClosed={!!isLocked}
          />
        )}
        {caseData.description && (
          <p style={{ marginTop: "0.75rem", color: "#4b5563", fontSize: "0.9rem", lineHeight: 1.5 }}>
            {caseData.description}
          </p>
        )}
      </div>

      {error && (
        <div
          style={{
            background: "#fee2e2",
            color: "#991b1b",
            padding: "0.75rem 1rem",
            borderRadius: "6px",
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      {/* Abas internas do caso */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "1.5rem",
          borderBottom: "2px solid #e5e7eb",
          paddingBottom: "0.5rem",
        }}
      >
        <button
          data-testid="tab-evidencias"
          onClick={() => switchTab("evidencias")}
          style={{
            padding: "0.6rem 1.2rem",
            background: activeTab === "evidencias" ? "#f3f4f6" : "transparent",
            color: activeTab === "evidencias" ? "#1a1a2e" : "#6b7280",
            border: "none",
            borderRadius: "6px 6px 0 0",
            cursor: "pointer",
            fontSize: "0.95rem",
            fontWeight: activeTab === "evidencias" ? 600 : 500,
            borderBottom: activeTab === "evidencias" ? "2px solid #1a1a2e" : "2px solid transparent",
            marginBottom: "-0.5rem",
          }}
        >
          📁 Evidencias ({evidences.length})
        </button>
        {isPeritusCase && (
          <button
            data-testid="tab-peritus-arquivos"
            onClick={() => switchTab("peritus_arquivos")}
            style={{
              padding: "0.6rem 1.2rem",
              background: activeTab === "peritus_arquivos" ? "#f3f4f6" : "transparent",
              color: activeTab === "peritus_arquivos" ? "#1a1a2e" : "#6b7280",
              border: "none",
              borderRadius: "6px 6px 0 0",
              cursor: "pointer",
              fontSize: "0.95rem",
              fontWeight: activeTab === "peritus_arquivos" ? 600 : 500,
              borderBottom:
                activeTab === "peritus_arquivos" ? "2px solid #4338ca" : "2px solid transparent",
              marginBottom: "-0.5rem",
            }}
          >
            📂 Arquivos Peritus ({peritusFileCount})
          </button>
        )}
        <button
          data-testid="tab-analises"
          onClick={() => switchTab("analises")}
          style={{
            padding: "0.6rem 1.2rem",
            background: activeTab === "analises" ? "#f3f4f6" : "transparent",
            color: activeTab === "analises" ? "#1a1a2e" : "#6b7280",
            border: "none",
            borderRadius: "6px 6px 0 0",
            cursor: "pointer",
            fontSize: "0.95rem",
            fontWeight: activeTab === "analises" ? 600 : 500,
            borderBottom: activeTab === "analises" ? "2px solid #1a1a2e" : "2px solid transparent",
            marginBottom: "-0.5rem",
          }}
        >
          🔬 Análises
        </button>
        <button
          data-testid="tab-derivados"
          onClick={() => switchTab("derivados")}
          style={{
            padding: "0.6rem 1.2rem",
            background: activeTab === "derivados" ? "#f3f4f6" : "transparent",
            color: activeTab === "derivados" ? "#1a1a2e" : "#6b7280",
            border: "none",
            borderRadius: "6px 6px 0 0",
            cursor: "pointer",
            fontSize: "0.95rem",
            fontWeight: activeTab === "derivados" ? 600 : 500,
            borderBottom: activeTab === "derivados" ? "2px solid #1a1a2e" : "2px solid transparent",
            marginBottom: "-0.5rem",
          }}
        >
          📦 Derivados ({derivativesCount})
        </button>
        <button
          data-testid="tab-custodia"
          onClick={() => switchTab("custodia")}
          style={{
            padding: "0.6rem 1.2rem",
            background: activeTab === "custodia" ? "#f3f4f6" : "transparent",
            color: activeTab === "custodia" ? "#1a1a2e" : "#6b7280",
            border: "none",
            borderRadius: "6px 6px 0 0",
            cursor: "pointer",
            fontSize: "0.95rem",
            fontWeight: activeTab === "custodia" ? 600 : 500,
            borderBottom: activeTab === "custodia" ? "2px solid #1a1a2e" : "2px solid transparent",
            marginBottom: "-0.5rem",
          }}
        >
          🔗 Cadeia de Custodia
        </button>
      </div>

      {activeTab === "evidencias" ? (
        <>
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "1rem",
          borderBottom: "1px solid #e5e7eb",
        }}
      >
        <button
          type="button"
          data-testid="subtab-evidencias-lista"
          onClick={() => setEvidenceSubview("lista")}
          style={{
            padding: "0.45rem 1rem",
            background: evidenceSubview === "lista" ? "#e0f2fe" : "transparent",
            border: "none",
            borderBottom: evidenceSubview === "lista" ? "2px solid #0369a1" : "2px solid transparent",
            cursor: "pointer",
            fontSize: "0.88rem",
            fontWeight: evidenceSubview === "lista" ? 600 : 500,
            color: evidenceSubview === "lista" ? "#0369a1" : "#6b7280",
          }}
        >
          Evidencias ({evidences.length})
        </button>
        <button
          type="button"
          data-testid="subtab-evidencias-referencias"
          onClick={() => {
            setEvidenceSubview("referencias");
            setReferencesRefreshKey((k) => k + 1);
          }}
          style={{
            padding: "0.45rem 1rem",
            background: evidenceSubview === "referencias" ? "#e0f2fe" : "transparent",
            border: "none",
            borderBottom: evidenceSubview === "referencias" ? "2px solid #0369a1" : "2px solid transparent",
            cursor: "pointer",
            fontSize: "0.88rem",
            fontWeight: evidenceSubview === "referencias" ? 600 : 500,
            color: evidenceSubview === "referencias" ? "#0369a1" : "#6b7280",
          }}
        >
          Referencias ({referencesCount})
        </button>
      </div>

      {evidenceSubview === "referencias" ? (
        <CaseReferencesPanel caseId={caseId!} refreshKey={referencesRefreshKey} />
      ) : (
        <>
      {/* Area de Upload */}
      <div style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "1.15rem", color: "#1a1a2e", marginBottom: "0.75rem" }}>
          Evidencias do caso
        </h2>
        {!isLocked ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            style={{
              border: `2px dashed ${dragOver ? "#1a1a2e" : "#d1d5db"}`,
              borderRadius: "8px",
              padding: "1.5rem",
              textAlign: "center",
              background: dragOver ? "#f9fafb" : "#fff",
              transition: "all 0.15s ease",
              cursor: "pointer",
            }}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              style={{ display: "none" }}
              onChange={(e) => handleUploadFiles(e.target.files)}
            />
            <div style={{ fontSize: "1.5rem", marginBottom: "0.4rem" }}>📁</div>
            <p style={{ margin: "0 0 0.25rem 0", color: "#374151", fontSize: "0.9rem" }}>
              <strong>Clique para selecionar</strong> ou arraste arquivos aqui
            </p>
            <p style={{ margin: 0, color: "#9ca3af", fontSize: "0.75rem" }}>
              Imagens, audio, video e PDF. Limite 500MB por arquivo.
            </p>
          </div>
        ) : (
          <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>
            {isClosurePending
              ? "Upload desabilitado — aguardando assinaturas de fechamento."
              : "Upload desabilitado — caso encerrado."}
          </p>
        )}
      </div>

      {/* Progresso de Upload */}
      {uploading && Object.keys(uploadProgress).length > 0 && (
        <div style={{ marginBottom: "1.5rem" }}>
          {Object.entries(uploadProgress).map(([name, percent]) => (
            <div key={name} style={{ marginBottom: "0.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "#374151", marginBottom: "0.2rem" }}>
                <span>{name}</span>
                <span>{percent}%</span>
              </div>
              <div style={{ width: "100%", height: "6px", background: "#e5e7eb", borderRadius: "3px", overflow: "hidden" }}>
                <div
                  style={{
                    width: `${percent}%`,
                    height: "100%",
                    background: "#1a1a2e",
                    transition: "width 0.2s ease",
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Toolbar da lista */}
      {evidences.length > 0 && (
        <FileListViewHeader
          viewMode={evidenceViewMode}
          onViewModeChange={setEvidenceViewMode}
          style={{ marginBottom: "0.5rem" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <input
              type="checkbox"
              checked={selectedIds.size === evidences.length && evidences.length > 0}
              onChange={toggleSelectAll}
              style={{ cursor: "pointer" }}
            />
            <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
              {selectedIds.size > 0 ? `${selectedIds.size} selecionada(s)` : `${evidences.length} arquivo(s)`}
            </span>
            {selectedIds.size > 0 && (
              <>
                <button
                  type="button"
                  onClick={handleDownloadSelected}
                  disabled={bulkDownloading}
                  style={{
                    padding: "0.35rem 0.75rem",
                    background: "#e0f2fe",
                    color: "#0369a1",
                    border: "none",
                    borderRadius: "4px",
                    cursor: bulkDownloading ? "wait" : "pointer",
                    fontSize: "0.8rem",
                    fontWeight: 500,
                    opacity: bulkDownloading ? 0.7 : 1,
                  }}
                >
                  {bulkDownloading ? "Baixando…" : "⬇️ Baixar selecionadas"}
                </button>
                <button
                  type="button"
                  onClick={handleDeleteSelected}
                  style={{
                    padding: "0.35rem 0.75rem",
                    background: "#fee2e2",
                    color: "#991b1b",
                    border: "none",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontSize: "0.8rem",
                    fontWeight: 500,
                  }}
                >
                  🗑️ Excluir selecionadas
                </button>
              </>
            )}
          </div>
        </FileListViewHeader>
      )}

      {/* Lista de Evidencias estilo gerenciador */}
      {evidences.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "3rem",
            color: "#9ca3af",
            border: "1px dashed #e5e7eb",
            borderRadius: "8px",
          }}
        >
          <p style={{ margin: 0 }}>Nenhuma evidencia adicionada ainda.</p>
        </div>
      ) : evidenceViewMode === "grid" ? (
        <div>
          {evidenceTypes.map((fileType) => (
            <section key={fileType} style={{ marginBottom: "1.5rem" }}>
              <h3
                style={{
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  color: "#374151",
                  marginBottom: "0.6rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                }}
              >
                {fileTypeIcon(fileType)} {EVIDENCE_TYPE_LABELS[fileType] || fileType} (
                {evidencesByType[fileType].length})
              </h3>
              <div
                style={{
                  border: "1px solid #e5e7eb",
                  borderRadius: 8,
                  padding: "0.75rem",
                  background: "#fff",
                  ...scrollableListStyle,
                  maxHeight: 420,
                  ...fileGridContainerStyle,
                }}
              >
          {evidencesByType[fileType].map((ev) => {
            const audioMeta =
              ev.file_type === "audio"
                ? mergeAudioMeta(audioMetaById[ev.id], audioMetaFromEvidence(ev.extra_metadata))
                : null;
            return (
              <div
                key={ev.id}
                role="button"
                tabIndex={0}
                onClick={() => toggleSelect(ev.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggleSelect(ev.id);
                  }
                }}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.35rem",
                  padding: "0.6rem",
                  border: `1px solid ${selectedIds.has(ev.id) ? "#7dd3fc" : "#e5e7eb"}`,
                  borderRadius: 8,
                  background: selectedIds.has(ev.id) ? "#eff6ff" : "#fff",
                  cursor: "pointer",
                  minWidth: 0,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(ev.id)}
                    onChange={() => toggleSelect(ev.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div style={{ display: "flex", gap: "0.25rem" }}>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDownloadEvidence(ev);
                      }}
                      disabled={downloadingId === ev.id || bulkDownloading}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: downloadingId === ev.id ? "wait" : "pointer",
                        fontSize: "0.75rem",
                        padding: 0,
                        color: "#0369a1",
                        opacity: downloadingId === ev.id ? 0.6 : 1,
                      }}
                      title="Baixar evidencia"
                    >
                      {downloadingId === ev.id ? "…" : "⬇️"}
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setCustodyFilterEvidenceId(ev.id);
                        switchTab("custodia");
                      }}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        fontSize: "0.68rem",
                        color: "#1a1a2e",
                        textDecoration: "underline",
                        padding: 0,
                      }}
                      title="Ver cadeia de custodia"
                    >
                      Custodia
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Excluir "${ev.original_filename}"?`)) {
                          api.delete(`/evidences/${ev.id}`).then(() => {
                            setEvidences((prev) => prev.filter((x) => x.id !== ev.id));
                            setSelectedIds((prev) => {
                              const next = new Set(prev);
                              next.delete(ev.id);
                              return next;
                            });
                          }).catch(() => setError("Erro ao excluir"));
                        }
                      }}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
                      title="Excluir"
                    >
                      🗑️
                    </button>
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    minHeight: 72,
                    background: "#f9fafb",
                    borderRadius: 6,
                  }}
                >
                  <EvidenceFilePreview
                    evidenceId={ev.id}
                    fileType={ev.file_type}
                    filename={ev.original_filename}
                    size={72}
                    showPlayBadge={ev.file_type === "video"}
                  />
                </div>
                <span
                  style={{
                    fontSize: "0.78rem",
                    fontWeight: 500,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={ev.original_filename}
                >
                  {ev.original_filename}
                </span>
                <span style={{ fontSize: "0.72rem", color: "#6b7280", textTransform: "capitalize" }}>
                  {ev.file_type} · {formatBytes(ev.file_size)}
                </span>
                {audioMeta && (
                  <span style={{ fontSize: "0.68rem", color: "#9ca3af" }}>
                    {formatAudioSampleRate(audioMeta.sample_rate_hz ?? null)} ·{" "}
                    {formatAudioDuration(audioMeta.duration_sec ?? null)}
                  </span>
                )}
              </div>
            );
          })}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div>
          {evidenceTypes.map((fileType) => {
            const sectionEvs = evidencesByType[fileType];
            const isAudioSection = fileType === "audio";
            const evidenceGridColumns = isAudioSection
              ? "40px minmax(120px, 1.3fr) 72px 88px 80px 68px minmax(70px, 0.9fr) 72px 130px 76px 72px"
              : "40px 1.8fr 100px 100px 140px 80px 76px 72px";
            const metaCell: CSSProperties = {
              fontSize: "0.8rem",
              color: "#6b7280",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            };

            return (
              <section key={fileType} style={{ marginBottom: "1.5rem" }}>
                <h3
                  style={{
                    fontSize: "0.85rem",
                    fontWeight: 600,
                    color: "#374151",
                    marginBottom: "0.6rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.03em",
                  }}
                >
                  {fileTypeIcon(fileType)} {EVIDENCE_TYPE_LABELS[fileType] || fileType} (
                  {sectionEvs.length})
                </h3>
                <div
                  style={{
                    border: "1px solid #e5e7eb",
                    borderRadius: "8px",
                    overflow: "hidden",
                    background: "#fff",
                  }}
                >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: evidenceGridColumns,
              gap: "0.5rem",
              padding: "0.6rem 1rem",
              background: "#f9fafb",
              borderBottom: "1px solid #e5e7eb",
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.03em",
            }}
          >
            <span></span>
            <span>Nome</span>
            <span>Tipo</span>
            {isAudioSection && (
              <>
                <span>Taxa</span>
                <span>Duração</span>
                <span>Bits</span>
                <span>Codec</span>
              </>
            )}
            <span>Tamanho</span>
            <span>SHA-256</span>
            <span>Rastreio</span>
            <span></span>
          </div>

          <div
            style={{
              ...scrollableListStyle,
              maxHeight: caseEvidenceListMaxHeight,
            }}
          >
          {sectionEvs.map((ev) => {
            const audioMeta =
              ev.file_type === "audio"
                ? mergeAudioMeta(audioMetaById[ev.id], audioMetaFromEvidence(ev.extra_metadata))
                : null;
            return (
            <div
              key={ev.id}
              style={{
                display: "grid",
                gridTemplateColumns: evidenceGridColumns,
                gap: "0.5rem",
                padding: "0.6rem 1rem",
                alignItems: "center",
                borderBottom: "1px solid #f3f4f6",
                background: selectedIds.has(ev.id) ? "#eff6ff" : "transparent",
                transition: "background 0.1s",
              }}
              onClick={() => toggleSelect(ev.id)}
            >
              <input
                type="checkbox"
                checked={selectedIds.has(ev.id)}
                onChange={() => toggleSelect(ev.id)}
                onClick={(e) => e.stopPropagation()}
                style={{ cursor: "pointer" }}
              />
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
                <EvidenceFilePreview
                  evidenceId={ev.id}
                  fileType={ev.file_type}
                  filename={ev.original_filename}
                  size={48}
                  showPlayBadge={ev.file_type === "video"}
                />
                <span
                  style={{
                    fontSize: "0.85rem",
                    color: "#1a1a2e",
                    fontWeight: 500,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={ev.original_filename}
                >
                  {ev.original_filename}
                </span>
              </div>
              <span style={{ fontSize: "0.8rem", color: "#6b7280", textTransform: "capitalize" }}>
                {ev.file_type}
              </span>
              {isAudioSection && (
                <>
                  <span style={metaCell} title={audioMeta ? formatAudioSampleRate(audioMeta.sample_rate_hz ?? null) : undefined}>
                    {audioMeta ? formatAudioSampleRate(audioMeta.sample_rate_hz ?? null) : "—"}
                  </span>
                  <span style={metaCell} title={audioMeta ? formatAudioDuration(audioMeta.duration_sec ?? null) : undefined}>
                    {audioMeta ? formatAudioDuration(audioMeta.duration_sec ?? null) : "—"}
                  </span>
                  <span style={metaCell}>
                    {audioMeta ? formatAudioBitDepth(audioMeta.bit_depth ?? null) : "—"}
                  </span>
                  <span style={metaCell} title={audioMeta ? formatAudioCodec(audioMeta.codec ?? null) : undefined}>
                    {audioMeta ? formatAudioCodec(audioMeta.codec ?? null) : "—"}
                  </span>
                </>
              )}
              <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>{formatBytes(ev.file_size)}</span>
              <span
                style={{
                  fontSize: "0.7rem",
                  color: "#9ca3af",
                  fontFamily: "monospace",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={ev.sha256}
              >
                {ev.sha256.slice(0, 16)}...
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setCustodyFilterEvidenceId(ev.id);
                  switchTab("custodia");
                }}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "0.75rem",
                  padding: "0.2rem",
                  color: "#1a1a2e",
                  textDecoration: "underline",
                }}
                title="Ver cadeia de custodia desta evidencia"
              >
                Ver
              </button>
              <div
                style={{ display: "flex", alignItems: "center", gap: "0.15rem" }}
                onClick={(e) => e.stopPropagation()}
              >
              <button
                type="button"
                onClick={() => void handleDownloadEvidence(ev)}
                disabled={downloadingId === ev.id || bulkDownloading}
                style={{
                  background: "none",
                  border: "none",
                  cursor: downloadingId === ev.id ? "wait" : "pointer",
                  fontSize: "0.75rem",
                  padding: "0.2rem",
                  color: "#0369a1",
                  opacity: downloadingId === ev.id ? 0.6 : 1,
                }}
                title="Baixar evidencia"
              >
                {downloadingId === ev.id ? "…" : "⬇️"}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (confirm(`Excluir "${ev.original_filename}"?`)) {
                    api.delete(`/evidences/${ev.id}`).then(() => {
                      setEvidences((prev) => prev.filter((x) => x.id !== ev.id));
                      setSelectedIds((prev) => {
                        const next = new Set(prev);
                        next.delete(ev.id);
                        return next;
                      });
                    }).catch(() => setError("Erro ao excluir"));
                  }
                }}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "0.9rem",
                  padding: "0.2rem",
                  color: "#9ca3af",
                }}
                title="Excluir"
              >
                🗑️
              </button>
              </div>
            </div>
            );
          })}
          </div>
                </div>
              </section>
            );
          })}
        </div>
      )}
        </>
      )}
        </>
      ) : activeTab === "peritus_arquivos" && caseId ? (
        <PeritusFilesPanel caseId={caseId} />
      ) : activeTab === "analises" ? (
        <CaseAnalysisPanels
          evidences={evidences}
          peritusFiles={peritusFiles}
        />
      ) : activeTab === "derivados" ? (
        <DerivativesPanel
          caseId={caseId!}
          parentEvidences={evidences}
          refreshKey={derivativesRefreshKey}
          initialGraphEvidenceId={searchParams.get("graph")}
        />
      ) : (
        <CustodyPanel
          caseId={caseId!}
          evidences={evidences}
          isPeritusCase={isPeritusCase}
          filterEvidenceId={custodyFilterEvidenceId}
          onClearFilter={() => setCustodyFilterEvidenceId(null)}
        />
      )}

      {caseId && (
        <CaseExportVcpModal
          open={showExportModal}
          caseId={caseId}
          protocolNumber={caseData?.protocol_number}
          onClose={closeExportModal}
        />
      )}

      {caseId && (
        <CaseExportPeritusModal
          open={showExportPeritusModal}
          caseId={caseId}
          protocolNumber={caseData?.protocol_number}
          onClose={closeExportPeritusModal}
        />
      )}

      {showCloseModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.45)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={() => !closing && setShowCloseModal(false)}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: "8px",
              padding: "1.5rem",
              maxWidth: "420px",
              width: "90%",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 0.75rem", color: "#1a1a2e" }}>
              {closureStatus?.current_user_must_sign
                ? "Assinar fechamento do caso"
                : "Iniciar fechamento do caso"}
            </h3>
            <p style={{ fontSize: "0.9rem", color: "#4b5563", marginBottom: "1rem" }}>
              {closureStatus && closureStatus.required_signers.length > 1 ? (
                <>
                  O manifesto forense sera assinado com Ed25519. O caso so encerra definitivamente
                  apos todos os participantes obrigatorios assinarem (
                  {closureStatus.required_signers.map((s) => s.username || "participante").join(", ")}
                  ). Enquanto houver assinatura pendente, uploads e derivados permanecem bloqueados.
                </>
              ) : (
                <>
                  O manifesto forense sera assinado pelo sistema. O caso sera encerrado e uploads
                  e derivados ficarao bloqueados.
                </>
              )}
            </p>
            <fieldset style={{ border: "none", padding: 0, margin: "0 0 1rem" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                <input type="radio" name="sig" defaultChecked />
                Assinatura do sistema (Ed25519)
              </label>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  opacity: 0.5,
                  cursor: "not-allowed",
                }}
                title="Disponivel em versao futura"
              >
                <input type="radio" name="sig" disabled />
                ICP-Brasil (em breve)
              </label>
            </fieldset>
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => setShowCloseModal(false)}
                disabled={closing}
                style={{
                  padding: "0.5rem 1rem",
                  background: "#f3f4f6",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleCloseCase}
                disabled={closing}
                style={{
                  padding: "0.5rem 1rem",
                  background: "#1a1a2e",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  cursor: closing ? "wait" : "pointer",
                }}
              >
                {closing
                  ? "Processando…"
                  : closureStatus?.current_user_must_sign
                    ? "Confirmar assinatura"
                    : "Confirmar fechamento"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
