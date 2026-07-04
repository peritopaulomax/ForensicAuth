import { useCallback, useEffect, useMemo, useState } from "react";
import {
  downloadPeritusFile,
  listPeritusFiles,
  type PeritusFileEntry,
} from "@/services/peritus";
import PeritusFilePreview from "@/components/PeritusFilePreview";
import FileListViewHeader from "@/components/FileListViewHeader";
import { EVIDENCE_TYPE_LABELS, EVIDENCE_TYPE_ORDER } from "@/lib/evidenceByType";
import { fileTypeIcon } from "@/lib/fileTypeIcons";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import { fileGridContainerStyle, scrollableListStyle } from "@/styles/listHeights";

interface Props {
  caseId: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function groupByType(files: PeritusFileEntry[]): { types: string[]; grouped: Record<string, PeritusFileEntry[]> } {
  const grouped = files.reduce<Record<string, PeritusFileEntry[]>>((acc, f) => {
    const t = f.file_type && f.file_type !== "xml" && f.file_type !== "outros" ? f.file_type : "outros";
    if (!acc[t]) acc[t] = [];
    acc[t].push(f);
    return acc;
  }, {});
  const types = [
    ...EVIDENCE_TYPE_ORDER.filter((t) => grouped[t]?.length),
    ...Object.keys(grouped).filter(
      (t) => !EVIDENCE_TYPE_ORDER.includes(t as (typeof EVIDENCE_TYPE_ORDER)[number]) && t !== "outros"
    ),
    ...(grouped.outros?.length ? ["outros"] : []),
  ];
  return { types, grouped };
}

export default function PeritusFilesPanel({ caseId }: Props) {
  const [files, setFiles] = useState<PeritusFileEntry[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [modified, setModified] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useFileListViewMode();

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listPeritusFiles(caseId);
      setFiles(data.files);
      setFolders(data.folders || []);
      setModified(data.modified);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao listar arquivos Peritus");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const folderBlocks = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = q
      ? files.filter(
          (f) =>
            f.path.toLowerCase().includes(q) ||
            f.filename.toLowerCase().includes(q) ||
            f.folder.toLowerCase().includes(q)
        )
      : files;

    const byFolder = new Map<string, PeritusFileEntry[]>();
    for (const f of filtered) {
      const list = byFolder.get(f.folder) || [];
      list.push(f);
      byFolder.set(f.folder, list);
    }

    const order = folders.length
      ? folders.filter((fo) => byFolder.has(fo))
      : Array.from(byFolder.keys()).sort();

    return order.map((folder) => ({
      folder,
      files: byFolder.get(folder) || [],
      ...groupByType(byFolder.get(folder) || []),
    }));
  }, [files, folders, search]);

  async function handleDownload(path: string) {
    const blob = await downloadPeritusFile(caseId, path);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = path.split("/").pop() || "arquivo";
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return <p style={{ color: "#6b7280" }}>Carregando arquivos Peritus…</p>;
  }

  if (error) {
    return (
      <div style={{ color: "#991b1b", padding: "0.75rem", background: "#fef2f2", borderRadius: "6px" }}>
        {error}
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          marginBottom: "1rem",
          padding: "0.75rem 1rem",
          background: "#eef2ff",
          border: "1px solid #c7d2fe",
          borderRadius: "8px",
          fontSize: "0.85rem",
          color: "#3730a3",
          lineHeight: 1.5,
        }}
      >
        Snapshot forense do pacote importado do <strong>Peritus Desktop</strong> — pastas, derivados e hashes do{" "}
        <strong>peritusCase.xml</strong>. Novos uploads e analises VA ficam nas abas Evidencias,
        Análises e Derivados.
        {modified && (
          <span style={{ color: "#b45309" }}> Caso alterado apos importacao — export Peritus regenera XML.</span>
        )}
      </div>

