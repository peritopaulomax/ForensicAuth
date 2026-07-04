import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { buildReturnToCaseAnalysesUrl } from "@/utils/caseAnalysisNav";
import { saveDerivative } from "@/services/evidence";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import { ForensicProgressBar, MessageBox } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { buildElaGainBlobUrl } from "@/utils/elaGainPreview";
import type { Evidence } from "@/types/api";

type ChannelMode = "rgb" | "y" | "crominancia" | "r" | "g" | "b";

const CHANNEL_LABELS: Record<ChannelMode, { left: string; right: string }> = {
  rgb: { left: "Original (RGB)", right: "ELA RGB" },
  y: { left: "Luminancia (Y)", right: "ELA Y" },
  crominancia: { left: "Crominancia (Cb+Cr)/2", right: "ELA Crominancia" },
  r: { left: "Canal R", right: "ELA R" },
  g: { left: "Canal G", right: "ELA G" },
  b: { left: "Canal B", right: "ELA B" },
};

const CHANNEL_OPTIONS: { value: ChannelMode; label: string }[] = [
  { value: "rgb", label: "RGB" },
  { value: "y", label: "Y (luminancia)" },
  { value: "crominancia", label: "Crominancia" },
  { value: "r", label: "R" },
  { value: "g", label: "G" },
  { value: "b", label: "B" },
];

function evidenceFileUrl(evidenceId: string): string {
  return `/api/v1/evidences/${evidenceId}/file`;
}

function preloadImage(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("Falha ao carregar imagem"));
    img.src = src;
  });
}

function isBlobUrl(src: string | null | undefined): src is string {
  return Boolean(src?.startsWith("blob:"));
}

