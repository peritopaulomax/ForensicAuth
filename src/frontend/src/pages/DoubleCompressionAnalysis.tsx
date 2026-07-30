import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import PlotlyHtmlFrame from "@/components/PlotlyHtmlFrame";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import api from "@/services/api";

export default function DoubleCompressionAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [dctmin, setDctmin] = useState(1);
  const [dctmax, setDctmax] = useState(10);
  const [htmlUrl, setHtmlUrl] = useState<string | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, reset } = useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime("double_compression");

  const runtimeOk = runtimeStatus?.available ?? null;

  useEffect(() => {
    return () => {
      if (htmlUrl) URL.revokeObjectURL(htmlUrl);
    };
  }, [htmlUrl]);

  const applyEvidence = useCallback(
    (_id: string, _source: "original" | "derivative") => {
      reset();
      if (htmlUrl) URL.revokeObjectURL(htmlUrl);
      setHtmlUrl(null);
      clearMessage();
    },
    [reset, htmlUrl, clearMessage]
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId) return;
    try {
      await runAnalysis(evidenceId, "double_compression", { dctmin, dctmax }, {
        onArtifactsLoaded: async (jobId) => {
          const response = await api.get(`/analysis/${jobId}/result/file?filename=interactive.html`, {
            responseType: "blob",
          });
          if (htmlUrl) URL.revokeObjectURL(htmlUrl);
          setHtmlUrl(URL.createObjectURL(new Blob([response.data], { type: "text/html" })));
        },
      });
    } catch {
    }
  }

  if (!caseId) return null;

  const indices = (result?.coefficient_indices as number[]) || [];
  const count = Number(result?.coefficient_count ?? indices.length);

  const parametersPanel = (
    <>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ fontSize: "0.85rem" }}>
          dctmin
          <input type="number" min={1} max={64} value={dctmin} onChange={(e) => setDctmin(Number(e.target.value))} style={inputBlock} />
        </label>
        <label style={{ fontSize: "0.85rem" }}>
          dctmax
          <input type="number" min={1} max={64} value={dctmax} onChange={(e) => setDctmax(Number(e.target.value))} style={inputBlock} />
        </label>
      </div>
      <div style={{ marginTop: "1rem" }}>
        <button type="button" onClick={process} disabled={!evidenceId || running} style={btnPrimary}>
          {running ? "Processando…" : "Processar dupla compressao"}
        </button>
      </div>
    </>
  );

  const resultPanel = result && htmlUrl && (
    <>
      <p style={{ fontSize: "0.88rem", color: "#4b5563", margin: "0 0 0.75rem 0" }}>
        {count} coeficiente(s) calculados ({indices.length ? `${indices[0]}–${indices[indices.length - 1]}` : `${dctmin}–${dctmax}`}).
        Histograma com zoom livre; espectro FFT com escala fixa 0–1000 × 0–600.
        Use a barra de coeficientes ou os botoes Anterior/Proximo (salto direto, sem animacao).
      </p>
      <PlotlyHtmlFrame url={htmlUrl} title="Dupla compressao — Plotly" height={560} />
      {currentJobId && (
        <div style={{ marginTop: "1rem" }}>
          <button
            type="button"
            disabled={saving}
            onClick={() => save(currentJobId, "interactive.html", "Grafico Plotly")}
            style={btnPrimary}
          >
            Salvar grafico Plotly na custodia
          </button>
        </div>
      )}
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="double_compression"
      mediaType="imagem"
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
      parametersPanel={parametersPanel}
      resultPanel={resultPanel || undefined}
    />
  );
}

const inputBlock: React.CSSProperties = {
  display: "block",
  marginTop: 4,
  padding: "0.35rem 0.5rem",
  borderRadius: 4,
  border: "1px solid #d1d5db",
};

const btnPrimary: React.CSSProperties = {
  padding: "0.5rem 1rem",
  background: "#0369a1",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
  fontWeight: 600,
};
