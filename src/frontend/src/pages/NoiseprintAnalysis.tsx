import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";

type ViewMode = "overlay" | "heatmap" | "noiseprint" | "valid_mask" | "valid_overlay";

export default function NoiseprintAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [viewMode, setViewMode] = useState<ViewMode>("overlay");
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [heatmapUrl, setHeatmapUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [noiseprintUrl, setNoiseprintUrl] = useState<string | null>(null);
  const [validMaskUrl, setValidMaskUrl] = useState<string | null>(null);
  const [validOverlayUrl, setValidOverlayUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  useEffect(() => {
    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((res) => {
        const t = res.data.find((x) => x.name === "noiseprint");
        if (t) {
          setRuntimeOk(t.available !== false);
          setRuntimeReason(t.unavailable_reason || "");
        } else {
          setRuntimeOk(false);
          setRuntimeReason("Tecnica noiseprint nao registrada no servidor.");
        }
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Nao foi possivel verificar disponibilidade do Noiseprint.");
      });
  }, []);

  const rightUrl =
    viewMode === "heatmap"
      ? heatmapUrl
      : viewMode === "noiseprint"
        ? noiseprintUrl
        : viewMode === "valid_mask"
          ? validMaskUrl
          : viewMode === "valid_overlay"
            ? validOverlayUrl
            : overlayUrl;
  const rightLabel =
    viewMode === "heatmap"
      ? "Heatmap blind (localizacao)"
      : viewMode === "noiseprint"
        ? "Impressao digital (extracao)"
        : viewMode === "valid_mask"
          ? "Máscara válida (branco = confiavel)"
          : viewMode === "valid_overlay"
            ? "Sobreposição válida (vermelho = nao confiavel)"
            : "Sobreposição do mapa de calor";

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setInputUrl(`/api/v1/evidences/${id}/file`);
      setHeatmapUrl(null);
      setOverlayUrl(null);
      setNoiseprintUrl(null);
      setValidMaskUrl(null);
      setValidOverlayUrl(null);
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
      await runAnalysis(evidenceId, "noiseprint", {}, {
        onArtifactsLoaded: async (jobId) => {
          const [input, heat, overlay, np, validMask, validOverlay] = await Promise.all([
            fetchImage(jobId, "input_image.png"),
            fetchImage(jobId, "heatmap.png"),
            fetchImage(jobId, "overlay.png"),
            fetchImage(jobId, "noiseprint_map.png").catch(() => null),
            fetchImage(jobId, "valid_mask.png").catch(() => null),
            fetchImage(jobId, "valid_overlay.png").catch(() => null),
          ]);
          setInputUrl(input);
          setHeatmapUrl(heat);
          setOverlayUrl(overlay);
          setNoiseprintUrl(np);
          setValidMaskUrl(validMask);
          setValidOverlayUrl(validOverlay);
          setViewMode("overlay");
          viewerRef.current?.resetZoom();
        },
      });
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
      title={FORENSIC_TECHNIQUE_META.noiseprint.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.noiseprint} techniqueId="noiseprint" />}
      embedded={embedded}
    >
      {runtimeOk === false && (
        <MessageBox type="err" text={runtimeReason || "Noiseprint indisponivel neste servidor."} />
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

      <AnalysisPanel title="Execução">
        <ProcessButton
          running={running}
          progress={progress}
          progressLabel={progressLabel}
          disabled={!evidenceId || !runtimeOk}
          onClick={process}
          label="Executar Noiseprint"
        />
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result?.success !== false && (heatmapUrl || overlayUrl) && (
        <AnalysisPanel title="Resultado">
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563" }}>
            {result?.jpeg_quality_factor != null && (
              <>
                QF JPEG: <strong>{String(result.jpeg_quality_factor)}</strong>
                {" · "}
              </>
            )}
            {result?.mean_noiseprint != null && (
              <>
                Media normalizada: <strong>{Number(result.mean_noiseprint).toFixed(4)}</strong>
              </>
            )}
            {result?.valid_pixel_fraction != null && (
              <>
                {" "}
                · Pixels validos:{" "}
                <strong>{(Number(result.valid_pixel_fraction) * 100).toFixed(1)}%</strong>
              </>
            )}
            {result?.inference_device != null && (
              <>
                {" "}
                · Dispositivo: <strong>{String(result.inference_device).toUpperCase()}</strong>
              </>
            )}
          </p>

          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["overlay", "Overlay"],
                ["heatmap", "Heatmap"],
                ...(noiseprintUrl ? ([["noiseprint", "Noiseprint"]] as const) : []),
                ...(validMaskUrl ? ([["valid_mask", "Valid"]] as const) : []),
                ...(validOverlayUrl ? ([["valid_overlay", "Valid overlay"]] as const) : []),
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
              <button
                type="button"
                disabled={saving}
                onClick={() => handleSave("overlay.png", "Overlay Noiseprint")}
                style={btnSecondary}
              >
                Salvar overlay
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => handleSave("heatmap.png", "Heatmap Noiseprint")}
                style={btnSecondary}
              >
                Salvar heatmap
              </button>
              {noiseprintUrl && (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => handleSave("noiseprint_map.png", "Mapa Noiseprint")}
                  style={btnSecondary}
                >
                  Salvar noiseprint
                </button>
              )}
              {validMaskUrl && (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => handleSave("valid_mask.png", "Máscara válida Noiseprint")}
                  style={btnSecondary}
                >
                  Salvar valid
                </button>
              )}
              {validOverlayUrl && (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => handleSave("valid_overlay.png", "Sobreposição válida Noiseprint")}
                  style={btnSecondary}
                >
                  Salvar valid overlay
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
