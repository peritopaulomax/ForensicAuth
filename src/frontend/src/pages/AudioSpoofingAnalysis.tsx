import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import { MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import AudioEvidenceSelector from "@/components/AudioEvidenceSelector";
import {
  MacroCategory,
  MetaClassifierSelect,
  ReferenceLrFeatureWeightsPanel,
  ReferenceLrPanel,
  ReferenceLrResult,
  ReferencePopulationEntry,
  ReferencePopulationSelector,
  itemsToEntries,
  referencePopulationPayload,
  referenceSelectionCounts,
  SaveButton,
  smallButtonStyle,
} from "@/components/LrReferencePanels";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import { getEvidenceFileUrl } from "@/services/evidence";
import api from "@/services/api";

type AudioSpoofingDetectorId = "df_arena_1b" | "sls_xlsr" | "wedefense_wavlm_mhfa" | "tfcl_xlsr";

/** Detectores expostos na UI (SLS/TFCL permanecem no backend, ocultos). */
const DEFAULT_DETECTORS: AudioSpoofingDetectorId[] = [
  "df_arena_1b",
  "wedefense_wavlm_mhfa",
];

const DETECTOR_OPTIONS: { id: AudioSpoofingDetectorId; label: string }[] = [
  { id: "df_arena_1b", label: "DF Arena 1B" },
  { id: "wedefense_wavlm_mhfa", label: "WeDefense ASV2025 WavLM + MHFA" },
];

const DEFAULT_AUDIO_REFERENCE: ReferencePopulationEntry[] = itemsToEntries(
  [
    { base_group: "MLAAD_PT", subgroup: "Voxtral" },
    { base_group: "MLAAD_PT", subgroup: "Qwen3-TTS-12Hz-1.7B-Base" },
    { base_group: "MLAAD_PT", subgroup: "OpenAI_TTS-1_HD" },
    { base_group: "MLAAD_PT", subgroup: "OmniVoice" },
    { base_group: "MLAAD_PT", subgroup: "MOSS-TTS-8B" },
    { base_group: "MLAAD_PT", subgroup: "Fish-S2-Pro" },
    { base_group: "MLAAD_PT", subgroup: "Llasa-1B-Multilingual" },
  ],
  "both"
);

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
  description?: string;
  paper?: string;
  paper_title?: string;
  paper_url?: string;
  repo_url?: string;
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
  reference_lr?: ReferenceLrResult;
  error?: string;
  message?: string;
}

const SCORE_HEADERS = [
  "Detector",
  "Logit Spoof",
  "Logit Bonafide",
  "Δ log10 (bona−spoof)",
  "Classificação",
  "Dispositivo",
];

function classificationColor(value: string): string {
  if (value === "Spoof" || value === "SPOOF") return "#b91c1c";
  if (value === "Bonafide" || value === "BONAFIDE") return "#166534";
  return "#b45309";
}

function deviceBadgeColor(value: string): string {
  if (value === "GPU") return "#1d4ed8";
  return "#6b7280";
}

function DetectorOptionInfo({ detector }: { detector: DetectorCatalogRow }) {
  const paperUrl = detector.paper_url || (detector.paper?.startsWith("http") ? detector.paper : undefined);
  const paperTitle = detector.paper_title || detector.paper;

  return (
    <span>
      <strong style={{ display: "block", color: "#1f2937" }}>{detector.label}</strong>
      {detector.description && (
        <span
          style={{
            display: "block",
            marginTop: "0.25rem",
            fontSize: "0.74rem",
            color: "#4b5563",
            lineHeight: 1.35,
          }}
        >
          {detector.description}
        </span>
      )}
      <span
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.35rem",
          marginTop: "0.35rem",
          fontSize: "0.72rem",
        }}
      >
        {paperUrl && (
          <a
            href={paperUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#1d4ed8", textDecoration: "none" }}
            onClick={(e) => e.stopPropagation()}
          >
            📄 {paperTitle || "Paper"}
          </a>
        )}
        {detector.repo_url && (
          <a
            href={detector.repo_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#0369a1", textDecoration: "none" }}
            onClick={(e) => e.stopPropagation()}
          >
            🔗 {detector.repo_url.includes("huggingface.co") ? "HuggingFace" : "Repositório"}
          </a>
        )}
      </span>
      {detector.available === false && detector.unavailable_reason && (
        <span style={{ display: "block", color: "#b45309", fontSize: "0.75rem", marginTop: "0.25rem" }}>
          {detector.unavailable_reason}
        </span>
      )}
    </span>
  );
}

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

