import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import MediaEvidenceSelector from "@/components/MediaEvidenceSelector";
import VideoPlayer, { useVideoEvidenceUrl } from "@/components/VideoPlayer";
import AnalysisPageShell, {
  AnalysisPanel,
  MessageBox,
  ProcessButton,
  formatInferenceDevice,
  parseDeviceFromProgress,
} from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";

const VIDEOFACT_META = FORENSIC_TECHNIQUE_META.videofact;
import { useForensicJob } from "@/hooks/useForensicJob";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";

type VideoFactMode = "both" | "xfer" | "df";

type FrameRow = {
  frame_idx: number;
  score: number;
  decision: string;
  heatmap?: string | null;
};

type ModeResult = {
  mode: string;
  model_label: string;
  threshold: number;
  video_decision: string;
  mean_score: number;
  max_score: number;
  max_frame_idx: number;
  frames: FrameRow[];
};

const PROGRESS_STAGES = [
  { min: 0, label: "Preparacao e carregamento VideoFACT" },
  { min: 15, label: "Amostragem de frames do video" },
  { min: 40, label: "Inferencia (edicoes / deepfake)" },
  { min: 85, label: "Mapas de localizacao e relatorio" },
];

function ProgressChecklist({
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
          Dispositivo:{" "}
          <strong style={{ color: inferenceDevice === "CPU" ? "#b45309" : "#1d4ed8" }}>
            {formatInferenceDevice(inferenceDevice)}
          </strong>
        </p>
      )}
      <ul style={{ margin: 0, padding: 0, listStyle: "none", fontSize: "0.78rem", display: "grid", gap: "0.3rem" }}>
        {PROGRESS_STAGES.map((stage, idx) => {
          const nextMin = PROGRESS_STAGES[idx + 1]?.min ?? 101;
          const done = pct >= nextMin;
          const active = pct >= stage.min && pct < nextMin;
          return (
            <li
              key={stage.min}
              style={{
                display: "flex",
                gap: "0.45rem",
                color: done ? "#166534" : active ? "#1a1a2e" : "#9ca3af",
                fontWeight: active ? 600 : 400,
              }}
            >
              <span style={{ width: "1rem", textAlign: "center" }}>{done ? "✓" : active ? "●" : "○"}</span>
              <span>{stage.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function decisionColor(decision: string) {
  const d = decision.toLowerCase();
  if (d.includes("forg") || d.includes("deep") || d.includes("fake")) return "#dc2626";
  return "#16a34a";
}

export default function VideoFactAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);
  const [mode, setMode] = useState<VideoFactMode>("both");
  const [maxSamples, setMaxSamples] = useState(100);
  const [sampleEvery, setSampleEvery] = useState(5);
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [report, setReport] = useState<{ modes: ModeResult[] } | null>(null);
  const [activeMode, setActiveMode] = useState<string>("xfer");
  const [selectedFrame, setSelectedFrame] = useState<number | null>(null);
  const [heatmapUrl, setHeatmapUrl] = useState<string | null>(null);
  const [chartUrls, setChartUrls] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const videoUrl = useVideoEvidenceUrl(selectedEvidence);
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
        const t = res.data.find((x) => x.name === "videofact");
        if (t) {
          setRuntimeOk(t.available !== false);
          setRuntimeReason(t.unavailable_reason || "");
        } else {
          setRuntimeOk(false);
          setRuntimeReason("Tecnica videofact nao registrada.");
        }
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Nao foi possivel verificar VideoFACT no servidor.");
      });
  }, []);

  const activeModeResult = useMemo(
    () => report?.modes.find((m) => m.mode === activeMode) ?? report?.modes[0] ?? null,
    [report, activeMode]
  );

  const onSelect = useCallback(
    (id: string) => {
      setSelectedEvidence(id);
      reset();
      setReport(null);
      setHeatmapUrl(null);
      setChartUrls({});
      setSelectedFrame(null);
      setSaveMessage(null);
    },
    [reset]
  );

  const loadArtifacts = useCallback(
    async (jobId: string, jobResult: Record<string, unknown>) => {
      const parsed = await fetchResultJson<{ modes: ModeResult[] }>(jobId, "videofact_report.json");
      if (parsed?.modes?.length) {
        setReport(parsed);
        setActiveMode(parsed.modes[0].mode);
        setSelectedFrame(parsed.modes[0].max_frame_idx);
      } else {
        const modes = jobResult.modes;
        if (Array.isArray(modes) && modes.length) {
          setReport({ modes: modes as ModeResult[] });
        } else {
          throw new Error("Relatorio VideoFACT nao encontrado nos artefatos do job.");
        }
      }

      const charts: Record<string, string> = {};
      for (const key of ["xfer", "df"] as const) {
        const pathKey = `videofact_${key}_scores_chart_path`;
        if (jobResult[pathKey]) {
          const url = await fetchImage(jobId, `videofact_${key}_scores.png`);
          if (url) charts[key] = url;
        }
      }
      setChartUrls(charts);
    },
    [fetchImage, fetchResultJson]
  );

  async function process() {
    if (!selectedEvidence || !runtimeOk) return;
    setSaveMessage(null);
    try {
      await runAnalysis(
        selectedEvidence,
        "videofact",
        {
          mode,
          max_num_samples: maxSamples,
          sample_every: sampleEvery,
          shuffle: false,
        },
        {
          onArtifactsLoaded: loadArtifacts,
        }
      );
    } catch {
      /* hook sets error */
    }
  }

  async function onFrameClick(frame: FrameRow) {
    setSelectedFrame(frame.frame_idx);
    if (!currentJobId || !frame.heatmap) return;
    try {
      const url = await fetchImage(currentJobId, `heatmaps_${activeMode}/${frame.heatmap}`);
      setHeatmapUrl(url);
    } catch {
      setHeatmapUrl(null);
    }
  }

  useEffect(() => {
    if (!currentJobId || !activeModeResult || selectedFrame == null) return;
    const fr = activeModeResult.frames.find((f) => f.frame_idx === selectedFrame);
    if (fr?.heatmap) {
      fetchImage(currentJobId, `heatmaps_${activeMode}/${fr.heatmap}`)
        .then(setHeatmapUrl)
        .catch(() => setHeatmapUrl(null));
    }
  }, [currentJobId, activeModeResult, selectedFrame, activeMode, fetchImage]);

  async function saveDerivativeReport() {
    if (!caseId || !currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await saveDerivative({
        job_id: currentJobId,
        artifact_filename: "videofact_report.json",
        label: `VideoFACT ${mode} — ${new Date().toLocaleString("pt-BR")}`,
        effective_parameters: { mode },
      });
      setSaveMessage({ type: "ok", text: "Relatorio VideoFACT salvo no caso." });
    } catch (e) {
      setSaveMessage({ type: "err", text: e instanceof Error ? e.message : "Falha ao salvar derivado." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <AnalysisPageShell
      caseId={caseId!}
      title="VideoFACT — Edicoes e Deepfake em Video"
      subtitle="WACV 2024 — atencao, contexto de cena e tracos forenses (inferencia direta no video)"
    >
      <TechniqueReferenceIntro meta={VIDEOFACT_META} />

      {runtimeOk === false && (
        <MessageBox type="err" text={`VideoFACT indisponivel: ${runtimeReason}`} />
      )}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 1fr) minmax(320px, 1.2fr)", gap: "1rem" }}>
        <AnalysisPanel title="Evidencia e parametros">
          <MediaEvidenceSelector
            caseId={caseId!}
            fileType="video"
            selectedId={selectedEvidence}
            onSelect={onSelect}
          />

          <div style={{ marginTop: "1rem", display: "grid", gap: "0.65rem" }}>
            <label style={{ fontSize: "0.82rem", color: "#374151" }}>
              Modo de analise
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as VideoFactMode)}
                style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.4rem" }}
              >
                <option value="both">Edicoes + Deepfake</option>
                <option value="xfer">Somente edicoes (Xfer)</option>
                <option value="df">Somente deepfake (DF)</option>
              </select>
            </label>
            <label style={{ fontSize: "0.82rem", color: "#374151" }}>
              Max. frames amostrados
              <input
                type="number"
                min={10}
                max={500}
                value={maxSamples}
                onChange={(e) => setMaxSamples(Number(e.target.value))}
                style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.4rem" }}
              />
            </label>
            <label style={{ fontSize: "0.82rem", color: "#374151" }}>
              Amostrar 1 frame a cada N
              <input
                type="number"
                min={1}
                max={120}
                value={sampleEvery}
                onChange={(e) => setSampleEvery(Number(e.target.value))}
                style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.4rem" }}
              />
            </label>
          </div>

          <div style={{ marginTop: "1rem" }}>
            <ProcessButton
            onClick={process}
            running={running}
            disabled={!selectedEvidence || runtimeOk === false}
            label="Analisar video"
          />
          </div>
          <ProgressChecklist progress={progress} running={running} inferenceDevice={inferenceDevice} />
          {error && <MessageBox type="err" text={error} />}
        </AnalysisPanel>

        <AnalysisPanel title="Visualizacao do video">
          <VideoPlayer src={videoUrl} seekFrame={selectedFrame} fps={25} />
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.78rem", color: "#6b7280" }}>
            Clique em um frame nos resultados para sincronizar o player e ver o mapa de localizacao.
          </p>
        </AnalysisPanel>
      </div>

      {report && (
        <div style={{ marginTop: "1.25rem", display: "grid", gap: "1rem" }}>
          <AnalysisPanel title="Resultados por modo">
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
              {report.modes.map((m) => (
                <button
                  key={m.mode}
                  type="button"
                  onClick={() => {
                    setActiveMode(m.mode);
                    setSelectedFrame(m.max_frame_idx);
                  }}
                  style={{
                    padding: "0.35rem 0.75rem",
                    borderRadius: 6,
                    border: activeMode === m.mode ? "2px solid #1a1a2e" : "1px solid #d1d5db",
                    background: activeMode === m.mode ? "#f3f4f6" : "#fff",
                    cursor: "pointer",
                    fontSize: "0.8rem",
                  }}
                >
                  {m.model_label}
                </button>
              ))}
            </div>

            {activeModeResult && (
              <>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                    gap: "0.5rem",
                    marginBottom: "0.75rem",
                    fontSize: "0.85rem",
                  }}
                >
                  <div>
                    <strong>Decisao video:</strong>{" "}
                    <span style={{ color: decisionColor(activeModeResult.video_decision) }}>
                      {activeModeResult.video_decision}
                    </span>
                  </div>
                  <div>
                    <strong>Score max:</strong> {activeModeResult.max_score.toFixed(4)} (frame{" "}
                    {activeModeResult.max_frame_idx})
                  </div>
                  <div>
                    <strong>Score medio:</strong> {activeModeResult.mean_score.toFixed(4)}
                  </div>
                  <div>
                    <strong>Limiar:</strong> {activeModeResult.threshold.toFixed(2)}
                  </div>
                </div>

                {chartUrls[activeMode as "xfer" | "df"] && (
                  <img
                    src={chartUrls[activeMode as "xfer" | "df"]}
                    alt="Grafico de scores"
                    style={{ width: "100%", maxHeight: 220, objectFit: "contain", marginBottom: "0.75rem" }}
                  />
                )}

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                  <div
                    style={{
                      maxHeight: 280,
                      overflow: "auto",
                      border: "1px solid #e5e7eb",
                      borderRadius: 6,
                      fontSize: "0.78rem",
                    }}
                  >
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ background: "#f9fafb", position: "sticky", top: 0 }}>
                          <th style={{ padding: "0.35rem", textAlign: "left" }}>Frame</th>
                          <th style={{ padding: "0.35rem", textAlign: "left" }}>Score</th>
                          <th style={{ padding: "0.35rem", textAlign: "left" }}>Decisao</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeModeResult.frames.map((fr) => (
                          <tr
                            key={fr.frame_idx}
                            onClick={() => onFrameClick(fr)}
                            style={{
                              cursor: "pointer",
                              background:
                                selectedFrame === fr.frame_idx ? "#eff6ff" : "transparent",
                            }}
                          >
                            <td style={{ padding: "0.3rem 0.35rem" }}>{fr.frame_idx}</td>
                            <td style={{ padding: "0.3rem 0.35rem" }}>{fr.score.toFixed(4)}</td>
                            <td
                              style={{
                                padding: "0.3rem 0.35rem",
                                color: decisionColor(fr.decision),
                              }}
                            >
                              {fr.decision}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div>
                    <p style={{ margin: "0 0 0.35rem", fontSize: "0.82rem", color: "#374151", fontWeight: 600 }}>
                      Mapa de localizacao — frame {selectedFrame ?? "—"}
                    </p>
                    {heatmapUrl ? (
                      <img
                        src={heatmapUrl}
                        alt="Heatmap VideoFACT"
                        style={{ width: "100%", borderRadius: 6, border: "1px solid #e5e7eb" }}
                      />
                    ) : (
                      <div
                        style={{
                          height: 200,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          background: "#f9fafb",
                          borderRadius: 6,
                          color: "#9ca3af",
                          fontSize: "0.8rem",
                        }}
                      >
                        Selecione um frame analisado
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </AnalysisPanel>

          {currentJobId && (
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
              <button
                type="button"
                onClick={saveDerivativeReport}
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
                {saving ? "Salvando…" : "Salvar derivado no caso"}
              </button>
              {saveMessage && (
                <MessageBox type={saveMessage.type === "ok" ? "ok" : "err"} text={saveMessage.text} />
              )}
            </div>
          )}
        </div>
      )}
    </AnalysisPageShell>
  );
}
