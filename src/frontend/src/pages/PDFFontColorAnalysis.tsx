import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import MediaEvidenceSelector from "@/components/MediaEvidenceSelector";
import { useForensicJob } from "@/hooks/useForensicJob";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";
import { PDF_VIEWER_HEIGHT } from "@/styles/pdfViewer";

export default function PDFFontColorAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [opacity, setOpacity] = useState(0.42);
  const [bySubset, setBySubset] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [legend, setLegend] = useState("");
  const [savingDerivative, setSavingDerivative] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, reset } =
    useForensicJob();

  useEffect(() => () => {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  }, [pdfUrl]);

  function clearResults() {
    reset();
    setLegend("");
    setSaveMessage(null);
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    setPdfUrl(null);
  }

  async function process() {
    if (!selectedId) return;
    setSaveMessage(null);
    setLegend("");
    if (pdfUrl) {
      URL.revokeObjectURL(pdfUrl);
      setPdfUrl(null);
    }
    try {
      await runAnalysis(selectedId, "pdf_font_color_overlay", { opacity, by_subset: bySubset }, {
        onArtifactsLoaded: async (jobId, jobResult) => {
          const res = await api.get(`/analysis/${jobId}/result/file?filename=font_overlay.pdf`, {
            responseType: "blob",
          });
          if (pdfUrl) URL.revokeObjectURL(pdfUrl);
          setPdfUrl(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })));
          setLegend(String(jobResult?.legend_preview || ""));
        },
      });
    } catch {
      /* hook */
    }
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

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="PDF — Overlay por fonte"
      subtitle="Cores por recurso de fonte. Visualize o PDF com overlay na propria ferramenta."
    >
      <AnalysisPanel title="Evidencia PDF">
        <MediaEvidenceSelector
          caseId={caseId}
          fileType="pdf"
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            clearResults();
          }}
          radioName="pdf-font-overlay"
        />
        <label style={{ display: "block", marginTop: "0.75rem", fontSize: "0.82rem" }}>
          Opacidade do overlay: {opacity}
          <input
            type="range"
            min={0.1}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => setOpacity(Number(e.target.value))}
            style={{ width: "100%", maxWidth: 320 }}
          />
        </label>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.45rem",
            marginTop: "0.75rem",
            fontSize: "0.82rem",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={bySubset}
            onChange={(e) => setBySubset(e.target.checked)}
          />
          Por subset (/BaseFont distinto por tag de subconjunto)
        </label>
        <p style={{ fontSize: "0.78rem", color: "#6b7280", margin: "0.35rem 0 0" }}>
          Desmarcado (padrão): uma cor por família de fonte. Marcado: analisa o content stream e
          distingue subsets (ex.: ABCDEF+Arial vs GHIJKL+Arial).
        </p>
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!selectedId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Gerar overlay"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {pdfUrl && (
        <AnalysisPanel title="PDF com overlay">
          <iframe
            title="PDF font overlay"
            src={pdfUrl}
            style={{
              width: "100%",
              height: PDF_VIEWER_HEIGHT,
              border: "1px solid #e5e7eb",
              borderRadius: 8,
            }}
          />
          {result && (
            <p style={{ fontSize: "0.82rem", color: "#374151", marginTop: 8 }}>
              {Number(result.fonts_count)} fontes · {Number(result.rectangles)} realces
            </p>
          )}
          {currentJobId && (
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
              <button
                type="button"
                onClick={() => handleSaveDerivative("font_overlay.pdf", "pdf_overlay")}
                disabled={!!savingDerivative}
                style={btnPrimary}
              >
                {savingDerivative === "font_overlay.pdf" ? "Salvando…" : "Salvar PDF overlay nos derivados"}
              </button>
              <button
                type="button"
                onClick={() => handleSaveDerivative("font_legend.txt", "font_legend")}
                disabled={!!savingDerivative}
                style={btnPrimary}
              >
                {savingDerivative === "font_legend.txt" ? "Salvando…" : "Salvar legenda TXT nos derivados"}
              </button>
              <button type="button" onClick={() => navigate(`/cases/${caseId}?tab=derivados`)} style={btnSecondary}>
                Abrir derivados
              </button>
            </div>
          )}
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}

      {legend && (
        <AnalysisPanel title="Legenda de fontes">
          <pre style={{ fontSize: "0.78rem", whiteSpace: "pre-wrap", background: "#f9fafb", padding: 12 }}>
            {legend}
          </pre>
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

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
