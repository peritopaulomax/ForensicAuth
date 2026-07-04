import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import RectRoiCanvas, { type RectRoi } from "@/components/RectRoiCanvas";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import api from "@/services/api";
import { saveDerivative } from "@/services/evidence";

type ViewMode = "overlay" | "colored" | "heatmap";

function revokeBlob(url: string | null) {
  if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
}

export default function WaveletNoiseResidueAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [viewMode, setViewMode] = useState<ViewMode>("overlay");
  const [levelsSlider, setLevelsSlider] = useState(4);
  const [blocksize, setBlocksize] = useState(3);
  const [thr, setThr] = useState(255);
  const [sliderThr, setSliderThr] = useState(255);
  const [post, setPost] = useState(true);
  const [useRoi, setUseRoi] = useState(false);
  const [roiRect, setRoiRect] = useState<RectRoi | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [coloredUrl, setColoredUrl] = useState<string | null>(null);
  const [heatmapUrl, setHeatmapUrl] = useState<string | null>(null);
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [loadingInput, setLoadingInput] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const previewGenRef = useRef(0);
  const inputBlobRef = useRef<string | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, reset } =
    useForensicJob();

  const order = levelsSlider * 2;
  const rightUrl = viewMode === "overlay" ? overlayUrl : viewMode === "colored" ? coloredUrl : heatmapUrl;
  const rightLabel =
    viewMode === "overlay" ? "Overlay" : viewMode === "colored" ? "Mapa JET" : "Heatmap (escala de cinza)";
  const previewReady = Boolean(currentJobId && result?.success);

  const loadPreviewImages = useCallback(
    async (jobId: string, cacheBust?: number) => {
      const suffix = cacheBust ? `&_=${cacheBust}` : "";
      const fetchCached = async (filename: string) => {
        try {
          const response = await api.get(`/analysis/${jobId}/result/file?filename=${filename}${suffix}`, {
            responseType: "blob",
          });
          return URL.createObjectURL(response.data);
        } catch {
          return null;
        }
      };
      const [overlay, colored, heatmap] = await Promise.all([
        fetchCached("overlay.png"),
        fetchCached("colored_overlay.png"),
        fetchCached("heatmap.png"),
      ]);
      setOverlayUrl((prev) => {
        if (prev?.startsWith("blob:")) revokeBlob(prev);
        return overlay;
      });
      setColoredUrl((prev) => {
        if (prev?.startsWith("blob:")) revokeBlob(prev);
        return colored;
      });
      setHeatmapUrl((prev) => {
        if (prev?.startsWith("blob:")) revokeBlob(prev);
        return heatmap;
      });
    },
    []
  );

  const loadResultImages = useCallback(
    async (jobId: string, cacheBust?: number) => {
      const suffix = cacheBust ? `&_=${cacheBust}` : "";
      try {
        const response = await api.get(`/analysis/${jobId}/result/file?filename=original.png${suffix}`, {
          responseType: "blob",
        });
        const orig = URL.createObjectURL(response.data);
        setOriginalUrl((prev) => {
          if (prev?.startsWith("blob:") && prev !== orig) revokeBlob(prev);
          return orig;
        });
      } catch {
        /* original optional */
      }
      await loadPreviewImages(jobId, cacheBust);
    },
    [loadPreviewImages]
  );

  const applyLivePreview = useCallback(
    async (jobId: string, bs: number, threshold: number, postProc: boolean) => {
      const gen = ++previewGenRef.current;
      setPreviewBusy(true);
      setPreviewError(null);
      try {
        await api.post(`/analysis/${jobId}/result/wavelet-noise-residue-preview`, {
          blocksize: bs,
          thr: threshold,
          post: postProc,
        });
        if (gen !== previewGenRef.current) return;
        await loadPreviewImages(jobId, Date.now());
      } catch (err: unknown) {
        if (gen !== previewGenRef.current) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          "Erro ao atualizar pos-processamento";
        setPreviewError(String(msg));
      } finally {
        if (gen === previewGenRef.current) setPreviewBusy(false);
      }
    },
    [loadPreviewImages]
  );

  const lastBlocksizeRef = useRef(blocksize);

  useEffect(() => {
    setSliderThr(thr);
  }, [thr]);

  useEffect(() => {
    if (!previewReady || !currentJobId || running) return;
    const blocksizeChanged = lastBlocksizeRef.current !== blocksize;
    lastBlocksizeRef.current = blocksize;
    const delay = blocksizeChanged ? 350 : 120;
    const timer = window.setTimeout(() => {
      void applyLivePreview(currentJobId, blocksize, thr, post);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [previewReady, currentJobId, blocksize, thr, post, running, applyLivePreview]);

  async function loadInputBlob(evidenceId: string) {
    setLoadingInput(true);
    revokeBlob(inputBlobRef.current);
    inputBlobRef.current = null;
    setInputUrl(null);
    try {
      const res = await api.get(`/evidences/${evidenceId}/file`, { responseType: "blob" });
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
      setHeatmapUrl(null);
      setRoiRect(null);
      setPreviewError(null);
      setSaveMessage(null);
      setViewMode("overlay");
      previewGenRef.current += 1;
      viewerRef.current?.resetZoom();
      void loadInputBlob(id);
    },
    [reset]
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId) return;
    setSaveMessage(null);
    setPreviewError(null);
    const parameters: Record<string, unknown> = {
      levels_slider: levelsSlider,
      order,
    };
    if (useRoi && roiRect) parameters.region = [roiRect.x, roiRect.y, roiRect.width, roiRect.height];
    try {
      await runAnalysis(evidenceId, "wavelet_noise_residue", parameters, {
        maxWaitMs: 30 * 60 * 1000,
        onArtifactsLoaded: async (jobId) => {
          await loadResultImages(jobId);
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
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: filename,
        effective_parameters: {
          blocksize,
          thr,
          post,
          levels_slider: levelsSlider,
          order,
        },
      });
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

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.wavelet_noise_residue.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.wavelet_noise_residue} techniqueId="wavelet_noise_residue" />}
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

      <AnalysisPanel title="Parametros wavelet (requer reprocessar)">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.75rem" }}>
          <label style={{ fontSize: "0.82rem" }}>
            Daubechies (slider 1–5 → db2…db10)
            <input
              type="range"
              min={1}
              max={5}
              value={levelsSlider}
              onChange={(e) => setLevelsSlider(Number(e.target.value))}
              style={{ display: "block", width: "100%", marginTop: 4 }}
            />
            <span>db{order}</span>
          </label>
        </div>
        <div style={{ display: "flex", gap: "1rem", marginTop: "0.75rem", flexWrap: "wrap", fontSize: "0.82rem" }}>
          <label>
            <input type="checkbox" checked={useRoi} onChange={(e) => setUseRoi(e.target.checked)} /> ROI
          </label>
        </div>
        {useRoi && evidenceId && (
          <AnalysisPanel title="Selecione a regiao de interesse">
            {loadingInput && <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Carregando imagem…</p>}
            {!loadingInput && inputUrl && (
              <RectRoiCanvas imageUrl={inputUrl} rect={roiRect} onRectChange={setRoiRect} maxHeight={520} />
            )}
            {!loadingInput && !inputUrl && (
              <MessageBox type="err" text="Nao foi possivel carregar a imagem de entrada." />
            )}
            {roiRect && (
              <p style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: "0.5rem" }}>
                ROI: x={roiRect.x}, y={roiRect.y}, largura={roiRect.width}, altura={roiRect.height}
              </p>
            )}
          </AnalysisPanel>
        )}
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!evidenceId || (useRoi && !roiRect)}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Processar Wavelet (DWT)"
          />
        </div>
        <p style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: "0.5rem", lineHeight: 1.45 }}>
          Executa apenas a decomposicao wavelet (DWT). Block size e threshold abaixo sao aplicados ao vivo, sem recomputar
          os wavelets.
        </p>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Pos-processamento (ao vivo)">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "0.75rem" }}>
            <label style={{ fontSize: "0.82rem" }}>
              Block size
              <input
                type="number"
                min={3}
                max={80}
                value={blocksize}
                onChange={(e) => setBlocksize(Number(e.target.value))}
                style={{ display: "block", width: "100%", marginTop: 4 }}
              />
            </label>
            <label style={{ fontSize: "0.82rem" }}>
              Threshold
              <input
                type="range"
                min={0}
                max={255}
                value={sliderThr}
                disabled={!post}
                onChange={(e) => setSliderThr(Number(e.target.value))}
                onPointerUp={() => setThr(sliderThr)}
                onMouseUp={() => setThr(sliderThr)}
                style={{ display: "block", width: "100%", marginTop: 4 }}
              />
              <span>{sliderThr}</span>
            </label>
          </div>
          <div style={{ display: "flex", gap: "1rem", marginTop: "0.75rem", flexWrap: "wrap", fontSize: "0.82rem" }}>
            <label>
              <input type="checkbox" checked={post} onChange={(e) => setPost(e.target.checked)} /> Pos-processamento
            </label>
            {previewBusy && <span style={{ color: "#6b7280" }}>Atualizando visualizacao…</span>}
          </div>
          {previewError && <MessageBox type="err" text={previewError} />}
        </AnalysisPanel>
      )}

      {result && (
        <AnalysisPanel title="Resultado">
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["overlay", "Overlay"],
                ["colored", "JET"],
                ["heatmap", "Heatmap"],
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
              <button type="button" disabled={saving || previewBusy} onClick={() => handleSave("overlay.png", "Overlay")} style={btnSecondary}>
                Salvar overlay
              </button>
              <button type="button" disabled={saving || previewBusy} onClick={() => handleSave("colored_overlay.png", "Mapa JET")} style={btnSecondary}>
                Salvar JET
              </button>
              <button type="button" disabled={saving || previewBusy} onClick={() => handleSave("heatmap.png", "Heatmap")} style={btnSecondary}>
                Salvar heatmap
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
