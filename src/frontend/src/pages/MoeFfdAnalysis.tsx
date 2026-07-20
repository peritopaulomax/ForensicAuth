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

const META = FORENSIC_TECHNIQUE_META.moe_ffd;

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
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [report, setReport] = useState<MoeFfdReport | null>(null);
  const [inputUrl, setInputUrl] = useState<string | null>(null);
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
        const t = res.data.find((x) => x.name === "moe_ffd");
        setRuntimeOk(t ? t.available !== false : false);
        setRuntimeReason(t?.unavailable_reason || "MoE-FFD nao registrado.");
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Falha ao verificar MoE-FFD.");
      });
  }, []);

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setReport(null);
      setInputUrl(`/api/v1/evidences/${id}/file`);
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
      /* hook sets error */
    }
  }

  async function handleSave() {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({ job_id: currentJobId, artifact_filename: "moe_ffd_result.json" });
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

  const pctFake = report ? Math.round(report.fake_prob * 100) : 0;

  return (
    <AnalysisPageShell
      caseId={caseId!}
      title={META.title}
      intro={<TechniqueReferenceIntro meta={META} techniqueId="moe_ffd" />}
      embedded={embedded}
    >
      {runtimeOk === false && (
        <MessageBox
          type="err"
          text={
            runtimeReason ||
            "MoE-FFD indisponivel neste servidor. Se a mensagem citar gates/w_gate, o MoE-FFD.tar do Hugging Face e um checkpoint de treino invalido — nao use estes scores."
          }
        />
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
        </AnalysisPanel>
      </div>

      {report && (
        <AnalysisPanel title="Resultado MoE-FFD">
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
              {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
            </div>
          )}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}
