import { useCallback, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import ZoomableImageViewer, { type ZoomableImageViewerHandle } from "@/components/ZoomableImageViewer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";

export default function BagExtractionAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [diffThresh, setDiffThresh] = useState(50);
  const [ac, setAc] = useState(33);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [mapUrl, setMapUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const mapViewerRef = useRef<ZoomableImageViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setOriginalUrl(`/api/v1/evidences/${id}/file`);
      setOverlayUrl(null);
      setMapUrl(null);
      setSaveMessage(null);
      viewerRef.current?.resetZoom();
      mapViewerRef.current?.resetZoom();
    },
    [reset],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId) return;
    setSaveMessage(null);
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
      /* erro exibido via hook (error) */
    }
  }

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    setSaving(true);
    try {
      const res = await saveDerivative({ job_id: currentJobId, artifact_filename: filename });
      setSaveMessage({
        type: "ok",
        text: `${label} na custodia. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: msg });
    } finally {
      setSaving(false);
    }
  }

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.bag_extraction.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.bag_extraction} techniqueId="bag_extraction" />}
      embedded={embedded}
    >
      <AnalysisPanel title="Evidencia">
        {showEvidencePicker && (
          <ImageEvidenceSelector
            caseId={caseId}
            selectedId={evidenceId}
            selectionSource={selectionSource}
            onSelect={onSelectEvidence}
          />
        )}
      </AnalysisPanel>

      <AnalysisPanel title="Parametros">
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
          <ProcessButton
            onClick={process}
            disabled={!evidenceId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Processar BAG"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Resultado">
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
              <button type="button" disabled={saving} onClick={() => handleSave("bag_map.png", "Mapa BAG")} style={btnSecondary}>
                Salvar mapa na custodia
              </button>
              <button type="button" disabled={saving} onClick={() => handleSave("overlay.png", "Overlay")} style={btnSecondary}>
                Salvar overlay na custodia
              </button>
            </div>
          )}
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

const inputStyle: React.CSSProperties = { display: "block", marginTop: 4, padding: "0.35rem 0.5rem", borderRadius: 4, border: "1px solid #d1d5db" };
const btnSecondary: React.CSSProperties = {
  padding: "0.45rem 0.9rem",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
};
