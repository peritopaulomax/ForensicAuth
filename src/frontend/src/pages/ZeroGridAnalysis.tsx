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

type ViewMode = "votes" | "forgery" | "overlay";

export default function ZeroGridAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [includeSimulation, setIncludeSimulation] = useState(false);
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("votes");
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [votesUrl, setVotesUrl] = useState<string | null>(null);
  const [forgeryUrl, setForgeryUrl] = useState<string | null>(null);
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null);
  const [votesSimUrl, setVotesSimUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const simViewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setOriginalUrl(`/api/v1/evidences/${id}/file`);
      setVotesUrl(null);
      setForgeryUrl(null);
      setOverlayUrl(null);
      setVotesSimUrl(null);
      setSaveMessage(null);
      viewerRef.current?.resetZoom();
      simViewerRef.current?.resetZoom();
    },
    [reset],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  useEffect(() => {
    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((res) => {
        const z = res.data.find((t) => t.name === "zero_grid");
        if (z) {
          setRuntimeOk(z.available !== false);
          setRuntimeReason(z.unavailable_reason || "");
        } else {
          setRuntimeOk(false);
          setRuntimeReason("Tecnica zero_grid nao registrada no servidor.");
        }
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Nao foi possivel verificar disponibilidade do ZERO.");
      });
  }, []);

  const rightUrl =
    viewMode === "votes" ? votesUrl : viewMode === "forgery" ? forgeryUrl : overlayUrl;
  const rightLabel =
    viewMode === "votes"
      ? "Mapa de votos (grade JPEG)"
      : viewMode === "forgery"
        ? "Mascara de falsificacao (hot)"
        : "Overlay na evidencia";

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    setSaveMessage(null);
    try {
      await runAnalysis(
        evidenceId,
        "zero_grid",
        { include_simulation: includeSimulation, simulation_quality: 99 },
        {
          onArtifactsLoaded: async (jobId) => {
            const [orig, votes, forgery, overlay, sim] = await Promise.all([
              fetchImage(jobId, "original.png"),
              fetchImage(jobId, "votes_colored.png"),
              fetchImage(jobId, "forgery_mask.png"),
              fetchImage(jobId, "overlay.png"),
              includeSimulation ? fetchImage(jobId, "votes_simulated.png") : Promise.resolve(null),
            ]);
            if (orig) setOriginalUrl(orig);
            setVotesUrl(votes);
            setForgeryUrl(forgery);
            setOverlayUrl(overlay);
            setVotesSimUrl(sim);
            viewerRef.current?.resetZoom();
            simViewerRef.current?.resetZoom();
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

  if (runtimeOk === false) {
    return (
      <AnalysisPageShell
        caseId={caseId}
        title={FORENSIC_TECHNIQUE_META.zero_grid.title}
        intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.zero_grid} />}
        embedded={embedded}
      >
        <AnalysisPanel title="Indisponivel">
          <MessageBox
            type="err"
            text={
              runtimeReason ||
              "ZERO requer backend Linux com libzero.so_. Em servidores Windows a tecnica fica desativada."
            }
          />
        </AnalysisPanel>
      </AnalysisPageShell>
    );
  }

  type ZeroRegion = {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
    grid_dx: number;
    grid_dy: number;
    lnfa: number;
  };
  const regions1 = (result?.forged_regions_pass1 as ZeroRegion[] | undefined) || [];

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.zero_grid.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.zero_grid} />}
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
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.88rem" }}>
          <input
            type="checkbox"
            checked={includeSimulation}
            onChange={(e) => setIncludeSimulation(e.target.checked)}
          />
          Incluir passagem com JPEG simulado (qualidade 99) — etapa opcional de recompressao
        </label>
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!evidenceId || runtimeOk !== true}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Processar ZERO"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Resultado">
          <div style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.75rem", lineHeight: 1.5 }}>
            {result.main_grid_detected ? (
              <p style={{ margin: "0 0 0.35rem" }}>
                Grade principal: ({Number(result.main_grid_dx)}, {Number(result.main_grid_dy)}) · indice{" "}
                {Number(result.main_grid)}
                {result.main_grid_misaligned ? " · possivel recorte (grade nao em 0,0)" : ""}
              </p>
            ) : (
              <p style={{ margin: "0 0 0.35rem" }}>Nenhuma grade JPEG global detectada (main_grid = -1).</p>
            )}
            <p style={{ margin: 0 }}>
              Regioes (passagem 1): {Number(result.forgery_found_pass1)}
              {includeSimulation ? ` · passagem 2: ${Number(result.forgery_found_pass2)}` : ""}
            </p>
          </div>

          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
            {(
              [
                ["votes", "Mapa de votos"],
                ["forgery", "Falsificacao"],
                ["overlay", "Overlay"],
              ] as const
            ).map(([mode, label]) => (
              <button key={mode} type="button" onClick={() => setViewMode(mode)} style={tabStyle(viewMode === mode)}>
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

          {votesSimUrl && originalUrl && (
            <div style={{ marginTop: "1rem" }}>
              <SyncedImagePairViewer
                ref={simViewerRef}
                leftSrc={originalUrl}
                rightSrc={votesSimUrl}
                leftLabel="Original"
                rightLabel="Mapa de votos apos JPEG simulado (Q=99)"
              />
            </div>
          )}

          {regions1.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <h4 style={{ fontSize: "0.9rem", margin: "0 0 0.5rem" }}>Regioes detectadas (passagem 1)</h4>
              <ul style={{ margin: 0, paddingLeft: "1.2rem", fontSize: "0.82rem", color: "#4b5563" }}>
                {regions1.map((r, i) => (
                  <li key={i}>
                    ({r.x0},{r.y0})–({r.x1},{r.y1}) · grade ({r.grid_dx},{r.grid_dy}) · log NFA={Number(r.lnfa).toFixed(3)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {currentJobId && (
            <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" disabled={saving} onClick={() => handleSave("votes_colored.png", "Mapa de votos")} style={btnSecondary}>
                Salvar mapa de votos
              </button>
              <button type="button" disabled={saving} onClick={() => handleSave("forgery_mask.png", "Mascara")} style={btnSecondary}>
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
function tabStyle(active: boolean): React.CSSProperties {
  return {
    padding: "0.4rem 0.85rem",
    borderRadius: 6,
    border: `1px solid ${active ? "#0369a1" : "#d1d5db"}`,
    background: active ? "#e0f2fe" : "#fff",
    cursor: "pointer",
    fontSize: "0.82rem",
  };
}
