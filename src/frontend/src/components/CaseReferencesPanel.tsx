import { useCallback, useEffect, useState } from "react";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import EvidenceFilePreview from "@/components/EvidenceFilePreview";
import FileListViewHeader from "@/components/FileListViewHeader";
import api from "@/services/api";
import { listCaseReferences, type ReferenceGroup } from "@/services/evidence";
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

function ReferenceGroupList({
  group,
  onDeleted,
  viewMode,
}: {
  group: ReferenceGroup;
  onDeleted: (id: string) => void;
  viewMode: "list" | "grid";
}) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function deleteFile(ev: Evidence) {
    if (!confirm(`Excluir referencia "${ev.original_filename}"?`)) return;
    try {
      await api.delete(`/evidences/${ev.id}`);
      onDeleted(ev.id);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(ev.id);
        return next;
      });
    } catch {
      alert("Erro ao excluir referencia");
    }
  }

  if (group.files.length === 0) return null;

  return (
    <div style={{ marginBottom: "1.75rem" }}>
      <h3 style={{ fontSize: "1rem", color: "#1a1a2e", margin: "0 0 0.5rem" }}>{group.display_label}</h3>
      <p style={{ fontSize: "0.78rem", color: "#6b7280", margin: "0 0 0.75rem" }}>
        Arquivos de referencia para {group.technique.toUpperCase()} — registrados na cadeia de custodia, nao sao
        evidencias do caso.
      </p>

      {viewMode === "grid" ? (
        <EvidenceFileGrid
          items={group.files}
          selected={(ev) => selectedIds.has(ev.id)}
          onSelect={(ev) => toggleSelect(ev.id)}
          maxHeight={referenceGroupListMaxHeight}
          renderFooter={(ev) => (
            <>
              <span style={{ fontSize: "0.68rem", color: "#6b7280" }}>{formatBytes(ev.file_size ?? 0)}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteFile(ev as Evidence);
                }}
                style={{
                  marginTop: "0.2rem",
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
              gridTemplateColumns: "40px 1.8fr 100px 140px 50px",
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
            {group.files.map((ev) => (
              <div
                key={ev.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "40px 1.8fr 100px 140px 50px",
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
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteFile(ev as Evidence);
                  }}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af" }}
                  title="Excluir"
                >
                  🗑️
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function CaseReferencesPanel({ caseId, refreshKey = 0 }: Props) {
  const [groups, setGroups] = useState<ReferenceGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useFileListViewMode();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listCaseReferences(caseId);
      setGroups(data.groups);
    } catch {
      setGroups([]);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  function handleDeleted(id: string) {
    setGroups((prev) =>
      prev
        .map((g) => ({ ...g, files: g.files.filter((f) => f.id !== id) }))
        .filter((g) => g.files.length > 0)
    );
  }

  if (loading) {
    return <p style={{ color: "#9ca3af", fontSize: "0.9rem" }}>Carregando referencias…</p>;
  }

  if (groups.length === 0) {
    return (
      <div
        style={{
          textAlign: "center",
          padding: "2.5rem",
          color: "#9ca3af",
          border: "1px dashed #e5e7eb",
          borderRadius: 8,
        }}
      >
        <p style={{ margin: 0 }}>
          Nenhuma referencia cadastrada. Envie padroes PRNU (ou outras tecnicas) nas paginas de analise
          correspondentes.
        </p>
      </div>
    );
  }

  return (
    <div>
      <FileListViewHeader viewMode={viewMode} onViewModeChange={setViewMode} style={{ marginBottom: "1rem" }} />
      {groups.map((group) => (
        <ReferenceGroupList
          key={`${group.technique}-${group.group_label}`}
          group={group}
          onDeleted={handleDeleted}
          viewMode={viewMode}
        />
      ))}
    </div>
  );
}