export default function ELAAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const [displayLeftSrc, setDisplayLeftSrc] = useState("");
  const [displayRightSrc, setDisplayRightSrc] = useState<string | null>(null);
  const [heatmapBaseSrc, setHeatmapBaseSrc] = useState<string | null>(null);
  const [savingDerivative, setSavingDerivative] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const [quality, setQuality] = useState(95);
  const [gain, setGain] = useState(1.0);
  const [discardV, setDiscardV] = useState(0);
  const [discardH, setDiscardH] = useState(0);
  const [channelMode, setChannelMode] = useState<ChannelMode>("rgb");

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const gainDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoSelectedRef = useRef(false);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const runGenRef = useRef(0);
  const gainGenRef = useRef(0);
  const blobUrlsRef = useRef<Set<string>>(new Set());
  const displayLeftRef = useRef("");
  const displayRightRef = useRef<string | null>(null);
  const heatmapBaseRef = useRef<string | null>(null);

  displayLeftRef.current = displayLeftSrc;
  displayRightRef.current = displayRightSrc;
  heatmapBaseRef.current = heatmapBaseSrc;

  const {
    running,
    currentJobId,
    error,
    progress,
    progressLabel,
    runAnalysis,
    fetchImage,
    setError,
  } = useForensicJob();

  const revokeBlob = useCallback((url: string | null | undefined) => {
    if (!isBlobUrl(url)) return;
    URL.revokeObjectURL(url);
    blobUrlsRef.current.delete(url);
  }, []);

  const registerBlob = useCallback((url: string) => {
    if (isBlobUrl(url)) blobUrlsRef.current.add(url);
    return url;
  }, []);

  const swapLeftEvidence = useCallback(
    async (nextLeft: string) => {
      const prevLeft = displayLeftSrc;
      try {
        await preloadImage(nextLeft);
        setDisplayLeftSrc(nextLeft);
        if (isBlobUrl(prevLeft) && prevLeft !== nextLeft) revokeBlob(prevLeft);
      } catch {
        setDisplayLeftSrc(nextLeft);
      }
    },
    [displayLeftSrc, revokeBlob],
  );

  const applyEvidence = useCallback(
    (evId: string, _source: "original" | "derivative") => {
      setSaveMessage(null);
      setError(null);
      setHeatmapBaseSrc((prev) => {
        revokeBlob(prev);
        return null;
      });
      setDisplayRightSrc((prev) => {
        revokeBlob(prev);
        return null;
      });
      viewerRef.current?.resetZoom();
      void swapLeftEvidence(evidenceFileUrl(evId));
    },
    [setError, swapLeftEvidence, revokeBlob],
  );

  const { showPageShell, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  useEffect(() => {
    return () => {
      blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      blobUrlsRef.current.clear();
    };
  }, []);

  const gainRef = useRef(gain);
  gainRef.current = gain;

  const applyGainPreview = useCallback(
    async (baseSrc: string, nextGain: number) => {
      const gen = ++gainGenRef.current;
      try {
        const url = registerBlob(await buildElaGainBlobUrl(baseSrc, nextGain));
        if (gen !== gainGenRef.current) {
          revokeBlob(url);
          return;
        }
        const prevRight = displayRightRef.current;
        setDisplayRightSrc(url);
        if (isBlobUrl(prevRight) && prevRight !== url) revokeBlob(prevRight);
      } catch {
        if (gen === gainGenRef.current) {
          setDisplayRightSrc(null);
        }
      }
    },
    [registerBlob, revokeBlob],
  );

  const runELA = useCallback(async () => {
    if (!evidenceId || !caseId) return;
    const gen = ++runGenRef.current;
    gainGenRef.current += 1;
    setSaveMessage(null);

    const prevLeft = displayLeftRef.current;
    const prevRight = displayRightRef.current;
    const prevBase = heatmapBaseRef.current;

    try {
      await runAnalysis(
        evidenceId,
        "ela",
        {
          quality,
          gain: 1.0,
          discard_vertical: discardV,
          discard_horizontal: discardH,
          channel_mode: channelMode,
        },
        {
          onArtifactsLoaded: async (jobId) => {
            if (gen !== runGenRef.current) return;

            const [heatmapBaseBlob, originalBlob] = await Promise.all([
              fetchImage(jobId, "heatmap_base.png").then((u) => u ?? fetchImage(jobId, "heatmap.png")),
              fetchImage(jobId, "original.png"),
            ]);

            if (gen !== runGenRef.current) {
              if (heatmapBaseBlob) revokeBlob(heatmapBaseBlob);
              if (originalBlob) revokeBlob(originalBlob);
              return;
            }

            if (!heatmapBaseBlob) {
              throw new Error("ELA concluido, mas o heatmap base nao foi encontrado no servidor.");
            }

            const nextLeft = originalBlob
              ? registerBlob(originalBlob)
              : prevLeft || evidenceFileUrl(evidenceId);
            const nextBase = registerBlob(heatmapBaseBlob);

            if (isBlobUrl(prevBase) && prevBase !== nextBase) revokeBlob(prevBase);
            setHeatmapBaseSrc(nextBase);
            setDisplayLeftSrc(nextLeft);
            if (isBlobUrl(prevLeft) && prevLeft !== nextLeft) revokeBlob(prevLeft);

            await applyGainPreview(nextBase, gainRef.current);
            if (isBlobUrl(prevRight) && prevRight !== displayRightRef.current) revokeBlob(prevRight);
          },
        },
      );
    } catch {
      /* hook define error */
    }
  }, [
    evidenceId,
    caseId,
    quality,
    discardV,
    discardH,
    channelMode,
    runAnalysis,
    fetchImage,
    registerBlob,
    revokeBlob,
    applyGainPreview,
  ]);

  useEffect(() => {
    if (!evidenceId || !caseId) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      runELA();
    }, 600);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [quality, discardV, discardH, channelMode, evidenceId, caseId, runELA]);

  useEffect(() => {
    if (!heatmapBaseSrc) return;
    if (gainDebounceRef.current) clearTimeout(gainDebounceRef.current);
    gainDebounceRef.current = setTimeout(() => {
      void applyGainPreview(heatmapBaseSrc, gain);
    }, 80);
    return () => {
      if (gainDebounceRef.current) clearTimeout(gainDebounceRef.current);
    };
  }, [gain, heatmapBaseSrc, applyGainPreview]);

  useEffect(() => {
    autoSelectedRef.current = false;
  }, [caseId]);

  function handleEvidenceLoaded(originals: Evidence[], derivatives: Evidence[]) {
    if (autoSelectedRef.current) return;
    autoSelectedRef.current = true;
    if (originals.length > 0) {
      onSelectEvidence(originals[0].id, "original");
    } else if (derivatives.length > 0) {
      onSelectEvidence(derivatives[0].id, "derivative");
    }
  }

  async function handleSaveDerivative() {
    if (!currentJobId) return;
    setSavingDerivative(true);
    setSaveMessage(null);
    try {
      const result = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: "heatmap.png",
        effective_parameters: {
          quality,
          gain,
          discard_vertical: discardV,
          discard_horizontal: discardH,
          channel_mode: channelMode,
        },
      });
      setSaveMessage({
        type: "ok",
        text: `${result.message}. Exporte na aba Derivados do caso. SHA-256: ${result.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setSaveMessage({ type: "err", text: detail || "Erro ao salvar derivado" });
    } finally {
      setSavingDerivative(false);
    }
  }

  const showViewer = Boolean(displayLeftSrc);

  return (
    <div style={{ padding: "2rem" }}>
      {showPageShell && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
          <button
            onClick={() => navigate(buildReturnToCaseAnalysesUrl(caseId!, location.pathname))}
            style={{ background: "none", border: "none", color: "#6b7280", cursor: "pointer", fontSize: "0.9rem", padding: 0 }}
          >
            ← Voltar ao caso
          </button>
        </div>
      )}

      {showPageShell && (
        <h1 style={{ fontSize: "1.5rem", color: "#1a1a2e", marginBottom: "0.75rem" }}>
          {FORENSIC_TECHNIQUE_META.ela.title}
        </h1>
      )}
      <TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.ela} techniqueId="ela" />

      {caseId && showEvidencePicker && (
        <ImageEvidenceSelector
          caseId={caseId}
          selectedId={evidenceId}
          selectionSource={selectionSource}
          onSelect={onSelectEvidence}
          onLoaded={handleEvidenceLoaded}
        />
      )}

      <div
        style={{
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: "8px",
          padding: "1.25rem",
          marginBottom: "1.5rem",
        }}
      >
        <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.75rem", fontWeight: 600 }}>
          Parâmetros ELA
        </h3>

        <div style={{ marginBottom: "1rem" }}>
          <span style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "0.4rem" }}>
            Canal / componente
          </span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
            {CHANNEL_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.35rem",
                  fontSize: "0.85rem",
                  color: "#374151",
                  cursor: "pointer",
                }}
              >
                <input
                  type="radio"
                  name="channel_mode"
                  value={opt.value}
                  checked={channelMode === opt.value}
                  onChange={() => setChannelMode(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
          <div>
            <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "0.25rem" }}>
              Qualidade JPEG ({quality})
            </label>
            <input
              type="range"
              min={50}
              max={100}
              value={quality}
              onChange={(e) => setQuality(parseInt(e.target.value))}
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "0.25rem" }}>
              Ganho/Brilho ({gain.toFixed(1)}) — preview instantaneo
            </label>
            <input
              type="range"
              min={0.5}
              max={5}
              step={0.1}
              value={gain}
              onChange={(e) => setGain(parseFloat(e.target.value))}
              style={{ width: "100%" }}
            />
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "0.5rem" }}>
          <div>
            <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "0.25rem" }}>
              Descartar linhas (0-7)
            </label>
            <input
              type="number"
              min={0}
              max={7}
              value={discardV}
              onChange={(e) => setDiscardV(Math.min(7, Math.max(0, parseInt(e.target.value) || 0)))}
              style={{
                width: "100%",
                padding: "0.4rem 0.6rem",
                border: "1px solid #d1d5db",
                borderRadius: "4px",
                fontSize: "0.85rem",
                color: "#1a1a2e",
              }}
            />
          </div>
          <div>
            <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "0.25rem" }}>
              Descartar colunas (0-7)
            </label>
            <input
              type="number"
              min={0}
              max={7}
              value={discardH}
              onChange={(e) => setDiscardH(Math.min(7, Math.max(0, parseInt(e.target.value) || 0)))}
              style={{
                width: "100%",
                padding: "0.4rem 0.6rem",
                border: "1px solid #d1d5db",
                borderRadius: "4px",
                fontSize: "0.85rem",
                color: "#1a1a2e",
              }}
            />
          </div>
        </div>

        <ForensicProgressBar progress={progress} progressLabel={progressLabel} running={running} />
        {error && <MessageBox type="err" text={error} />}
      </div>

      {showViewer && (
        <div style={{ position: "relative" }}>
          <SyncedImagePairViewer
            ref={viewerRef}
            height={500}
            leftLabel={CHANNEL_LABELS[channelMode].left}
            rightLabel={CHANNEL_LABELS[channelMode].right}
            leftSrc={displayLeftSrc}
            rightSrc={displayRightSrc}
            rightPlaceholder={
              !displayRightSrc ? (
                <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>
                  Ajuste os parametros para gerar o heatmap ELA
                </p>
              ) : undefined
            }
          />
          {running && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                pointerEvents: "none",
                display: "flex",
                alignItems: "flex-end",
                justifyContent: "center",
                paddingBottom: "0.75rem",
              }}
            >
              <span
                style={{
                  background: "rgba(255,255,255,0.92)",
                  border: "1px solid #e5e7eb",
                  borderRadius: 6,
                  padding: "0.35rem 0.75rem",
                  fontSize: "0.78rem",
                  color: "#4b5563",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
                }}
              >
                Atualizando resultado…
              </span>
            </div>
          )}
        </div>
      )}

      {showViewer && (
        <div
          style={{
            marginTop: "1rem",
            padding: "1rem",
            background: "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
          }}
        >
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => viewerRef.current?.resetZoom()}
              style={{
                padding: "0.6rem 1rem",
                background: "#f3f4f6",
                color: "#374151",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "0.9rem",
              }}
            >
              Reset zoom
            </button>
            {displayRightSrc && currentJobId && (
              <button
                type="button"
                onClick={handleSaveDerivative}
                disabled={savingDerivative || running}
                title="Grava o resultado, calcula SHA-256 e registra na cadeia de custodia"
                style={{
                  padding: "0.6rem 1rem",
                  background: "#1a1a2e",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  cursor: savingDerivative ? "wait" : "pointer",
                  fontSize: "0.9rem",
                  fontWeight: 500,
                }}
              >
                {savingDerivative ? "Salvando…" : "Salvar como derivado"}
              </button>
            )}
            {caseId && (
              <button
                type="button"
                onClick={() => navigate(`/cases/${caseId}?tab=derivados`)}
                style={{
                  padding: "0.6rem 1rem",
                  background: "#fff",
                  color: "#1a1a2e",
                  border: "1px solid #1a1a2e",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontSize: "0.9rem",
                }}
              >
                Abrir derivados
              </button>
            )}
          </div>
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
        </div>
      )}
    </div>
  );
}
