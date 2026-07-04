import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import AnalysisPageShell, {
  AnalysisPanel,
  MessageBox,
  ProcessButton,
  formatInferenceDevice,
  parseDeviceFromProgress,
} from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";

const META = FORENSIC_TECHNIQUE_META.presentation_attack_detection;

type PadReport = {
  label: string;
  raw_label?: string;
  score: number;
  threshold: number;
  bbox: { x: number; y: number; w: number; h: number };
  inference_device: string;
  models_used?: string[];
};

function decisionColor(label: string) {
  return label === "real" ? "#16a34a" : "#dc2626";
}

export default function PresentationAttackDetectionAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [threshold, setThreshold] = useState(0.5);
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [report, setReport] = useState<PadReport | null>(null);
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [annotatedUrl, setAnnotatedUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const {
    running,
    currentJobId,
    error,
    progress,
    progressLabel,
    runAnalysis,
    fetchImage,
    fetchResultJson,
    reset,
  } = useForensicJob();

  const inferenceDevice = parseDeviceFromProgress(progressLabel);

  useEffect(() => {
    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((res) => {
        const t = res.data.find((x) => x.name === "presentation_attack_detection");
        setRuntimeOk(t ? t.available !== false : false);
        setRuntimeReason(t?.unavailable_reason || "PAD nao registrado.");
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Falha ao verificar PAD.");
      });
  }, []);

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setReport(null);
      setInputUrl(`/api/v1/evidences/${id}/file`);
      setAnnotatedUrl(null);
      setSaveMessage(null);
    },
    [reset],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    setSaveMessage(null);
    try {
      await runAnalysis(
        evidenceId,
        "presentation_attack_detection",
        { threshold },
        {
          onArtifactsLoaded: async (jobId, jobResult) => {
            const parsed = await fetchResultJson<PadReport>(jobId, "pad_result.json");
            if (parsed) {
              setReport(parsed);
            } else if (typeof jobResult.label === "string") {
              setReport({
                label: String(jobResult.label),
                raw_label: String(jobResult.raw_label ?? jobResult.label),
                score: Number(jobResult.score ?? 0),
                threshold: Number(jobResult.threshold ?? threshold),
                bbox: (jobResult.bbox as PadReport["bbox"]) ?? { x: 0, y: 0, w: 0, h: 0 },
                inference_device: String(jobResult.inference_device ?? ""),
                models_used: Array.isArray(jobResult.models_used) ? (jobResult.models_used as string[]) : undefined,
              });
            }
            const [input, annotated] = await Promise.all([
              fetchImage(jobId, "pad_annotated.png"),
              fetchImage(jobId, "pad_face_crop.png"),
            ]);
            if (input) setAnnotatedUrl(input);
            setInputUrl(annotated ?? inputUrl);
          },
        },
      );
    } catch {
      /* hook sets error */
    }
  }

  async function handleSave() {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({ job_id: currentJobId, artifact_filename: "pad_result.json" });
      setSaveMessage({
        type: "ok",
        text: `Relatorio salvo. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: String(msg) });
    } finally {
      setSaving(false);
    }
  }

  const pctScore = report ? Math.round(report.score * 100) : 0;

  return (
    <AnalysisPageShell
      caseId={caseId!}
      title={META.title}
      intro={<TechniqueReferenceIntro meta={META} techniqueId="presentation_attack_detection" />}
      embedded={embedded}
    >
      {runtimeOk === false && (
        <MessageBox type="err" text={runtimeReason || "PAD indisponivel neste servidor."} />
      )}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 1fr) minmax(320px, 1.2fr)", gap: "1rem" }}>
        <AnalysisPanel title="Evidencia e parametros">
          {showEvidencePicker && (
            <ImageEvidenceSelector
              caseId={caseId!}
              selectedId={evidenceId}
              selectionSource={selectionSource}
              onSelect={onSelectEvidence}
            />
          )}

          <div style={{ marginTop: "1rem", display: "grid", gap: "0.65rem" }}>
            <label style={{ fontSize: "0.82rem", color: "#374151" }}>
              Limiar de decisao ({threshold.toFixed(2)})
              <input
                type="range"
                min={0.1}
                max={0.9}
                step={0.05}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                style={{ display: "block", width: "100%", marginTop: "0.25rem" }}
              />
            </label>
          </div>

          <div style={{ marginTop: "1rem" }}>
            <ProcessButton
              onClick={process}
              running={running}
              disabled={!evidenceId || runtimeOk === false}
              label="Analisar imagem"
            />
          </div>

          {running && (
            <p style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "#6b7280" }}>
              Progresso: {Math.round(progress)}%
              {inferenceDevice && (
                <>
                  {" "}
                  — {formatInferenceDevice(inferenceDevice)}
                </>
              )}
              {progressLabel ? ` — ${progressLabel}` : ""}
            </p>
          )}
          {error && <MessageBox type="err" text={error} />}
        </AnalysisPanel>

        <AnalysisPanel title="Visualizacao">
          <div style={{ display: "grid", gap: "1rem" }}>
            {annotatedUrl ? (
              <figure style={{ margin: 0 }}>
                <img
                  src={annotatedUrl}
                  alt="Face detectada e classificada"
                  style={{ maxWidth: "100%", height: "auto", borderRadius: 6, border: "1px solid #e5e7eb" }}
                />
                <figcaption style={{ marginTop: "0.35rem", fontSize: "0.78rem", color: "#6b7280" }}>
                  Face detectada e classificada
                </figcaption>
              </figure>
            ) : inputUrl ? (
              <figure style={{ margin: 0 }}>
                <img
                  src={inputUrl}
                  alt="Preview da evidencia"
                  style={{ maxWidth: "100%", height: "auto", borderRadius: 6, border: "1px solid #e5e7eb" }}
                />
                <figcaption style={{ marginTop: "0.35rem", fontSize: "0.78rem", color: "#6b7280" }}>
                  Preview da evidencia
                </figcaption>
              </figure>
            ) : (
              <div
                style={{
                  minHeight: 200,
                  background: "#f9fafb",
                  borderRadius: 6,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#9ca3af",
                  fontSize: "0.85rem",
                }}
              >
                —
              </div>
            )}
          </div>
        </AnalysisPanel>
      </div>

      {report && (
        <AnalysisPanel title="Resultado PAD">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: "0.75rem",
              marginBottom: "1rem",
              fontSize: "0.9rem",
            }}
          >
            <div>
              <strong>Classificação:</strong>{" "}
              <span style={{ color: decisionColor(report.label), fontWeight: 700 }}>
                {report.label === "real" ? "Rosto real" : "Ataque de apresentacao"}
              </span>
            </div>
            <div>
              <strong>Score (real):</strong> {report.score.toFixed(4)} ({pctScore}%)
            </div>
            <div>
              <strong>Limiar:</strong> {report.threshold.toFixed(2)}
            </div>
            <div>
              <strong>Dispositivo:</strong> {formatInferenceDevice(report.inference_device)}
            </div>
            {report.models_used && (
              <div>
                <strong>Modelos:</strong> {report.models_used.join(", ")}
              </div>
            )}
          </div>

          <div
            style={{
              height: 10,
              borderRadius: 5,
              background: "#e5e7eb",
              overflow: "hidden",
              maxWidth: 420,
              marginBottom: "1rem",
            }}
          >
            <div
              style={{
                width: `${pctScore}%`,
                height: "100%",
                background: report.label === "real" ? "#16a34a" : "#dc2626",
                transition: "width 0.3s",
              }}
            />
          </div>

          {report.bbox && (
            <p style={{ margin: "0 0 1rem", fontSize: "0.82rem", color: "#4b5563" }}>
              <strong>Bounding box:</strong> x={report.bbox.x}, y={report.bbox.y}, w={report.bbox.w}, h={report.bbox.h}
            </p>
          )}

          {currentJobId && (
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                style={{
                  padding: "0.45rem 0.9rem",
                  borderRadius: 6,
                  border: "none",
                  background: "#1a1a2e",
                  color: "#fff",
                  cursor: saving ? "wait" : "pointer",
                }}
              >
                {saving ? "Salvando…" : "Salvar relatorio no caso"}
              </button>
              {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
            </div>
          )}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}
