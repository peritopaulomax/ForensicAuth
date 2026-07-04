import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import AudioEvidenceSelector from "@/components/AudioEvidenceSelector";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import AudioOverlayPlot, { type AudioOverlayPlotHandle } from "@/components/AudioOverlayPlot";
import PlotlyHtmlFrame from "@/components/PlotlyHtmlFrame";
import SpectrogramPlot, {
  DEFAULT_SPECTROGRAM_COLORSCALE,
  SPECTROGRAM_COLORSCALES,
  type SpectrogramColorscale,
  type SpectrogramFullData,
  type SpectrogramPlotHandle,
} from "@/components/SpectrogramPlot";
import { useForensicJob } from "@/hooks/useForensicJob";
import { saveDerivative } from "@/services/evidence";
import {
  appendOverlayLayer,
  appendLtasOverlays,
  emptyLtasOverlays,
  type AudioOverlayLayer,
  type LtasPanelKey,
  type PlotBundleJson,
  LTAS_PANELS,
} from "@/lib/audioComparison";
import api from "@/services/api";

type AudioTab = "spectrogram" | "enf" | "levels" | "dc" | "ltas";
type CompareTab = "enf" | "levels" | "dc" | "ltas";

function isCompareTab(t: AudioTab): t is CompareTab {
  return t !== "spectrogram";
}

const TABS: { id: AudioTab; label: string; emoji: string }[] = [
  { id: "spectrogram", label: "Espectrograma", emoji: "📊" },
  { id: "enf", label: "Análise ENF", emoji: "🌊" },
  { id: "ltas", label: "LTAS", emoji: "📈" },
  { id: "levels", label: "Níveis", emoji: "📊" },
  { id: "dc", label: "DC Local", emoji: "⚡" },
];

const SPECTRAL_TAB_IDS = new Set<AudioTab>(["spectrogram", "enf", "ltas"]);
const LEVELS_TAB_IDS = new Set<AudioTab>(["levels", "dc"]);
type AudioGroup = "spectral" | "levels";

const TECHNIQUE: Record<AudioTab, string> = {
  spectrogram: "audio_spectrogram",
  enf: "audio_enf",
  levels: "audio_levels",
  dc: "audio_dc_local",
  ltas: "audio_ltas",
};

const LTAS_ARTIFACTS: Record<LtasPanelKey, { filename: string; label: string; title: string }> = {
  normal: { filename: "ltas_normal.html", label: "ltas_normal", title: "LTAS normal" },
  "6db": { filename: "ltas_6db.html", label: "ltas_6db", title: "LTAS 6 dB/oitava" },
  sorted: { filename: "ltas_sorted.html", label: "ltas_sorted", title: "LTAS ordenado" },
  derivative: { filename: "ltas_derivative.html", label: "ltas_derivative", title: "Derivada LTAS ordenado" },
};

const COMPARE_DERIVATIVE: Partial<Record<CompareTab, { filename: string; label: string }>> = {
  enf: { filename: "interactive.html", label: "enf" },
  levels: { filename: "interactive.html", label: "niveis" },
  dc: { filename: "interactive.html", label: "dc_local" },
};

const OVERLAY_SNAPSHOT: Record<"enf" | "levels" | "dc", string> = {
  enf: "enf_overlay_snapshot.png",
  levels: "levels_overlay_snapshot.png",
  dc: "dc_overlay_snapshot.png",
};

const LTAS_OVERLAY_SNAPSHOT: Record<LtasPanelKey, string> = {
  normal: "ltas_normal_overlay_snapshot.png",
  "6db": "ltas_6db_overlay_snapshot.png",
  sorted: "ltas_sorted_overlay_snapshot.png",
  derivative: "ltas_derivative_overlay_snapshot.png",
};

const COMPARE_PLOT_HEIGHT = 560;
/** Altura de cada painel LTAS empilhado (largura 100% do painel). */
const LTAS_PANEL_HEIGHT = 520;
/** Estéreo com canal 0 (ambos): curvas empilhadas verticalmente (altura 700px). */
const LEVELS_STACKED_PLOT_HEIGHT = COMPARE_PLOT_HEIGHT + 120;

