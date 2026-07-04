import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import AnalysisPageShell, {
  AnalysisPanel,
  MessageBox,
  ProcessButton,
} from "@/components/AnalysisPageShell";
import AudioEvidenceSelector from "@/components/AudioEvidenceSelector";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { getEvidenceFileUrl, saveDerivative } from "@/services/evidence";
import api from "@/services/api";

const META = FORENSIC_TECHNIQUE_META.audio_spoofing_detection;

type AudioSpoofingDetectorId = "df_arena_1b" | "sls_xlsr" | "wedefense_wavlm_mhfa";

const DEFAULT_DETECTORS: AudioSpoofingDetectorId[] = [
  "df_arena_1b",
  "sls_xlsr",
  "wedefense_wavlm_mhfa",
];

const DETECTOR_OPTIONS: { id: AudioSpoofingDetectorId; label: string }[] = [
  { id: "df_arena_1b", label: "DF Arena 1B" },
  { id: "sls_xlsr", label: "SLS XLS-R (ACM MM 2024)" },
  { id: "wedefense_wavlm_mhfa", label: "WeDefense ASV2025 WavLM + MHFA" },
];

type ResultRow = [string, string, string, string, string, string];

type PlotSeries = {
  centers: number[];
  spoof_probs: number[];
  bonafide_probs: number[];
  window_seconds: number;
  detector?: string;
};

interface PlotData {
  centers: number[];
  spoof_probs: number[];
  bonafide_probs: number[];
  window_seconds: number;
  duration_seconds: number;
  original_duration_seconds?: number;
  max_duration_seconds?: number;
  truncated?: boolean;
  plot_by_detector?: Record<string, PlotSeries>;
}

interface DetectorCatalogRow {
  id: AudioSpoofingDetectorId;
  label: string;
  paper?: string;
  available?: boolean;
  unavailable_reason?: string | null;
}

interface AnalysisResult {
  success?: boolean;
  label?: string;
  score_spoof?: number;
  score_bonafide?: number;
  spoof_logit?: number;
  bonafide_logit?: number;
  window_count?: number;
  window_seconds?: number;
  duration_seconds?: number;
  original_duration_seconds?: number;
  max_duration_seconds?: number;
  truncated?: boolean;
  inference_device?: string;
  selected_analyses?: string[];
  individual_results?: ResultRow[];
  detector_scores?: Record<string, { spoof_prob?: number; bonafide_prob?: number; decision?: string }>;
  plot_data?: PlotData;
  plot_by_detector?: Record<string, PlotSeries>;
  error?: string;
  message?: string;
}

const SCORE_HEADERS = [
  "Detector",
  "Score Spoof",
  "Score Bonafide",
  "Razão (Log)",
  "Classificação",
  "Dispositivo",
];

