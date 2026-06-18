import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";
import {
  IMDL_ADMIN_ONLY_METHOD_IDS,
  IMDL_DEDICATED_METHOD_IDS,
  IMDL_METHOD_LABELS,
  isImageTechniqueDisabledById,
} from "@/config/imageAnalysisGroups";
import { useAuthStore } from "@/store/authStore";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import TruForConfidenceColorScale from "@/components/TruForConfidenceColorScale";
import TruForHeatmapColorScale from "@/components/TruForHeatmapColorScale";
import { getForensicTechniqueMeta } from "@/config/forensicTechniqueMeta";
import { useLocalizationMaskPreview } from "@/hooks/useLocalizationMaskPreview";
import { revokeBlobUrl } from "@/utils/localizationMaskPreview";
import api from "@/services/api";

type ViewMode = "overlay" | "heatmap" | "mask" | "confidence";

function deviceLabelFromProgress(message: string): string | null {
  if (/GPU|CUDA/i.test(message)) return "GPU";
  if (/\bCPU\b/i.test(message)) return "CPU";
  return null;
}

function formatInferenceDevice(value: unknown): string | null {
  if (value == null || value === "") return null;
  const raw = String(value).toLowerCase();
  if (raw === "cuda" || raw === "gpu") return "GPU";
  if (raw === "cpu") return "CPU";
  return String(value).toUpperCase();
}

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
  description: string;
  repo_url: string;
  status: string;
  ready: boolean;
  unavailable_reason: string | null;
  variants: MesorchVariant[] | null;
}

