import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import AnalysisPageShell, {
  AnalysisPanel,
  MessageBox,
  ProcessButton,
  formatInferenceDevice,
  parseDeviceFromProgress,
} from "@/components/AnalysisPageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";

type ResultRow = [string, string, string, string, string, string];

const INDIVIDUAL_HEADERS = [
  "Modelo",
  "Score AI",
  "Score Real",
  "Razão (Log)",
  "Classificação",
  "Dispositivo",
];

const DETECTION_PROGRESS_STAGES: { min: number; label: string }[] = [
  { min: 0, label: "Preparacao e carregamento de modelos" },
  { min: 32, label: "Inferencia CNN e difusao" },
  { min: 48, label: "FFT e XGBoost" },
  { min: 52, label: "Effort (GenImage / Chameleon)" },
  { min: 62, label: "SAFE (KDD'25)" },
  { min: 64, label: "CAMO (BitMind UCF MoE)" },
  { min: 65, label: "IAPL (GenImage)" },
  { min: 68, label: "Visualizacoes forenses (FFT, residuos)" },
  { min: 86, label: "Salvando artefatos e relatorio" },
];

function DetectionProgressChecklist({
  progress,
  running,
  inferenceDevice,
}: {
  progress: number;
  running: boolean;
  inferenceDevice: string | null;
}) {
  if (!running) return null;
  const pct = Math.round(Math.min(100, Math.max(0, progress)));

  return (
    <div style={{ marginTop: "0.75rem" }}>
      {inferenceDevice && (
        <p style={{ margin: "0 0 0.5rem", fontSize: "0.8rem", color: "#374151" }}>
          Dispositivo de inferencia ML:{" "}
          <strong style={{ color: inferenceDevice === "CPU" ? "#b45309" : "#1d4ed8" }}>
            {inferenceDevice}
          </strong>
          {inferenceDevice === "CPU" && (
            <span style={{ color: "#b45309", fontWeight: 400 }}> — mais lento que GPU</span>
          )}
        </p>
      )}
      <ul
        style={{
          margin: 0,
          padding: 0,
          listStyle: "none",
          fontSize: "0.78rem",
          color: "#6b7280",
          display: "grid",
          gap: "0.3rem",
        }}
      >
      {DETECTION_PROGRESS_STAGES.map((stage, idx) => {
        const nextMin = DETECTION_PROGRESS_STAGES[idx + 1]?.min ?? 101;
        const done = pct >= nextMin;
        const active = pct >= stage.min && pct < nextMin;
        const icon = done ? "✓" : active ? "●" : "○";
        const color = done ? "#166534" : active ? "#1a1a2e" : "#9ca3af";
        const weight = active ? 600 : 400;

        return (
          <li key={stage.min} style={{ display: "flex", alignItems: "center", gap: "0.45rem", color, fontWeight: weight }}>
            <span style={{ width: "1rem", textAlign: "center", flexShrink: 0 }}>{icon}</span>
            <span>{stage.label}</span>
          </li>
        );
      })}
      </ul>
    </div>
  );
}

