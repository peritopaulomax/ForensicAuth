import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import MediaEvidenceSelector from "@/components/MediaEvidenceSelector";
import VideoPlayer, { useVideoEvidenceUrl } from "@/components/VideoPlayer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";

const META = FORENSIC_TECHNIQUE_META.stil_video_detection;

type ClipRow = { start_frame: number; score: number; decision: string };

export default function StilVideoAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [report, setReport] = useState<{
    video_decision: string;
    mean_score: number;
    max_score: number;
    max_start_frame: number;
    clips: ClipRow[];
  } | null>(null);
  const [selectedFrame, setSelectedFrame] = useState<number | null>(null);
  const [chartUrl, setChartUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const videoUrl = useVideoEvidenceUrl(selectedEvidence);
  const { running, error, progress, currentJobId, runAnalysis, fetchImage, fetchResultJson, reset } =
    useForensicJob();

  useEffect(() => {
    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((res) => {
        const t = res.data.find((x) => x.name === "stil_video_detection");
        setRuntimeOk(t ? t.available !== false : false);
        setRuntimeReason(t?.unavailable_reason || "STIL nao registrado.");
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Falha ao verificar STIL.");
      });
  }, []);

  const onSelect = useCallback(
    (id: string) => {
      setSelectedEvidence(id);
      reset();
      setReport(null);
      setChartUrl(null);
      setSelectedFrame(null);
      setSaveMessage(null);
    },
    [reset]
  );

  async function process() {
    if (!selectedEvidence || !runtimeOk) return;
    await runAnalysis(selectedEvidence, "stil_video_detection", { sample_every: 4, max_frames: 64 }, {
      onArtifactsLoaded: async (jobId) => {
        const parsed = await fetchResultJson<{
          video_decision: string;
          mean_score: number;
          max_score: number;
          max_start_frame: number;
          clips: ClipRow[];
        }>(jobId, "stil_report.json");
        if (parsed) {
          setReport(parsed);
          setSelectedFrame(parsed.max_start_frame);
        }
        setChartUrl((await fetchImage(jobId, "stil_scores_chart.png")) ?? null);
      },
    });
  }

  async function saveDerivativeReport(artifactFilename: string, label: string) {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await saveDerivative({
        job_id: currentJobId,
        artifact_filename: artifactFilename,
        label,
        effective_parameters: { sample_every: 4, max_frames: 64 },
      });
      setSaveMessage({ type: "ok", text: `${label} salvo no caso.` });
    } catch (e) {
      setSaveMessage({ type: "err", text: e instanceof Error ? e.message : "Falha ao salvar derivado." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <AnalysisPageShell caseId={caseId!} title={META.title} subtitle={META.cardSubtitle}>
      <TechniqueReferenceIntro meta={META} />
      {runtimeOk === false && (
        <MessageBox type="err" text={runtimeReason} />
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: "1rem" }}>
        <AnalysisPanel title="Evidencia">
          <MediaEvidenceSelector caseId={caseId!} fileType="video" selectedId={selectedEvidence} onSelect={onSelect} />
          <div style={{ marginTop: "1rem" }}>
            <ProcessButton
            onClick={process}
            running={running}
            disabled={!selectedEvidence || runtimeOk === false}
            label="Analisar com STIL"
          />
          </div>
          {running && <p style={{ fontSize: "0.8rem", color: "#6b7280" }}>Progresso: {Math.round(progress)}%</p>}
          {error && <MessageBox type="err" text={error} />}
        </AnalysisPanel>
        <AnalysisPanel title="Video">
          <VideoPlayer src={videoUrl} seekFrame={selectedFrame} />
        </AnalysisPanel>
      </div>
      {report && (
        <div style={{ marginTop: "1rem" }}>
        <AnalysisPanel title="Resultados STIL">
          <p>
            <strong>Decisao:</strong> {report.video_decision} · <strong>Score max:</strong>{" "}
            {report.max_score.toFixed(4)} (frame {report.max_start_frame})
          </p>
          {chartUrl && <img src={chartUrl} alt="STIL scores" style={{ width: "100%", maxHeight: 220 }} />}
          {currentJobId && (
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
              <button
                type="button"
                onClick={() => void saveDerivativeReport("stil_report.json", "STIL — relatorio")}
                disabled={saving}
                style={{
                  padding: "0.45rem 0.75rem",
                  borderRadius: 6,
                  border: "1px solid #1a1a2e",
                  background: "#fff",
                  cursor: saving ? "wait" : "pointer",
                  fontSize: "0.8rem",
                }}
              >
                {saving ? "Salvando…" : "Salvar relatorio JSON"}
              </button>
              <button
                type="button"
                onClick={() => void saveDerivativeReport("stil_scores_chart.png", "STIL — grafico")}
                disabled={saving}
                style={{
                  padding: "0.45rem 0.75rem",
                  borderRadius: 6,
                  border: "1px solid #1a1a2e",
                  background: "#fff",
                  cursor: saving ? "wait" : "pointer",
                  fontSize: "0.8rem",
                }}
              >
                Salvar grafico PNG
              </button>
            </div>
          )}
          {saveMessage && (
            <p
              style={{
                margin: "0.5rem 0 0",
                fontSize: "0.78rem",
                color: saveMessage.type === "ok" ? "#166534" : "#991b1b",
              }}
            >
              {saveMessage.text}
            </p>
          )}
          <div style={{ maxHeight: 240, overflow: "auto", marginTop: "0.5rem" }}>
            <table style={{ width: "100%", fontSize: "0.78rem" }}>
              <thead>
                <tr>
                  <th>Frame inicio</th>
                  <th>Score</th>
                  <th>Decisao</th>
                </tr>
              </thead>
              <tbody>
                {report.clips?.map((c) => (
                  <tr
                    key={c.start_frame}
                    onClick={() => setSelectedFrame(c.start_frame)}
                    style={{ cursor: "pointer", background: selectedFrame === c.start_frame ? "#eff6ff" : undefined }}
                  >
                    <td>{c.start_frame}</td>
                    <td>{c.score.toFixed(4)}</td>
                    <td>{c.decision}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AnalysisPanel>
        </div>
      )}
    </AnalysisPageShell>
  );
}
