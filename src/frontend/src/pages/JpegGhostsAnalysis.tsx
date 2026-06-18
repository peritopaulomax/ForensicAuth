import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";

type ViewMode = "ghost" | "metric";

export default function JpegGhostsAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [qmin, setQmin] = useState(50);
  const [qmax, setQmax] = useState(100);
  const [step, setStep] = useState(10);
  const [blockSize, setBlockSize] = useState(16);
  const [neighborhoodK, setNeighborhoodK] = useState(3);
  const [shiftSearch, setShiftSearch] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>("ghost");
  const [selectedQuality, setSelectedQuality] = useState<number | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [ghostUrl, setGhostUrl] = useState<string | null>(null);
  const [metricUrl, setMetricUrl] = useState<string | null>(null);
  const [shiftGridUrl, setShiftGridUrl] = useState<string | null>(null);
  const [montageUrl, setMontageUrl] = useState<string | null>(null);
  const [qualityGhostUrls, setQualityGhostUrls] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const saveMessageRef = useRef<HTMLDivElement>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      setOriginalUrl(`/api/v1/evidences/${id}/file`);
      setGhostUrl(null);
      setMetricUrl(null);
      setShiftGridUrl(null);
      setMontageUrl(null);
      setQualityGhostUrls({});
      setSelectedQuality(null);
      setSaveMessage(null);
      viewerRef.current?.resetZoom();
    },
    [reset],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  const qualities = useMemo(() => {
    const fromResult = result?.qualities as number[] | undefined;
    if (fromResult?.length) return fromResult;
    const list: number[] = [];
    for (let q = qmin; q <= qmax; q += step) list.push(q);
    return list;
  }, [result, qmin, qmax, step]);

  const metricPeaks = (result?.metric_peaks_by_quality as Record<string, number>) || {};

  useEffect(() => {
    if (selectedQuality == null && qualities.length > 0) {
      const best = result?.best_quality as number | undefined;
      setSelectedQuality(best ?? qualities[0]);
    }
  }, [qualities, result, selectedQuality]);

  const activeGhostUrl =
    selectedQuality != null && qualityGhostUrls[String(selectedQuality)]
      ? qualityGhostUrls[String(selectedQuality)]
      : ghostUrl;

  async function process() {
    if (!evidenceId) return;
    setSaveMessage(null);
    try {
      await runAnalysis(
        evidenceId,
        "jpeg_ghosts",
        {
          qmin,
          qmax,
          step,
          block_size: blockSize,
          neighborhood_k: neighborhoodK,
          shift_search: shiftSearch,
        },
        {
          onArtifactsLoaded: async (jobId, jobResult) => {
            const filenames = (jobResult?.quality_ghost_filenames as Record<string, string>) || {};
            const qUrls: Record<string, string> = {};
            await Promise.all(
              Object.entries(filenames).map(async ([q, fname]) => {
                const url = await fetchImage(jobId, fname);
                if (url) qUrls[q] = url;
              })
            );
            setQualityGhostUrls(qUrls);

            const [orig, ghost, metric, grid, montage] = await Promise.all([
              fetchImage(jobId, "original.png"),
              fetchImage(jobId, "ghost_map.png"),
              fetchImage(jobId, "metric_map.png"),
              shiftSearch ? fetchImage(jobId, "shift_grid.png") : Promise.resolve(null),
              fetchImage(jobId, "quality_montage.png"),
            ]);
            if (orig) setOriginalUrl(orig);
            setGhostUrl(ghost);
            setMetricUrl(metric);
            setShiftGridUrl(grid);
            setMontageUrl(montage);

            const bestQ = jobResult?.best_quality as number | undefined;
            if (bestQ != null) setSelectedQuality(bestQ);
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
        text: `${res.message} (${label}). SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
      requestAnimationFrame(() => {
        saveMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: msg });
    } finally {
      setSaving(false);
    }
  }

  const rightUrl = viewMode === "ghost" ? activeGhostUrl : metricUrl;
  const rightLabel =
    viewMode === "ghost"
      ? selectedQuality != null
        ? `Mapa fantasma (Q=${selectedQuality})`
        : "Mapa fantasma (melhor Q)"
      : "Mapa de metrica (hot)";

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.jpeg_ghosts.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.jpeg_ghosts} />}
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
          <label style={labelStyle}>
            Q min
            <input type="number" min={1} max={99} value={qmin} onChange={(e) => setQmin(Number(e.target.value))} style={inputStyle} />
          </label>
          <label style={labelStyle}>
            Q max
            <input type="number" min={2} max={100} value={qmax} onChange={(e) => setQmax(Number(e.target.value))} style={inputStyle} />
          </label>
          <label style={labelStyle}>
            Passo Q
            <input type="number" min={1} max={20} value={step} onChange={(e) => setStep(Number(e.target.value))} style={inputStyle} />
          </label>
          <label style={labelStyle}>
            Bloco b
            <input type="number" min={4} value={blockSize} onChange={(e) => setBlockSize(Number(e.target.value))} style={inputStyle} />
          </label>
          <label style={labelStyle}>
            Vizinhanca K
            <input type="number" min={1} step={2} value={neighborhoodK} onChange={(e) => setNeighborhoodK(Number(e.target.value))} style={inputStyle} />
          </label>
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.75rem", fontSize: "0.88rem" }}>
          <input type="checkbox" checked={shiftSearch} onChange={(e) => setShiftSearch(e.target.checked)} />
          Buscar alinhamento da grade JPEG (64 deslocamentos 8×8)
        </label>
        <p style={{ fontSize: "0.8rem", color: "#6b7280", margin: "0.5rem 0 0" }}>
          Com busca de grade o processamento e mais lento, mas inclui deteccao completa de deslocamento.
        </p>
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!evidenceId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Processar JPEG Ghosts"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <>
          {saveMessage && (
            <div ref={saveMessageRef} style={{ marginBottom: "0.75rem" }}>
              <MessageBox type={saveMessage.type} text={saveMessage.text} />
            </div>
          )}
          <AnalysisPanel title="Resultado principal">
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "1rem",
                fontSize: "0.9rem",
                color: "#374151",
                marginBottom: "0.75rem",
              }}
            >
              <span>
                Melhor deslocamento: dx={Number(result.best_dx)}, dy={Number(result.best_dy)}
              </span>
              <span>Qualidade JPEG: Q={Number(result.best_quality)}</span>
              <span>Pico da metrica: {Number(result.peak_metric).toFixed(4)}</span>
            </div>

            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
              {(
                [
                  ["ghost", "Mapa fantasma"],
                  ["metric", "Metrica (hot)"],
                ] as const
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setViewMode(mode)}
                  style={tabStyle(viewMode === mode)}
                >
                  {label}
                </button>
              ))}
            </div>

            {viewMode === "ghost" && qualities.length > 1 && (
              <div style={{ marginBottom: "0.75rem" }}>
                <label style={{ fontSize: "0.82rem", color: "#4b5563" }}>
                  Qualidade JPEG (no melhor deslocamento)
                  <input
                    type="range"
                    min={0}
                    max={qualities.length - 1}
                    value={Math.max(0, qualities.indexOf(selectedQuality ?? qualities[0]))}
                    onChange={(e) => setSelectedQuality(qualities[Number(e.target.value)])}
                    style={{ display: "block", width: "100%", marginTop: 6 }}
                  />
                </label>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78rem", color: "#6b7280" }}>
                  <span>Q={selectedQuality}</span>
                  <span>pico metrica: {(metricPeaks[String(selectedQuality)] ?? 0).toFixed(4)}</span>
                </div>
              </div>
            )}

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
                <button type="button" disabled={saving} onClick={() => handleSave("ghost_map.png", "Mapa fantasma")} style={btnSecondary}>
                  Salvar mapa fantasma
                </button>
                <button type="button" disabled={saving} onClick={() => handleSave("metric_map.png", "Mapa de metrica")} style={btnSecondary}>
                  Salvar metrica
                </button>
              </div>
            )}
          </AnalysisPanel>

          {montageUrl && (
            <AnalysisPanel title="Galeria por qualidade">
              <p style={{ fontSize: "0.85rem", color: "#6b7280", margin: "0 0 0.5rem" }}>
                Todos os mapas fantasma no melhor deslocamento (varias qualidades lado a lado).
              </p>
              <img src={montageUrl} alt="Montagem por qualidade" style={imgStyle} />
              {currentJobId && (
                <div style={{ marginTop: "0.75rem" }}>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => handleSave("quality_montage.png", "Galeria por qualidade")}
                    style={btnSecondary}
                  >
                    Salvar galeria na custodia
                  </button>
                </div>
              )}
            </AnalysisPanel>
          )}

          {shiftGridUrl && shiftSearch && (
            <AnalysisPanel title="Grade de deslocamentos (8×8)">
              <p style={{ fontSize: "0.85rem", color: "#6b7280", margin: "0 0 0.5rem" }}>
                Miniatura do melhor mapa fantasma em cada alinhamento (dx, dy). O destaque indica onde a metrica foi maxima.
              </p>
              <img src={shiftGridUrl} alt="Grade 8x8 de deslocamentos" style={imgStyle} />
              {currentJobId && (
                <div style={{ marginTop: "0.75rem" }}>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => handleSave("shift_grid.png", "Grade de deslocamentos")}
                    style={btnSecondary}
                  >
                    Salvar grade na custodia
                  </button>
                </div>
              )}
            </AnalysisPanel>
          )}
        </>
      )}
    </AnalysisPageShell>
  );
}

const labelStyle: React.CSSProperties = { fontSize: "0.85rem" };
const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 4,
  padding: "0.35rem 0.5rem",
  borderRadius: 4,
  border: "1px solid #d1d5db",
};
const imgStyle: React.CSSProperties = { width: "100%", borderRadius: 8, border: "1px solid #e5e7eb" };
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
