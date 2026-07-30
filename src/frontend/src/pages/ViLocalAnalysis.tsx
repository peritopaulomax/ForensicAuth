import { useCallback, useState } from "react";
import { useParams } from "react-router-dom";
import VideoPlayer, { useVideoEvidenceUrl } from "@/components/VideoPlayer";
import TechniquePageShell from "@/components/TechniquePageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";

type ClipRow = {
  start_frame: number;
  mean_mask_ratio: number;
  max_mask_ratio: number;
};

const PARAMS = { sample_every: 5, max_clips: 24, clip_len: 5 };

export default function ViLocalAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [report, setReport] = useState<{
    mean_mask_ratio: number;
    max_mask_ratio: number;
    max_start_frame: number;
    threshold?: number;
    clips: ClipRow[];
  } | null>(null);
  const [selectedFrame, setSelectedFrame] = useState<number | null>(null);
  const [chartUrl, setChartUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [maskUrl, setMaskUrl] = useState<string | null>(null);
  const [heatmapUrl, setHeatmapUrl] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"heatmap" | "overlay" | "mask">("heatmap");
  const { running, error, progress, progressLabel, currentJobId, runAnalysis, fetchImage, fetchResultJson, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime("vilocal");
  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  const applyEvidence = useCallback(
    (_id: string, _source: "original" | "derivative") => {
      reset();
      setReport(null);
      setChartUrl(null);
      setOverlayUrl(null);
      setMaskUrl(null);
      setHeatmapUrl(null);
      setSelectedFrame(null);
      setViewMode("heatmap");
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
    await runAnalysis(evidenceId, "vilocal", { ...PARAMS }, {
      onArtifactsLoaded: async (jobId) => {
        const parsed = await fetchResultJson<{
          mean_mask_ratio: number;
          max_mask_ratio: number;
          max_start_frame: number;
          threshold?: number;
          clips: ClipRow[];
        }>(jobId, "vilocal_report.json");
        if (parsed) {
          setReport(parsed);
          setSelectedFrame(parsed.max_start_frame);
        }
        setChartUrl((await fetchImage(jobId, "vilocal_scores_chart.png")) ?? null);
        setOverlayUrl((await fetchImage(jobId, "vilocal_overlay_preview.png")) ?? null);
        setMaskUrl((await fetchImage(jobId, "vilocal_mask_preview.png")) ?? null);
        setHeatmapUrl((await fetchImage(jobId, "vilocal_heatmap_preview.png")) ?? null);
        setViewMode("heatmap");
      },
    });
  }

  async function saveDerivativeReport(artifactFilename: string, label: string) {
    if (!currentJobId) return;
    await save(currentJobId, artifactFilename, label, { ...PARAMS });
  }

  if (!caseId) return null;

  const previewUrl =
    viewMode === "mask" ? maskUrl : viewMode === "overlay" ? overlayUrl : heatmapUrl;

  const parametersPanel = (
    <>
      <div style={{ marginTop: "1rem" }}>
        <button
          type="button"
          onClick={process}
          disabled={!evidenceId || runtimeOk !== true || running}
          style={btnPrimary}
        >
          {running ? "Processando…" : "Analisar com ViLocal"}
        </button>
      </div>
      {running && (
        <p style={{ fontSize: "0.8rem", color: "#6b7280" }}>
          Progresso: {Math.round(progress)}% {progressLabel ? `· ${progressLabel}` : ""}
        </p>
      )}
    </>
  );

  const resultPanel = (
    <>
      <VideoPlayer src={videoUrl} seekFrame={selectedFrame} />

      {report && (
        <div style={{ marginTop: "1rem" }}>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["heatmap", "Heatmap"],
                ["overlay", "Overlay"],
                ["mask", "Máscara"],
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                style={viewMode === mode ? btnPrimary : btnSecondary}
              >
                {label}
              </button>
            ))}
          </div>
          {previewUrl && (
            <img
              src={previewUrl}
              alt={`ViLocal ${viewMode}`}
              style={{ width: "100%", maxHeight: 320, objectFit: "contain", marginBottom: "0.75rem" }}
            />
          )}
          <p>
            <strong>Máscara média:</strong> {report.mean_mask_ratio.toFixed(4)} ·{" "}
            <strong>Máx clip:</strong> {report.max_mask_ratio.toFixed(4)} (frame {report.max_start_frame})
            {report.threshold != null && (
              <>
                {" "}
                · <strong>Limiar binário:</strong> {report.threshold}
              </>
            )}
          </p>
          <p style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.35rem" }}>
            Sem rótulo autêntico/manipulado. Protocolo oficial: clips de {PARAMS.clip_len} frames em{" "}
            240×432; heatmap = logits (inv-sigmoid do score contínuo).
          </p>
          {chartUrl && <img src={chartUrl} alt="ViLocal scores" style={{ width: "100%", maxHeight: 220 }} />}
          {currentJobId && (
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
              <button
                type="button"
                onClick={() => void saveDerivativeReport("vilocal_report.json", "ViLocal — relatório")}
                disabled={saving}
                style={btnSecondary}
              >
                {saving ? "Salvando…" : "Salvar relatório JSON"}
              </button>
              {heatmapUrl && (
                <button
                  type="button"
                  onClick={() => void saveDerivativeReport("vilocal_heatmap_preview.png", "ViLocal — heatmap")}
                  disabled={saving}
                  style={btnSecondary}
                >
                  Salvar heatmap PNG
                </button>
              )}
              {overlayUrl && (
                <button
                  type="button"
                  onClick={() => void saveDerivativeReport("vilocal_overlay_preview.png", "ViLocal — overlay")}
                  disabled={saving}
                  style={btnSecondary}
                >
                  Salvar overlay PNG
                </button>
              )}
              {maskUrl && (
                <button
                  type="button"
                  onClick={() => void saveDerivativeReport("vilocal_mask_preview.png", "ViLocal — máscara")}
                  disabled={saving}
                  style={btnSecondary}
                >
                  Salvar máscara PNG
                </button>
              )}
            </div>
          )}
          {saveMessage && (
            <p style={{ fontSize: "0.8rem", color: saveMessage.type === "ok" ? "#047857" : "#b91c1c" }}>
              {saveMessage.text}
            </p>
          )}
          <div style={{ maxHeight: 240, overflow: "auto", marginTop: "0.5rem" }}>
            <table style={{ width: "100%", fontSize: "0.78rem" }}>
              <thead>
                <tr>
                  <th>Frame início</th>
                  <th>Máscara média</th>
                </tr>
              </thead>
              <tbody>
                {report.clips?.map((c) => (
                  <tr
                    key={c.start_frame}
                    onClick={() => setSelectedFrame(c.start_frame)}
                    style={{
                      cursor: "pointer",
                      background: selectedFrame === c.start_frame ? "#eff6ff" : undefined,
                    }}
                  >
                    <td>{c.start_frame}</td>
                    <td>{c.mean_mask_ratio.toFixed(4)}</td>
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
      techniqueId="vilocal"
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
  background: "#1d4ed8",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  padding: "0.5rem 1rem",
  cursor: "pointer",
  fontWeight: 600,
};

const btnSecondary: React.CSSProperties = {
  background: "#f3f4f6",
  color: "#111827",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  padding: "0.35rem 0.75rem",
  cursor: "pointer",
  fontSize: "0.8rem",
};
