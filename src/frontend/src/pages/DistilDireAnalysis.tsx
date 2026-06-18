import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer from "@/components/SyncedImagePairViewer";
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

const META = FORENSIC_TECHNIQUE_META.distildire;

type DistilDireReport = {
  df_probability: number;
  prediction: string;
  threshold: number;
  checkpoint: string;
  inference_device: string;
};

function decisionColor(prediction: string) {
  const p = prediction.toUpperCase();
  if (p.includes("FAKE") || p.includes("SINT")) return "#dc2626";
  return "#16a34a";
}

export default function DistilDireAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [checkpoint, setCheckpoint] = useState<"imagenet" | "celebahq">("imagenet");
  const [threshold, setThreshold] = useState(0.5);
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [report, setReport] = useState<DistilDireReport | null>(null);
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [epsUrl, setEpsUrl] = useState<string | null>(null);
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
        const t = res.data.find((x) => x.name === "distildire");
        setRuntimeOk(t ? t.available !== false : false);
        setRuntimeReason(t?.unavailable_reason || "DistilDIRE nao registrado.");
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Falha ao verificar DistilDIRE.");
      });
  }, []);

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setReport(null);
      setInputUrl(`/api/v1/evidences/${id}/file`);
      setEpsUrl(null);
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
        "distildire",
        { checkpoint, threshold, generate_visuals: true },
        {
          onArtifactsLoaded: async (jobId, jobResult) => {
            const parsed = await fetchResultJson<DistilDireReport>(jobId, "distildire_report.json");
            if (parsed) {
              setReport(parsed);
            } else if (typeof jobResult.df_probability === "number") {
              setReport({
                df_probability: jobResult.df_probability as number,
                prediction: String(jobResult.prediction ?? ""),
                threshold: Number(jobResult.threshold ?? threshold),
                checkpoint: String(jobResult.checkpoint ?? checkpoint),
                inference_device: String(jobResult.inference_device ?? ""),
              });
            }
            const [input, eps] = await Promise.all([
              fetchImage(jobId, "input_image.png"),
              fetchImage(jobId, "distildire_eps_heatmap.png"),
            ]);
            if (input) setInputUrl(input);
            setEpsUrl(eps);
          },
        }
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
      const res = await saveDerivative({ job_id: currentJobId, artifact_filename: "distildire_report.json" });
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

  const pctScore = report ? Math.round(report.df_probability * 100) : 0;

  return (
    <AnalysisPageShell caseId={caseId!} title={META.title} intro={<TechniqueReferenceIntro meta={META} />} embedded={embedded}>
      {runtimeOk === false && (
        <MessageBox type="err" text={runtimeReason || "DistilDIRE indisponivel neste servidor."} />
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
              Checkpoint treinado
              <select
                value={checkpoint}
                onChange={(e) => setCheckpoint(e.target.value as "imagenet" | "celebahq")}
                style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.4rem" }}
              >
                <option value="imagenet">ImageNet (geral)</option>
                <option value="celebahq">CelebA-HQ (rostos)</option>
              </select>
            </label>
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
            <ProcessButton onClick={process} running={running} disabled={!evidenceId || runtimeOk === false} label="Analisar imagem" />
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
          <SyncedImagePairViewer
            leftSrc={inputUrl ?? ""}
            leftLabel="Evidencia (preview)"
            rightSrc={epsUrl}
            rightLabel="Mapa do ruido DDIM (eps)"
          />
        </AnalysisPanel>
      </div>

      {report && (
        <AnalysisPanel title="Resultado DistilDIRE">
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
              <strong>Classificacao:</strong>{" "}
              <span style={{ color: decisionColor(report.prediction), fontWeight: 700 }}>
                {report.prediction}
              </span>
            </div>
            <div>
              <strong>Prob. sintetica:</strong> {report.df_probability.toFixed(4)} ({pctScore}%)
            </div>
            <div>
              <strong>Limiar:</strong> {report.threshold.toFixed(2)}
            </div>
            <div>
              <strong>Checkpoint:</strong> {report.checkpoint}
            </div>
            <div>
              <strong>Dispositivo:</strong> {formatInferenceDevice(report.inference_device)}
            </div>
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
                background: pctScore >= report.threshold * 100 ? "#dc2626" : "#16a34a",
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
