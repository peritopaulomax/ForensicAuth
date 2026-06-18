import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";

const SAFIRE_META = FORENSIC_TECHNIQUE_META.safire;
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";

type SafireMode = "binary" | "multi";
type ViewMode = "heatmap" | "overlay" | "multi";

export default function SafireAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [mode, setMode] = useState<SafireMode>("binary");
  const [clusterType, setClusterType] = useState<"kmeans" | "dbscan">("kmeans");
  const [kmeansClusters, setKmeansClusters] = useState(3);
  const [viewMode, setViewMode] = useState<ViewMode>("heatmap");
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [heatmapUrl, setHeatmapUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [multiUrl, setMultiUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  useEffect(() => {
    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((res) => {
        const t = res.data.find((x) => x.name === "safire");
        if (t) {
          setRuntimeOk(t.available !== false);
          setRuntimeReason(t.unavailable_reason || "");
        } else {
          setRuntimeOk(false);
          setRuntimeReason("Tecnica safire nao registrada no servidor.");
        }
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Nao foi possivel verificar disponibilidade do SAFIRE.");
      });
  }, []);

  const rightUrl =
    viewMode === "heatmap" ? heatmapUrl : viewMode === "multi" ? multiUrl : overlayUrl;
  const rightLabel =
    viewMode === "heatmap"
      ? "Mapa de probabilidade (SAFIRE)"
      : viewMode === "multi"
        ? "Particionamento multi-fonte"
        : "Overlay inferno na evidencia";

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setInputUrl(`/api/v1/evidences/${id}/file`);
      setHeatmapUrl(null);
      setOverlayUrl(null);
      setMultiUrl(null);
      setSaveMessage(null);
      viewerRef.current?.resetZoom();
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
        "safire",
        {
          mode,
          cluster_type: clusterType,
          kmeans_cluster_num: kmeansClusters,
        },
        {
          onArtifactsLoaded: async (jobId) => {
            const [input, heat, overlay, multi] = await Promise.all([
              fetchImage(jobId, "input_image.png"),
              fetchImage(jobId, "heatmap.png"),
              fetchImage(jobId, "overlay.png"),
              fetchImage(jobId, "safire_multi_segment.png").catch(() => null),
            ]);
            setInputUrl(input);
            setHeatmapUrl(heat);
            setOverlayUrl(overlay);
            setMultiUrl(multi);
            setViewMode(mode === "multi" ? (multi ? "multi" : "heatmap") : "heatmap");
            viewerRef.current?.resetZoom();
          },
        }
      );
    } catch {
      /* hook sets error */
    }
  }

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({ job_id: currentJobId, artifact_filename: filename });
      setSaveMessage({
        type: "ok",
        text: `${label} salvo na cadeia de custodia. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
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
      title={SAFIRE_META.title}
      intro={<TechniqueReferenceIntro meta={SAFIRE_META} techniqueId="safire" />}
      embedded={embedded}
    >
      {runtimeOk === false && (
        <MessageBox type="err" text={runtimeReason || "SAFIRE indisponivel neste servidor."} />
      )}

      <AnalysisPanel title="Evidencia">
        {showEvidencePicker && (
          <ImageEvidenceSelector
            caseId={caseId!}
            selectedId={evidenceId}
            selectionSource={selectionSource}
            onSelect={onSelectEvidence}
          />
        )}
      </AnalysisPanel>

      <AnalysisPanel title="Parametros">
        <div style={{ display: "grid", gap: "0.75rem", maxWidth: 520 }}>
          <label style={{ fontSize: "0.82rem" }}>
            Modo
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as SafireMode)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: "0.4rem" }}
            >
              <option value="binary">Localizacao binaria (heatmap)</option>
              <option value="multi">Particionamento multi-fonte</option>
            </select>
          </label>

          {mode === "multi" && (
            <>
              <label style={{ fontSize: "0.82rem" }}>
                Clustering
                <select
                  value={clusterType}
                  onChange={(e) => setClusterType(e.target.value as "kmeans" | "dbscan")}
                  style={{ display: "block", width: "100%", marginTop: 4, padding: "0.4rem" }}
                >
                  <option value="kmeans">k-means</option>
                  <option value="dbscan">DBSCAN</option>
                </select>
              </label>
              {clusterType === "kmeans" && (
                <label style={{ fontSize: "0.82rem" }}>
                  Numero de clusters (k)
                  <input
                    type="number"
                    min={2}
                    max={8}
                    value={kmeansClusters}
                    onChange={(e) => setKmeansClusters(Number(e.target.value))}
                    style={{ display: "block", width: "100%", marginTop: 4 }}
                  />
                </label>
              )}
            </>
          )}
          <p style={{ margin: 0, fontSize: "0.82rem", color: "#6b7280" }}>
            Inferencia em 1024×1024; mapas de visualizacao ajustados as dimensoes da entrada.
          </p>
        </div>

        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            disabled={!evidenceId || !runtimeOk}
            onClick={process}
            label="Executar SAFIRE"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result?.success !== false && (heatmapUrl || overlayUrl) && (
        <AnalysisPanel title="Resultado">
          {result?.mean_forgery_score != null && (
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563" }}>
              Score medio do mapa: <strong>{Number(result.mean_forgery_score).toFixed(4)}</strong>
              {result.inference_device != null && (
                <>
                  {" "}
                  · Dispositivo: <strong>{String(result.inference_device).toUpperCase()}</strong>
                </>
              )}
              {result.cluster_count != null && (
                <>
                  {" "}
                  · Clusters detectados: <strong>{String(result.cluster_count)}</strong>
                </>
              )}
            </p>
          )}
          {Boolean(result?.gpu_fallback_warning || result?.gpu_fallback_reason) && (
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.82rem", color: "#b45309" }}>
              {result?.gpu_fallback_warning
                ? String(result.gpu_fallback_warning)
                : String(result?.gpu_fallback_reason ?? "")}
            </p>
          )}

          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["heatmap", "Heatmap (oficial)"],
                ["overlay", "Overlay"],
                ...(multiUrl ? ([["multi", "Multi-fonte"]] as const) : []),
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
              rightHoverSrc={viewMode === "heatmap" ? multiUrl : null}
              rightHoverLabel="Particionamento multi-fonte (passe o mouse)"
              leftLabel="Entrada"
              rightLabel={rightLabel}
            />
          )}
          {viewMode === "heatmap" && multiUrl && (
            <p style={{ margin: "0.5rem 0 0", fontSize: "0.78rem", color: "#6b7280" }}>
              Passe o mouse sobre o mapa à direita para ver a partição multi-fonte colorida.
            </p>
          )}

          {currentJobId && (
            <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button
                type="button"
                disabled={saving}
                onClick={() => handleSave("overlay.png", "Overlay SAFIRE")}
                style={btnSecondary}
              >
                Salvar overlay
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => handleSave("heatmap.png", "Heatmap SAFIRE")}
                style={btnSecondary}
              >
                Salvar heatmap
              </button>
              {multiUrl && (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => handleSave("safire_multi_segment.png", "Segmentacao multi-fonte")}
                  style={btnSecondary}
                >
                  Salvar multi-fonte
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