function ResultsTable({ rows }: { rows: ResultRow[] }) {
  return (
    <div>
      <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.88rem", color: "#374151", fontWeight: 600 }}>
        Resultados dos Modelos Individuais
      </h4>
      <div style={{ overflow: "auto", maxHeight: 180, border: "1px solid #e5e7eb", borderRadius: 6 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
          <thead>
            <tr style={{ background: "#f9fafb", position: "sticky", top: 0 }}>
              {INDIVIDUAL_HEADERS.map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: "left",
                    padding: "0.45rem 0.6rem",
                    borderBottom: "1px solid #e5e7eb",
                    color: "#4b5563",
                    fontWeight: 600,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const cells = [...row, ...Array(Math.max(0, INDIVIDUAL_HEADERS.length - row.length)).fill("—")];
              return (
              <tr key={i}>
                {cells.map((cell, j) => (
                  <td
                    key={j}
                    style={{
                      padding: "0.4rem 0.6rem",
                      borderBottom: "1px solid #f3f4f6",
                      color:
                        j === 4
                          ? classificationColor(cell)
                          : j === 5
                            ? deviceBadgeColor(cell)
                            : "#1f2937",
                      fontWeight: j === 4 || j === 5 ? 600 : 400,
                    }}
                  >
                    {j === 5 ? (
                      <span
                        style={{
                          display: "inline-block",
                          padding: "0.1rem 0.45rem",
                          borderRadius: 4,
                          fontSize: "0.72rem",
                          background: cell === "GPU" ? "#dbeafe" : "#f3f4f6",
                          color: deviceBadgeColor(cell),
                        }}
                      >
                        {cell}
                      </span>
                    ) : (
                      cell
                    )}
                  </td>
                ))}
              </tr>
            );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function classificationColor(value: string): string {
  if (value === "AI") return "#b91c1c";
  if (value === "REAL") return "#166534";
  return "#b45309";
}

function deviceBadgeColor(value: string): string {
  if (value === "GPU") return "#1d4ed8";
  return "#6b7280";
}

function ForensicImage({
  src,
  label,
  imageStyle,
  placeholderStyle: placeholderOverride,
  captionStyle,
}: {
  src: string | null;
  label: string;
  imageStyle?: React.CSSProperties;
  placeholderStyle?: React.CSSProperties;
  captionStyle?: React.CSSProperties;
}) {
  const cap = captionStyle ?? capStyle;
  if (!src) {
    return (
      <figure style={{ margin: 0, width: "100%" }}>
        <div style={{ ...placeholderStyle, ...placeholderOverride }}>—</div>
        <figcaption style={cap}>{label}</figcaption>
      </figure>
    );
  }
  return (
    <figure style={{ margin: 0, width: "100%" }}>
      <img src={src} alt={label} style={{ ...imgStyle, ...imageStyle }} />
      <figcaption style={cap}>{label}</figcaption>
    </figure>
  );
}

const inputPreviewPlaceholderStyle: React.CSSProperties = {
  minHeight: 270,
};
const inputPreviewImgStyle: React.CSSProperties = {
  minHeight: 270,
};
const forensicThumbImgStyle: React.CSSProperties = {
  width: "100%",
  height: "auto",
};
const forensicThumbPlaceholderStyle: React.CSSProperties = {
  width: "100%",
  aspectRatio: "1",
  minHeight: 0,
};
const forensicThumbCapStyle: React.CSSProperties = {
  fontSize: "0.68rem",
  color: "#6b7280",
  marginTop: 4,
  textAlign: "center",
  lineHeight: 1.25,
};

export default function SyntheticImageDetectionAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [generateVisuals, setGenerateVisuals] = useState(true);
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [inputFftUrl, setInputFftUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [nlmResidueUrl, setNlmResidueUrl] = useState<string | null>(null);
  const [medianResidueUrl, setMedianResidueUrl] = useState<string | null>(null);
  const [nlmFftUrl, setNlmFftUrl] = useState<string | null>(null);
  const [medianFftUrl, setMedianFftUrl] = useState<string | null>(null);
  const blobUrlsRef = useRef<string[]>([]);

  const [saving, setSaving] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const [liveInferenceDevice, setLiveInferenceDevice] = useState<string | null>(null);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  useEffect(() => {
    if (!running) {
      setLiveInferenceDevice(null);
      return;
    }
    const parsed = parseDeviceFromProgress(progressLabel);
    if (parsed) setLiveInferenceDevice(parsed);
  }, [running, progressLabel]);

  const activeInferenceDevice =
    formatInferenceDevice(result?.inference_device) ?? (running ? liveInferenceDevice : null);

  const revokeBlobs = useCallback(() => {
    blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    blobUrlsRef.current = [];
  }, []);

  const trackBlob = useCallback((url: string | null) => {
    if (url) blobUrlsRef.current.push(url);
    return url;
  }, []);

  const setArtifactUrl = useCallback(
    (setter: (url: string | null) => void, url: string | null) => {
      setter(url ? trackBlob(url) : null);
    },
    [trackBlob]
  );

  const loadEvidencePreview = useCallback(
    async (evidenceId: string) => {
      setPreviewLoading(true);
      setOriginalUrl(null);
      try {
        const res = await api.get(`/evidences/${evidenceId}/file`, { responseType: "blob" });
        setOriginalUrl(trackBlob(URL.createObjectURL(res.data)));
      } catch {
        setOriginalUrl(null);
      } finally {
        setPreviewLoading(false);
      }
    },
    [trackBlob]
  );

  useEffect(() => {
    return () => revokeBlobs();
  }, [revokeBlobs]);

  useEffect(() => {
    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((res) => {
        const item = res.data.find((t) => t.name === "synthetic_image_detection");
        if (item) {
          setRuntimeOk(item.available !== false);
          setRuntimeReason(item.unavailable_reason || "");
        } else {
          setRuntimeOk(false);
          setRuntimeReason("Detecção de imagens sintéticas não registrada no servidor.");
        }
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Nao foi possivel verificar disponibilidade do Detecção de imagens sintéticas.");
      });
  }, []);

  function clearVisuals() {
    setInputFftUrl(null);
    setNlmResidueUrl(null);
    setMedianResidueUrl(null);
    setNlmFftUrl(null);
    setMedianFftUrl(null);
  }

  function clearArtifactBlobs() {
    revokeBlobs();
    setOriginalUrl(null);
    clearVisuals();
  }

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      clearArtifactBlobs();
      setSaveMessage(null);
      void loadEvidencePreview(id);
    },
    [reset, revokeBlobs, loadEvidencePreview],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    setSaving(filename);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: filename,
        label,
      });
      setSaveMessage({
        type: "ok",
        text: `${label} salvo na cadeia de custodia. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: String(msg) });
    } finally {
      setSaving(null);
    }
  }

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    clearVisuals();
    setSaveMessage(null);
    try {
      await runAnalysis(
        evidenceId,
        "synthetic_image_detection",
        { generate_visuals: generateVisuals, mode: generateVisuals ? "full" : "fast" },
        {
          maxWaitMs: 15 * 60 * 1000,
          onArtifactsLoaded: async (jobId) => {
            const [inputImg, inputFft, nlmResidue, medianResidue, nlmFft, medianFft] = await Promise.all([
              fetchImage(jobId, "input_image.png"),
              fetchImage(jobId, "input_fft.png"),
              generateVisuals ? fetchImage(jobId, "nlm_residue.png") : Promise.resolve(null),
              generateVisuals ? fetchImage(jobId, "median_residue.png") : Promise.resolve(null),
              generateVisuals ? fetchImage(jobId, "nlm_fft.png") : Promise.resolve(null),
              generateVisuals ? fetchImage(jobId, "median_fft.png") : Promise.resolve(null),
            ]);
            if (inputImg) {
              revokeBlobs();
              setOriginalUrl(trackBlob(inputImg));
            }
            setArtifactUrl(setInputFftUrl, inputFft);
            setArtifactUrl(setNlmResidueUrl, nlmResidue);
            setArtifactUrl(setMedianResidueUrl, medianResidue);
            setArtifactUrl(setNlmFftUrl, nlmFft);
            setArtifactUrl(setMedianFftUrl, medianFft);
          },
        }
      );
    } catch {
      /* hook */
    }
  }

  if (!caseId) return null;

  const individualRows = (result?.individual_results as ResultRow[]) || [];

  if (runtimeOk === false) {
    return (
      <AnalysisPageShell
        caseId={caseId}
        title="Detecção de Imagens Sintéticas"
        subtitle="Detecção de imagens sintéticas indisponivel neste servidor."
        embedded={embedded}
      >
        <AnalysisPanel title="Indisponivel">
          <MessageBox type="err" text={runtimeReason || "Detecção de imagens sintéticas indisponivel neste servidor."} />
        </AnalysisPanel>
      </AnalysisPageShell>
    );
  }

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="Detecção de Imagens Sintéticas"
      subtitle="Ensemble CNN + Effort + SAFE + IAPL (CVPR 2026) — difusao, FFT e probabilidade p."
      embedded={embedded}
    >
      <AnalysisPanel title="Evidencia">
        {showEvidencePicker && (
          <ImageEvidenceSelector
            caseId={caseId}
            selectedId={evidenceId}
            selectionSource={selectionSource}
            onSelect={onSelectEvidence}
          />
        )}
      </AnalysisPanel>

      <AnalysisPanel title="Parametros">
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.88rem" }}>
          <input
            type="checkbox"
            checked={generateVisuals}
            onChange={(e) => setGenerateVisuals(e.target.checked)}
          />
          Gerar Visualizacoes Forenses (residuos NLM e mediana)
        </label>
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!evidenceId || runtimeOk !== true}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            inferenceDevice={activeInferenceDevice}
            label="Analisar Imagem"
          />
          <DetectionProgressChecklist
            progress={progress}
            running={running}
            inferenceDevice={activeInferenceDevice}
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {(evidenceId || result) && (
        <AnalysisPanel title="Resultado">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(450px, 1.5fr) minmax(280px, 2fr)",
              gap: "1rem",
              alignItems: "start",
            }}
          >
            <div>
              <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#6b7280" }}>
                Imagem de Entrada e FFT
              </h4>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(225px, 1fr))",
                  gap: "0.75rem",
                }}
              >
                {originalUrl ? (
                  <ForensicImage src={originalUrl} label="Imagem de Entrada" imageStyle={inputPreviewImgStyle} />
                ) : (
                  <figure style={{ margin: 0 }}>
                    <div style={{ ...placeholderStyle, ...inputPreviewPlaceholderStyle }}>
                      {previewLoading ? "Carregando imagem…" : "Aguardando imagem de entrada"}
                    </div>
                    <figcaption style={capStyle}>Imagem de Entrada</figcaption>
                  </figure>
                )}
                <ForensicImage
                  src={inputFftUrl}
                  label="FFT(log) da imagem de entrada"
                  imageStyle={inputPreviewImgStyle}
                  placeholderStyle={inputPreviewPlaceholderStyle}
                />
              </div>
            </div>
            <ResultsTable rows={individualRows} />
          </div>

          <details open style={{ marginTop: "1.5rem" }}>
            <summary
              style={{
                cursor: "pointer",
                fontWeight: 600,
                fontSize: "0.95rem",
                color: "#1a1a2e",
                marginBottom: "1rem",
              }}
            >
              Residuos de Denoising
            </summary>

            <h4 style={{ fontSize: "0.9rem", margin: "0 0 0.75rem", color: "#374151" }}>
              Residuos de ruido e FFT
            </h4>
            <div style={{ width: "100%" }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                  gap: "0.5rem",
                  width: "100%",
                }}
              >
                <ForensicImage
                  src={nlmResidueUrl}
                  label="Residuo NLM"
                  imageStyle={forensicThumbImgStyle}
                  placeholderStyle={forensicThumbPlaceholderStyle}
                  captionStyle={forensicThumbCapStyle}
                />
                <ForensicImage
                  src={nlmFftUrl}
                  label="FFT(log) NLM"
                  imageStyle={forensicThumbImgStyle}
                  placeholderStyle={forensicThumbPlaceholderStyle}
                  captionStyle={forensicThumbCapStyle}
                />
                <ForensicImage
                  src={medianResidueUrl}
                  label="Residuo Mediana"
                  imageStyle={forensicThumbImgStyle}
                  placeholderStyle={forensicThumbPlaceholderStyle}
                  captionStyle={forensicThumbCapStyle}
                />
                <ForensicImage
                  src={medianFftUrl}
                  label="FFT(log) Mediana"
                  imageStyle={forensicThumbImgStyle}
                  placeholderStyle={forensicThumbPlaceholderStyle}
                  captionStyle={forensicThumbCapStyle}
                />
              </div>
            </div>
          </details>

          {!generateVisuals && result && (
            <p style={{ marginTop: "1rem", fontSize: "0.82rem", color: "#6b7280" }}>
              Visualizacoes forenses nao foram geradas. Marque a opcao acima e execute novamente.
            </p>
          )}

          {currentJobId && result && (
            <div style={{ marginTop: "1.5rem", borderTop: "1px solid #e5e7eb", paddingTop: "1rem" }}>
              <h4 style={{ margin: "0 0 0.75rem", fontSize: "0.9rem", color: "#374151" }}>
                Salvar em derivados
              </h4>
              <p style={{ margin: "0 0 0.75rem", fontSize: "0.8rem", color: "#6b7280" }}>
                O relatorio de escores (TXT) e o artefato principal para reproducibilidade e cadeia de custodia.
                Imagens sao opcionais.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                <SaveButton
                  label="Escores dos modelos (TXT)"
                  filename="model_scores.txt"
                  saving={saving}
                  onSave={handleSave}
                  primary
                />
                <SaveButton
                  label="Imagem de entrada"
                  filename="input_image.png"
                  saving={saving}
                  onSave={handleSave}
                />
                <SaveButton
                  label="FFT entrada"
                  filename="input_fft.png"
                  saving={saving}
                  onSave={handleSave}
                />
                {generateVisuals && (
                  <>
                    <SaveButton
                      label="Residuo NLM"
                      filename="nlm_residue.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="FFT NLM"
                      filename="nlm_fft.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="Residuo mediana"
                      filename="median_residue.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="FFT mediana"
                      filename="median_fft.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                  </>
                )}
              </div>
              {saveMessage && (
                <div style={{ marginTop: "0.75rem" }}>
                  <MessageBox type={saveMessage.type} text={saveMessage.text} />
                </div>
              )}
            </div>
          )}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

function SaveButton({
  label,
  filename,
  saving,
  onSave,
  primary,
}: {
  label: string;
  filename: string;
  saving: string | null;
  onSave: (filename: string, label: string) => void;
  primary?: boolean;
}) {
  const busy = saving === filename;
  return (
    <button
      type="button"
      disabled={!!saving}
      onClick={() => onSave(filename, label)}
      style={{
        padding: "0.45rem 0.85rem",
        fontSize: "0.8rem",
        borderRadius: 6,
        border: primary ? "none" : "1px solid #d1d5db",
        background: primary ? "#1a1a2e" : "#fff",
        color: primary ? "#fff" : "#374151",
        cursor: saving ? "not-allowed" : "pointer",
        opacity: saving && !busy ? 0.6 : 1,
      }}
    >
      {busy ? "Salvando…" : label}
    </button>
  );
}

const imgStyle: React.CSSProperties = {
  width: "100%",
  borderRadius: 6,
  border: "1px solid #e5e7eb",
  display: "block",
};
const capStyle: React.CSSProperties = { fontSize: "0.78rem", color: "#6b7280", marginTop: 4, textAlign: "center" };
const placeholderStyle: React.CSSProperties = {
  aspectRatio: "1",
  minHeight: 180,
  background: "#f3f4f6",
  borderRadius: 6,
  border: "1px solid #e5e7eb",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#9ca3af",
  fontSize: "0.8rem",
};
