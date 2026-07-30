import { useCallback, useState } from "react";
import { useParams } from "react-router-dom";
import VideoPlayer, { useVideoEvidenceUrl } from "@/components/VideoPlayer";
import TechniquePageShell from "@/components/TechniquePageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";

type ClipRow = { start_frame: number; score: number; decision: string };

export default function StilVideoAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [report, setReport] = useState<{
    video_decision: string;
    mean_score: number;
    max_score: number;
    max_start_frame: number;
    clips: ClipRow[];
  } | null>(null);
  const [selectedFrame, setSelectedFrame] = useState<number | null>(null);
  const [chartUrl, setChartUrl] = useState<string | null>(null);
  const { running, error, progress, progressLabel, currentJobId, runAnalysis, fetchImage, fetchResultJson, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime("stil_video_detection");
  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  const applyEvidence = useCallback(
    (_id: string, _source: "original" | "derivative") => {
      reset();
      setReport(null);
      setChartUrl(null);
      setSelectedFrame(null);
      clearMessage();
    },
    [reset, clearMessage],
  );

  const { embedded, showEvidencePicker, evidenceId, onSelectEvidence } = useGroupAwareEvidence(
    caseId!,
    applyEvidence,
  );

  const videoUrl = useVideoEvidenceUrl(evidenceId);

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    clearMessage();
    await runAnalysis(evidenceId, "stil_video_detection", { sample_every: 4, max_frames: 64 }, {
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
    await save(currentJobId, artifactFilename, label, { sample_every: 4, max_frames: 64 });
  }

  if (!caseId) return null;

  const parametersPanel = (
    <>
      <div style={{ marginTop: "1rem" }}>
        <button
          type="button"
          onClick={process}
          disabled={!evidenceId || runtimeOk !== true || running}
          style={btnPrimary}
        >
          {running ? "Processando…" : "Analisar com STIL"}
        </button>
      </div>
      {running && <p style={{ fontSize: "0.8rem", color: "#6b7280" }}>Progresso: {Math.round(progress)}%</p>}
    </>
  );

  const resultPanel = (
    <>
      <VideoPlayer src={videoUrl} seekFrame={selectedFrame} />

      {report && (
        <div style={{ marginTop: "1rem" }}>
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
                style={btnSecondary}
              >
                {saving ? "Salvando…" : "Salvar relatorio JSON"}
              </button>
              <button
                type="button"
                onClick={() => void saveDerivativeReport("stil_scores_chart.png", "STIL — grafico")}
                disabled={saving}
                style={btnSecondary}
              >
                Salvar grafico PNG
              </button>
            </div>
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
        </div>
      )}
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="stil_video_detection"
      mediaType="video"
      embedded={embedded}
      evidenceId={evidenceId}
      onSelectEvidence={onSelectEvidence as never}
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

const btnSecondary: React.CSSProperties = {
  padding: "0.45rem 0.75rem",
  borderRadius: 6,
  border: "1px solid #1a1a2e",
  background: "#fff",
  cursor: "pointer",
  fontSize: "0.8rem",
};
