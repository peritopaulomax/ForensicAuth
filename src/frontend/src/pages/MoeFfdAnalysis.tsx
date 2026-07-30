import { useCallback, useState } from "react";
import { useParams } from "react-router-dom";
import { formatInferenceDevice, parseDeviceFromProgress } from "@/components/AnalysisPageShell";
import TechniquePageShell from "@/components/TechniquePageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";

type MoeFfdReport = {
  label: string;
  fake_prob: number;
  real_prob: number;
  score: number;
  threshold: number;
  inference_device: string;
  model_checkpoint?: string;
  face_cropped?: boolean;
  face_confidence?: number | null;
  face_margin?: number | null;
  preprocess?: string;
};

function decisionColor(label: string) {
  return label === "real" ? "#16a34a" : "#dc2626";
}

export default function MoeFfdAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [threshold, setThreshold] = useState(0.5);
  const [report, setReport] = useState<MoeFfdReport | null>(null);
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();

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

  const { status: runtimeStatus } = useTechniqueRuntime("moe_ffd");
  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  const inferenceDevice = parseDeviceFromProgress(progressLabel);

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setReport(null);
      setInputUrl(`/api/v1/evidences/${id}/file`);
      clearMessage();
    },
    [reset, clearMessage],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    clearMessage();
    try {
      await runAnalysis(
        evidenceId,
        "moe_ffd",
        { threshold },
        {
          onArtifactsLoaded: async (jobId, jobResult) => {
            const parsed = await fetchResultJson<MoeFfdReport>(jobId, "moe_ffd_result.json");
            if (parsed) {
              setReport(parsed);
            } else if (typeof jobResult.label === "string") {
              setReport({
                label: String(jobResult.label),
                fake_prob: Number(jobResult.fake_prob ?? jobResult.score ?? 0),
                real_prob: Number(jobResult.real_prob ?? 0),
                score: Number(jobResult.score ?? jobResult.fake_prob ?? 0),
                threshold: Number(jobResult.threshold ?? threshold),
                inference_device: String(jobResult.inference_device ?? ""),
                model_checkpoint: jobResult.model_checkpoint
                  ? String(jobResult.model_checkpoint)
                  : undefined,
              });
            }
            const preview = await fetchImage(jobId, "moe_ffd_input.png");
            if (preview) setInputUrl(preview);
          },
        },
      );
    } catch {
    }
  }

  async function handleSave() {
    if (!currentJobId) return;
    await save(currentJobId, "moe_ffd_result.json", "Relatorio MoE-FFD");
  }

  const pctFake = report ? Math.round(report.fake_prob * 100) : 0;

  if (!caseId) return null;

  const parametersPanel = (
    <>
      <div style={{ display: "grid", gap: "0.65rem" }}>
        <label style={{ fontSize: "0.82rem", color: "#374151" }}>
          Limiar fake ({threshold.toFixed(2)})
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
        <p style={{ margin: 0, fontSize: "0.78rem", color: "#6b7280" }}>
          Pré-processamento: <strong>RetinaFace</strong> detecta a face principal, aplica crop
          quadrado com margem (padrão 1.3×) e só então o resize 224×224 oficial do MoE-FFD.
          Softmax classe 1 = forgery. Evite mosaicos com várias faces (usa a de maior confiança).
        </p>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <button
          type="button"
          onClick={process}
          disabled={!evidenceId || runtimeOk !== true || running}
          style={btnPrimary}
        >
          {running ? "Processando…" : "Analisar imagem"}
        </button>
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
    </>
  );

  const resultPanel = (
    <>
      {inputUrl ? (
        <figure style={{ margin: 0 }}>
          <img
            src={inputUrl}
            alt="Preview da evidencia"
            style={{ maxWidth: "100%", height: "auto", borderRadius: 6, border: "1px solid #e5e7eb" }}
          />
          <figcaption style={{ marginTop: "0.35rem", fontSize: "0.78rem", color: "#6b7280" }}>
            {report?.face_cropped
              ? "Crop facial (RetinaFace) enviado ao modelo"
              : "Preview da entrada"}
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

      {report && (
        <div style={{ marginTop: "1.5rem" }}>
          <h4 style={{ fontSize: "0.95rem", margin: "0 0 0.75rem" }}>Resultado MoE-FFD</h4>
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
                {report.label === "real" ? "Bonafide (real)" : "Forgery (fake)"}
              </span>
            </div>
            <div>
              <strong>P(fake):</strong> {report.fake_prob.toFixed(4)} ({pctFake}%)
            </div>
            <div>
              <strong>P(real):</strong> {report.real_prob.toFixed(4)}
            </div>
            <div>
              <strong>Limiar:</strong> {report.threshold.toFixed(2)}
            </div>
            <div>
              <strong>Dispositivo:</strong> {formatInferenceDevice(report.inference_device)}
            </div>
            {report.model_checkpoint && (
              <div>
                <strong>Checkpoint:</strong> {report.model_checkpoint}
              </div>
            )}
            {report.face_cropped != null && (
              <div>
                <strong>Crop facial:</strong>{" "}
                {report.face_cropped
                  ? `sim${
                      report.face_confidence != null
                        ? ` (conf=${Number(report.face_confidence).toFixed(3)})`
                        : ""
                    }`
                  : "não"}
              </div>
            )}
            {report.preprocess && (
              <div>
                <strong>Preprocess:</strong> {report.preprocess}
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
                width: `${pctFake}%`,
                height: "100%",
                background: report.label === "fake" ? "#dc2626" : "#16a34a",
                transition: "width 0.3s",
              }}
            />
          </div>

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
            </div>
          )}
        </div>
      )}
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="moe_ffd"
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
      runtimeReason={runtimeReason}
      parametersPanel={parametersPanel}
      resultPanel={resultPanel}
    />
  );
}

const btnPrimary: React.CSSProperties = {
  padding: "0.5rem 1rem",
  background: "#0369a1",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
};
