import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { saveDerivative } from "@/services/evidence";
import { useLocalizationMaskPreview } from "@/hooks/useLocalizationMaskPreview";
import { revokeBlobUrl } from "@/utils/localizationMaskPreview";
import api from "@/services/api";

type MethodTier = "native" | "ecosystem";
type MethodStatus = "ready" | "weights_missing" | "vendor_missing" | "unavailable";
type FilterTier = "all" | MethodTier;
type ViewMode = "overlay" | "heatmap" | "mask";

interface MesorchVariant {
  id: string;
  label: string;
  filename: string;
  ready: boolean;
}

interface ImdlMethod {
  id: string;
  name: string;
  venue: string;
  tier: MethodTier;
  description: string;
  repo_url: string;
  stars: number | null;
  accent: string;
  status: MethodStatus;
  unavailable_reason: string | null;
  ready: boolean;
  variants: MesorchVariant[] | null;
}

const TIER_LABEL: Record<MethodTier, string> = {
  native: "Nativos IMDL-BenCo",
  ecosystem: "Ecossistema (repos parceiros)",
};

const STATUS_LABEL: Record<MethodStatus, string> = {
  ready: "Pronto",
  weights_missing: "Pesos ausentes",
  vendor_missing: "Repo externo",
  unavailable: "Indisponivel",
};

