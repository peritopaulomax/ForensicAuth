import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { getEvidenceLineage, type LineageGraph } from "@/services/evidence";
import DerivationDagView from "@/components/DerivationDagView";

interface Props {
  evidenceId: string;
  evidenceName: string;
  onClose: () => void;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function graphToXml(graph: LineageGraph): string {
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const nodes = graph.nodes
    .map(
      (n) =>
        `    <node id="${esc(n.evidence_id)}" derived="${n.is_derived}">` +
        `<filename>${esc(n.original_filename)}</filename>` +
        `<sha256>${esc(n.sha256)}</sha256>` +
        `<file_type>${esc(n.file_type)}</file_type>` +
        (n.procedure_summary ? `<procedure>${esc(n.procedure_summary)}</procedure>` : "") +
        `</node>`
    )
    .join("\n");
  const edges = graph.edges
    .map(
      (e) =>
        `    <edge from="${esc(e.from_evidence_id)}" to="${esc(e.to_evidence_id)}">` +
        `<technique>${esc(e.technique || "")}</technique>` +
        `<procedure>${esc(e.procedure_summary || "")}</procedure>` +
        `</edge>`
    )
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<derivation_graph target="${esc(graph.target_id)}">\n  <nodes>\n${nodes}\n  </nodes>\n  <edges>\n${edges}\n  </edges>\n</derivation_graph>`;
}

async function loadThumbnailDataUrl(evidenceId: string, fileType: string): Promise<string | null> {
  if (fileType !== "imagem" && fileType !== "video") return null;
  try {
    const { default: api } = await import("@/services/api");
    const res = await api.get(`/evidences/${evidenceId}/thumbnail`, { responseType: "blob" });
    return await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(res.data);
    });
  } catch {
    return null;
  }
}

export default function DerivationGraphModal({ evidenceId, evidenceName, onClose }: Props) {
  const [graph, setGraph] = useState<LineageGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    setLoading(true);
    setError("");
    getEvidenceLineage(evidenceId)
      .then(setGraph)
      .catch(() => setError("Erro ao carregar grafo de derivacao"))
      .finally(() => setLoading(false));
  }, [evidenceId]);

  const exportPng = useCallback(async () => {
    if (!graph || !canvasRef.current) return;
    setExporting(true);
    try {
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const sorted = [...graph.nodes].sort((a, b) => (a.layer ?? 0) - (b.layer ?? 0));
      const nodeW = 120;
      const nodeH = 100;
      const edgeW = 140;
      const pad = 24;
      const count = sorted.length;
      const width = pad * 2 + count * nodeW + Math.max(0, count - 1) * edgeW;
      const height = 220;
      canvas.width = width;
      canvas.height = height;

      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);

      const thumbs = await Promise.all(
        sorted.map((n) => loadThumbnailDataUrl(n.evidence_id, n.file_type))
      );

      for (let i = 0; i < sorted.length; i++) {
        const x = pad + i * (nodeW + edgeW);
        const y = pad;

        ctx.strokeStyle = "#e5e7eb";
        ctx.lineWidth = 1;
        ctx.strokeRect(x, y, nodeW, nodeH);

        const thumb = thumbs[i];
        if (thumb) {
          const img = new Image();
          await new Promise<void>((res) => {
            img.onload = () => {
              ctx.drawImage(img, x + 30, y + 8, 60, 60);
              res();
            };
            img.onerror = () => res();
            img.src = thumb;
          });
        } else {
          ctx.fillStyle = "#f3f4f6";
          ctx.fillRect(x + 30, y + 8, 60, 60);
        }

        ctx.fillStyle = "#1a1a2e";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "center";
        const name = sorted[i].original_filename;
        const short = name.length > 16 ? name.slice(0, 14) + "…" : name;
        ctx.fillText(short, x + nodeW / 2, y + nodeH - 28);
        ctx.fillStyle = "#6b7280";
        ctx.font = "8px monospace";
        ctx.fillText(sorted[i].evidence_id.slice(0, 8), x + nodeW / 2, y + nodeH - 14);

        if (i < sorted.length - 1) {
          const edge = graph.edges.find(
            (e) => e.from_evidence_id === sorted[i].evidence_id && e.to_evidence_id === sorted[i + 1].evidence_id
          );
          if (!edge) continue;
          const ax = x + nodeW;
          const ay = y + nodeH / 2;
          const bx = ax + edgeW;
          ctx.strokeStyle = "#1a1a2e";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(bx - 8, ay);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(bx - 8, ay);
          ctx.lineTo(bx - 14, ay - 5);
          ctx.lineTo(bx - 14, ay + 5);
          ctx.closePath();
          ctx.fillStyle = "#1a1a2e";
          ctx.fill();

          const label = edge.procedure_summary || edge.technique || "derivacao";
          ctx.fillStyle = "#374151";
          ctx.font = "9px sans-serif";
          ctx.textAlign = "center";
          ctx.fillText(label, ax + edgeW / 2, ay - 8);
        }
      }

      canvas.toBlob((blob) => {
        if (blob) downloadBlob(blob, `grafo_${evidenceName.replace(/[^\w.-]+/g, "_")}.png`);
      }, "image/png");
    } finally {
      setExporting(false);
    }
  }, [graph, evidenceName]);

  function exportJson() {
    if (!graph) return;
    const blob = new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" });
    downloadBlob(blob, `grafo_${evidenceName.replace(/[^\w.-]+/g, "_")}.json`);
  }

  function exportXml() {
    if (!graph) return;
    const blob = new Blob([graphToXml(graph)], { type: "application/xml" });
    downloadBlob(blob, `grafo_${evidenceName.replace(/[^\w.-]+/g, "_")}.xml`);
  }

  return (
    <div
      role="dialog"
      aria-modal
      aria-labelledby="derivation-graph-title"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "1rem",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: "10px",
          maxWidth: graph ? "1100px" : "920px",
          width: "100%",
          maxHeight: "90vh",
          overflow: "auto",
          boxShadow: "0 20px 40px rgba(0,0,0,0.15)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "1rem 1.25rem",
            borderBottom: "1px solid #e5e7eb",
          }}
        >
          <h3 id="derivation-graph-title" style={{ margin: 0, fontSize: "1.05rem", color: "#1a1a2e" }}>
            Grafo de derivacao — {evidenceName}
          </h3>
          <button
            type="button"
            onClick={onClose}
            style={{ background: "none", border: "none", fontSize: "1.25rem", cursor: "pointer", color: "#6b7280" }}
          >
            ×
          </button>
        </div>

        <div style={{ padding: "1.25rem" }}>
          {loading && <p style={{ color: "#6b7280" }}>Carregando cadeia…</p>}
          {error && (
            <p style={{ color: "#991b1b", background: "#fee2e2", padding: "0.6rem", borderRadius: "6px" }}>{error}</p>
          )}

          {graph && !loading && (
            <>
              <div style={{ marginBottom: "1rem" }}>
                <DerivationDagView graph={graph} />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                <div>
                  <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#374151" }}>
                    Dados estruturados (JSON)
                  </h4>
                  <pre
                    style={{
                      margin: 0,
                      padding: "0.75rem",
                      background: "#1a1a2e",
                      color: "#e5e7eb",
                      borderRadius: "6px",
                      fontSize: "0.68rem",
                      overflow: "auto",
                      maxHeight: "180px",
                    }}
                  >
                    {JSON.stringify(graph, null, 2)}
                  </pre>
                </div>
                <div>
                  <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#374151" }}>Exportar</h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <button
                      type="button"
                      onClick={() => void exportPng()}
                      disabled={exporting}
                      style={exportBtnStyle}
                    >
                      {exporting ? "Gerando PNG…" : "Salvar como imagem (PNG)"}
                    </button>
                    <button type="button" onClick={exportJson} style={exportBtnStyle}>
                      Salvar como JSON
                    </button>
                    <button type="button" onClick={exportXml} style={exportBtnStyle}>
                      Salvar como XML
                    </button>
                  </div>
                  <canvas ref={canvasRef} style={{ display: "none" }} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const exportBtnStyle: CSSProperties = {
  padding: "0.5rem 0.75rem",
  background: "#fff",
  color: "#1a1a2e",
  border: "1px solid #1a1a2e",
  borderRadius: "6px",
  cursor: "pointer",
  fontSize: "0.8rem",
  fontWeight: 500,
  textAlign: "left",
};
