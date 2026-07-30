import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import { MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import api from "@/services/api";
import { PDF_VIEWER_HEIGHT } from "@/styles/pdfViewer";

export default function PDFFontColorAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [opacity, setOpacity] = useState(0.42);
  const [bySubset, setBySubset] = useState(false);
  const [mode, setMode] = useState<"font" | "size">("font");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [, setLegend] = useState("");
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime("pdf_font_color_overlay");

  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  useEffect(() => () => {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  }, [pdfUrl]);

  function clearResults() {
    reset();
    setLegend("");
    clearMessage();
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    setPdfUrl(null);
  }

  const applyEvidence = useCallback(
    (_id: string) => {
      clearResults();
    },
    []
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    clearMessage();
    setLegend("");
    if (pdfUrl) {
      URL.revokeObjectURL(pdfUrl);
      setPdfUrl(null);
    }
    try {
      await runAnalysis(evidenceId, "pdf_font_color_overlay", { opacity, by_subset: bySubset, mode }, {
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
    }
  }

  if (!caseId) return null;

  const parametersPanel = (
    <>
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

      <label style={{ display: "block", marginTop: "0.75rem", fontSize: "0.82rem" }}>
        Modo de overlay
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as "font" | "size")}
          style={{
            display: "block",
            width: "100%",
            maxWidth: 320,
            marginTop: "0.25rem",
            padding: "0.35rem 0.5rem",
            borderRadius: 6,
            border: "1px solid #d1d5db",
            background: "#fff",
          }}
        >
          <option value="font">Por fonte (cor por recurso de fonte)</option>
          <option value="size">Por tamanho (heatmap azul → vermelho)</option>
        </select>
      </label>
      <p style={{ fontSize: "0.78rem", color: "#6b7280", margin: "0.35rem 0 0" }}>
        {mode === "font"
          ? "Cada fonte recebe uma cor distinta no PDF."
          : "Cada tamanho de fonte recebe uma cor: azul (pequeno) → verde → amarelo → vermelho (grande)."}
      </p>
      <div style={{ marginTop: "1rem" }}>
        <ProcessButton
          onClick={process}
          disabled={!evidenceId || runtimeOk === false}
          running={running}
          progress={progress}
          progressLabel={progressLabel}
          label="Gerar overlay"
        />
      </div>
    </>
  );

  const resultPanel = (
    <>
      {pdfUrl && (
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
      )}
      {result && (
        <p style={{ fontSize: "0.82rem", color: "#374151", marginTop: 8 }}>
          {mode === "size"
            ? `${Number(result.sizes_count)} tamanhos · ${Number(result.rectangles)} realces`
            : `${Number(result.fonts_count)} fontes · ${Number(result.rectangles)} realces`}
        </p>
      )}
      {currentJobId && (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
          <button
            type="button"
            onClick={() => save(currentJobId, "font_overlay.pdf", "pdf_overlay")}
            disabled={!!saving}
            style={btnPrimary}
          >
            {saving ? "Salvando…" : "Salvar PDF overlay nos derivados"}
          </button>
          <button
            type="button"
            onClick={() => save(currentJobId, "font_legend.txt", "font_legend")}
            disabled={!!saving}
            style={btnPrimary}
          >
            {saving ? "Salvando…" : "Salvar legenda TXT nos derivados"}
          </button>
        </div>
      )}
      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="pdf_font_color_overlay"
      mediaType="pdf"
      embedded={embedded}
      evidenceId={evidenceId}
      selectionSource={selectionSource}
      onSelectEvidence={onSelectEvidence}
      showEvidencePicker={showEvidencePicker}
      running={running}
      error={error}
      progress={progress}
      progressLabel={progressLabel}
      saveMessage={saveMessage}
      runtimeOk={runtimeOk}
      runtimeReason={runtimeReason}
      parametersPanel={parametersPanel}
      resultPanel={resultPanel || undefined}
    />
  );
}

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
