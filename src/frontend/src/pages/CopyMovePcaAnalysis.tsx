import { useCallback, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import RectRoiCanvas, { type RectRoi } from "@/components/RectRoiCanvas";
import { AnalysisPanel, MessageBox } from "@/components/AnalysisPageShell";
import TechniquePageShell from "@/components/TechniquePageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import api from "@/services/api";

type ViewMode = "overlay" | "colored" | "mask";

function revokeBlob(url: string | null) {
  if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
}

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
  const [roiRect, setRoiRect] = useState<RectRoi | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [coloredUrl, setColoredUrl] = useState<string | null>(null);
  const [maskUrl, setMaskUrl] = useState<string | null>(null);
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [loadingInput, setLoadingInput] = useState(false);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const inputBlobRef = useRef<string | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime("copy_move_pca");

  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  async function loadInputBlob(id: string) {
    setLoadingInput(true);
    revokeBlob(inputBlobRef.current);
    inputBlobRef.current = null;
    setInputUrl(null);
    try {
      const res = await api.get(`/evidences/${id}/file`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      inputBlobRef.current = url;
      setInputUrl(url);
    } catch {
      setInputUrl(null);
    } finally {
      setLoadingInput(false);
    }
  }

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setOriginalUrl(`/api/v1/evidences/${id}/file`);
      setOverlayUrl(null);
      setColoredUrl(null);
      setMaskUrl(null);
      setRoiRect(null);
      clearMessage();
      setViewMode("overlay");
      viewerRef.current?.resetZoom();
      void loadInputBlob(id);
    },
    [reset, clearMessage],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    if (useRoi && !roiRect) return;
    clearMessage();
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
    if (useRoi && roiRect) {
      parameters.region = [roiRect.x, roiRect.y, roiRect.width, roiRect.height];
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
    }
  }

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    await save(currentJobId, filename, label);
  }

  const rightUrl = viewMode === "overlay" ? overlayUrl : viewMode === "colored" ? coloredUrl : maskUrl;
  const rightLabel =
    viewMode === "overlay"
      ? "Overlay (alpha ou blend)"
      : viewMode === "colored"
        ? "Mapa colorido por deslocamento"
        : "Máscara de cantos de bloco";

  if (!caseId) return null;

  const parametersPanel = (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "1rem 1.25rem" }}>
        {(
          [
            { label: "Tamanho do bloco (b)", value: b, onChange: setB, step: 1 },
            { label: "PCA % (n_comp)", value: nComp, onChange: setNComp, step: 0.05 },
            { label: "Prof. de busc (nn)", value: nn, onChange: setNn, step: 1 },
            { label: "Quantização (Q)", value: q, onChange: setQ, step: 16 },
            { label: "Clone mínimo (nf)", value: nf, onChange: setNf, step: 16 },
            { label: "Distância mínima (nd)", value: nd, onChange: setNd, step: 4 },
          ] as const
        ).map(({ label, value, onChange, step }) => (
          <label key={label} style={{ fontSize: "0.82rem", display: "flex", flexDirection: "column", gap: 6 }}>
            {label}
            <input
              type="number"
              step={step}
              min={0}
              value={value}
              onChange={(e) => onChange(Number(e.target.value))}
              style={{ display: "block", width: "100%", boxSizing: "border-box" }}
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
      {useRoi && evidenceId && (
        <AnalysisPanel title="Selecione a região de interesse">
          {loadingInput && <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Carregando imagem…</p>}
          {!loadingInput && inputUrl && (
            <RectRoiCanvas imageUrl={inputUrl} rect={roiRect} onRectChange={setRoiRect} maxHeight={520} />
          )}
          {!loadingInput && !inputUrl && (
            <MessageBox type="err" text="Não foi possível carregar a imagem de entrada." />
          )}
          {roiRect && (
            <p style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: "0.5rem" }}>
              ROI: x={roiRect.x}, y={roiRect.y}, largura={roiRect.width}, altura={roiRect.height}
            </p>
          )}
        </AnalysisPanel>
      )}
      <div style={{ marginTop: "1rem" }}>
        <button
          type="button"
          onClick={process}
          disabled={!evidenceId || runtimeOk !== true || running || (useRoi && !roiRect)}
          style={btnPrimary}
        >
          {running ? "Processando…" : "Processar Copy-Move PCA"}
        </button>
      </div>
      <p style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: "0.5rem", lineHeight: 1.45 }}>
        Imagens grandes podem levar vários minutos (resolução completa). Use ROI para analisar apenas uma região.
      </p>
    </>
  );

  const resultPanel = result ? (
    <>
      <p style={{ fontSize: "0.9rem", margin: "0 0 0.75rem 0", color: "#374151" }}>
        Deslocamentos únicos: {Number(result.clone_regions_detected)} · Área mascarada:{" "}
        {Number(result.mask_area_pixels).toLocaleString()} px ({(Number(result.mask_ratio) * 100).toFixed(3)}%)
      </p>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
        {(
          [
            ["overlay", "Overlay"],
            ["colored", "Colorido"],
            ["mask", "Máscara"],
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
          <button type="button" disabled={saving} onClick={() => handleSave("mask.png", "Máscara")} style={btnSecondary}>
            Salvar máscara
          </button>
        </div>
      )}
    </>
  ) : null;

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="copy_move_pca"
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
      runtimeReason={runtimeReason}
      parametersPanel={parametersPanel}
      resultPanel={resultPanel || undefined}
    />
  );
}

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
