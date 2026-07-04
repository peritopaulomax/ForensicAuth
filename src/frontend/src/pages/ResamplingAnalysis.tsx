import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import PolygonRoiCanvas, { type PolygonPoint } from "@/components/PolygonRoiCanvas";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";
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
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerEntradaRef = useRef<SyncedImagePairViewerHandle>(null);
  const viewerDerivRef = useRef<SyncedImagePairViewerHandle>(null);
  const inputBlobRef = useRef<string | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

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
      setSaveMessage(null);
      viewerEntradaRef.current?.resetZoom();
      viewerDerivRef.current?.resetZoom();
      loadInputBlob(id);
    },
    [reset],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId) return;
    setSaveMessage(null);
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
      /* error in hook */
    }
  }

  async function handleSaveCustodyBundle() {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    const files: { name: string; label: string }[] = [
      { name: "spectrum_combined.png", label: "FFT combinado" },
      { name: "spectrum_vertical.png", label: "FFT vertical" },
      { name: "spectrum_horizontal.png", label: "FFT horizontal" },
    ];
    if (polygon && polygon.length >= 3) {
      files.push({ name: "original.png", label: "Entrada apos selecao" });
    }
    try {
      await Promise.all(
        files.map((f) => saveDerivative({ job_id: currentJobId, artifact_filename: f.name }))
      );
      setSaveMessage({
        type: "ok",
        text: `${files.length} artefato(s) salvos na cadeia de custodia (FFT + entrada).`,
      });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: msg });
    } finally {
      setSaving(false);
    }
  }

  if (!caseId) return null;

  const showChannelSelect = isColorInput || !result;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.resampling.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.resampling} techniqueId="resampling" />}
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
        <ProcessButton
          onClick={process}
          disabled={!evidenceId}
          running={running}
          progress={progress}
          progressLabel={progressLabel}
          label="Processar reamostragem"
        />
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

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
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
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

const primarySaveStyle: React.CSSProperties = {
  ...saveBtnStyle,
  background: "#0369a1",
  color: "#fff",
  borderColor: "#0369a1",
  fontWeight: 600,
};