function ResultsTable({ rows }: { rows: ResultRow[] }) {
  return (
    <div>
      <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.88rem", color: "#374151", fontWeight: 600 }}>
        Resultados dos Detectores
      </h4>
      <div style={{ overflow: "auto", maxHeight: 180, border: "1px solid #e5e7eb", borderRadius: 6 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
          <thead>
            <tr style={{ background: "#f9fafb", position: "sticky", top: 0 }}>
              {SCORE_HEADERS.map((h) => (
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
              const cells = [...row, ...Array(Math.max(0, SCORE_HEADERS.length - row.length)).fill("—")];
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

export default function AudioSpoofingAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [selectedFilename, setSelectedFilename] = useState<string>("");
  const [catalog, setCatalog] = useState<DetectorCatalogRow[]>([]);
  const [selectedDetectors, setSelectedDetectors] = useState<AudioSpoofingDetectorId[]>(DEFAULT_DETECTORS);
  const [plotDetector, setPlotDetector] = useState<AudioSpoofingDetectorId>("df_arena_1b");
  const [plotData, setPlotData] = useState<PlotData | null>(null);
  const [referenceCatalog, setReferenceCatalog] = useState<MacroCategory[]>([]);
  const [referenceCatalogLoading, setReferenceCatalogLoading] = useState(true);
  const [referenceCatalogError, setReferenceCatalogError] = useState<string | null>(null);
  const [detectorEerLabels, setDetectorEerLabels] = useState<string[]>([]);
  const [referenceEntries, setReferenceEntries] = useState<ReferencePopulationEntry[]>(DEFAULT_AUDIO_REFERENCE);
  const [metaClassifier, setMetaClassifier] = useState<string>("logistic");
  const [useAugmentedReference, setUseAugmentedReference] = useState(false);
  const [useLatentTypicality, setUseLatentTypicality] = useState(false);
  const [referenceLrTippettUrl, setReferenceLrTippettUrl] = useState<string | null>(null);
  const [referenceLrDistributionUrl, setReferenceLrDistributionUrl] = useState<string | null>(null);
  const [referenceLrIdentityUrl, setReferenceLrIdentityUrl] = useState<string | null>(null);
  const [liveInferenceDevice, setLiveInferenceDevice] = useState<string | null>(null);
  const blobUrlsRef = useRef<string[]>([]);

  const {
    running,
    result,
    error,
    progress,
    progressLabel,
    currentJobId,
    runAnalysis,
    fetchImage,
    reset,
  } = useForensicJob();
  const { saveMessage, save, clearMessage } = useDerivativeSave();
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const { status: runtimeStatus } = useTechniqueRuntime("audio_spoofing_detection");

  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  const typedResult = result as AnalysisResult | null;

  useEffect(() => {
    if (!running) {
      setLiveInferenceDevice(null);
      return;
    }
    const msg = progressLabel || "";
    if (/\bem GPU\b|GPU\/CPU \(cuda\)|\(cuda\)|CUDA/i.test(msg)) setLiveInferenceDevice("GPU");
    else if (/\bCPU\b|fallback VRAM|recarregando em CPU/i.test(msg)) setLiveInferenceDevice("CPU");
  }, [running, progressLabel]);

  const activeInferenceDevice = typedResult?.inference_device ?? (running ? liveInferenceDevice : null);

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

  useEffect(() => {
    return () => revokeBlobs();
  }, [revokeBlobs]);

  useEffect(() => {
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

    api
      .get<{
        categories: MacroCategory[];
        detector_eer_labels?: string[];
        default_reference_items?: { base_group: string; subgroup: string }[];
      }>("/analysis/audio-spoofing-reference-catalog")
      .then((res) => {
        setReferenceCatalog(res.data.categories);
        setDetectorEerLabels(res.data.detector_eer_labels ?? []);
        if (res.data.default_reference_items?.length) {
          setReferenceEntries(itemsToEntries(res.data.default_reference_items, "both"));
        }
        setReferenceCatalogLoading(false);
      })
      .catch((err: unknown) => {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || String(err);
        setReferenceCatalogError(message);
        setReferenceCatalogLoading(false);
      });
  }, []);

  const clearAll = useCallback(() => {
    reset();
    setPlotData(null);
    setReferenceLrTippettUrl(null);
    setReferenceLrDistributionUrl(null);
    setReferenceLrIdentityUrl(null);
    clearMessage();
  }, [reset, clearMessage]);

  const applyEvidence = useCallback(
    (_id: string) => {
      clearAll();
    },
    [clearAll]
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  const onSelectAudio = useCallback(
    (id: string, source: "original" | "derivative", filename?: string) => {
      setSelectedFilename(filename || "");
      onSelectEvidence(id, source);
    },
    [onSelectEvidence]
  );

  const toggleDetector = useCallback((id: AudioSpoofingDetectorId, checked: boolean) => {
    setSelectedDetectors((prev) => {
      if (checked) {
        return prev.includes(id) ? prev : [...prev, id];
      }
      const next = prev.filter((x) => x !== id);
      return next.length ? next : prev;
    });
  }, []);

  const referenceCounts = useMemo(
    () => referenceSelectionCounts(referenceEntries, true),
    [referenceEntries]
  );
  const referencePayload = useMemo(
    () => referencePopulationPayload(referenceEntries, true),
    [referenceEntries]
  );
  const referenceSelectionValid = referenceCounts.fit > 0 && referenceCounts.test > 0;

  const clearLrArtifacts = useCallback(() => {
    setReferenceLrTippettUrl(null);
    setReferenceLrDistributionUrl(null);
    setReferenceLrIdentityUrl(null);
  }, []);

  const process = useCallback(async () => {
    if (!evidenceId || !runtimeOk || selectedDetectors.length === 0 || !referenceSelectionValid) return;
    setPlotData(null);
    clearLrArtifacts();
    clearMessage();
    try {
      const needsLongCalibration = useLatentTypicality || useAugmentedReference;
      const { result: jobResult } = await runAnalysis(
        evidenceId,
        "audio_spoofing_detection",
        {
          window_seconds: 4.0,
          selected_analyses: selectedDetectors,
          reference_lr_enabled: true,
          reference_population: referencePayload,
          meta_classifier: metaClassifier,
          use_augmented_reference: useAugmentedReference,
          use_latent_typicality: useLatentTypicality,
        },
        {
          maxWaitMs: needsLongCalibration ? Number.POSITIVE_INFINITY : undefined,
          retainResult: true,
          onArtifactsLoaded: async (jobId) => {
            const [lrTippett, lrDistribution, lrIdentity] = await Promise.all([
              fetchImage(jobId, "lr_reference_tippett.png"),
              fetchImage(jobId, "lr_reference_distribution.png"),
              fetchImage(jobId, "lr_reference_identity.png"),
            ]);
            setArtifactUrl(setReferenceLrTippettUrl, lrTippett);
            setArtifactUrl(setReferenceLrDistributionUrl, lrDistribution);
            setArtifactUrl(setReferenceLrIdentityUrl, lrIdentity);
          },
        }
      );
      const r = jobResult as AnalysisResult | null;
      if (r?.plot_data) {
        setPlotData(r.plot_data);
        const first = r.selected_analyses?.[0] as AudioSpoofingDetectorId | undefined;
        if (first) setPlotDetector(first);
      }
    } catch {
    }
  }, [
    evidenceId,
    runtimeOk,
    selectedDetectors,
    referenceSelectionValid,
    referencePayload,
    metaClassifier,
    useAugmentedReference,
    useLatentTypicality,
    runAnalysis,
    fetchImage,
    setArtifactUrl,
    clearLrArtifacts,
    clearMessage,
  ]);

  async function handleSaveDerivative(artifactFilename: string, label: string) {
    if (!currentJobId) return;
    setSavingKey(artifactFilename);
    try {
      await save(currentJobId, artifactFilename, label, {
        window_seconds: 4.0,
        selected_analyses: selectedDetectors,
        reference_lr_enabled: true,
        reference_population: referencePayload,
        meta_classifier: metaClassifier,
        use_augmented_reference: useAugmentedReference,
        use_latent_typicality: useLatentTypicality,
      });
    } finally {
      setSavingKey(null);
    }
  }

  const audioUrl = useMemo(() => {
    return evidenceId ? getEvidenceFileUrl(evidenceId) : null;
  }, [evidenceId]);

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

  const detectorRows = catalog.length ? catalog : DETECTOR_OPTIONS.map((o) => ({ ...o, available: true }));
  const individualRows = typedResult?.individual_results || [];
  const referenceLr = typedResult?.reference_lr || null;

  if (!caseId) return null;

  const parametersPanel = (
    <>
      {showEvidencePicker && (
        <div style={{ marginBottom: "1rem" }}>
          <AudioEvidenceSelector
            caseId={caseId}
            selectedId={evidenceId}
            selectionSource={selectionSource}
            onSelect={onSelectAudio}
          />
        </div>
      )}

      <div style={{ marginBottom: "1rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "0.75rem",
            marginBottom: "0.6rem",
          }}
        >
          <div>
            <h4 style={{ margin: 0, fontSize: "0.9rem", color: "#374151" }}>
              Detectores a executar
            </h4>
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.78rem", color: "#6b7280" }}>
              Marque os detectores que deseja rodar nesta evidencia. Os logits alimentam o meta-classificador LR.
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.4rem", flexShrink: 0 }}>
            <button
              type="button"
              onClick={() => setSelectedDetectors([...DEFAULT_DETECTORS])}
              disabled={running}
              style={smallButtonStyle}
            >
              Marcar todas
            </button>
            <button
              type="button"
              onClick={() => setSelectedDetectors([])}
              disabled={running}
              style={smallButtonStyle}
            >
              Limpar
            </button>
          </div>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: "0.45rem",
          }}
        >
          {detectorRows.map((det) => {
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
                  border: "1px solid #e5e7eb",
                  borderRadius: 6,
                  padding: "0.55rem 0.65rem",
                  background: checked ? "#f8fafc" : "#fff",
                  fontSize: "0.83rem",
                  color: "#374151",
                  opacity: unavailable ? 0.55 : 1,
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={running || unavailable}
                  onChange={(e) => toggleDetector(id, e.target.checked)}
                  style={{ marginTop: "0.15rem" }}
                />
                <DetectorOptionInfo detector={det} />
              </label>
            );
          })}
        </div>
        {selectedDetectors.length === 0 && (
          <p style={{ margin: "0.55rem 0 0", fontSize: "0.78rem", color: "#b91c1c" }}>
            Selecione pelo menos um detector para executar.
          </p>
        )}
      </div>

      <ReferencePopulationSelector
        catalog={referenceCatalog}
        loading={referenceCatalogLoading}
        error={referenceCatalogError}
        entries={referenceEntries}
        onChange={setReferenceEntries}
        disabled={running}
        enableSplitRoles
        defaultPresetItems={DEFAULT_AUDIO_REFERENCE.map(({ base_group, subgroup }) => ({
          base_group,
          subgroup,
        }))}
        subgroupUnitLabel="subgrupos"
        detectorEerLabels={detectorEerLabels}
        hypothesisHint="Defina subgrupos para treino/calibração (splits 1–2) e para avaliação (split 3). LR positiva favorece H1 = bonafide/autêntico."
      />
      {!referenceSelectionValid && (
        <p style={{ margin: "0.55rem 0 0", fontSize: "0.78rem", color: "#b91c1c" }}>
          Selecione pelo menos um subgrupo em treino/calibração e um em teste.
        </p>
      )}

      <div style={{ marginTop: "0.75rem" }}>
        <MetaClassifierSelect value={metaClassifier} disabled={running} onChange={setMetaClassifier} />
        <label
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "0.5rem",
            marginTop: "0.55rem",
            fontSize: "0.85rem",
            color: "#374151",
          }}
        >
          <input
            type="checkbox"
            checked={useAugmentedReference}
            disabled={running}
            onChange={(e) => setUseAugmentedReference(e.target.checked)}
            style={{ marginTop: "0.15rem" }}
          />
          <span>
            Usar população de referência aumentada
            <span style={{ display: "block", fontSize: "0.74rem", color: "#6b7280", marginTop: "0.15rem" }}>
              Inclui variações MP3 128 kbps, Opus 32 kbps, ruído ambiente 20 dB e 15 dB SNR na calibração LR.
              {useLatentTypicality
                ? " Requer matriz de representações (scores+embeddings) com variantes aumentadas."
                : " Requer score matrix aumentado gerado offline."}
            </span>
          </span>
        </label>
        <label
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "0.5rem",
            marginTop: "0.55rem",
            fontSize: "0.85rem",
            color: "#374151",
          }}
        >
          <input
            type="checkbox"
            checked={useLatentTypicality}
            disabled={running}
            onChange={(e) => setUseLatentTypicality(e.target.checked)}
            style={{ marginTop: "0.15rem" }}
            aria-label="Tipicidade latente (k-NN)"
          />
          <span>
            Tipicidade latente (k-NN)
            <span style={{ display: "block", fontSize: "0.74rem", color: "#6b7280", marginTop: "0.15rem" }}>
              Fusão enriquecida com embeddings dos detectores (sistema D, cosine, k=5). A primeira calibração
              de uma seleção nova pode levar vários minutos; o progresso LR aparece na barra. Repetições usam cache.
            </span>
          </span>
        </label>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <ProcessButton
          onClick={process}
          disabled={
            !evidenceId ||
            runtimeOk !== true ||
            selectedDetectors.length === 0 ||
            !referenceSelectionValid
          }
          running={running}
          label="Analisar audio"
          progress={progress}
          progressLabel={progressLabel}
          inferenceDevice={activeInferenceDevice}
        />
      </div>
    </>
  );

  const resultPanel = (
    <>
      {audioUrl && (
        <div style={{ marginBottom: "1rem" }}>
          <p style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#374151", fontWeight: 500 }}>
            {selectedFilename}
          </p>
          <audio controls src={audioUrl} style={{ width: "100%" }} />
        </div>
      )}

      {typedResult?.success === true && (
        <>
          {individualRows.length > 0 && (
            <div style={{ marginBottom: "1rem" }}>
              <ResultsTable rows={individualRows} />
            </div>
          )}

          <ReferenceLrPanel
            lr={referenceLr}
            tippettUrl={referenceLrTippettUrl}
            distributionUrl={referenceLrDistributionUrl}
            identityUrl={referenceLrIdentityUrl}
            populationUnitLabel="amostras de audio"
            lrPositiveLabel="bonafide"
            augmentedDescription={
              referenceLr?.augmented_reference
                ? `População aumentada ativa (multiplicador ${referenceLr.sample_multiplier ?? "—"}×) — MP3, Opus e ruído ambiente.`
                : undefined
            }
          />

          {activePlot && (
            <div style={{ marginTop: "1.5rem", borderTop: "1px solid #e5e7eb", paddingTop: "1rem" }}>
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
                Probabilidade de spoof por janela de {activePlot.window_seconds}s
              </p>
              <TemporalChart data={activePlot} />
            </div>
          )}

          {currentJobId && (
            <div style={{ marginTop: "1.5rem", borderTop: "1px solid #e5e7eb", paddingTop: "1rem" }}>
              <h4 style={{ margin: "0 0 0.75rem", fontSize: "0.9rem", color: "#374151" }}>
                Salvar em derivados
              </h4>
              <p style={{ margin: "0 0 0.75rem", fontSize: "0.8rem", color: "#6b7280" }}>
                O vetor de escores (TXT) e o artefato principal para reproducibilidade e cadeia de custodia.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                <SaveButton
                  label="Escores dos detectores (TXT)"
                  filename="detector_scores.txt"
                  saving={savingKey}
                  onSave={handleSaveDerivative}
                  primary
                />
                <SaveButton
                  label="Relatorio JSON"
                  filename="audio_spoofing_details.json"
                  saving={savingKey}
                  onSave={handleSaveDerivative}
                />
                <SaveButton
                  label="Plot temporal (JSON)"
                  filename="audio_spoofing_plot.json"
                  saving={savingKey}
                  onSave={handleSaveDerivative}
                />
              </div>

              {referenceLr && referenceLr.success !== false && (
                <div style={{ marginTop: "1rem" }}>
                  <p style={{ margin: "0 0 0.5rem", fontSize: "0.8rem", color: "#6b7280" }}>
                    Artefatos da calibracao LR (populacao de referencia, CLLR, EER, graficos):
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    <SaveButton
                      label="Resumo LR (TXT)"
                      filename="lr_reference_summary.txt"
                      saving={savingKey}
                      onSave={handleSaveDerivative}
                    />
                    <SaveButton
                      label="Relatorio LR (JSON)"
                      filename="lr_reference_report.json"
                      saving={savingKey}
                      onSave={handleSaveDerivative}
                    />
                    <SaveButton
                      label="Tippett plot"
                      filename="lr_reference_tippett.png"
                      saving={savingKey}
                      onSave={handleSaveDerivative}
                    />
                    <SaveButton
                      label="Distribuicao LR"
                      filename="lr_reference_distribution.png"
                      saving={savingKey}
                      onSave={handleSaveDerivative}
                    />
                    <SaveButton
                      label="Funcao identidade"
                      filename="lr_reference_identity.png"
                      saving={savingKey}
                      onSave={handleSaveDerivative}
                    />
                  </div>
                </div>
              )}

              {saveMessage && (
                <div style={{ marginTop: "0.75rem" }}>
                  <MessageBox type={saveMessage.type} text={saveMessage.text} />
                </div>
              )}
            </div>
          )}
        </>
      )}

      <ReferenceLrFeatureWeightsPanel lr={referenceLr} />
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="audio_spoofing_detection"
      mediaType="audio"
      embedded={embedded}
      evidenceId={evidenceId}
      selectionSource={selectionSource}
      onSelectEvidence={onSelectEvidence}
      showEvidencePicker={false}
      running={running}
      error={error}
      progress={progress}
      progressLabel={progressLabel}
      saveMessage={saveMessage}
      runtimeOk={runtimeOk}
      runtimeReason={runtimeReason}
      parametersPanel={parametersPanel}
      resultPanel={resultPanel || undefined}
    />
  );
}
