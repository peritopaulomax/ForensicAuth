import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import PolygonRoiCanvas, { type PolygonPoint } from "@/components/PolygonRoiCanvas";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import { AnalysisPanel, MessageBox } from "@/components/AnalysisPageShell";
import TechniquePageShell from "@/components/TechniquePageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import api from "@/services/api";

type ChannelMode = "luminance" | "r" | "g" | "b" | "consolidated";

export default function ResamplingAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [channelMode, setChannelMode] = useState<ChannelMode>("luminance");
  const [inputUrl, setInputUrl] = useState<string | null>(null);
  const [polygon, setPolygon] = useState<PolygonPoint[] | null>(null);
  const [useComplement, setUseComplement] = useState(false);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [derivVUrl, setDerivVUrl] = useState<string | null>(null);
  const [derivHUrl, setDerivHUrl] = useState<string | null>(null);
  const [specVUrl, setSpecVUrl] = useState<string | null>(null);
  const [specHUrl, setSpecHUrl] = useState<string | null>(null);
  const [specCombinedUrl, setSpecCombinedUrl] = useState<string | null>(null);
  const [isColorInput, setIsColorInput] = useState(true);
  const [loadingInput, setLoadingInput] = useState(false);
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const viewerEntradaRef = useRef<SyncedImagePairViewerHandle>(null);
  const viewerDerivRef = useRef<SyncedImagePairViewerHandle>(null);
  const inputBlobRef = useRef<string | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const { status: runtimeStatus } = useTechniqueRuntime("resampling");

  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  function revokeBlob(url: string | null) {
    if (url && url.startsWith("blob:")) {
      URL.revokeObjectURL(url);
    }
  }

  useEffect(() => {
    return () => {
      revokeBlob(inputBlobRef.current);
      revokeBlob(originalUrl);
      revokeBlob(derivVUrl);
      revokeBlob(derivHUrl);
      revokeBlob(specVUrl);
      revokeBlob(specHUrl);
      revokeBlob(specCombinedUrl);
    };
  }, []);

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
      setPolygon(null);
      setUseComplement(false);
      setOriginalUrl(null);
      setDerivVUrl(null);
      setDerivHUrl(null);
      setSpecVUrl(null);
      setSpecHUrl(null);
      setSpecCombinedUrl(null);
      setIsColorInput(true);
      clearMessage();
      viewerEntradaRef.current?.resetZoom();
      viewerDerivRef.current?.resetZoom();
      loadInputBlob(id);
    },
    [reset, clearMessage],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    clearMessage();
    try {
      const params: Record<string, unknown> = { channel_mode: channelMode };
      if (polygon && polygon.length >= 3) {
        params.polygon = polygon.map((p) => [p.x, p.y]);
        params.polygon_complement = useComplement;
      }

      await runAnalysis(evidenceId, "resampling", params, {
        onArtifactsLoaded: async (jobId, jobResult) => {
          setIsColorInput(Boolean(jobResult?.is_color_input ?? true));
          const [orig, dv, dh, sv, sh, sc] = await Promise.all([
            fetchImage(jobId, "original.png"),
            fetchImage(jobId, "deriv_vertical.png"),
            fetchImage(jobId, "deriv_horizontal.png"),
            fetchImage(jobId, "spectrum_vertical.png"),
            fetchImage(jobId, "spectrum_horizontal.png"),
            fetchImage(jobId, "spectrum_combined.png"),
          ]);
          if (orig) setOriginalUrl(orig);
          setDerivVUrl(dv);
          setDerivHUrl(dh);
          setSpecVUrl(sv);
          setSpecHUrl(sh);
          setSpecCombinedUrl(sc);
          viewerEntradaRef.current?.resetZoom();
          viewerDerivRef.current?.resetZoom();
        },
      });
    } catch {
    }
  }

  async function handleSaveCustodyBundle() {
    if (!currentJobId) return;
    const files: { name: string; label: string }[] = [
      { name: "spectrum_vertical.png", label: "FFT vertical" },
      { name: "spectrum_horizontal.png", label: "FFT horizontal" },
    ];
    if (polygon && polygon.length >= 3) {
      files.push({ name: "original.png", label: "Entrada apos selecao" });
    }
    files.push({ name: "spectrum_combined.png", label: "FFT combinado" });
    for (const f of files) {
      await save(currentJobId, f.name, f.label);
    }
  }

  if (!caseId) return null;

  const showChannelSelect = isColorInput || !result;

  const parametersPanel = (
    <>
      <p style={{ fontSize: "0.82rem", color: "#6b7280", margin: "0 0 0.75rem 0" }}>
        Ordem fixa: 2ª derivada (Mahdian &amp; Saic).
      </p>
      {showChannelSelect && (
        <label style={{ fontSize: "0.85rem", display: "block", marginBottom: "0.75rem" }}>
          Canal (imagens coloridas):{" "}
          <select
            value={channelMode}
            onChange={(e) => setChannelMode(e.target.value as ChannelMode)}
            style={{ marginLeft: 4, padding: "0.25rem 0.4rem" }}
          >
            <option value="luminance">Luminancia (Y)</option>
            <option value="r">Vermelho (R)</option>
            <option value="g">Verde (G)</option>
            <option value="b">Azul (B)</option>
            <option value="consolidated">Consolidado (media FFT R+G+B)</option>
          </select>
        </label>
      )}
      <div style={{ marginTop: "1rem" }}>
        <button
          type="button"
          onClick={process}
          disabled={!evidenceId || runtimeOk !== true || running}
          style={btnPrimary}
        >
          {running ? "Processando…" : "Processar reamostragem"}
        </button>
      </div>
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="resampling"
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
    >
      {evidenceId && (
        <AnalysisPanel title="Entrada — selecione regiao (opcional)">
          {loadingInput && <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Carregando imagem…</p>}
          {!loadingInput && inputUrl && (
            <>
              <PolygonRoiCanvas imageUrl={inputUrl} polygon={polygon} onPolygonChange={setPolygon} maxHeight={520} />
              <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button
                  type="button"
                  disabled={!polygon || polygon.length < 3}
                  onClick={() => setUseComplement(true)}
                  style={{
                    padding: "0.45rem 0.9rem",
                    background: useComplement ? "#e0f2fe" : "#fff",
                    border: "1px solid #0369a1",
                    borderRadius: 6,
                    cursor: !polygon || polygon.length < 3 ? "not-allowed" : "pointer",
                    fontSize: "0.82rem",
                    opacity: !polygon || polygon.length < 3 ? 0.5 : 1,
                  }}
                >
                  Analisar complemento (pixels fora do ROI)
                </button>
                {useComplement && (
                  <button type="button" onClick={() => setUseComplement(false)} style={saveBtnStyle}>
                    Voltar ao ROI primario
                  </button>
                )}
              </div>
            </>
          )}
          {!loadingInput && !inputUrl && (
            <MessageBox type="err" text="Nao foi possivel carregar a imagem de entrada." />
          )}
        </AnalysisPanel>
      )}

      {result && originalUrl && derivVUrl && derivHUrl && (
        <AnalysisPanel title="Resultado — imagens">
          <SyncedImagePairViewer
            ref={viewerEntradaRef}
            height={420}
            leftSrc={originalUrl}
            rightSrc={derivVUrl}
            leftLabel="Entrada analisada (ROI / canal)"
            rightLabel="Derivada vertical |d²|"
          />

          <div style={{ marginTop: "1rem" }}>
            <SyncedImagePairViewer
              ref={viewerDerivRef}
              height={420}
              leftSrc={originalUrl}
              rightSrc={derivHUrl}
              leftLabel="Entrada analisada"
              rightLabel="Derivada horizontal |d²|"
            />
          </div>
        </AnalysisPanel>
      )}

      {result && (specCombinedUrl || specVUrl || specHUrl) && (
        <AnalysisPanel title="Resultado — FFT (espectro completo)">
          {specCombinedUrl && (
            <figure style={{ marginBottom: "1rem" }}>
              <img
                src={specCombinedUrl}
                alt="FFT vertical e horizontal"
                style={{ width: "100%", borderRadius: 6, border: "1px solid #e5e7eb" }}
              />
              <figcaption style={capStyle}>FFT da covariancia — vertical + horizontal</figcaption>
            </figure>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            {specVUrl && (
              <figure>
                <img src={specVUrl} alt="FFT vertical" style={spectrumImgStyle} />
                <figcaption style={capStyle}>FFT vertical</figcaption>
              </figure>
            )}
            {specHUrl && (
              <figure>
                <img src={specHUrl} alt="FFT horizontal" style={spectrumImgStyle} />
                <figcaption style={capStyle}>FFT horizontal</figcaption>
              </figure>
            )}
          </div>

          {currentJobId && (
            <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button
                type="button"
                disabled={saving}
                onClick={handleSaveCustodyBundle}
                style={primarySaveStyle}
              >
                {saving ? "Salvando…" : "Salvar FFT + entrada na custodia"}
              </button>
            </div>
          )}
        </AnalysisPanel>
      )}
    </TechniquePageShell>
  );
}

const capStyle: React.CSSProperties = { fontSize: "0.8rem", color: "#6b7280", marginTop: 4 };

const spectrumImgStyle: React.CSSProperties = {
  width: "100%",
  borderRadius: 6,
  border: "1px solid #e5e7eb",
};

const saveBtnStyle: React.CSSProperties = {
  padding: "0.45rem 0.9rem",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
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

const primarySaveStyle: React.CSSProperties = {
  ...saveBtnStyle,
  background: "#0369a1",
  color: "#fff",
  borderColor: "#0369a1",
  fontWeight: 600,
};
