import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import PlotlyHtmlFrame from "@/components/PlotlyHtmlFrame";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";

export default function DoubleCompressionAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [dctmin, setDctmin] = useState(1);
  const [dctmax, setDctmax] = useState(10);
  const [htmlUrl, setHtmlUrl] = useState<string | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, reset } = useForensicJob();
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

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
      setSaveMessage(null);
    },
    [reset, htmlUrl],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function handleSavePlotly() {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({ job_id: currentJobId, artifact_filename: "interactive.html" });
      setSaveMessage({
        type: "ok",
        text: `Grafico Plotly salvo na custodia. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: msg });
    } finally {
      setSaving(false);
    }
  }

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
      /* hook sets error */
    }
  }

  if (!caseId) return null;

  const indices = (result?.coefficient_indices as number[]) || [];
  const count = Number(result?.coefficient_count ?? indices.length);

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.double_compression.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.double_compression} techniqueId="double_compression" />}
      embedded={embedded}
    >
      <AnalysisPanel title="Evidencia (JPEG)">
        {showEvidencePicker && (
          <ImageEvidenceSelector
            caseId={caseId}
            selectedId={evidenceId}
            selectionSource={selectionSource}
            onSelect={onSelectEvidence}
          />
        )}
      </AnalysisPanel>

      <AnalysisPanel title="Intervalo de coeficientes DCT">
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
          <ProcessButton
            onClick={process}
            disabled={!evidenceId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Processar dupla compressao"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && htmlUrl && (
        <AnalysisPanel title="Graficos interativos">
          <p style={{ fontSize: "0.88rem", color: "#4b5563", margin: "0 0 0.75rem 0" }}>
            {count} coeficiente(s) calculados ({indices.length ? `${indices[0]}–${indices[indices.length - 1]}` : `${dctmin}–${dctmax}`}).
            Histograma com zoom livre; espectro FFT com escala fixa 0–1000 × 0–600.
            Use a barra de coeficientes ou os botoes Anterior/Proximo (salto direto, sem animacao).
          </p>
          <PlotlyHtmlFrame
            url={htmlUrl}
            title="Dupla compressao — Plotly"
            height={560}
          />
          {currentJobId && (
            <div style={{ marginTop: "1rem" }}>
              <button
                type="button"
                disabled={saving}
                onClick={handleSavePlotly}
                style={{
                  padding: "0.5rem 1rem",
                  background: "#0369a1",
                  color: "#fff",
                  border: "none",
                  borderRadius: 6,
                  cursor: saving ? "wait" : "pointer",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                }}
              >
                Salvar grafico Plotly na custodia
              </button>
            </div>
          )}
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

const inputBlock: React.CSSProperties = {
  display: "block",
  marginTop: 4,
  padding: "0.35rem 0.5rem",
  borderRadius: 4,
  border: "1px solid #d1d5db",
};
