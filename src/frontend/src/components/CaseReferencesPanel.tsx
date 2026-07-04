import { useCallback, useEffect, useState } from "react";
import EvidenceDropZone from "@/components/EvidenceDropZone";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import EvidenceFilePreview from "@/components/EvidenceFilePreview";
import FileListViewHeader from "@/components/FileListViewHeader";
import api from "@/services/api";
import { downloadEvidenceFile, listCaseReferences, uploadGlobalReference, type GlobalReferenceGroup, type ReferenceGroup } from "@/services/evidence";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import type { Evidence } from "@/types/api";
import { referenceGroupListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

interface Props {
  caseId: string;
  refreshKey?: number;
}

function ReferenceFileActions({ ev, onDeleted }: { ev: Evidence; onDeleted: (id: string) => void }) {
  async function deleteFile(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm(`Excluir referencia "${ev.original_filename}"?`)) return;
    try {
      await api.delete(`/evidences/${ev.id}`);
      onDeleted(ev.id);
    } catch {
      alert("Erro ao excluir referencia");
    }
  }

  async function downloadFile(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await downloadEvidenceFile(ev.id, ev.original_filename);
    } catch {
      alert("Erro ao baixar referencia");
    }
  }

  return (
    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.2rem" }}>
      <button
        type="button"
        onClick={downloadFile}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "#0369a1",
          fontSize: "0.75rem",
          padding: 0,
          textAlign: "left",
        }}
      >
        Baixar
      </button>
      <button
        type="button"
        onClick={deleteFile}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "#991b1b",
          fontSize: "0.75rem",
          padding: 0,
          textAlign: "left",
        }}
      >
        Excluir
      </button>
    </div>
  );
}