export default function AudioForensicsHub() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") as AudioTab | null;
  const groupParam = (searchParams.get("group") as AudioGroup | null) || "spectral";
  const tab =
    tabParam && TABS.some((t) => t.id === tabParam)
      ? tabParam
      : groupParam === "levels"
        ? "levels"
        : "spectrogram";
  const activeGroup: AudioGroup =
    groupParam === "levels" || LEVELS_TAB_IDS.has(tab) ? "levels" : "spectral";
  const visibleTabs = TABS.filter((t) =>
    activeGroup === "levels" ? LEVELS_TAB_IDS.has(t.id) : SPECTRAL_TAB_IDS.has(t.id)
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedFilename, setSelectedFilename] = useState("");
  const [retainForComparison, setRetainForComparison] = useState(false);
  const [stereoDiff, setStereoDiff] = useState(false);

  const [fftExp, setFftExp] = useState(10);
  const [windowType, setWindowType] = useState("hamming");
  const [windowSizePct, setWindowSizePct] = useState(75);
  const [specResample, setSpecResample] = useState("");
  const [spectrogramAutoRefresh, setSpectrogramAutoRefresh] = useState(true);
  const [decimateDisplay, setDecimateDisplay] = useState(false);
  const [savingDerivativeKey, setSavingDerivativeKey] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const spectrogramPlotRef = useRef<SpectrogramPlotHandle>(null);
  const compareOverlayRef = useRef<AudioOverlayPlotHandle>(null);
  const ltasOverlayRefs = {
    normal: useRef<AudioOverlayPlotHandle>(null),
    "6db": useRef<AudioOverlayPlotHandle>(null),
    sorted: useRef<AudioOverlayPlotHandle>(null),
    derivative: useRef<AudioOverlayPlotHandle>(null),
  } as const satisfies Record<LtasPanelKey, React.RefObject<AudioOverlayPlotHandle | null>>;

  const FNOM_MIN = 1;
  const FNOM_MAX = 300;
  type FnomPreset = 50 | 60 | "custom";
  const [fnomPreset, setFnomPreset] = useState<FnomPreset>(60);
  const [fnomCustom, setFnomCustom] = useState(60);
  const [bwenf, setBwenf] = useState(0.8);

  const resolvedFnom = fnomPreset === "custom" ? fnomCustom : fnomPreset;
  const fnomCustomInvalid =
    fnomPreset === "custom" &&
    (!Number.isFinite(fnomCustom) || fnomCustom < FNOM_MIN || fnomCustom > FNOM_MAX);

  const [bitdepth, setBitdepth] = useState(16);
  const [levelsCanais, setLevelsCanais] = useState(0);

  const [dcDur, setDcDur] = useState(5);

  const [ltasFftExp, setLtasFftExp] = useState(12);
  const [ltasCanais, setLtasCanais] = useState(0);
  const [ltasResample, setLtasResample] = useState("");

  const [comparePlotUrls, setComparePlotUrls] = useState<Partial<Record<CompareTab, string>>>({});
  /** Job concluído por aba comparativa — mantém exportação após trocar de sub-aba. */
  const [exportJobByTab, setExportJobByTab] = useState<Partial<Record<CompareTab, string>>>({});
  const [spectrogramData, setSpectrogramData] = useState<SpectrogramFullData | null>(null);
  const [colorscale, setColorscale] = useState<SpectrogramColorscale>(DEFAULT_SPECTROGRAM_COLORSCALE);
  const [ltasUrls, setLtasUrls] = useState<{
    normal: string | null;
    sixDb: string | null;
    sorted: string | null;
    derivative: string | null;
  }>({ normal: null, sixDb: null, sorted: null, derivative: null });

  const [overlayEnf, setOverlayEnf] = useState<AudioOverlayLayer[]>([]);
  const [overlayLevels, setOverlayLevels] = useState<AudioOverlayLayer[]>([]);
  const [overlayDc, setOverlayDc] = useState<AudioOverlayLayer[]>([]);
  const [overlayLtas, setOverlayLtas] = useState<Record<LtasPanelKey, AudioOverlayLayer[]>>(
    emptyLtasOverlays()
  );
  const [resultByTab, setResultByTab] = useState<
    Partial<Record<AudioTab, Record<string, unknown>>>
  >({});

  const { running, currentJobId, error, progress, progressLabel, runAnalysis, reset, clearRunDisplay } =
    useForensicJob();

  const revokeAll = useCallback(() => {
    Object.values(comparePlotUrls).forEach((u) => {
      if (u) URL.revokeObjectURL(u);
    });
    Object.values(ltasUrls).forEach((u) => {
      if (u) URL.revokeObjectURL(u);
    });
  }, [comparePlotUrls, ltasUrls]);

  const activePlotUrl = isCompareTab(tab) ? comparePlotUrls[tab] ?? null : null;

  function jobIdForDerivativeExport(): string | null {
    if (tab === "spectrogram") {
      return currentJobId ?? null;
    }
    if (isCompareTab(tab)) {
      return exportJobByTab[tab] ?? null;
    }
    return null;
  }

  const tabMetrics = resultByTab[tab] ?? null;

  useEffect(() => () => revokeAll(), [revokeAll]);

  function setGroup(next: AudioGroup) {
    const defaultTab: AudioTab = next === "levels" ? "levels" : "spectrogram";
    setSearchParams({ tab: defaultTab, group: next });
  }

  function setTab(next: AudioTab) {
    if (next !== tab) {
      setSaveMessage(null);
      clearRunDisplay();
    }
    const group: AudioGroup = LEVELS_TAB_IDS.has(next) ? "levels" : "spectral";
    setSearchParams({ tab: next, group });
  }

  function clearOverlays() {
    setOverlayEnf([]);
    setOverlayLevels([]);
    setOverlayDc([]);
    setOverlayLtas(emptyLtasOverlays());
  }

  function clearDisplayOnly() {
    revokeAll();
    setComparePlotUrls({});
    setExportJobByTab({});
    setSpectrogramData(null);
    setLtasUrls({ normal: null, sixDb: null, sorted: null, derivative: null });
  }

  function clearPlots() {
    clearDisplayOnly();
    clearOverlays();
    setResultByTab({});
    reset();
  }

  function clearOverlayForTab(t: CompareTab) {
    switch (t) {
      case "enf":
        setOverlayEnf([]);
        break;
      case "levels":
        setOverlayLevels([]);
        break;
      case "dc":
        setOverlayDc([]);
        break;
      case "ltas":
        setOverlayLtas(emptyLtasOverlays());
        break;
    }
  }

  async function loadPlotBundle(jobId: string): Promise<PlotBundleJson> {
    const response = await api.get<PlotBundleJson>(`/analysis/${jobId}/result/audio-plot-data`);
    return response.data;
  }

  async function loadLtasPlotData(
    jobId: string
  ): Promise<Record<LtasPanelKey, PlotBundleJson>> {
    const response = await api.get<Record<LtasPanelKey, PlotBundleJson>>(
      `/analysis/${jobId}/result/audio-plot-data`
    );
    return response.data;
  }

  async function loadSpectrogramDisplay(
    jobId: string,
    jobResult: Record<string, unknown>
  ): Promise<SpectrogramFullData> {
    const response = await api.get<SpectrogramFullData>(`/analysis/${jobId}/result/spectrogram-display`);
    return {
      ...response.data,
      window_type: String(jobResult.window_type ?? ""),
      window_size_percent: Number(jobResult.window_size_percent ?? 0),
    };
  }

  async function handleSaveJobDerivative(artifactFilename: string, label: string) {
    const jobId = jobIdForDerivativeExport();
    if (!jobId) return;
    setSavingDerivativeKey(artifactFilename);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: jobId,
        artifact_filename: artifactFilename,
        label,
      });
      setSaveMessage({
        type: "ok",
        text: `${res.message} «${res.evidence.original_filename}». SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setSaveMessage({
        type: "err",
        text: detail || (err instanceof Error ? err.message : "Erro ao salvar derivado"),
      });
    } finally {
      setSavingDerivativeKey(null);
    }
  }

  async function handleSaveSpectrogramDerivative() {
    if (!currentJobId || !spectrogramData) return;
    setSavingDerivativeKey("spectrogram_snapshot.png");
    setSaveMessage(null);
    try {
      const blob = await spectrogramPlotRef.current?.exportPngBlob();
      if (!blob) throw new Error("Grafico nao pronto");

      const form = new FormData();
      form.append("file", blob, "spectrogram_snapshot.png");
      await api.post(`/analysis/${currentJobId}/spectrogram/snapshot`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: "spectrogram_snapshot.png",
        label: "espectrograma",
        effective_parameters: {
          fft_points: fftExp,
          window_type: windowType,
          window_size_percent: windowSizePct,
          resample_rate: specResample ? Number(specResample) : null,
          colorscale,
          stereo_diff: stereoDiff,
        },
      });
      setSaveMessage({
        type: "ok",
        text: `${res.message} «${res.evidence.original_filename}». SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setSaveMessage({
        type: "err",
        text: detail || (err instanceof Error ? err.message : "Erro ao salvar derivado"),
      });
    } finally {
      setSavingDerivativeKey(null);
    }
  }

  function overlayEffectiveParameters(layers: AudioOverlayLayer[]): Record<string, unknown> {
    return {
      ...buildParams(),
      view: "client_overlay_composite",
      overlay_evidence_labels: layers.map((layer) => layer.evidenceLabel),
      overlay_layer_count: layers.length,
      retain_for_comparison: retainForComparison,
    };
  }

  async function handleSaveOverlayDerivative(
    artifactFilename: string,
    label: string,
    layers: AudioOverlayLayer[],
    plotRef: React.RefObject<AudioOverlayPlotHandle | null>
  ) {
    const jobId = jobIdForDerivativeExport();
    if (!jobId || layers.length === 0) return;
    setSavingDerivativeKey(artifactFilename);
    setSaveMessage(null);
    try {
      const blob = await plotRef.current?.exportPngBlob();
      if (!blob) throw new Error("Grafico nao pronto");

      const form = new FormData();
      form.append("file", blob, artifactFilename);
      form.append("artifact_filename", artifactFilename);
      await api.post(`/analysis/${jobId}/plot-snapshot`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const res = await saveDerivative({
        job_id: jobId,
        artifact_filename: artifactFilename,
        label,
        effective_parameters: overlayEffectiveParameters(layers),
      });
      setSaveMessage({
        type: "ok",
        text: `${res.message} «${res.evidence.original_filename}». SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setSaveMessage({
        type: "err",
        text: detail || (err instanceof Error ? err.message : "Erro ao salvar derivado"),
      });
    } finally {
      setSavingDerivativeKey(null);
    }
  }

  function renderOverlayDerivativeActions(
    artifactFilename: string,
    label: string,
    layers: AudioOverlayLayer[],
    plotRef: React.RefObject<AudioOverlayPlotHandle | null>,
    buttonText = "Salvar composição nos derivados"
  ) {
    if (!jobIdForDerivativeExport() || !caseId || layers.length === 0) return null;
    const saving = savingDerivativeKey === artifactFilename;
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
        <button
          type="button"
          onClick={() => handleSaveOverlayDerivative(artifactFilename, label, layers, plotRef)}
          disabled={!!savingDerivativeKey}
          style={btnPrimary}
        >
          {saving ? "Salvando…" : buttonText}
        </button>
        <button type="button" onClick={() => navigate(`/cases/${caseId}?tab=derivados`)} style={btnSecondary}>
          Abrir derivados
        </button>
      </div>
    );
  }

  function renderDerivativeActions(
    artifactFilename: string,
    label: string,
    buttonText = "Salvar nos derivados"
  ) {
    if (!jobIdForDerivativeExport() || !caseId) return null;
    const saving = savingDerivativeKey === artifactFilename;
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
        <button
          type="button"
          onClick={() => handleSaveJobDerivative(artifactFilename, label)}
          disabled={!!savingDerivativeKey}
          style={btnPrimary}
        >
          {saving ? "Salvando…" : buttonText}
        </button>
        <button type="button" onClick={() => navigate(`/cases/${caseId}?tab=derivados`)} style={btnSecondary}>
          Abrir derivados
        </button>
      </div>
    );
  }

  function onSelectEvidence(id: string, filename: string) {
    setSelectedId(id);
    setSelectedFilename(filename);
    clearPlots();
    setSaveMessage(null);
  }

  async function loadHtml(jobId: string, filename: string): Promise<string> {
    const response = await api.get(`/analysis/${jobId}/result/file?filename=${encodeURIComponent(filename)}`, {
      responseType: "blob",
    });
    return URL.createObjectURL(new Blob([response.data], { type: "text/html" }));
  }

  function buildParams(): Record<string, unknown> {
    const base = { stereo_diff: stereoDiff };
    switch (tab) {
      case "spectrogram":
        return {
          ...base,
          fft_points: fftExp,
          window_type: windowType,
          window_size_percent: windowSizePct,
          resample_rate: specResample ? Number(specResample) : null,
        };
      case "enf":
        return { ...base, fnom: resolvedFnom, bwenf };
      case "levels":
        return { ...base, bitdepth, canais: levelsCanais };
      case "dc":
        return { ...base, dur: dcDur };
      case "ltas":
        return {
          ...base,
          fft_points: ltasFftExp,
          nperseg: 2 ** ltasFftExp,
          canais: ltasCanais,
          resample_rate: ltasResample ? Number(ltasResample) : null,
        };
      default:
        return base;
    }
  }

  async function process(fromAutoRefresh = false) {
    if (!selectedId) return;
    const evidenceLabel = selectedFilename || "evidência";
    const keepSpectrogramVisible =
      fromAutoRefresh && tab === "spectrogram" && spectrogramData !== null;

    if (tab === "spectrogram") {
      if (!keepSpectrogramVisible) {
        setSpectrogramData(null);
      }
    } else if (tab === "ltas") {
      if (!retainForComparison) {
        Object.values(ltasUrls).forEach((u) => {
          if (u) URL.revokeObjectURL(u);
        });
        setLtasUrls({ normal: null, sixDb: null, sorted: null, derivative: null });
        clearOverlayForTab("ltas");
      }
    } else if (isCompareTab(tab) && !retainForComparison) {
      const prevUrl = comparePlotUrls[tab];
      if (prevUrl) URL.revokeObjectURL(prevUrl);
      setComparePlotUrls((prev) => {
        const next = { ...prev };
        delete next[tab];
        return next;
      });
      clearOverlayForTab(tab);
    }

    const technique = TECHNIQUE[tab];
    try {
      await runAnalysis(selectedId, technique, buildParams(), {
        onArtifactsLoaded: async (jobId, jobResult) => {
          setResultByTab((prev) => ({ ...prev, [tab]: jobResult }));
          if (isCompareTab(tab)) {
            setExportJobByTab((prev) => ({ ...prev, [tab]: jobId }));
          }
          if (tab === "ltas") {
            const [normal, sixDb, sorted, derivative] = await Promise.all([
              loadHtml(jobId, "ltas_normal.html"),
              loadHtml(jobId, "ltas_6db.html"),
              loadHtml(jobId, "ltas_sorted.html"),
              loadHtml(jobId, "ltas_derivative.html"),
            ]);
            setLtasUrls({ normal, sixDb, sorted, derivative });
            try {
              const panels = await loadLtasPlotData(jobId);
              setOverlayLtas((prev) =>
                appendLtasOverlays(prev, retainForComparison, evidenceLabel, panels)
              );
            } catch {
              /* HTML interativo ja carregado */
            }
          } else if (tab === "spectrogram") {
            setSpectrogramData(await loadSpectrogramDisplay(jobId, jobResult));
          } else if (tab === "enf") {
            const htmlUrl = await loadHtml(jobId, "interactive.html");
            setComparePlotUrls((prev) => {
              const old = prev.enf;
              if (old) URL.revokeObjectURL(old);
              return { ...prev, enf: htmlUrl };
            });
            try {
              const bundle = await loadPlotBundle(jobId);
              setOverlayEnf((prev) =>
                appendOverlayLayer(prev, retainForComparison, evidenceLabel, bundle)
              );
            } catch {
              if (!retainForComparison) setOverlayEnf([]);
            }
          } else if (tab === "levels") {
            const htmlUrl = await loadHtml(jobId, "interactive.html");
            setComparePlotUrls((prev) => {
              const old = prev.levels;
              if (old) URL.revokeObjectURL(old);
              return { ...prev, levels: htmlUrl };
            });
            try {
              const bundle = await loadPlotBundle(jobId);
              setOverlayLevels((prev) =>
                appendOverlayLayer(prev, retainForComparison, evidenceLabel, bundle)
              );
            } catch {
              if (!retainForComparison) setOverlayLevels([]);
            }
          } else if (tab === "dc") {
            const htmlUrl = await loadHtml(jobId, "interactive.html");
            setComparePlotUrls((prev) => {
              const old = prev.dc;
              if (old) URL.revokeObjectURL(old);
              return { ...prev, dc: htmlUrl };
            });
            try {
              const bundle = await loadPlotBundle(jobId);
              setOverlayDc((prev) =>
                appendOverlayLayer(prev, retainForComparison, evidenceLabel, bundle)
              );
            } catch {
              if (!retainForComparison) setOverlayDc([]);
            }
          }
        },
      });
    } catch {
      /* hook */
    }
  }

  const processRef = useRef(process);
  processRef.current = process;

  const specAutoParamsBaseline = useRef<string | null>(null);

  useEffect(() => {
    specAutoParamsBaseline.current = null;
  }, [selectedId]);

  useEffect(() => {
    if (tab !== "spectrogram" || !spectrogramAutoRefresh || !selectedId || running) return;
    if (!spectrogramData && !currentJobId) return;

    const paramKey = `${fftExp}|${windowType}|${windowSizePct}`;
    if (specAutoParamsBaseline.current === null) {
      specAutoParamsBaseline.current = paramKey;
      return;
    }
    if (specAutoParamsBaseline.current === paramKey) return;
    specAutoParamsBaseline.current = paramKey;

    const timer = window.setTimeout(() => {
      void processRef.current(true);
    }, 500);

    return () => window.clearTimeout(timer);
  }, [
    tab,
    spectrogramAutoRefresh,
    selectedId,
    running,
    spectrogramData,
    currentJobId,
    fftExp,
    windowType,
    windowSizePct,
  ]);

  function overlayLayersForTab(): AudioOverlayLayer[] {
    switch (tab) {
      case "enf":
        return overlayEnf;
      case "levels":
        return overlayLevels;
      case "dc":
        return overlayDc;
      default:
        return [];
    }
  }

  const compareLayers = overlayLayersForTab();
  const comparePlotHeight =
    tab === "levels" && levelsCanais === 0 ? LEVELS_STACKED_PLOT_HEIGHT : COMPARE_PLOT_HEIGHT;
  const showCompareOverlay = isCompareTab(tab) && compareLayers.length > 1;
  const compareDerivative = isCompareTab(tab) ? COMPARE_DERIVATIVE[tab] : undefined;
  /** Painel de resultado já exibe gráfico + ações de derivado — evita duplicar o bloco fallback. */
  const showCompareDerivativePanel =
    isCompareTab(tab) &&
    (showCompareOverlay || !!activePlotUrl || compareLayers.length === 1);
  const showCompareDerivativeFallback =
    isCompareTab(tab) &&
    !!compareDerivative &&
    !!jobIdForDerivativeExport() &&
    !running &&
    !showCompareDerivativePanel;
  const maxLtasOverlayLayers = Math.max(0, ...LTAS_PANELS.map((p) => overlayLtas[p.key].length));
  const showLtasCompareOverlay = tab === "ltas" && maxLtasOverlayLayers > 1;

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="Análise forense de Áudio"
      subtitle="Análise espectral (espectrograma, ENF, LTAS) e análise de níveis (níveis, DC local)."
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
        <button
          type="button"
          onClick={() => setGroup("spectral")}
          style={{
            textAlign: "left",
            padding: "1rem",
            borderRadius: 8,
            border: `2px solid ${activeGroup === "spectral" ? "#0369a1" : "#e5e7eb"}`,
            background: activeGroup === "spectral" ? "#f0f9ff" : "#fff",
            cursor: "pointer",
          }}
        >
          <strong style={{ display: "block", marginBottom: 4 }}>Análise espectral</strong>
          <span style={{ fontSize: "0.82rem", color: "#6b7280" }}>Espectrograma, ENF e LTAS</span>
        </button>
        <button
          type="button"
          onClick={() => setGroup("levels")}
          style={{
            textAlign: "left",
            padding: "1rem",
            borderRadius: 8,
            border: `2px solid ${activeGroup === "levels" ? "#0369a1" : "#e5e7eb"}`,
            background: activeGroup === "levels" ? "#f0f9ff" : "#fff",
            cursor: "pointer",
          }}
        >
          <strong style={{ display: "block", marginBottom: 4 }}>Análise de níveis</strong>
          <span style={{ fontSize: "0.82rem", color: "#6b7280" }}>Níveis e DC local</span>
        </button>
      </div>

      <AnalysisPanel title="Evidência de áudio">
        <AudioEvidenceSelector caseId={caseId} selectedId={selectedId} onSelect={onSelectEvidence} />
      </AnalysisPanel>

      <AnalysisPanel title="Pré-processamento">
        <label style={checkRow}>
          <input type="checkbox" checked={stereoDiff} onChange={(e) => setStereoDiff(e.target.checked)} />
          Gerar resíduo diferencial estéreo (L invertido + R, ÷2) — apenas estéreo
        </label>
      </AnalysisPanel>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: "1rem" }}>
        {visibleTabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            style={{
              padding: "0.45rem 0.9rem",
              borderRadius: 6,
              border: `1px solid ${tab === t.id ? "#0369a1" : "#d1d5db"}`,
              background: tab === t.id ? "#e0f2fe" : "#fff",
              cursor: "pointer",
              fontSize: "0.85rem",
            }}
          >
            {t.emoji} {t.label}
          </button>
        ))}
      </div>

      {tab === "spectrogram" && (
        <AnalysisPanel title="Parâmetros do espectrograma">
          <div style={paramGrid}>
            <label style={lbl}>
              Pontos FFT (2^N)
              <input type="range" min={7} max={16} value={fftExp} onChange={(e) => setFftExp(Number(e.target.value))} />
              <span style={hint}>N = {fftExp} → {2 ** fftExp} pontos (128–65536)</span>
            </label>
            <label style={lbl}>
              Tipo de janela
              <select value={windowType} onChange={(e) => setWindowType(e.target.value)} style={inputBlock}>
                <option value="hamming">hamming</option>
                <option value="hanning">hanning</option>
                <option value="blackman">blackman</option>
                <option value="blackmanharris">blackmanharris</option>
                <option value="kaiser">kaiser</option>
              </select>
            </label>
            <label style={lbl}>
              Tamanho da janela (%)
              <input
                type="range"
                min={10}
                max={100}
                step={5}
                value={windowSizePct}
                onChange={(e) => setWindowSizePct(Number(e.target.value))}
              />
              <span style={hint}>{windowSizePct}%</span>
            </label>
            <label style={lbl}>
              Taxa de reamostragem (Hz)
              <input
                type="number"
                placeholder="vazio = original"
                value={specResample}
                onChange={(e) => setSpecResample(e.target.value)}
                style={inputBlock}
              />
            </label>
            <label style={{ ...checkRow, alignSelf: "flex-end", minWidth: 220 }}>
              <input
                type="checkbox"
                checked={spectrogramAutoRefresh}
                onChange={(e) => setSpectrogramAutoRefresh(e.target.checked)}
              />
              Atualizar automaticamente
            </label>
          </div>
          <p style={{ fontSize: "0.8rem", color: "#6b7280", margin: "0.5rem 0 0" }}>
            Com a opção marcada, alterações em pontos FFT, tipo de janela e tamanho da janela (%)
            reprocessam o espectrograma após ~0,5 s (é necessário gerar uma vez antes). A taxa de
            reamostragem não dispara atualização automática — use &quot;Gerar espectrograma&quot;.
          </p>
        </AnalysisPanel>
      )}

      {tab === "enf" && (
        <AnalysisPanel title="Parâmetros ENF">
          <div style={paramGrid}>
            <label style={lbl}>
              Frequência nominal fnom (Hz)
              <select
                value={fnomPreset === "custom" ? "custom" : String(fnomPreset)}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "custom") setFnomPreset("custom");
                  else setFnomPreset(Number(v) as 50 | 60);
                }}
                style={inputBlock}
              >
                <option value="60">60 (Américas)</option>
                <option value="50">50 (Europa/BR rede)</option>
                <option value="custom">Personalizada</option>
              </select>
            </label>
            {fnomPreset === "custom" && (
              <label style={lbl}>
                Frequência customizada (Hz)
                <input
                  type="number"
                  min={FNOM_MIN}
                  max={FNOM_MAX}
                  step={0.1}
                  value={fnomCustom}
                  onChange={(e) => setFnomCustom(Number(e.target.value))}
                  style={inputBlock}
                />
                {fnomCustomInvalid && (
                  <span style={{ ...hint, color: "#b91c1c" }}>
                    Informe um valor entre {FNOM_MIN} e {FNOM_MAX} Hz
                  </span>
                )}
              </label>
            )}
            <label style={lbl}>
              Largura de banda BWenf (Hz)
              <input
                type="range"
                min={0.1}
                max={2}
                step={0.1}
                value={bwenf}
                onChange={(e) => setBwenf(Number(e.target.value))}
              />
              <span style={hint}>{bwenf.toFixed(1)} Hz</span>
            </label>
          </div>
        </AnalysisPanel>
      )}

      {tab === "levels" && (
        <AnalysisPanel title="Parâmetros de quantização (níveis)">
          <div style={paramGrid}>
            <label style={lbl}>
              Bits por amostra
              <select value={bitdepth} onChange={(e) => setBitdepth(Number(e.target.value))} style={inputBlock}>
                <option value={8}>8</option>
                <option value={16}>16</option>
                <option value={24}>24</option>
                <option value={32}>32</option>
              </select>
            </label>
            <label style={lbl}>
              Canal (0=ambos, 1=esquerdo, 2=direito)
              <input
                type="number"
                min={0}
                max={2}
                value={levelsCanais}
                onChange={(e) => setLevelsCanais(Number(e.target.value))}
                style={inputBlock}
              />
            </label>
          </div>
        </AnalysisPanel>
      )}

      {tab === "dc" && (
        <AnalysisPanel title="Parâmetros DC local">
          <label style={lbl}>
            Duração da janela (s)
            <input
              type="number"
              min={0.1}
              step={0.5}
              value={dcDur}
              onChange={(e) => setDcDur(Number(e.target.value))}
              style={inputBlock}
            />
          </label>
        </AnalysisPanel>
      )}

      {tab === "ltas" && (
        <AnalysisPanel title="Parâmetros LTAS">
          <div style={paramGrid}>
            <label style={lbl}>
              N para FFT / Welch (2^N)
              <input
                type="range"
                min={8}
                max={16}
                value={ltasFftExp}
                onChange={(e) => setLtasFftExp(Number(e.target.value))}
              />
              <span style={hint}>nperseg = {2 ** ltasFftExp}</span>
            </label>
            <label style={lbl}>
              Canal (0=mono equiv., 1=E, 2=D)
              <input
                type="number"
                min={0}
                max={2}
                value={ltasCanais}
                onChange={(e) => setLtasCanais(Number(e.target.value))}
                style={inputBlock}
              />
            </label>
            <label style={lbl}>
              Taxa de reamostragem (Hz)
              <input
                type="number"
                placeholder="vazio = original"
                value={ltasResample}
                onChange={(e) => setLtasResample(e.target.value)}
                style={inputBlock}
              />
            </label>
          </div>
        </AnalysisPanel>
      )}

      {isCompareTab(tab) && (
        <AnalysisPanel title="Comparação entre evidências">
          <label style={checkRow}>
            <input
              type="checkbox"
              checked={retainForComparison}
              onChange={(e) => setRetainForComparison(e.target.checked)}
            />
            Reter dados para comparação
          </label>
          <p style={{ fontSize: "0.8rem", color: "#6b7280", margin: "0.5rem 0 0" }}>
            Com a opção marcada, cada nova análise sobrepõe a evidência atual às anteriores nesta aba
            (cores distintas por áudio). Desmarque para substituir o gráfico.
          </p>
        </AnalysisPanel>
      )}

      <AnalysisPanel title="Executar">
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          <ProcessButton
            onClick={process}
            disabled={!selectedId || (tab === "enf" && fnomCustomInvalid)}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label={
              tab === "spectrogram"
                ? "Gerar espectrograma"
                : tab === "enf"
                  ? "Analisar ENF"
                  : tab === "levels"
                    ? "Analisar níveis"
                    : tab === "dc"
                      ? "Analisar DC local"
                      : "Analisar LTAS"
            }
          />
          <button type="button" onClick={clearPlots} style={btnSecondary}>
            Limpar gráficos
          </button>
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {tab === "spectrogram" && spectrogramData && (
        <AnalysisPanel title="Espectrograma interativo">
          <div style={{ position: "relative" }}>
            {running && tab === "spectrogram" && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  zIndex: 2,
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "flex-end",
                  padding: "0.5rem",
                  pointerEvents: "none",
                }}
              >
                <span
                  style={{
                    fontSize: "0.75rem",
                    color: "#0369a1",
                    background: "rgba(255,255,255,0.92)",
                    border: "1px solid #bae6fd",
                    borderRadius: 6,
                    padding: "0.25rem 0.55rem",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
                  }}
                >
                  Atualizando… {Math.round(progress)}%
                </span>
              </div>
            )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "1.25rem", marginBottom: "0.75rem", alignItems: "flex-end" }}>
            <label style={{ ...lbl, maxWidth: 280 }}>
              Paleta de cores
              <select
                value={colorscale}
                onChange={(e) => setColorscale(e.target.value as SpectrogramColorscale)}
                style={inputBlock}
              >
                {SPECTROGRAM_COLORSCALES.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label style={checkRow}>
              <input
                type="checkbox"
                checked={decimateDisplay}
                onChange={(e) => setDecimateDisplay(e.target.checked)}
              />
              Decimar exibição (max-pool 2000×512)
            </label>
          </div>
          <SpectrogramPlot
            ref={spectrogramPlotRef}
            data={spectrogramData}
            colorscale={colorscale}
            decimateDisplay={decimateDisplay}
            height={560}
          />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
            <button
              type="button"
              onClick={handleSaveSpectrogramDerivative}
              disabled={!currentJobId || !!savingDerivativeKey}
              style={btnPrimary}
            >
              {savingDerivativeKey === "spectrogram_snapshot.png" ? "Salvando…" : "Salvar nos derivados"}
            </button>
            {caseId && (
              <button type="button" onClick={() => navigate(`/cases/${caseId}?tab=derivados`)} style={btnSecondary}>
                Abrir derivados
              </button>
            )}
          </div>
          {saveMessage && tab === "spectrogram" && (
            <MessageBox type={saveMessage.type} text={saveMessage.text} />
          )}
          </div>
        </AnalysisPanel>
      )}

      {isCompareTab(tab) && showCompareOverlay && (
        <AnalysisPanel title="Resultado comparativo">
          <p style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 0 }}>
            {compareLayers.length} evidência(s) sobrepostas — zoom, pan e hover no gráfico. Troque de evidência
            e execute de novo com &quot;Reter dados&quot; para acrescentar outra curva.
          </p>
          <AudioOverlayPlot ref={compareOverlayRef} layers={compareLayers} height={comparePlotHeight} width={900} />
          {compareDerivative &&
            tab !== "ltas" &&
            renderOverlayDerivativeActions(
              OVERLAY_SNAPSHOT[tab],
              compareDerivative.label,
              compareLayers,
              compareOverlayRef,
              tab === "enf" ? "Salvar ENF (composição) nos derivados" : "Salvar composição nos derivados"
            )}
          {saveMessage && isCompareTab(tab) && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}

      {isCompareTab(tab) && !showCompareOverlay && activePlotUrl && (
        <AnalysisPanel title="Resultado interativo">
          <p style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 0 }}>
            Gráfico Plotly com zoom, pan e hover. Marque &quot;Reter dados para
            comparação&quot; e execute outra evidência para sobrepor curvas.
          </p>
          <PlotlyHtmlFrame url={activePlotUrl} height={comparePlotHeight} />
          {compareDerivative &&
            renderDerivativeActions(
              compareDerivative.filename,
              compareDerivative.label,
              tab === "enf" ? "Salvar ENF nos derivados" : undefined
            )}
          {saveMessage && isCompareTab(tab) && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}

      {isCompareTab(tab) && !showCompareOverlay && !activePlotUrl && compareLayers.length === 1 && (
        <AnalysisPanel title="Resultado interativo">
          <AudioOverlayPlot ref={compareOverlayRef} layers={compareLayers} height={comparePlotHeight} width={900} />
          {compareDerivative &&
            tab !== "ltas" &&
            renderOverlayDerivativeActions(
              OVERLAY_SNAPSHOT[tab],
              compareDerivative.label,
              compareLayers,
              compareOverlayRef,
              tab === "enf" ? "Salvar ENF (composição) nos derivados" : "Salvar composição nos derivados"
            )}
          {saveMessage && isCompareTab(tab) && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}

      {showCompareDerivativeFallback && compareDerivative && (
        <AnalysisPanel title={tab === "enf" ? "Exportar ENF" : "Exportar resultado"}>
          <p style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 0 }}>
            Análise concluída. O relatório interativo (
            <code>{compareDerivative.filename}</code>) pode ser salvo nos derivados do caso.
          </p>
          {renderDerivativeActions(
            compareDerivative.filename,
            compareDerivative.label,
            tab === "enf" ? "Salvar ENF nos derivados" : "Salvar nos derivados"
          )}
          {saveMessage && isCompareTab(tab) && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}

      {tab === "ltas" && showLtasCompareOverlay && (
        <AnalysisPanel title="LTAS — comparação (quatro painéis)">
          <p style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 0 }}>
            {maxLtasOverlayLayers} evidência(s) por painel — legendas curtas; detalhes no hover.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {LTAS_PANELS.map((panel) => (
              <div key={panel.key} style={{ width: "100%" }}>
                <AudioOverlayPlot
                  ref={ltasOverlayRefs[panel.key]}
                  layers={overlayLtas[panel.key]}
                  panelTitle={panel.title}
                  height={LTAS_PANEL_HEIGHT}
                />
                {renderOverlayDerivativeActions(
                  LTAS_OVERLAY_SNAPSHOT[panel.key],
                  LTAS_ARTIFACTS[panel.key].label,
                  overlayLtas[panel.key],
                  ltasOverlayRefs[panel.key],
                  `Salvar ${panel.title} (composição) nos derivados`
                )}
              </div>
            ))}
          </div>
          {saveMessage && tab === "ltas" && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}

      {tab === "ltas" && !showLtasCompareOverlay && (ltasUrls.normal || ltasUrls.sixDb) && (
        <AnalysisPanel title="LTAS — quatro visualizações">
          <p style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 0 }}>
            Visualização Plotly interativa (HTML). Use &quot;Reter dados&quot; em duas ou mais
            evidências para comparar no modo sobreposto.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {LTAS_PANELS.map((panel) => {
              const url =
                panel.key === "normal"
                  ? ltasUrls.normal
                  : panel.key === "6db"
                    ? ltasUrls.sixDb
                    : panel.key === "sorted"
                      ? ltasUrls.sorted
                      : ltasUrls.derivative;
              if (!url) return null;
              const artifact = LTAS_ARTIFACTS[panel.key];
              return (
                <div key={panel.key} style={{ width: "100%" }}>
                  <PlotlyHtmlFrame url={url} title={panel.title} height={LTAS_PANEL_HEIGHT} />
                  {renderDerivativeActions(
                    artifact.filename,
                    artifact.label,
                    `Salvar ${panel.title} nos derivados`
                  )}
                </div>
              );
            })}
          </div>
          {saveMessage && tab === "ltas" && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}

      {tabMetrics && (
        <AnalysisPanel title="Métricas">
          <pre style={metricsPre}>{JSON.stringify(tabMetrics, null, 2)}</pre>
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

const lbl: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: "0.82rem",
  minWidth: 180,
};

const hint: CSSProperties = { fontSize: "0.75rem", color: "#6b7280" };

const inputBlock: CSSProperties = { padding: "0.4rem", maxWidth: 220 };

const paramGrid: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "1.25rem",
};

const checkRow: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  fontSize: "0.85rem",
  cursor: "pointer",
};

const btnSecondary: CSSProperties = {
  padding: "0.45rem 0.9rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
};

const btnPrimary: CSSProperties = {
  padding: "0.45rem 0.9rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
  fontWeight: 500,
};

const metricsPre: CSSProperties = {
  maxHeight: 200,
  overflow: "auto",
  background: "#f9fafb",
  padding: "0.75rem",
  borderRadius: 8,
  fontSize: "0.75rem",
  margin: 0,
};