      <FileListViewHeader viewMode={viewMode} onViewModeChange={setViewMode} style={{ marginBottom: "1rem" }}>
        <input
          type="search"
          placeholder="Buscar arquivo ou pasta…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: "1 1 220px",
            padding: "0.45rem 0.65rem",
            borderRadius: "6px",
            border: "1px solid #ddd",
          }}
        />
      </FileListViewHeader>

      {folderBlocks.map(({ folder, types, grouped }) => (
        <section key={folder} style={{ marginBottom: "2rem" }}>
          <h2
            style={{
              fontSize: "1rem",
              fontWeight: 700,
              color: "#1a1a2e",
              margin: "0 0 1rem",
              paddingBottom: "0.35rem",
              borderBottom: "2px solid #4338ca",
            }}
          >
            📂 {folder}
          </h2>

          {types.map((fileType) => {
            const sectionFiles = grouped[fileType] || [];
            const label =
              fileType === "outros"
                ? "Outros arquivos"
                : EVIDENCE_TYPE_LABELS[fileType] || fileType;

            return (
              <div key={`${folder}-${fileType}`} style={{ marginBottom: "1.25rem" }}>
                <h3
                  style={{
                    fontSize: "0.85rem",
                    fontWeight: 600,
                    color: "#374151",
                    margin: "0 0 0.6rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.03em",
                  }}
                >
                  {fileTypeIcon(fileType)} {label} ({sectionFiles.length})
                </h3>

                {viewMode === "grid" ? (
                  <div style={{ ...fileGridContainerStyle, marginBottom: "0.5rem" }}>
                    {sectionFiles.map((f) => (
                      <div
                        key={f.path}
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.35rem",
                          padding: "0.6rem",
                          border: "1px solid #e5e7eb",
                          borderRadius: 8,
                          background: f.is_derived ? "#f0fdf4" : "#fff",
                        }}
                      >
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
                          {f.is_xml ? (
                            <span style={{ fontSize: "1.5rem" }}>📄</span>
                          ) : (
                            <PeritusFilePreview
                              caseId={caseId}
                              path={f.path}
                              fileType={f.file_type}
                              filename={f.filename}
                              size={72}
                              showPlayBadge={f.file_type === "video"}
                            />
                          )}
                        </div>
                        <span
                          style={{
                            fontSize: "0.78rem",
                            fontWeight: 500,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={f.filename}
                        >
                          {f.filename}
                        </span>
                        <span style={{ fontSize: "0.72rem", color: "#6b7280" }}>
                          {formatBytes(f.size)}
                          {f.is_derived ? " · derivado Peritus" : ""}
                        </span>
                        {f.sha256 && (
                          <span
                            style={{
                              fontSize: "0.65rem",
                              color: "#9ca3af",
                              fontFamily: "monospace",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                            }}
                            title={f.sha256}
                          >
                            {f.sha256.slice(0, 16)}…
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => void handleDownload(f.path)}
                          style={{
                            padding: "0.3rem",
                            fontSize: "0.75rem",
                            background: "#f3f4f6",
                            border: "none",
                            borderRadius: 4,
                            cursor: "pointer",
                          }}
                        >
                          Baixar
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div
                    style={{
                      border: "1px solid #e5e7eb",
                      borderRadius: 8,
                      overflow: "hidden",
                      ...scrollableListStyle,
                      maxHeight: 360,
                    }}
                  >
                    {sectionFiles.map((f) => (
                      <div
                        key={f.path}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "48px 1fr 90px 120px 80px",
                          gap: "0.5rem",
                          padding: "0.55rem 0.75rem",
                          alignItems: "center",
                          borderBottom: "1px solid #f3f4f6",
                          background: f.is_derived ? "#f0fdf4" : "#fff",
                        }}
                      >
                        {f.is_xml ? (
                          <span>📄</span>
                        ) : (
                          <PeritusFilePreview
                            caseId={caseId}
                            path={f.path}
                            fileType={f.file_type}
                            filename={f.filename}
                            size={40}
                          />
                        )}
                        <span style={{ fontSize: "0.82rem" }} title={f.path}>
                          {f.filename}
                        </span>
                        <span style={{ fontSize: "0.8rem", color: "#6b7280", textTransform: "capitalize" }}>
                          {f.file_type}
                        </span>
                        <span style={{ fontSize: "0.75rem", color: "#9ca3af", fontFamily: "monospace" }}>
                          {f.sha256 ? `${f.sha256.slice(0, 12)}…` : "—"}
                        </span>
                        <button type="button" onClick={() => void handleDownload(f.path)}>
                          Baixar
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      ))}

      <p style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "#9ca3af" }}>
        {files.length} arquivo(s) · {folders.length} pasta(s)
      </p>
    </div>
  );
}