export default function ImdlMethodAnalysis({ embedMethodId }: { embedMethodId?: string } = {}) {
  const { caseId, methodId } = useParams<{ caseId: string; methodId: string }>();
  const effectiveMethodId = embedMethodId ?? methodId;
  const [methodMeta, setMethodMeta] = useState<ImdlMethod | null>(null);
  const [loadingMeta, setLoadingMeta] = useState(true);
  const [threshold, setThreshold] = useState(0.85);
  const [mesorchVariant, setMesorchVariant] = useState("standard");
  const [viewMode, setViewMode] = useState<ViewMode>("overlay");
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [heatmapUrl, setHeatmapUrl] = useState<string | null>(null);
  const [scoreMapUrl, setScoreMapUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [confidenceUrl, setConfidenceUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const userRole = useAuthStore((s) => s.user?.role);

  if (!embedMethodId) {
    if (!effectiveMethodId || !IMDL_DEDICATED_METHOD_IDS.has(effectiveMethodId)) {
      return <Navigate to={caseId ? `/cases/${caseId}?tab=analises&media=imagem` : "/"} replace />;
    }

    if (IMDL_ADMIN_ONLY_METHOD_IDS.has(effectiveMethodId) && userRole !== "admin") {
      return <Navigate to={caseId ? `/cases/${caseId}?tab=analises&media=imagem` : "/"} replace />;
    }
  }

  useEffect(() => {
    if (!effectiveMethodId) return;
    setLoadingMeta(true);
    api
      .get<ImdlMethod[]>("/analysis/imdlbenco/methods")
      .then((res) => {
        const found = res.data.find((m) => m.id === effectiveMethodId) ?? null;
        setMethodMeta(found);
      })
      .catch(() => setMethodMeta(null))
      .finally(() => setLoadingMeta(false));
  }, [effectiveMethodId]);

  const forceDisabled = effectiveMethodId ? isImageTechniqueDisabledById(effectiveMethodId) : false;
  const mesorchVariants = methodMeta?.variants ?? [];
  const selectedMesorchReady =
    effectiveMethodId !== "mesorch" || mesorchVariants.find((v) => v.id === mesorchVariant)?.ready === true;
  const canProcess = !forceDisabled && Boolean(methodMeta?.ready && selectedMesorchReady);
  const maskPreviewReady = result?.success !== false && Boolean(scoreMapUrl) && !running;
  const maskUrl = useLocalizationMaskPreview(scoreMapUrl, threshold, maskPreviewReady);

  const rightUrl =
    viewMode === "heatmap"
      ? heatmapUrl
      : viewMode === "mask"
        ? maskUrl
        : viewMode === "confidence"
          ? confidenceUrl
          : overlayUrl;
  const rightLabel =
    viewMode === "heatmap"
      ? "Mapa de localização"
      : viewMode === "mask"
        ? "Máscara binária"
        : viewMode === "confidence"
          ? "Mapa de confiança"
          : "Overlay";

  useEffect(() => {
    if (effectiveMethodId !== "mesorch" || !mesorchVariants.length) return;
    const ready = mesorchVariants.find((v) => v.ready);
    setMesorchVariant(ready?.id ?? mesorchVariants[0].id);
  }, [effectiveMethodId, mesorchVariants]);

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setInputUrl(`/api/v1/evidences/${id}/file`);
      revokeBlobUrl(heatmapUrl);
      revokeBlobUrl(scoreMapUrl);
      revokeBlobUrl(overlayUrl);
      revokeBlobUrl(confidenceUrl);
      setHeatmapUrl(null);
      setScoreMapUrl(null);
      setOverlayUrl(null);
      setConfidenceUrl(null);
      setSaveMessage(null);
      viewerRef.current?.resetZoom();
    },
    [reset, heatmapUrl, scoreMapUrl, overlayUrl, confidenceUrl],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId || !effectiveMethodId || !canProcess) return;
    setSaveMessage(null);
    const params: Record<string, string | number> = { method: effectiveMethodId, threshold };
    if (effectiveMethodId === "mesorch") {
      params.mesorch_variant = mesorchVariant;
    }
    try {
      await runAnalysis(evidenceId, "imdlbenco", params, {
        onArtifactsLoaded: async (jobId) => {
          const scoreMap =
            (await fetchImage(jobId, "score_map.png")) ?? (await fetchImage(jobId, "heatmap.png"));
          const [input, heat, overlay, conf] = await Promise.all([
            fetchImage(jobId, "input_image.png"),
            fetchImage(jobId, "heatmap.png"),
            fetchImage(jobId, "overlay.png"),
            fetchImage(jobId, "confidence_map.png").catch(() => null),
          ]);
          setInputUrl(input);
          setHeatmapUrl(heat);
          setScoreMapUrl(scoreMap);
          setOverlayUrl(overlay);
          setConfidenceUrl(conf);
          setViewMode("overlay");
          viewerRef.current?.resetZoom();
        },
      });
    } catch {
      /* hook */
    }
  }

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const effective_parameters: Record<string, unknown> = { threshold };
      if (effectiveMethodId === "mesorch") {
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

  const title = IMDL_METHOD_LABELS[effectiveMethodId ?? ""] || methodMeta?.name || effectiveMethodId || "IMDL";
  const techniqueMeta = effectiveMethodId ? getForensicTechniqueMeta(effectiveMethodId) : undefined;
  const resultDevice = formatInferenceDevice(result?.inference_device);
  const progressDevice = deviceLabelFromProgress(progressLabel);
  const activeDevice = resultDevice ?? (running ? progressDevice : null);

  return (
    <AnalysisPageShell
      caseId={caseId!}
      title={title}
      intro={
        techniqueMeta ? (
          <TechniqueReferenceIntro meta={techniqueMeta} techniqueId={effectiveMethodId} />
        ) : undefined
      }
      subtitle={techniqueMeta ? undefined : methodMeta?.description || "Localização de manipulação via IMDL-BenCo"}
      embedded={embedded}
    >
      {loadingMeta ? (
        <AnalysisPanel title="Carregando">
          <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Verificando pesos e runtime…</p>
        </AnalysisPanel>
      ) : (
        forceDisabled ? (
          <MessageBox type="err" text="Em breve nesta versão" />
        ) : (
          methodMeta &&
          !methodMeta.ready &&
          methodMeta.unavailable_reason && <MessageBox type="err" text={methodMeta.unavailable_reason} />
        )
      )}

      <AnalysisPanel title="Evidência e execução">
        {showEvidencePicker && (
          <ImageEvidenceSelector
            caseId={caseId!}
            selectedId={evidenceId}
            selectionSource={selectionSource}
            onSelect={onSelectEvidence}
            radioNamePrefix="imdl-questioned"
          />
        )}

        <div style={{ marginTop: "1rem", display: "grid", gap: "0.75rem", maxWidth: 520 }}>
          {effectiveMethodId === "mesorch" && mesorchVariants.length > 0 && (
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
          {effectiveMethodId === "trufor" && (
            <p style={{ margin: 0, fontSize: "0.82rem", color: "#6b7280" }}>
              Inferencia full-res (sem resize). Primeira execucao apos reiniciar o backend pode levar ~30 s;
              repetidas ~10 s na GPU.
            </p>
          )}
          {(running || activeDevice) && (
            <p style={{ margin: 0, fontSize: "0.82rem", color: "#374151" }}>
              Dispositivo:{" "}
              <strong style={{ color: activeDevice === "CPU" ? "#b45309" : "#0369a1" }}>
                {activeDevice ?? "detectando…"}
              </strong>
              {activeDevice === "CPU" && (
                <span style={{ color: "#b45309" }}> — muito mais lento que GPU</span>
              )}
            </p>
          )}
          {Boolean(result?.gpu_fallback_warning || result?.gpu_fallback_reason) && (
            <p style={{ margin: 0, fontSize: "0.82rem", color: "#b45309" }}>
              {result?.gpu_fallback_warning
                ? String(result.gpu_fallback_warning)
                : `GPU indisponível: ${String(result?.gpu_fallback_reason ?? "").slice(0, 200)}`}
            </p>
          )}
          <label style={{ fontSize: "0.82rem" }}>
            Limiar da máscara ({threshold.toFixed(2)})
            <input
              type="range"
              min={0.1}
              max={0.95}
              step={0.05}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              style={{ display: "block", width: "100%", marginTop: 4 }}
            />
          </label>
          {maskPreviewReady && (
            <p style={{ margin: 0, fontSize: "0.78rem", color: "#6b7280" }}>
              O limiar atualiza a máscara na hora, sem nova inferência.
            </p>
          )}
          <ProcessButton
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            disabled={!evidenceId || !canProcess}
            onClick={process}
            label={
              forceDisabled
                ? "Em breve nesta versão"
                : canProcess
                  ? `Executar ${title}`
                  : methodMeta?.ready && !selectedMesorchReady
                    ? "Variante Mesorch sem pesos"
                    : `${title} indisponível`
            }
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result?.success !== false && (heatmapUrl || overlayUrl) && (
        <AnalysisPanel title="Resultado">
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563" }}>
            {result?.integrity_score != null && (
              <>
                Score integridade: <strong>{Number(result.integrity_score).toFixed(3)}</strong>
                {" · "}
              </>
            )}
            {result?.mean_manipulation_score != null && (
              <>
                Média localização: <strong>{Number(result.mean_manipulation_score).toFixed(4)}</strong>
              </>
            )}
            {maskPreviewReady && (
              <>
                {" · "}
                Limiar máscara: <strong>{threshold.toFixed(2)}</strong>
              </>
            )}
            {resultDevice != null && (
              <>
                {" · "}
                Dispositivo: <strong>{resultDevice}</strong>
              </>
            )}
          </p>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["overlay", "Overlay"],
                ["heatmap", "Heatmap"],
                ["mask", "Máscara"],
                ...(confidenceUrl ? ([["confidence", "Confiança"]] as const) : []),
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                style={{
                  padding: "0.35rem 0.75rem",
                  fontSize: "0.8rem",
                  borderRadius: 6,
                  border: viewMode === mode ? "2px solid #0369a1" : "1px solid #d1d5db",
                  background: viewMode === mode ? "#f0f9ff" : "#fff",
                  cursor: "pointer",
                }}
              >
                {label}
              </button>
            ))}
          </div>
          {effectiveMethodId === "trufor" && (viewMode === "heatmap" || viewMode === "overlay") && (
            <TruForHeatmapColorScale
              caption={
                viewMode === "overlay"
                  ? "O overlay usa a mesma escala de cores sobre a evidência."
                  : "Probabilidade por pixel de manipulação (softmax, classe forgery)."
              }
            />
          )}
          {effectiveMethodId === "trufor" && viewMode === "confidence" && <TruForConfidenceColorScale />}
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
            <div style={{ marginTop: "1rem", display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              {[
                ["heatmap.png", "Heatmap"],
                ["overlay.png", "Overlay"],
                ["mask.png", "Máscara"],
                ...(confidenceUrl ? ([["confidence_map.png", "Confiança"]] as const) : []),
              ].map(([file, label]) => (
                <button
                  key={file}
                  type="button"
                  disabled={saving}
                  onClick={() => handleSave(file, label)}
                  style={saveBtnStyle}
                >
                  {saving ? "Salvando…" : `Salvar ${label}`}
                </button>
              ))}
            </div>
          )}
          {saveMessage && (
            <div style={{ marginTop: "0.75rem" }}>
              <MessageBox type={saveMessage.type} text={saveMessage.text} />
            </div>
          )}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

const saveBtnStyle: React.CSSProperties = {
  padding: "0.45rem 0.85rem",
  fontSize: "0.8rem",
  borderRadius: 6,
  border: "1px solid #d1d5db",
  background: "#fff",
  cursor: "pointer",
};
