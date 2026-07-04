import { useCallback, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";

type ViewMode = "overlay" | "colored" | "mask";

export default function CopyMovePcaAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [viewMode, setViewMode] = useState<ViewMode>("overlay");
  const [b, setB] = useState(7);
  const [nComp, setNComp] = useState(0.75);
  const [nn, setNn] = useState(2);
  const [q, setQ] = useState(256);
  const [nf, setNf] = useState(128);
  const [nd, setNd] = useState(16);
  const [morph, setMorph] = useState(true);
  const [alphaMask, setAlphaMask] = useState(false);
  const [useRoi, setUseRoi] = useState(false);
  const [roiX, setRoiX] = useState(0);
  const [roiY, setRoiY] = useState(0);
  const [roiW, setRoiW] = useState(512);
  const [roiH, setRoiH] = useState(512);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [coloredUrl, setColoredUrl] = useState<string | null>(null);
  const [maskUrl, setMaskUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setOriginalUrl(`/api/v1/evidences/${id}/file`);
      setOverlayUrl(null);
      setColoredUrl(null);
      setMaskUrl(null);
      setSaveMessage(null);
      setViewMode("overlay");
      viewerRef.current?.resetZoom();
    },
    [reset],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId) return;
    setSaveMessage(null);
    const parameters: Record<string, unknown> = {
      b,
      n_comp: nComp,
      nn,
      q,
      nf,
      nd,
      morph,
      alpha_mask: alphaMask,
    };
    if (useRoi) {
      parameters.region = [roiX, roiY, roiW, roiH];
    }
    try {
      await runAnalysis(evidenceId, "copy_move_pca", parameters, {
        maxWaitMs: 60 * 60 * 1000,
        onArtifactsLoaded: async (jobId) => {
          const [orig, overlay, colored, mask] = await Promise.all([
            fetchImage(jobId, "original.png"),
            fetchImage(jobId, "overlay.png"),
            fetchImage(jobId, "colored_overlay.png"),
            fetchImage(jobId, "mask.png"),
          ]);
          if (orig) setOriginalUrl(orig);
          setOverlayUrl(overlay);
          setColoredUrl(colored);
          setMaskUrl(mask);
          setViewMode("overlay");
        },
      });
    } catch {
      /* hook */
    }
  }

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    setSaving(true);
    try {
      const res = await saveDerivative({ job_id: currentJobId, artifact_filename: filename });
      setSaveMessage({
        type: "ok",
        text: `${label} registrado na custodia. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: msg });
    } finally {
      setSaving(false);
    }
  }

  const rightUrl = viewMode === "overlay" ? overlayUrl : viewMode === "colored" ? coloredUrl : maskUrl;
  const rightLabel =
    viewMode === "overlay"
      ? "Overlay (alpha ou blend)"
      : viewMode === "colored"
        ? "Mapa colorido por deslocamento"
        : "Mascara de cantos de bloco";

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.copy_move_pca.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.copy_move_pca} techniqueId="copy_move_pca" />}
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
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: "0.75rem" }}>
          {(
            [
              { label: "Tamanho do bloco (b)", value: b, onChange: setB, step: 1 },
              { label: "PCA % (n_comp)", value: nComp, onChange: setNComp, step: 0.05 },
              { label: "Profundidade de busca (nn)", value: nn, onChange: setNn, step: 1 },
              { label: "Quantização (Q)", value: q, onChange: setQ, step: 16 },
              { label: "Clone mínimo (nf)", value: nf, onChange: setNf, step: 16 },
              { label: "Distância mínima (nd)", value: nd, onChange: setNd, step: 4 },
            ] as const
          ).map(({ label, value, onChange, step }) => (
            <label key={label} style={{ fontSize: "0.82rem" }}>
              {label}
              <input
                type="number"
                step={step}
                min={0}
                value={value}
                onChange={(e) => onChange(Number(e.target.value))}
                style={{ display: "block", width: "100%", marginTop: 4 }}
              />
            </label>
          ))}
        </div>
        <div style={{ display: "flex", gap: "1rem", marginTop: "0.75rem", flexWrap: "wrap", fontSize: "0.82rem" }}>
          <label>
            <input type="checkbox" checked={morph} onChange={(e) => setMorph(e.target.checked)} /> Morfologia
          </label>
          <label>
            <input type="checkbox" checked={alphaMask} onChange={(e) => setAlphaMask(e.target.checked)} /> Máscara alfa
          </label>
          <label>
            <input type="checkbox" checked={useRoi} onChange={(e) => setUseRoi(e.target.checked)} /> ROI
          </label>
        </div>
        {useRoi && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem", marginTop: "0.5rem" }}>
            {(
              [
                ["X", roiX, setRoiX],
                ["Y", roiY, setRoiY],
                ["Largura", roiW, setRoiW],
                ["Altura", roiH, setRoiH],
              ] as const
            ).map(([label, val, setVal]) => (
              <label key={label} style={{ fontSize: "0.82rem" }}>
                {label}
                <input
                  type="number"
                  min={1}
                  value={val}
                  onChange={(e) => setVal(Number(e.target.value))}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
            ))}
          </div>
        )}
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!evidenceId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Processar Copy-Move PCA"
          />
        </div>
        <p style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: "0.5rem", lineHeight: 1.45 }}>
          Imagens grandes podem levar varios minutos (resolucao completa). Use ROI para analisar apenas uma regiao.
        </p>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Resultado">
          <p style={{ fontSize: "0.9rem", margin: "0 0 0.75rem 0", color: "#374151" }}>
            Deslocamentos unicos: {Number(result.clone_regions_detected)} · Area mascarada:{" "}
            {Number(result.mask_area_pixels).toLocaleString()} px ({(Number(result.mask_ratio) * 100).toFixed(3)}%)
          </p>

          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["overlay", "Overlay"],
                ["colored", "Colorido"],
                ["mask", "Mascara"],
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                style={{
                  padding: "0.4rem 0.85rem",
                  borderRadius: 6,
                  border: `1px solid ${viewMode === mode ? "#0369a1" : "#d1d5db"}`,
                  background: viewMode === mode ? "#e0f2fe" : "#fff",
                  cursor: "pointer",
                  fontSize: "0.82rem",
                }}
              >
                {label}
              </button>
            ))}
          </div>

          {originalUrl && rightUrl && (
            <SyncedImagePairViewer
              ref={viewerRef}
              leftSrc={originalUrl}
              rightSrc={rightUrl}
              leftLabel="Original"
              rightLabel={rightLabel}
            />
          )}

          {currentJobId && (
            <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" disabled={saving} onClick={() => handleSave("overlay.png", "Overlay")} style={btnSecondary}>
                Salvar overlay
              </button>
              <button type="button" disabled={saving} onClick={() => handleSave("colored_overlay.png", "Mapa colorido")} style={btnSecondary}>
                Salvar colorido
              </button>
              <button type="button" disabled={saving} onClick={() => handleSave("mask.png", "Mascara")} style={btnSecondary}>
                Salvar mascara
              </button>
            </div>
          )}
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

const btnSecondary: React.CSSProperties = {
  padding: "0.45rem 0.9rem",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
};
