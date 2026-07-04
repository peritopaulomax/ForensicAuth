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

type ViewMode = "vectors" | "colored" | "mask";

export default function PatchMatchAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [viewMode, setViewMode] = useState<ViewMode>("colored");
  const [p, setP] = useState(10);
  const [maxZrd, setMaxZrd] = useState(6);
  const [minDn, setMinDn] = useState(64);
  const [iterations, setIterations] = useState(5);
  const [minRegion, setMinRegion] = useState(128);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [vectorsUrl, setVectorsUrl] = useState<string | null>(null);
  const [coloredUrl, setColoredUrl] = useState<string | null>(null);
  const [maskUrl, setMaskUrl] = useState<string | null>(null);
  const [distUrl, setDistUrl] = useState<string | null>(null);
  const [vectIUrl, setVectIUrl] = useState<string | null>(null);
  const [vectJUrl, setVectJUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setOriginalUrl(`/api/v1/evidences/${id}/file`);
      setVectorsUrl(null);
      setColoredUrl(null);
      setMaskUrl(null);
      setDistUrl(null);
      setVectIUrl(null);
      setVectJUrl(null);
      setSaveMessage(null);
      setViewMode("colored");
      viewerRef.current?.resetZoom();
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
        "patchmatch",
        {
          p,
          max_zrd: maxZrd,
          min_dn: minDn,
          n_rs_candidates: 5,
          iterations,
          min_region_size: minRegion,
          zernike: true,
          max_arrows: 400,
        },
        {
          onArtifactsLoaded: async (jobId) => {
            const [orig, vectors, colored, mask, dist, vi, vj] = await Promise.all([
              fetchImage(jobId, "original.png"),
              fetchImage(jobId, "vectors.png"),
              fetchImage(jobId, "colored_overlay.png"),
              fetchImage(jobId, "mask.png"),
              fetchImage(jobId, "Campo de distância.png"),
              fetchImage(jobId, "vect_field_i.png"),
              fetchImage(jobId, "vect_field_j.png"),
            ]);
            if (orig) setOriginalUrl(orig);
            setVectorsUrl(vectors);
            setColoredUrl(colored);
            setMaskUrl(mask);
            setDistUrl(dist);
            setVectIUrl(vi);
            setVectJUrl(vj);
            setViewMode("colored");
          },
        }
      );
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

  const rightUrl =
    viewMode === "vectors" ? vectorsUrl : viewMode === "colored" ? coloredUrl : maskUrl;
  const rightLabel =
    viewMode === "vectors"
      ? "Vetores de deslocamento (origem → destino)"
      : viewMode === "colored"
        ? "Cores por deslocamento (mesma cor ≈ mesmo par)"
        : "Mascara binaria";

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.patchmatch.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.patchmatch} techniqueId="patchmatch" />}
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
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "0.75rem" }}>
          {(
            [
              { label: "p (meio-patch)", value: p, onChange: setP },
              { label: "max_zrd", value: maxZrd, onChange: setMaxZrd },
              { label: "min_dn (T)", value: minDn, onChange: setMinDn },
              { label: "iteracoes", value: iterations, onChange: setIterations },
              { label: "min regiao (px)", value: minRegion, onChange: setMinRegion },
            ] as const
          ).map(({ label, value, onChange }) => (
            <label key={label} style={{ fontSize: "0.82rem" }}>
              {label}
              <input
                type="number"
                min={1}
                value={value}
                onChange={(e) => onChange(Number(e.target.value))}
                style={{ display: "block", width: "100%", marginTop: 4 }}
              />
            </label>
          ))}
        </div>
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!evidenceId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Processar PatchMatch"
          />
        </div>
        <p style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: "0.5rem", lineHeight: 1.45 }}>
          A inicializacao (Zernike + campo de distancias) costuma ser a etapa mais longa em imagens grandes.
          A barra exibe tempo decorrido nessa fase e avanca a cada iteracao do algoritmo.
        </p>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Resultado">
          <p style={{ fontSize: "0.9rem", margin: "0 0 0.75rem 0", color: "#374151" }}>
            Area mascarada: {Number(result.mask_area_pixels).toLocaleString()} px (
            {(Number(result.mask_ratio) * 100).toFixed(3)}%) · Grupos de deslocamento distintos:{" "}
            {Number(result.displacement_groups)}
          </p>

          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["colored", "Overlay (cores por deslocamento)"],
                ["mask", "Mascara"],
                ["vectors", "Vetores de deslocamento"],
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

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem", marginTop: "1rem" }}>
            {vectIUrl && (
              <figure>
                <img src={vectIUrl} alt="Componente i" style={imgStyle} />
                <figcaption style={capStyle}>Campo vetorial — componente i</figcaption>
              </figure>
            )}
            {vectJUrl && (
              <figure>
                <img src={vectJUrl} alt="Componente j" style={imgStyle} />
                <figcaption style={capStyle}>Campo vetorial — componente j</figcaption>
              </figure>
            )}
            {distUrl && (
              <figure>
                <img src={distUrl} alt="Distancia" style={imgStyle} />
                <figcaption style={capStyle}>Campo de distância</figcaption>
              </figure>
            )}
          </div>

          {currentJobId && (
            <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" disabled={saving} onClick={() => handleSave("colored_overlay.png", "Overlay colorido")} style={btnSecondary}>
                Salvar overlay
              </button>
              <button type="button" disabled={saving} onClick={() => handleSave("mask.png", "Mascara")} style={btnSecondary}>
                Salvar mascara
              </button>
              <button type="button" disabled={saving} onClick={() => handleSave("vectors.png", "Mapa de vetores")} style={btnSecondary}>
                Salvar vetores de deslocamento
              </button>
            </div>
          )}
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

const imgStyle: React.CSSProperties = { width: "100%", borderRadius: 6, border: "1px solid #e5e7eb" };
const capStyle: React.CSSProperties = { fontSize: "0.8rem", color: "#6b7280", marginTop: 4 };
const btnSecondary: React.CSSProperties = {
  padding: "0.45rem 0.9rem",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
};