function ReferenceGroupList({
  group,
  onDeleted,
  viewMode,
}: {
  group: ReferenceGroup | GlobalReferenceGroup;
  onDeleted: (id: string) => void;
  viewMode: "list" | "grid";
}) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const files = group.files;

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (files.length === 0) return null;

  const isGlobal = "reference_type" in group;
  const subtitle = isGlobal
    ? `Referencias globais do tipo ${(group as GlobalReferenceGroup).reference_type.toUpperCase()}`
    : `Arquivos de referencia para ${(group as ReferenceGroup).technique.toUpperCase()} — registrados na cadeia de custodia, nao sao evidencias do caso.`;

  return (
    <div style={{ marginBottom: "1.75rem" }}>
      <h3 style={{ fontSize: "1rem", color: "#1a1a2e", margin: "0 0 0.25rem" }}>{group.display_label}</h3>
      <p style={{ fontSize: "0.78rem", color: "#6b7280", margin: "0 0 0.75rem" }}>{subtitle}</p>

      {viewMode === "grid" ? (
        <EvidenceFileGrid
          items={files}
          selected={(ev) => selectedIds.has(ev.id)}
          onSelect={(ev) => toggleSelect(ev.id)}
          maxHeight={referenceGroupListMaxHeight}
          renderFooter={(ev) => (
            <>
              <span style={{ fontSize: "0.68rem", color: "#6b7280" }}>{formatBytes(ev.file_size ?? 0)}</span>
              <ReferenceFileActions ev={ev as Evidence} onDeleted={onDeleted} />
            </>
          )}
        />
      ) : (
        <div
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            overflow: "hidden",
            background: "#fff",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "40px 1.8fr 100px 140px 90px",
              gap: "0.5rem",
              padding: "0.6rem 1rem",
              background: "#f9fafb",
              borderBottom: "1px solid #e5e7eb",
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "#6b7280",
              textTransform: "uppercase",
            }}
          >
            <span />
            <span>Nome</span>
            <span>Tamanho</span>
            <span>SHA-256</span>
            <span />
          </div>
          <div
            style={{
              ...scrollableListStyle,
              maxHeight: referenceGroupListMaxHeight,
            }}
          >
            {files.map((ev) => (
              <div
                key={ev.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "40px 1.8fr 100px 140px 90px",
                  gap: "0.5rem",
                  padding: "0.6rem 1rem",
                  alignItems: "center",
                  borderBottom: "1px solid #f3f4f6",
                  background: selectedIds.has(ev.id) ? "#eff6ff" : "transparent",
                }}
                onClick={() => toggleSelect(ev.id)}
              >
                <input
                  type="checkbox"
                  checked={selectedIds.has(ev.id)}
                  onChange={() => toggleSelect(ev.id)}
                  onClick={(e) => e.stopPropagation()}
                />
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
                  <EvidenceFilePreview
                    evidenceId={ev.id}
                    fileType={ev.file_type}
                    filename={ev.original_filename}
                    size={40}
                  />
                  <span
                    style={{
                      fontSize: "0.85rem",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={ev.original_filename}
                  >
                    {ev.original_filename}
                  </span>
                </div>
                <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>{formatBytes(ev.file_size)}</span>
                <span style={{ fontSize: "0.7rem", color: "#9ca3af", fontFamily: "monospace" }}>
                  {ev.sha256.slice(0, 16)}…
                </span>
                <div onClick={(e) => e.stopPropagation()}>
                  <ReferenceFileActions ev={ev as Evidence} onDeleted={onDeleted} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function CaseReferencesPanel({ caseId, refreshKey = 0 }: Props) {
  const [pluginGroups, setPluginGroups] = useState<ReferenceGroup[]>([]);
  const [globalGroups, setGlobalGroups] = useState<GlobalReferenceGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useFileListViewMode();
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [groupLabel, setGroupLabel] = useState("");
  const [referenceType, setReferenceType] = useState<"imagem" | "video" | "audio" | "pdf">("imagem");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listCaseReferences(caseId);
      setPluginGroups(data.groups);
      setGlobalGroups(data.global_groups);
    } catch {
      setPluginGroups([]);
      setGlobalGroups([]);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  function handleDeleted(id: string) {
    setPluginGroups((prev) =>
      prev
        .map((g) => ({ ...g, files: g.files.filter((f) => f.id !== id) }))
        .filter((g) => g.files.length > 0)
    );
    setGlobalGroups((prev) =>
      prev
        .map((g) => ({ ...g, files: g.files.filter((f) => f.id !== id) }))
        .filter((g) => g.files.length > 0)
    );
  }

  async function handleUpload(files: FileList) {
    const label = groupLabel.trim();
    if (!label) {
      setUploadError("Informe um rotulo para o grupo de referencias antes de enviar os arquivos.");
      return;
    }
    const filesArray = Array.from(files);
    if (filesArray.length === 0) return;

    setUploading(true);
    setUploadError(null);
    try {
      for (const file of filesArray) {
        await uploadGlobalReference(caseId, file, label, referenceType);
      }
      setGroupLabel("");
      await load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao enviar referencia";
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  }

  const acceptMap = {
    imagem: "image/*",
    video: "video/*",
    audio: "audio/*",
    pdf: ".pdf,application/pdf",
  };

  if (loading) {
    return <p style={{ color: "#9ca3af", fontSize: "0.9rem" }}>Carregando referencias…</p>;
  }

  return (
    <div>
      <FileListViewHeader viewMode={viewMode} onViewModeChange={setViewMode} style={{ marginBottom: "1rem" }} />

      <div
        style={{
          border: "1px solid #dbeafe",
          borderRadius: 8,
          padding: "1rem",
          background: "#eff6ff",
          marginBottom: "1.5rem",
        }}
      >
        <h3 style={{ fontSize: "0.95rem", color: "#1e3a8a", margin: "0 0 0.75rem" }}>Adicionar referencias globais</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "0.75rem", marginBottom: "0.75rem" }}>
          <label style={{ fontSize: "0.82rem", color: "#374151" }}>
            Rotulo do grupo
            <input
              type="text"
              value={groupLabel}
              onChange={(e) => setGroupLabel(e.target.value)}
              placeholder="Ex.: Cameras de referencia"
              style={{ display: "block", width: "100%", marginTop: 4, padding: "0.35rem 0.5rem", borderRadius: 4, border: "1px solid #d1d5db" }}
            />
          </label>
          <label style={{ fontSize: "0.82rem", color: "#374151" }}>
            Tipo de arquivo
            <select
              value={referenceType}
              onChange={(e) => setReferenceType(e.target.value as "imagem" | "video" | "audio" | "pdf")}
              style={{ display: "block", width: "100%", marginTop: 4, padding: "0.35rem 0.5rem", borderRadius: 4, border: "1px solid #d1d5db" }}
            >
              <option value="imagem">Imagem</option>
              <option value="video">Video</option>
              <option value="audio">Audio</option>
              <option value="pdf">PDF</option>
            </select>
          </label>
        </div>
        <EvidenceDropZone
          inputId="global-reference-upload"
          accept={acceptMap[referenceType]}
          multiple
          disabled={uploading || !groupLabel.trim()}
          uploading={uploading}
          hint={groupLabel.trim() ? "Clique ou arraste arquivos de referencia" : "Informe o rotulo acima para habilitar o upload"}
          subHint={`Somente arquivos do tipo ${referenceType.toUpperCase()} serao aceitos.`}
          onFiles={handleUpload}
        />
        {uploadError && <p style={{ color: "#b91c1c", fontSize: "0.82rem", marginTop: "0.5rem" }}>{uploadError}</p>}
      </div>

      {globalGroups.length > 0 && (
        <div style={{ marginBottom: "2rem" }}>
          <h2 style={{ fontSize: "1.1rem", color: "#111827", margin: "0 0 1rem", borderBottom: "2px solid #0369a1", paddingBottom: "0.35rem" }}>
            Referencias globais
          </h2>
          {globalGroups.map((group) => (
            <ReferenceGroupList key={`global-${group.reference_type}-${group.group_label}`} group={group} onDeleted={handleDeleted} viewMode={viewMode} />
          ))}
        </div>
      )}

      {pluginGroups.length > 0 && (
        <div>
          <h2 style={{ fontSize: "1.1rem", color: "#111827", margin: "0 0 1rem", borderBottom: "2px solid #6b7280", paddingBottom: "0.35rem" }}>
            Referencias de plugins
          </h2>
          {pluginGroups.map((group) => (
            <ReferenceGroupList key={`plugin-${group.technique}-${group.group_label}`} group={group} onDeleted={handleDeleted} viewMode={viewMode} />
          ))}
        </div>
      )}

      {globalGroups.length === 0 && pluginGroups.length === 0 && (
        <div
          style={{
            textAlign: "center",
            padding: "2.5rem",
            color: "#9ca3af",
            border: "1px dashed #e5e7eb",
            borderRadius: 8,
          }}
        >
          <p style={{ margin: 0 }}>Nenhuma referencia cadastrada. Use o formulario acima para enviar referencias globais.</p>
        </div>
      )}
    </div>
  );
}