function TemporalChart({ data }: { data: PlotSeries }) {
  const padding = { top: 25, right: 25, bottom: 40, left: 45 };
  const width = 900;
  const height = 260;
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const points = useMemo(() => {
    return data.centers.map((c, i) => ({
      center_seconds: c,
      spoof_prob: data.spoof_probs[i] ?? 0,
      bonafide_prob: data.bonafide_probs[i] ?? 0,
    }));
  }, [data]);

  const xMax = Math.max(...points.map((p) => p.center_seconds), 1);
  const xMin = 0;
  const yMin = 0;
  const yMax = 1;

  const xScale = (v: number) => padding.left + ((v - xMin) / (xMax - xMin)) * innerWidth;
  const yScale = (v: number) => padding.top + innerHeight - ((v - yMin) / (yMax - yMin)) * innerHeight;

  const ticksX = 8;
  const ticksY = 5;

  const pathSpoof = useMemo(() => {
    return points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.center_seconds)} ${yScale(p.spoof_prob)}`)
      .join(" ");
  }, [points]);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      style={{ width: "100%", height: "auto", minHeight: 220 }}
      role="img"
      aria-label="Evolucao temporal da probabilidade de spoofing"
    >
      {Array.from({ length: ticksY + 1 }).map((_, i) => {
        const y = padding.top + (innerHeight / ticksY) * i;
        return (
          <g key={`h-${i}`}>
            <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#e5e7eb" strokeWidth={1} />
            <text x={padding.left - 8} y={y + 4} textAnchor="end" fontSize={11} fill="#6b7280">
              {Math.round((1 - i / ticksY) * 100)}%
            </text>
          </g>
        );
      })}

      {Array.from({ length: ticksX + 1 }).map((_, i) => {
        const x = padding.left + (innerWidth / ticksX) * i;
        const value = xMin + (xMax - xMin) * (i / ticksX);
        return (
          <g key={`v-${i}`}>
            <line x1={x} y1={padding.top} x2={x} y2={height - padding.bottom} stroke="#e5e7eb" strokeWidth={1} />
            <text x={x} y={height - padding.bottom + 18} textAnchor="middle" fontSize={11} fill="#6b7280">
              {value.toFixed(0)}s
            </text>
          </g>
        );
      })}

      {[0.35, 0.65].map((threshold) => (
        <g key={threshold}>
          <line
            x1={padding.left}
            y1={yScale(threshold)}
            x2={width - padding.right}
            y2={yScale(threshold)}
            stroke="#f59e0b"
            strokeWidth={1.5}
            strokeDasharray="4 4"
          />
        </g>
      ))}

      <path d={pathSpoof} fill="none" stroke="#dc2626" strokeWidth={2} />
      {points.map((p, i) => (
        <circle key={i} cx={xScale(p.center_seconds)} cy={yScale(p.spoof_prob)} r={3} fill="#dc2626" />
      ))}
    </svg>
  );
}

function ScoreBadge({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div
      style={{
        padding: "0.6rem 0.9rem",
        borderRadius: 8,
        background: "#f9fafb",
        border: "1px solid #e5e7eb",
        minWidth: 140,
      }}
    >
      <div style={{ fontSize: "0.75rem", color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.03em" }}>
        {label}
      </div>
      <div style={{ fontSize: "1.5rem", fontWeight: 700, color }}>{pct}%</div>
    </div>
  );
}

export default function AudioSpoofingAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedFilename, setSelectedFilename] = useState<string>("");
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [catalog, setCatalog] = useState<DetectorCatalogRow[]>([]);
  const [selectedDetectors, setSelectedDetectors] = useState<AudioSpoofingDetectorId[]>(DEFAULT_DETECTORS);
  const [plotDetector, setPlotDetector] = useState<AudioSpoofingDetectorId>("df_arena_1b");
  const [plotData, setPlotData] = useState<PlotData | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const {
    running,
    result,
    error,
    progress,
    progressLabel,
    currentJobId,
    runAnalysis,
    reset,
  } = useForensicJob();

  const typedResult = result as AnalysisResult | null;

  useEffect(() => {
    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((res) => {
        const t = res.data.find((x) => x.name === "audio_spoofing_detection");
        if (t) {
          setRuntimeOk(t.available !== false);
          setRuntimeReason(t.unavailable_reason || "");
        } else {
          setRuntimeOk(false);
          setRuntimeReason("Tecnica audio_spoofing_detection nao registrada.");
        }
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Nao foi possivel verificar o detector no servidor.");
      });

    api
      .get<DetectorCatalogRow[]>("/analysis/audio-spoofing-detectors")
      .then((res) => {
        setCatalog(res.data);
        const available = res.data.filter((d) => d.available !== false).map((d) => d.id);
        if (available.length > 0) {
          setSelectedDetectors(available);
          setPlotDetector(available[0]);
        }
      })
      .catch(() => {
        setCatalog(DETECTOR_OPTIONS.map((o) => ({ ...o, available: true })));
      });
  }, []);

  const onSelect = useCallback(
    (id: string, filename: string) => {
      setSelectedId(id);
      setSelectedFilename(filename);
      reset();
      setPlotData(null);
      setSaveMessage(null);
    },
    [reset]
  );

  const toggleDetector = (id: AudioSpoofingDetectorId) => {
    setSelectedDetectors((prev) => {
      if (prev.includes(id)) {
        const next = prev.filter((x) => x !== id);
        return next.length ? next : prev;
      }
      return [...prev, id];
    });
  };

  const process = useCallback(async () => {
    if (!selectedId || !runtimeOk || selectedDetectors.length === 0) return;
    setPlotData(null);
    try {
      const { result: jobResult } = await runAnalysis(
        selectedId,
        "audio_spoofing_detection",
        { window_seconds: 4.0, selected_analyses: selectedDetectors },
        { retainResult: true }
      );
      const r = jobResult as AnalysisResult | null;
      if (r?.plot_data) {
        setPlotData(r.plot_data);
        const first = r.selected_analyses?.[0] as AudioSpoofingDetectorId | undefined;
        if (first) setPlotDetector(first);
      }
    } catch {
      // erro ja esta no estado do hook
    }
  }, [selectedId, runtimeOk, selectedDetectors, runAnalysis]);

  async function handleSaveDerivative(artifactFilename: string, label: string) {
    if (!currentJobId) return;
    setSaving(artifactFilename);
    setSaveMessage(null);
    try {
      await saveDerivative({
        job_id: currentJobId,
        artifact_filename: artifactFilename,
        label,
        effective_parameters: { window_seconds: 4.0, selected_analyses: selectedDetectors },
      });
      setSaveMessage({ type: "ok", text: `${label} salvo no caso.` });
    } catch (e) {
      setSaveMessage({
        type: "err",
        text: e instanceof Error ? e.message : "Falha ao salvar derivado.",
      });
    } finally {
      setSaving(null);
    }
  }

  const audioUrl = useMemo(() => {
    return selectedId ? getEvidenceFileUrl(selectedId) : null;
  }, [selectedId]);

  const activePlot = useMemo(() => {
    if (!plotData) return null;
    const byDetector = plotData.plot_by_detector;
    if (byDetector && byDetector[plotDetector]) {
      return byDetector[plotDetector];
    }
    return {
      centers: plotData.centers,
      spoof_probs: plotData.spoof_probs,
      bonafide_probs: plotData.bonafide_probs,
      window_seconds: plotData.window_seconds,
    };
  }, [plotData, plotDetector]);

  const plotDetectorOptions = useMemo(() => {
    const fromResult = typedResult?.selected_analyses as AudioSpoofingDetectorId[] | undefined;
    return fromResult?.length ? fromResult : selectedDetectors;
  }, [typedResult, selectedDetectors]);

  return (
    <AnalysisPageShell caseId={caseId!} title={META.title} subtitle={META.cardSubtitle}>
      <TechniqueReferenceIntro meta={META} />

      {runtimeOk === false && <MessageBox type="err" text={`Detector indisponivel: ${runtimeReason}`} />}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(320px, 1fr) minmax(320px, 1fr)", gap: "1rem" }}>
        <AnalysisPanel title="Evidencia de audio">
          <AudioEvidenceSelector caseId={caseId!} selectedId={selectedId} onSelect={onSelect} />
        </AnalysisPanel>

        <AnalysisPanel title="Detectores de spoofing">
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.82rem", color: "#4b5563" }}>
            Selecione um ou mais detectores. Os escores serao agregados em vetor para meta-classificador futuro.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", marginBottom: "1rem" }}>
            {(catalog.length ? catalog : DETECTOR_OPTIONS).map((det) => {
              const id = det.id;
              const checked = selectedDetectors.includes(id);
              const unavailable = det.available === false;
              return (
                <label
                  key={id}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "0.5rem",
                    fontSize: "0.85rem",
                    opacity: unavailable ? 0.55 : 1,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={unavailable}
                    onChange={() => toggleDetector(id)}
                  />
                  <span>
                    <strong>{det.label}</strong>
                    {unavailable && det.unavailable_reason ? (
                      <span style={{ display: "block", color: "#b45309", fontSize: "0.75rem" }}>
                        {det.unavailable_reason}
                      </span>
                    ) : null}
                  </span>
                </label>
              );
            })}
          </div>

          <ProcessButton
            onClick={process}
            disabled={!selectedId || runtimeOk !== true || selectedDetectors.length === 0}
            running={running}
            label="Analisar audio"
            progress={progress}
            progressLabel={progressLabel}
          />

          {error && <MessageBox type="err" text={error} />}

          {typedResult?.success === true && (
            <div style={{ marginTop: "1rem" }}>
              <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "1rem" }}>
                <ScoreBadge label="Spoof (primario)" value={typedResult.score_spoof ?? 0} color="#dc2626" />
                <ScoreBadge label="Bonafide (primario)" value={typedResult.score_bonafide ?? 0} color="#16a34a" />
              </div>

              {typedResult.individual_results && typedResult.individual_results.length > 0 && (
                <div style={{ overflowX: "auto", marginBottom: "1rem" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
                    <thead>
                      <tr>
                        {SCORE_HEADERS.map((h) => (
                          <th
                            key={h}
                            style={{
                              textAlign: "left",
                              padding: "0.35rem 0.5rem",
                              borderBottom: "2px solid #e5e7eb",
                              color: "#374151",
                            }}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {typedResult.individual_results.map((row, idx) => (
                        <tr key={idx}>
                          {row.map((cell, ci) => (
                            <td
                              key={ci}
                              style={{
                                padding: "0.35rem 0.5rem",
                                borderBottom: "1px solid #f3f4f6",
                                color: ci === 4 && cell === "Spoof" ? "#dc2626" : undefined,
                              }}
                            >
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <p style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#374151" }}>
                <strong>Decisao agregada (detector primario):</strong>{" "}
                <span
                  style={{
                    color:
                      typedResult.label === "spoof"
                        ? "#dc2626"
                        : typedResult.label === "uncertain"
                        ? "#b45309"
                        : "#16a34a",
                    fontWeight: 700,
                  }}
                >
                  {typedResult.label === "spoof"
                    ? "Spoof"
                    : typedResult.label === "uncertain"
                    ? "Incerto"
                    : "Bonafide"}
                </span>
              </p>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.8rem", color: "#6b7280" }}>
                Detectores: {(typedResult.selected_analyses ?? selectedDetectors).join(", ")}
                {" · "}
                Janelas: {typedResult.window_count ?? 0} de {typedResult.window_seconds ?? 4}s
                {" · "}
                Dispositivo: {typedResult.inference_device || "auto"}
                {" · "}
                Duracao: {typedResult.duration_seconds ?? 0}s
              </p>

              {currentJobId && (
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                  <button
                    type="button"
                    onClick={() => void handleSaveDerivative("detector_scores.txt", "Audio spoofing — escores")}
                    disabled={saving !== null}
                    style={{
                      padding: "0.45rem 0.75rem",
                      borderRadius: 6,
                      border: "1px solid #1a1a2e",
                      background: "#fff",
                      cursor: saving ? "wait" : "pointer",
                      fontSize: "0.8rem",
                    }}
                  >
                    {saving === "detector_scores.txt" ? "Salvando…" : "Salvar vetor de escores"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleSaveDerivative("audio_spoofing_details.json", "Audio spoofing — detalhes")}
                    disabled={saving !== null}
                    style={{
                      padding: "0.45rem 0.75rem",
                      borderRadius: 6,
                      border: "1px solid #1a1a2e",
                      background: "#fff",
                      cursor: saving ? "wait" : "pointer",
                      fontSize: "0.8rem",
                    }}
                  >
                    {saving === "audio_spoofing_details.json" ? "Salvando…" : "Salvar relatorio JSON"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleSaveDerivative("audio_spoofing_plot.json", "Audio spoofing — plot temporal")}
                    disabled={saving !== null}
                    style={{
                      padding: "0.45rem 0.75rem",
                      borderRadius: 6,
                      border: "1px solid #1a1a2e",
                      background: "#fff",
                      cursor: saving ? "wait" : "pointer",
                      fontSize: "0.8rem",
                    }}
                  >
                    {saving === "audio_spoofing_plot.json" ? "Salvando…" : "Salvar plot temporal"}
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
            </div>
          )}
        </AnalysisPanel>
      </div>

      {(audioUrl || activePlot) && (
        <AnalysisPanel title="Player e evolucao temporal" className="audio-spoofing-results-panel">
          <div style={{ display: "grid", gap: "1rem" }}>
            {audioUrl && (
              <div>
                <p style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#374151", fontWeight: 500 }}>
                  {selectedFilename}
                </p>
                <audio controls src={audioUrl} style={{ width: "100%" }} />
              </div>
            )}

            {activePlot && (
              <div>
                {plotDetectorOptions.length > 1 && (
                  <div style={{ marginBottom: "0.5rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {plotDetectorOptions.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => setPlotDetector(id)}
                        style={{
                          padding: "0.25rem 0.6rem",
                          borderRadius: 6,
                          border: plotDetector === id ? "2px solid #1a1a2e" : "1px solid #d1d5db",
                          background: plotDetector === id ? "#f3f4f6" : "#fff",
                          fontSize: "0.75rem",
                          cursor: "pointer",
                        }}
                      >
                        {DETECTOR_OPTIONS.find((o) => o.id === id)?.label ?? id}
                      </button>
                    ))}
                  </div>
                )}
                <p style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#374151", fontWeight: 500 }}>
                  Probabilidade por janela de {activePlot.window_seconds}s
                </p>
                <TemporalChart data={activePlot} />
              </div>
            )}
          </div>
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}
