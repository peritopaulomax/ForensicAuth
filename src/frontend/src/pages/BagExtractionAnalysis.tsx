import { useCallback, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import ZoomableImageViewer, { type ZoomableImageViewerHandle } from "@/components/ZoomableImageViewer";
import TechniquePageShell from "@/components/TechniquePageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";

export default function BagExtractionAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [diffThresh, setDiffThresh] = useState(50);
  const [ac, setAc] = useState(33);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [mapUrl, setMapUrl] = useState<string | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const mapViewerRef = useRef<ZoomableImageViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime("bag_extraction");

  const runtimeOk = runtimeStatus?.available ?? null;

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setOriginalUrl(`/api/v1/evidences/${id}/file`);
      setOverlayUrl(null);
      setMapUrl(null);
      clearMessage();
      viewerRef.current?.resetZoom();
      mapViewerRef.current?.resetZoom();
    },
    [reset, clearMessage]
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId) return;
    clearMessage();
    try {
      await runAnalysis(
        evidenceId,
        "bag_extraction",
        { diff_thresh: diffThresh, ac },
        {
          onArtifactsLoaded: async (jobId) => {
            const [orig, overlay, map] = await Promise.all([
              fetchImage(jobId, "original.png"),
              fetchImage(jobId, "overlay.png"),
              fetchImage(jobId, "bag_map.png"),
            ]);
            if (orig) setOriginalUrl(orig);
            setOverlayUrl(overlay);
            setMapUrl(map);
          },
        }
      );
    } catch {
    }
  }

  if (!caseId) return null;

  const parametersPanel = (
    <>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        <label style={{ fontSize: "0.85rem" }}>
          DiffThresh
          <input type="number" min={1} value={diffThresh} onChange={(e) => setDiffThresh(Number(e.target.value))} style={inputStyle} />
        </label>
        <label style={{ fontSize: "0.85rem" }}>
          AC (janela)
          <input type="number" min={3} value={ac} onChange={(e) => setAc(Number(e.target.value))} style={inputStyle} />
        </label>
      </div>
      <div style={{ marginTop: "1rem" }}>
        <button type="button" onClick={process} disabled={!evidenceId || running} style={btnPrimary}>
          {running ? "Processando…" : "Processar BAG"}
        </button>
      </div>
    </>
  );

  const resultPanel = result && (
    <>
      <p style={{ fontSize: "0.9rem", margin: "0 0 0.75rem 0" }}>
        Mapa: min {Number(result.map_min).toFixed(2)} · max {Number(result.map_max).toFixed(2)} · media{" "}
        {Number(result.map_mean).toFixed(2)}
      </p>

      {originalUrl && overlayUrl && (
        <SyncedImagePairViewer
          ref={viewerRef}
          leftSrc={originalUrl}
          rightSrc={overlayUrl}
          leftLabel="Original"
          rightLabel="Overlay BAG"
        />
      )}

      {mapUrl && (
        <ZoomableImageViewer
          ref={mapViewerRef}
          title="Mapa de metricas de desalinhamento (BlockDiff)"
          label="Mapa BAG"
          src={mapUrl}
          alt="Mapa BAG"
          height={420}
          imageStyle={{ imageRendering: "pixelated" }}
        />
      )}

      {currentJobId && (
        <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
          <button type="button" disabled={saving} onClick={() => save(currentJobId, "bag_map.png", "Mapa BAG")} style={btnSecondary}>
            Salvar mapa na custodia
          </button>
          <button type="button" disabled={saving} onClick={() => save(currentJobId, "overlay.png", "Overlay")} style={btnSecondary}>
            Salvar overlay na custodia
          </button>
        </div>
      )}
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="bag_extraction"
      mediaType="imagem"
      embedded={embedded}
      evidenceId={evidenceId}
      selectionSource={selectionSource}
      onSelectEvidence={onSelectEvidence}
      showEvidencePicker={showEvidencePicker}
      running={running}
      error={error}
      progress={progress}
      progressLabel={progressLabel}
      saveMessage={saveMessage}
      runtimeOk={runtimeOk}
      parametersPanel={parametersPanel}
      resultPanel={resultPanel || undefined}
    />
  );
}

const inputStyle: React.CSSProperties = {
  display: "block",
  marginTop: 4,
  padding: "0.35rem 0.5rem",
  borderRadius: 4,
  border: "1px solid #d1d5db",
};
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
  padding: "0.45rem 0.9rem",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
};
