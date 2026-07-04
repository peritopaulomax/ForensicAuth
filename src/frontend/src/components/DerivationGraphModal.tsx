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
    .map((n) => {
      const attrs = [
        `id="${esc(n.evidence_id)}"`,
        `derived="${n.is_derived}"`,
        n.layer != null ? `layer="${n.layer}"` : "",
        n.technique ? `technique="${esc(n.technique)}"` : "",
        n.derivation_step ? `derivation_step="${esc(n.derivation_step)}"` : "",
        n.source_job_id ? `source_job_id="${esc(n.source_job_id)}"` : "",
      ]
        .filter(Boolean)
        .join(" ");
      return (
        `    <node ${attrs}>` +
        `<filename>${esc(n.original_filename)}</filename>` +
        `<sha256>${esc(n.sha256)}</sha256>` +
        `<file_type>${esc(n.file_type)}</file_type>` +
        (n.procedure_summary ? `<procedure>${esc(n.procedure_summary)}</procedure>` : "") +
        (n.parameters ? `<parameters>${esc(JSON.stringify(n.parameters))}</parameters>` : "") +
        (n.derivation_outputs ? `<outputs>${esc(JSON.stringify(n.derivation_outputs))}</outputs>` : "") +
        `</node>`
      );
    })
    .join("\n");
  const edges = graph.edges
    .map((e) => {
      const attrs = [
        `from="${esc(e.from_evidence_id)}"`,
        `to="${esc(e.to_evidence_id)}"`,
        e.derivation_step ? `derivation_step="${esc(e.derivation_step)}"` : "",
        e.source_job_id ? `source_job_id="${esc(e.source_job_id)}"` : "",
      ]
        .filter(Boolean)
        .join(" ");
      return (
        `    <edge ${attrs}>` +
        `<technique>${esc(e.technique || "")}</technique>` +
        `<procedure>${esc(e.procedure_summary || "")}</procedure>` +
        `<parameters>${esc(JSON.stringify(e.parameters || {}))}</parameters>` +
        `</edge>`
      );
    })
    .join("\n");
  const operations = (graph.operations ?? [])
    .map(
      (op) =>
        `    <operation id="${esc(op.id)}" to="${esc(op.to_evidence_id)}"` +
        `${op.derivation_step ? ` step="${esc(op.derivation_step)}"` : ""}>` +
        `<label>${esc(op.label)}</label>` +
        `<inputs>${esc(JSON.stringify(op.inputs))}</inputs>` +
        `${op.outputs ? `<outputs>${esc(JSON.stringify(op.outputs))}</outputs>` : ""}` +
        `</operation>`
    )
    .join("\n");
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<derivation_graph target="${esc(graph.target_id)}" layout="${esc(graph.layout || "dag")}">\n` +
    `  <nodes>\n${nodes}\n  </nodes>\n` +
    `  <edges>\n${edges}\n  </edges>\n` +
    (operations ? `  <operations>\n${operations}\n  </operations>\n` : "") +
    `</derivation_graph>`
  );
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

      const layers = new Map<number, typeof graph.nodes>();
      for (const node of graph.nodes) {
        const layer = node.layer ?? 0;
        const bucket = layers.get(layer) ?? [];
        bucket.push(node);
        layers.set(layer, bucket);
      }
      const sortedLayers = [...layers.keys()].sort((a, b) => a - b);
      const nodeW = 120;
      const nodeH = 108;
      const hGap = 16;
      const vGap = 56;
      const pad = 24;
      const maxRow = Math.max(1, ...sortedLayers.map((layer) => layers.get(layer)?.length ?? 0));
      const width = pad * 2 + maxRow * nodeW + Math.max(0, maxRow - 1) * hGap;
      const height = pad * 2 + sortedLayers.length * nodeH + Math.max(0, sortedLayers.length - 1) * vGap;
      canvas.width = width;
      canvas.height = height;

      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);

      const nodePos = new Map<string, { x: number; y: number }>();
      sortedLayers.forEach((layer, layerIdx) => {
        const row = layers.get(layer) ?? [];
        const rowWidth = row.length * nodeW + Math.max(0, row.length - 1) * hGap;
        const startX = pad + (width - pad * 2 - rowWidth) / 2;
        const y = pad + layerIdx * (nodeH + vGap);
        row.forEach((node, idx) => {
          const x = startX + idx * (nodeW + hGap);
          nodePos.set(node.evidence_id, { x, y });
        });
      });

      const thumbs = await Promise.all(
        graph.nodes.map((n) => loadThumbnailDataUrl(n.evidence_id, n.file_type))
      );
      const thumbById = new Map(graph.nodes.map((n, i) => [n.evidence_id, thumbs[i]]));

      for (const edge of graph.edges) {
        const from = nodePos.get(edge.from_evidence_id);
        const to = nodePos.get(edge.to_evidence_id);
        if (!from || !to) continue;
        const ax = from.x + nodeW / 2;
        const ay = from.y + nodeH;
        const bx = to.x + nodeW / 2;
        const by = to.y;
        ctx.strokeStyle = "#94a3b8";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.stroke();
      }

      for (const node of graph.nodes) {
        const pos = nodePos.get(node.evidence_id);
        if (!pos) continue;
        const { x, y } = pos;
        ctx.strokeStyle = node.is_derived ? "#0369a1" : "#e5e7eb";
        ctx.lineWidth = node.is_derived ? 2 : 1;
        ctx.strokeRect(x, y, nodeW, nodeH);

        const thumb = thumbById.get(node.evidence_id);
        if (thumb) {
          const img = new Image();
          await new Promise<void>((res) => {
            img.onload = () => {
              ctx.drawImage(img, x + 30, y + 8, 60, 48);
              res();
            };
            img.onerror = () => res();
            img.src = thumb;
          });
        } else {
          ctx.fillStyle = "#f3f4f6";
          ctx.fillRect(x + 30, y + 8, 60, 48);
        }

        ctx.fillStyle = "#1a1a2e";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "center";
        const name = node.original_filename;
        const short = name.length > 16 ? name.slice(0, 14) + "…" : name;
        ctx.fillText(short, x + nodeW / 2, y + nodeH - 30);
        if (node.technique) {
          ctx.fillStyle = "#0369a1";
          ctx.font = "8px sans-serif";
          ctx.fillText(node.technique, x + nodeW / 2, y + nodeH - 18);
        }
        ctx.fillStyle = "#6b7280";
        ctx.font = "8px monospace";
        ctx.fillText(node.evidence_id.slice(0, 8), x + nodeW / 2, y + nodeH - 6);
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