export default function ImdlBencoHub() {
  const { caseId } = useParams<{ caseId: string }>();
  const [methods, setMethods] = useState<ImdlMethod[]>([]);
  const [loadingMethods, setLoadingMethods] = useState(true);
  const [filter, setFilter] = useState<FilterTier>("all");
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);
  const [selectionSource, setSelectionSource] = useState<"original" | "derivative">("original");
  const [threshold, setThreshold] = useState(0.5);
  const [mesorchVariant, setMesorchVariant] = useState("standard");
  const [viewMode, setViewMode] = useState<ViewMode>("overlay");
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [heatmapUrl, setHeatmapUrl] = useState<string | null>(null);
  const [scoreMapUrl, setScoreMapUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  useEffect(() => {
    api
      .get<ImdlMethod[]>("/analysis/imdlbenco/methods")
      .then((res) => {
        setMethods(res.data);
        const firstReady = res.data.find((m) => m.ready);
        setSelectedMethod(firstReady?.id ?? res.data[0]?.id ?? null);
      })
      .catch(() => setMethods([]))
      .finally(() => setLoadingMethods(false));
  }, []);

  const filtered = useMemo(
    () => methods.filter((m) => filter === "all" || m.tier === filter),
    [methods, filter]
  );

  const active = methods.find((m) => m.id === selectedMethod) ?? null;
  const readyCount = methods.filter((m) => m.ready).length;
  const mesorchVariants = active?.variants ?? [];
  const selectedMesorchReady =
    active?.id !== "mesorch" ||
    mesorchVariants.find((v) => v.id === mesorchVariant)?.ready === true;
  const canProcess = Boolean(active?.ready && selectedMesorchReady);
  const maskPreviewReady = result?.success !== false && Boolean(scoreMapUrl) && !running;
  const maskUrl = useLocalizationMaskPreview(scoreMapUrl, threshold, maskPreviewReady);

  const rightUrl = viewMode === "heatmap" ? heatmapUrl : viewMode === "mask" ? maskUrl : overlayUrl;
  const rightLabel =
    viewMode === "heatmap" ? "Heatmap IMDL-BenCo" : viewMode === "mask" ? "Mascara binaria" : "Overlay";

  function onSelectEvidence(id: string, source: "original" | "derivative") {
    setSelectedEvidence(id);
    setSelectionSource(source);
    reset();
    setInputUrl(`/api/v1/evidences/${id}/file`);
    revokeBlobUrl(heatmapUrl);
    revokeBlobUrl(scoreMapUrl);
    revokeBlobUrl(overlayUrl);
    setHeatmapUrl(null);
    setScoreMapUrl(null);
    setOverlayUrl(null);
    setSaveMessage(null);
    viewerRef.current?.resetZoom();
  }

  useEffect(() => {
    if (active?.id !== "mesorch" || !active.variants?.length) return;
    const ready = active.variants.find((v) => v.ready);
    setMesorchVariant(ready?.id ?? active.variants[0].id);
  }, [active?.id, active?.variants]);

  async function process() {
    if (!selectedEvidence || !selectedMethod || !canProcess) return;
    setSaveMessage(null);
    const params: Record<string, string | number> = { method: selectedMethod, threshold };
    if (selectedMethod === "mesorch") {
      params.mesorch_variant = mesorchVariant;
    }
    try {
      await runAnalysis(
        selectedEvidence,
        "imdlbenco",
        params,
        {
          onArtifactsLoaded: async (jobId) => {
            const scoreMap =
              (await fetchImage(jobId, "score_map.png")) ?? (await fetchImage(jobId, "heatmap.png"));
            const [input, heat, overlay] = await Promise.all([
              fetchImage(jobId, "input_image.png"),
              fetchImage(jobId, "heatmap.png"),
              fetchImage(jobId, "overlay.png"),
            ]);
            setInputUrl(input);
            setHeatmapUrl(heat);
            setScoreMapUrl(scoreMap);
            setOverlayUrl(overlay);
            setViewMode("overlay");
            viewerRef.current?.resetZoom();
          },
        }
      );
    } catch {
      /* hook */
    }
  }

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const effective_parameters: Record<string, unknown> = {
        threshold,
        method: selectedMethod,
      };
      if (selectedMethod === "mesorch") {
        effective_parameters.mesorch_variant = mesorchVariant;
      }
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: filename,
        effective_parameters: filename === "mask.png" ? effective_parameters : undefined,
      });
      setSaveMessage({
        type: "ok",
        text: `${label} salvo. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: String(msg) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <AnalysisPageShell
      caseId={caseId!}
      title="IMDL-BenCo — Hub de Localizacao"
      subtitle="NeurIPS'24 Spotlight · benchmark modular para deteccao e localizacao de manipulacao."
    >
      <AnalysisPanel title="Metodos do benchmark">
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.85rem" }}>
          {(["all", "native", "ecosystem"] as const).map((f) => (
            <button key={f} type="button" onClick={() => setFilter(f)} style={filterBtn(filter === f)}>
              {f === "all" ? `Todos (${methods.length})` : TIER_LABEL[f]}
            </button>
          ))}
          <span style={{ marginLeft: "auto", fontSize: "0.8rem", color: "#6b7280", alignSelf: "center" }}>
            {readyCount} prontos ·{" "}
            <a href="https://github.com/scu-zjz/IMDLBenCo" target="_blank" rel="noreferrer">
              repositorio oficial
            </a>
          </span>
        </div>

        {loadingMethods ? (
          <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Carregando metodos...</p>
        ) : (
          <div style={methodGridStyle}>
            {filtered.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setSelectedMethod(m.id)}
                style={methodCardStyle(m, selectedMethod === m.id)}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <strong style={{ fontSize: "0.92rem" }}>{m.name}</strong>
                  <span style={venueBadge(m.accent)}>{m.venue}</span>
                </div>
                <p style={{ margin: "0.45rem 0 0.55rem", fontSize: "0.78rem", color: "#4b5563", lineHeight: 1.35 }}>
                  {m.description}
                </p>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={statusPill(m.status, m.ready)}>{STATUS_LABEL[m.status]}</span>
                  {m.stars != null && (
                    <span style={{ fontSize: "0.72rem", color: "#9ca3af" }}>★ {m.stars}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}

        {active && !active.ready && active.unavailable_reason && (
          <MessageBox type="err" text={active.unavailable_reason} />
        )}
      </AnalysisPanel>

      <AnalysisPanel title="Evidencia e execucao">
        <ImageEvidenceSelector
          caseId={caseId!}
          selectedId={selectedEvidence}
          selectionSource={selectionSource}
          onSelect={onSelectEvidence}
        />

        {active && (
          <div style={{ marginTop: "1rem", display: "grid", gap: "0.75rem", maxWidth: 520 }}>
            <p style={{ margin: 0, fontSize: "0.82rem", color: "#374151" }}>
              Metodo selecionado: <strong>{active.name}</strong>
              {active.repo_url && (
                <>
                  {" "}
                  ·{" "}
                  <a href={active.repo_url} target="_blank" rel="noreferrer">
                    GitHub
                  </a>
                </>
              )}
            </p>
            {active.id === "mesorch" && mesorchVariants.length > 0 && (
              <label style={{ fontSize: "0.82rem" }}>
                Variante Mesorch
                <select
                  value={mesorchVariant}
                  onChange={(e) => setMesorchVariant(e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 4, padding: "0.35rem" }}
                >
                  {mesorchVariants.map((v) => (
                    <option key={v.id} value={v.id} disabled={!v.ready}>
                      {v.label} ({v.filename}){v.ready ? "" : " — ausente"}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label style={{ fontSize: "0.82rem" }}>
              Limiar da mascara ({threshold.toFixed(2)})
              <input
                type="range"
                min={0.1}
                max={0.9}
                step={0.05}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                style={{ display: "block", width: "100%", marginTop: 4 }}
              />
            </label>
            {maskPreviewReady && (
              <p style={{ margin: 0, fontSize: "0.78rem", color: "#6b7280" }}>
                O limiar atualiza a mascara na hora, sem nova inferencia.
              </p>
            )}
            <ProcessButton
              running={running}
              progress={progress}
              progressLabel={progressLabel}
              disabled={!selectedEvidence || !canProcess}
              onClick={process}
              label={
                canProcess
                  ? `Executar ${active.name}`
                  : active.ready && !selectedMesorchReady
                    ? "Variante Mesorch sem pesos"
                    : `${active.name} indisponivel`
              }
            />
          </div>
        )}
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result?.success !== false && (heatmapUrl || overlayUrl) && (
        <AnalysisPanel title="Resultado">
          {result?.method_name != null && (
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563" }}>
              {String(result.method_name)}
              {result.method_venue != null && <> · {String(result.method_venue)}</>}
              {result.mean_manipulation_score != null && (
                <>
                  {" "}
                  · Score: <strong>{Number(result.mean_manipulation_score).toFixed(4)}</strong>
                </>
              )}
              {result.inference_device != null && (
                <>
                  {" "}
                  · {String(result.inference_device).toUpperCase()}
                </>
              )}
            </p>
          )}
          {typeof result?.inference_window_note === "string" && (
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.82rem", color: "#92400e" }}>
              {result.inference_window_note}
            </p>
          )}

          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["overlay", "Overlay"],
                ["heatmap", "Heatmap"],
                ...(maskUrl ? ([["mask", "Mascara"]] as const) : []),
              ] as const
            ).map(([m, label]) => (
              <button key={m} type="button" onClick={() => setViewMode(m)} style={tabStyle(viewMode === m)}>
                {label}
              </button>
            ))}
          </div>

          {inputUrl && rightUrl && (
            <SyncedImagePairViewer
              ref={viewerRef}
              leftSrc={inputUrl}
              rightSrc={rightUrl}
              leftLabel="Entrada"
              rightLabel={rightLabel}
            />
          )}

          {currentJobId && (
            <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" disabled={saving} onClick={() => handleSave("overlay.png", "Overlay")} style={btnSecondary}>
                Salvar overlay
              </button>
              <button type="button" disabled={saving} onClick={() => handleSave("heatmap.png", "Heatmap")} style={btnSecondary}>
                Salvar heatmap
              </button>
              {maskUrl && (
                <button type="button" disabled={saving} onClick={() => handleSave("mask.png", "Mascara")} style={btnSecondary}>
                  Salvar mascara
                </button>
              )}
            </div>
          )}
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

const methodGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
  gap: "0.75rem",
};

function methodCardStyle(m: ImdlMethod, active: boolean): React.CSSProperties {
  return {
    textAlign: "left",
    padding: "0.85rem 0.9rem",
    borderRadius: 10,
    border: `2px solid ${active ? m.accent : "#e5e7eb"}`,
    background: active ? `${m.accent}10` : "#fff",
    cursor: "pointer",
    boxShadow: active ? `0 0 0 1px ${m.accent}33` : "none",
  };
}

function venueBadge(color: string): React.CSSProperties {
  return {
    fontSize: "0.68rem",
    fontWeight: 600,
    padding: "0.15rem 0.45rem",
    borderRadius: 999,
    background: `${color}18`,
    color,
    whiteSpace: "nowrap",
  };
}

function statusPill(status: MethodStatus, ready: boolean): React.CSSProperties {
  const bg = ready ? "#dcfce7" : status === "weights_missing" ? "#fef3c7" : "#fee2e2";
  const color = ready ? "#166534" : status === "weights_missing" ? "#92400e" : "#991b1b";
  return {
    fontSize: "0.72rem",
    fontWeight: 600,
    padding: "0.2rem 0.5rem",
    borderRadius: 999,
    background: bg,
    color,
  };
}

const filterBtn = (active: boolean): React.CSSProperties => ({
  padding: "0.35rem 0.75rem",
  borderRadius: 999,
  border: `1px solid ${active ? "#0369a1" : "#d1d5db"}`,
  background: active ? "#e0f2fe" : "#fff",
  color: active ? "#0369a1" : "#374151",
  cursor: "pointer",
  fontSize: "0.78rem",
});

const tabStyle = (active: boolean): React.CSSProperties => ({
  padding: "0.35rem 0.75rem",
  borderRadius: 6,
  border: `1px solid ${active ? "#0369a1" : "#d1d5db"}`,
  background: active ? "#e0f2fe" : "#fff",
  color: active ? "#0369a1" : "#374151",
  cursor: "pointer",
  fontSize: "0.8rem",
});

const btnSecondary: React.CSSProperties = {
  padding: "0.45rem 0.85rem",
  borderRadius: 6,
  border: "1px solid #d1d5db",
  background: "#fff",
  cursor: "pointer",
  fontSize: "0.82rem",
};
