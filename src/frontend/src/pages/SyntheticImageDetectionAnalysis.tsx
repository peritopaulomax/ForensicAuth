import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import AnalysisPageShell, {
  AnalysisPanel,
  MessageBox,
  ProcessButton,
  formatInferenceDevice,
  parseDeviceFromProgress,
} from "@/components/AnalysisPageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";
import {
  flattenCatalog,
  ForensicImage,
  MacroCategory,
  MetaClassifierSelect,
  capStyle,
  placeholderStyle,
  ReferenceLrPanel,
  ReferenceLrResult,
  ReferencePopulationEntry,
  ReferencePopulationSelector,
  itemsToEntries,
  referencePopulationPayload,
  referenceSelectionCounts,
  SaveButton,
  smallButtonStyle,
} from "@/components/LrReferencePanels";
import { getForensicTechniqueMeta } from "@/config/forensicTechniqueMeta";

type ResultRow = [string, string, string, string, string, string];

type SyntheticAnalysisId =
  | "ai_image_detector_deploy"
  | "sdxl_flux_detector_v1_1"
  | "bfree"
  | "corvi2023"
  | "safe";

const SYNTHETIC_ANALYSIS_OPTIONS: { id: SyntheticAnalysisId; label: string }[] = [
  { id: "ai_image_detector_deploy", label: "ai-image-detector-deploy" },
  { id: "sdxl_flux_detector_v1_1", label: "sdxl-flux-detector v1.1" },
  { id: "bfree", label: "B-Free / Bias-free" },
  { id: "corvi2023", label: "DMImageDetection" },
  { id: "safe", label: "SAFE" },
];

const DEFAULT_SYNTHETIC_ANALYSES: SyntheticAnalysisId[] = SYNTHETIC_ANALYSIS_OPTIONS.map(
  (option) => option.id
);

const INDIVIDUAL_HEADERS = [
  "Modelo",
  "Score AI",
  "Score Real",
  "Razão (Log)",
  "Classificação",
  "Dispositivo",
];

const DETECTION_PROGRESS_STAGES: {
  min: number;
  label: string;
  analysisId?: SyntheticAnalysisId;
  visualOnly?: boolean;
}[] = [
  { min: 0, label: "Preparacao e carregamento de modelos" },
  { min: 32, label: "ai-image-detector-deploy", analysisId: "ai_image_detector_deploy" },
  { min: 46, label: "sdxl-flux-detector v1.1", analysisId: "sdxl_flux_detector_v1_1" },
  { min: 52, label: "B-Free / Bias-free", analysisId: "bfree" },
  { min: 54, label: "DMImageDetection em tiles 1024px", analysisId: "corvi2023" },
  { min: 58, label: "SAFE (KDD 2025)", analysisId: "safe" },
  { min: 68, label: "Visualizacoes forenses (FFT, residuos)", visualOnly: true },
  { min: 86, label: "Salvando artefatos e relatorio" },
];

function DetectionProgressChecklist({
  progress,
  running,
  inferenceDevice,
  selectedAnalyses,
  generateVisuals,
}: {
  progress: number;
  running: boolean;
  inferenceDevice: string | null;
  selectedAnalyses: SyntheticAnalysisId[];
  generateVisuals: boolean;
}) {
  if (!running) return null;
  const pct = Math.round(Math.min(100, Math.max(0, progress)));
  const visibleStages = DETECTION_PROGRESS_STAGES.filter((stage) => {
    if (stage.visualOnly) return generateVisuals;
    if (stage.analysisId) return selectedAnalyses.includes(stage.analysisId);
    return true;
  });

  return (
    <div style={{ marginTop: "0.75rem" }}>
      {inferenceDevice && (
        <p style={{ margin: "0 0 0.5rem", fontSize: "0.8rem", color: "#374151" }}>
          Dispositivo de inferencia ML:{" "}
          <strong style={{ color: inferenceDevice === "CPU" ? "#b45309" : "#1d4ed8" }}>
            {inferenceDevice}
          </strong>
          {inferenceDevice === "CPU" && (
            <span style={{ color: "#b45309", fontWeight: 400 }}> — mais lento que GPU</span>
          )}
        </p>
      )}
      <ul
        style={{
          margin: 0,
          padding: 0,
          listStyle: "none",
          fontSize: "0.78rem",
          color: "#6b7280",
          display: "grid",
          gap: "0.3rem",
        }}
      >
      {visibleStages.map((stage, idx) => {
        const nextMin = visibleStages[idx + 1]?.min ?? 101;
        const done = pct >= nextMin;
        const active = pct >= stage.min && pct < nextMin;
        const icon = done ? "✓" : active ? "●" : "○";
        const color = done ? "#166534" : active ? "#1a1a2e" : "#9ca3af";
        const weight = active ? 600 : 400;

        return (
          <li key={stage.min} style={{ display: "flex", alignItems: "center", gap: "0.45rem", color, fontWeight: weight }}>
            <span style={{ width: "1rem", textAlign: "center", flexShrink: 0 }}>{icon}</span>
            <span>{stage.label}</span>
          </li>
        );
      })}
      </ul>
    </div>
  );
}

function ResultsTable({ rows }: { rows: ResultRow[] }) {
  return (
    <div>
      <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.88rem", color: "#374151", fontWeight: 600 }}>
        Resultados dos Modelos Individuais
      </h4>
      <div style={{ overflow: "auto", maxHeight: 180, border: "1px solid #e5e7eb", borderRadius: 6 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
          <thead>
            <tr style={{ background: "#f9fafb", position: "sticky", top: 0 }}>
              {INDIVIDUAL_HEADERS.map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: "left",
                    padding: "0.45rem 0.6rem",
                    borderBottom: "1px solid #e5e7eb",
                    color: "#4b5563",
                    fontWeight: 600,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const cells = [...row, ...Array(Math.max(0, INDIVIDUAL_HEADERS.length - row.length)).fill("—")];
              return (
              <tr key={i}>
                {cells.map((cell, j) => (
                  <td
                    key={j}
                    style={{
                      padding: "0.4rem 0.6rem",
                      borderBottom: "1px solid #f3f4f6",
                      color:
                        j === 4
                          ? classificationColor(cell)
                          : j === 5
                            ? deviceBadgeColor(cell)
                            : "#1f2937",
                      fontWeight: j === 4 || j === 5 ? 600 : 400,
                    }}
                  >
                    {j === 5 ? (
                      <span
                        style={{
                          display: "inline-block",
                          padding: "0.1rem 0.45rem",
                          borderRadius: 4,
                          fontSize: "0.72rem",
                          background: cell === "GPU" ? "#dbeafe" : "#f3f4f6",
                          color: deviceBadgeColor(cell),
                        }}
                      >
                        {cell}
                      </span>
                    ) : (
                      cell
                    )}
                  </td>
                ))}
              </tr>
            );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function classificationColor(value: string): string {
  if (value === "AI") return "#b91c1c";
  if (value === "REAL") return "#166534";
  return "#b45309";
}

function deviceBadgeColor(value: string): string {
  if (value === "GPU") return "#1d4ed8";
  return "#6b7280";
}

const inputPreviewPlaceholderStyle: React.CSSProperties = {
  minHeight: 270,
};
const inputPreviewImgStyle: React.CSSProperties = {
  minHeight: 270,
};
const forensicThumbImgStyle: React.CSSProperties = {
  width: "100%",
  height: "auto",
};
const forensicThumbPlaceholderStyle: React.CSSProperties = {
  width: "100%",
  aspectRatio: "1",
  minHeight: 0,
};
const forensicThumbCapStyle: React.CSSProperties = {
  fontSize: "0.68rem",
  color: "#6b7280",
  marginTop: 4,
  textAlign: "center",
  lineHeight: 1.25,
};

function DetectorOptionInfo({ option }: { option: { id: SyntheticAnalysisId; label: string } }) {
  const meta = getForensicTechniqueMeta(option.id);

  return (
    <span>
      <strong style={{ display: "block", color: "#1f2937" }}>{option.label}</strong>
      {meta?.cardSubtitle && (
        <span style={{ display: "block", marginTop: "0.1rem", color: "#6b7280", fontSize: "0.75rem" }}>
          {meta.cardSubtitle}
        </span>
      )}
      <span
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.35rem",
          marginTop: "0.35rem",
          fontSize: "0.72rem",
        }}
      >
        {meta?.repoUrl && (
          <a
            href={meta.repoUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#0369a1", textDecoration: "none" }}
            onClick={(e) => e.stopPropagation()}
          >
            🔗 {meta.repoUrl.includes("huggingface.co") ? "HuggingFace" : "Repositório"}
          </a>
        )}
      </span>
      {meta?.detail && (
        <span
          style={{
            display: "block",
            marginTop: "0.35rem",
            fontSize: "0.74rem",
            color: "#4b5563",
            lineHeight: 1.35,
          }}
        >
          {meta.detail}
        </span>
      )}
      {meta?.citation && (
        <span
          style={{
            display: "block",
            marginTop: "0.25rem",
            fontSize: "0.68rem",
            color: "#9ca3af",
            fontStyle: "italic",
            lineHeight: 1.3,
            whiteSpace: "pre-line",
          }}
        >
          {meta.citation}
        </span>
      )}
    </span>
  );
}

export default function SyntheticImageDetectionAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [generateVisuals, setGenerateVisuals] = useState(true);
  const [selectedAnalyses, setSelectedAnalyses] = useState<SyntheticAnalysisId[]>([
    ...DEFAULT_SYNTHETIC_ANALYSES,
  ]);
  const [runtimeOk, setRuntimeOk] = useState<boolean | null>(null);
  const [runtimeReason, setRuntimeReason] = useState("");
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [inputFftUrl, setInputFftUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [nlmResidueUrl, setNlmResidueUrl] = useState<string | null>(null);
  const [medianResidueUrl, setMedianResidueUrl] = useState<string | null>(null);
  const [nlmFftUrl, setNlmFftUrl] = useState<string | null>(null);
  const [medianFftUrl, setMedianFftUrl] = useState<string | null>(null);
  const [referenceLrTippettUrl, setReferenceLrTippettUrl] = useState<string | null>(null);
  const [referenceLrDistributionUrl, setReferenceLrDistributionUrl] = useState<string | null>(null);
  const [referenceLrIdentityUrl, setReferenceLrIdentityUrl] = useState<string | null>(null);
  const blobUrlsRef = useRef<string[]>([]);
  const [referenceCatalog, setReferenceCatalog] = useState<MacroCategory[]>([]);
  const [referenceCatalogLoading, setReferenceCatalogLoading] = useState(true);
  const [referenceCatalogError, setReferenceCatalogError] = useState<string | null>(null);
  const [referenceEntries, setReferenceEntries] = useState<ReferencePopulationEntry[]>([]);
  const [metaClassifier, setMetaClassifier] = useState<string>("logistic");
  const [useAugmentedReference, setUseAugmentedReference] = useState(false);
  const [useLatentTypicality, setUseLatentTypicality] = useState(false);

  const [saving, setSaving] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const [liveInferenceDevice, setLiveInferenceDevice] = useState<string | null>(null);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  useEffect(() => {
    if (!running) {
      setLiveInferenceDevice(null);
      return;
    }
    const parsed = parseDeviceFromProgress(progressLabel);
    if (parsed) setLiveInferenceDevice(parsed);
  }, [running, progressLabel]);

  const activeInferenceDevice =
    formatInferenceDevice(result?.inference_device) ?? (running ? liveInferenceDevice : null);

  const revokeBlobs = useCallback(() => {
    blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    blobUrlsRef.current = [];
  }, []);

  const trackBlob = useCallback((url: string | null) => {
    if (url) blobUrlsRef.current.push(url);
    return url;
  }, []);

  const setArtifactUrl = useCallback(
    (setter: (url: string | null) => void, url: string | null) => {
      setter(url ? trackBlob(url) : null);
    },
    [trackBlob]
  );

  const loadEvidencePreview = useCallback(
    async (evidenceId: string) => {
      setPreviewLoading(true);
      setOriginalUrl(null);
      try {
        const res = await api.get(`/evidences/${evidenceId}/file`, { responseType: "blob" });
        setOriginalUrl(trackBlob(URL.createObjectURL(res.data)));
      } catch {
        setOriginalUrl(null);
      } finally {
        setPreviewLoading(false);
      }
    },
    [trackBlob]
  );

  useEffect(() => {
    return () => revokeBlobs();
  }, [revokeBlobs]);

  useEffect(() => {
    api
      .get<{ categories: MacroCategory[] }>("/analysis/synthetic-reference-catalog")
      .then((res) => {
        const categories = res.data.categories;
        setReferenceCatalog(categories);
        setReferenceEntries(itemsToEntries(flattenCatalog(categories), "both"));
        setReferenceCatalogLoading(false);
      })
      .catch((err: unknown) => {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          String(err);
        setReferenceCatalogError(message);
        setReferenceCatalogLoading(false);
      });
  }, []);

  useEffect(() => {
    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((res) => {
        const item = res.data.find((t) => t.name === "synthetic_image_detection");
        if (item) {
          setRuntimeOk(item.available !== false);
          setRuntimeReason(item.unavailable_reason || "");
        } else {
          setRuntimeOk(false);
          setRuntimeReason("Detecção de imagens sintéticas não registrada no servidor.");
        }
      })
      .catch(() => {
        setRuntimeOk(false);
        setRuntimeReason("Nao foi possivel verificar disponibilidade do Detecção de imagens sintéticas.");
      });
  }, []);

  function clearVisuals() {
    setInputFftUrl(null);
    setNlmResidueUrl(null);
    setMedianResidueUrl(null);
    setNlmFftUrl(null);
    setMedianFftUrl(null);
    setReferenceLrTippettUrl(null);
    setReferenceLrDistributionUrl(null);
    setReferenceLrIdentityUrl(null);
  }

  function clearArtifactBlobs() {
    revokeBlobs();
    setOriginalUrl(null);
    clearVisuals();
  }

  const applyEvidence = useCallback(
    (id: string, _source: "original" | "derivative") => {
      reset();
      clearArtifactBlobs();
      setSaveMessage(null);
      void loadEvidencePreview(id);
    },
    [reset, revokeBlobs, loadEvidencePreview],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  const toggleAnalysis = useCallback((id: SyntheticAnalysisId, checked: boolean) => {
    setSelectedAnalyses((current) => {
      if (checked) {
        return current.includes(id) ? current : [...current, id];
      }
      return current.filter((item) => item !== id);
    });
  }, []);

  const referenceCounts = referenceSelectionCounts(referenceEntries, false);
  const referencePayload = referencePopulationPayload(referenceEntries, false);
  const referenceSelectionCount = referenceCounts.total;

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    setSaving(filename);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: filename,
        label,
      });
      setSaveMessage({
        type: "ok",
        text: `${label} salvo na cadeia de custodia. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSaveMessage({ type: "err", text: String(msg) });
    } finally {
      setSaving(null);
    }
  }

  async function process() {
    if (!evidenceId || !runtimeOk || selectedAnalyses.length === 0 || referenceSelectionCount === 0) {
      return;
    }
    clearVisuals();
    setSaveMessage(null);
    try {
      await runAnalysis(
        evidenceId,
        "synthetic_image_detection",
        {
          generate_visuals: generateVisuals,
          mode: generateVisuals ? "full" : "fast",
          selected_analyses: selectedAnalyses,
          reference_lr_enabled: true,
          reference_population: referencePayload,
          meta_classifier: metaClassifier,
          use_augmented_reference: useAugmentedReference,
          use_latent_typicality: useLatentTypicality,
        },
        {
          maxWaitMs: useLatentTypicality ? Number.POSITIVE_INFINITY : 15 * 60 * 1000,
          onArtifactsLoaded: async (jobId) => {
            const [
              inputImg,
              inputFft,
              nlmResidue,
              medianResidue,
              nlmFft,
              medianFft,
              lrTippett,
              lrDistribution,
              lrIdentity,
            ] = await Promise.all([
              fetchImage(jobId, "input_image.png"),
              fetchImage(jobId, "input_fft.png"),
              generateVisuals ? fetchImage(jobId, "nlm_residue.png") : Promise.resolve(null),
              generateVisuals ? fetchImage(jobId, "median_residue.png") : Promise.resolve(null),
              generateVisuals ? fetchImage(jobId, "nlm_fft.png") : Promise.resolve(null),
              generateVisuals ? fetchImage(jobId, "median_fft.png") : Promise.resolve(null),
              fetchImage(jobId, "lr_reference_tippett.png"),
              fetchImage(jobId, "lr_reference_distribution.png"),
              fetchImage(jobId, "lr_reference_identity.png"),
            ]);
            if (inputImg) {
              revokeBlobs();
              setOriginalUrl(trackBlob(inputImg));
            }
            setArtifactUrl(setInputFftUrl, inputFft);
            setArtifactUrl(setNlmResidueUrl, nlmResidue);
            setArtifactUrl(setMedianResidueUrl, medianResidue);
            setArtifactUrl(setNlmFftUrl, nlmFft);
            setArtifactUrl(setMedianFftUrl, medianFft);
            setArtifactUrl(setReferenceLrTippettUrl, lrTippett);
            setArtifactUrl(setReferenceLrDistributionUrl, lrDistribution);
            setArtifactUrl(setReferenceLrIdentityUrl, lrIdentity);
          },
        }
      );
    } catch {
      /* hook */
    }
  }

  if (!caseId) return null;

  const individualRows = (result?.individual_results as ResultRow[]) || [];
  const referenceLr = (result?.reference_lr as ReferenceLrResult | undefined) || null;

  if (runtimeOk === false) {
    return (
      <AnalysisPageShell
        caseId={caseId}
        title="Detecção de Imagens Sintéticas"
        subtitle="Detecção de imagens sintéticas indisponivel neste servidor."
        embedded={embedded}
      >
        <AnalysisPanel title="Indisponivel">
          <MessageBox type="err" text={runtimeReason || "Detecção de imagens sintéticas indisponivel neste servidor."} />
        </AnalysisPanel>
      </AnalysisPageShell>
    );
  }

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="Detecção de Imagens Sintéticas"
      subtitle=""
      embedded={embedded}
    >
      {showEvidencePicker && (
        <AnalysisPanel title="Evidencia">
          <ImageEvidenceSelector
            caseId={caseId}
            selectedId={evidenceId}
            selectionSource={selectionSource}
            onSelect={onSelectEvidence}
          />
        </AnalysisPanel>
      )}

      <AnalysisPanel title="Parametros">
        <div style={{ marginBottom: "1rem" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "0.75rem",
              marginBottom: "0.6rem",
            }}
          >
            <div>
              <h4 style={{ margin: 0, fontSize: "0.9rem", color: "#374151" }}>
                Análises a executar
              </h4>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.78rem", color: "#6b7280" }}>
                Marque apenas os modelos que deseja rodar nesta evidencia.
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.4rem", flexShrink: 0 }}>
              <button
                type="button"
                onClick={() => setSelectedAnalyses([...DEFAULT_SYNTHETIC_ANALYSES])}
                disabled={running}
                style={smallButtonStyle}
              >
                Marcar todas
              </button>
              <button
                type="button"
                onClick={() => setSelectedAnalyses([])}
                disabled={running}
                style={smallButtonStyle}
              >
                Limpar
              </button>
            </div>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "0.45rem",
            }}
          >
            {SYNTHETIC_ANALYSIS_OPTIONS.map((option) => (
              <label
                key={option.id}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.5rem",
                  border: "1px solid #e5e7eb",
                  borderRadius: 6,
                  padding: "0.55rem 0.65rem",
                  background: selectedAnalyses.includes(option.id) ? "#f8fafc" : "#fff",
                  fontSize: "0.83rem",
                  color: "#374151",
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedAnalyses.includes(option.id)}
                  disabled={running}
                  onChange={(e) => toggleAnalysis(option.id, e.target.checked)}
                  style={{ marginTop: "0.15rem" }}
                />
                <DetectorOptionInfo option={option} />
              </label>
            ))}
          </div>
          {selectedAnalyses.length === 0 && (
            <p style={{ margin: "0.55rem 0 0", fontSize: "0.78rem", color: "#b91c1c" }}>
              Selecione pelo menos uma analise para executar.
            </p>
          )}
        </div>
        <ReferencePopulationSelector
          catalog={referenceCatalog}
          loading={referenceCatalogLoading}
          error={referenceCatalogError}
          entries={referenceEntries}
          onChange={setReferenceEntries}
          disabled={running}
          enableSplitRoles={false}
        />
        {referenceSelectionCount === 0 && (
          <p style={{ margin: "0.55rem 0 0", fontSize: "0.78rem", color: "#b91c1c" }}>
            Selecione pelo menos um gerador/subgrupo para a população de referência.
          </p>
        )}
        <div style={{ marginTop: "0.75rem" }}>
          <MetaClassifierSelect value={metaClassifier} disabled={running} onChange={setMetaClassifier} />
          <label
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "0.5rem",
              marginTop: "0.55rem",
              fontSize: "0.85rem",
              color: "#374151",
            }}
          >
            <input
              type="checkbox"
              checked={useAugmentedReference}
              disabled={running}
              onChange={(e) => setUseAugmentedReference(e.target.checked)}
              style={{ marginTop: "0.15rem" }}
            />
            <span>
              Usar população de referência aumentada
              <span style={{ display: "block", fontSize: "0.74rem", color: "#6b7280", marginTop: "0.15rem" }}>
                Inclui variações JPEG 85, WebP 80, crop+upscale e resize 50% na calibração LR.
                Aplica-se às bases com score matrix aumentado (GenImage, Defactify, AIGCDetect,
                OpenSDI, AIGIBench, Synthbuster e BFree extended).
              </span>
            </span>
          </label>
          <label
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "0.5rem",
              marginTop: "0.55rem",
              fontSize: "0.85rem",
              color: "#374151",
            }}
          >
            <input
              type="checkbox"
              checked={useLatentTypicality}
              disabled={running}
              onChange={(e) => setUseLatentTypicality(e.target.checked)}
              style={{ marginTop: "0.15rem" }}
              aria-label="Tipicidade latente (k-NN)"
            />
            <span>
              Usar tipicidade latente (k-NN sobre embeddings)
              <span style={{ display: "block", fontSize: "0.74rem", color: "#6b7280", marginTop: "0.15rem" }}>
                Estende o vetor de features do meta-classificador com medidas de tipicidade
                extraídas das embeddings de última camada dos detectores.
                Requer matriz de representações (scores + embeddings) gerada offline.
              </span>
            </span>
          </label>
        </div>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            marginTop: "0.75rem",
            fontSize: "0.88rem",
          }}
        >
          <input
            type="checkbox"
            checked={generateVisuals}
            onChange={(e) => setGenerateVisuals(e.target.checked)}
          />
          Gerar Visualizacoes Forenses (residuos NLM e mediana)
        </label>
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={
              !evidenceId ||
              runtimeOk !== true ||
              selectedAnalyses.length === 0 ||
              referenceSelectionCount === 0
            }
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            inferenceDevice={activeInferenceDevice}
            label="Analisar Imagem"
          />
          <DetectionProgressChecklist
            progress={progress}
            running={running}
            inferenceDevice={activeInferenceDevice}
            selectedAnalyses={selectedAnalyses}
            generateVisuals={generateVisuals}
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {(evidenceId || result) && (
        <AnalysisPanel title="Resultado">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(450px, 1.5fr) minmax(280px, 2fr)",
              gap: "1rem",
              alignItems: "start",
            }}
          >
            <div>
              <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#6b7280" }}>
                Imagem de Entrada e FFT
              </h4>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(225px, 1fr))",
                  gap: "0.75rem",
                }}
              >
                {originalUrl ? (
                  <ForensicImage src={originalUrl} label="Imagem de Entrada" imageStyle={inputPreviewImgStyle} />
                ) : (
                  <figure style={{ margin: 0 }}>
                    <div style={{ ...placeholderStyle, ...inputPreviewPlaceholderStyle }}>
                      {previewLoading ? "Carregando imagem…" : "Aguardando imagem de entrada"}
                    </div>
                    <figcaption style={capStyle}>Imagem de Entrada</figcaption>
                  </figure>
                )}
                <ForensicImage
                  src={inputFftUrl}
                  label="FFT(log) da imagem de entrada"
                  imageStyle={inputPreviewImgStyle}
                  placeholderStyle={inputPreviewPlaceholderStyle}
                />
              </div>
            </div>
            <ResultsTable rows={individualRows} />
          </div>

          <ReferenceLrPanel
            lr={referenceLr}
            tippettUrl={referenceLrTippettUrl}
            distributionUrl={referenceLrDistributionUrl}
            identityUrl={referenceLrIdentityUrl}
          />

          <details open style={{ marginTop: "1.5rem" }}>
            <summary
              style={{
                cursor: "pointer",
                fontWeight: 600,
                fontSize: "0.95rem",
                color: "#1a1a2e",
                marginBottom: "1rem",
              }}
            >
              Residuos de Denoising
            </summary>

            <h4 style={{ fontSize: "0.9rem", margin: "0 0 0.75rem", color: "#374151" }}>
              Residuos de ruido e FFT
            </h4>
            <div style={{ width: "100%" }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                  gap: "0.5rem",
                  width: "100%",
                }}
              >
                <ForensicImage
                  src={nlmResidueUrl}
                  label="Residuo NLM"
                  imageStyle={forensicThumbImgStyle}
                  placeholderStyle={forensicThumbPlaceholderStyle}
                  captionStyle={forensicThumbCapStyle}
                />
                <ForensicImage
                  src={nlmFftUrl}
                  label="FFT(log) NLM"
                  imageStyle={forensicThumbImgStyle}
                  placeholderStyle={forensicThumbPlaceholderStyle}
                  captionStyle={forensicThumbCapStyle}
                />
                <ForensicImage
                  src={medianResidueUrl}
                  label="Residuo Mediana"
                  imageStyle={forensicThumbImgStyle}
                  placeholderStyle={forensicThumbPlaceholderStyle}
                  captionStyle={forensicThumbCapStyle}
                />
                <ForensicImage
                  src={medianFftUrl}
                  label="FFT(log) Mediana"
                  imageStyle={forensicThumbImgStyle}
                  placeholderStyle={forensicThumbPlaceholderStyle}
                  captionStyle={forensicThumbCapStyle}
                />
              </div>
            </div>
          </details>

          {!generateVisuals && result && (
            <p style={{ marginTop: "1rem", fontSize: "0.82rem", color: "#6b7280" }}>
              Visualizacoes forenses nao foram geradas. Marque a opcao acima e execute novamente.
            </p>
          )}

          {currentJobId && result && (
            <div style={{ marginTop: "1.5rem", borderTop: "1px solid #e5e7eb", paddingTop: "1rem" }}>
              <h4 style={{ margin: "0 0 0.75rem", fontSize: "0.9rem", color: "#374151" }}>
                Salvar em derivados
              </h4>
              <p style={{ margin: "0 0 0.75rem", fontSize: "0.8rem", color: "#6b7280" }}>
                O relatorio de escores (TXT) e o artefato principal para reproducibilidade e cadeia de custodia.
                Imagens sao opcionais.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                <SaveButton
                  label="Escores dos modelos (TXT)"
                  filename="model_scores.txt"
                  saving={saving}
                  onSave={handleSave}
                  primary
                />
                <SaveButton
                  label="Imagem de entrada"
                  filename="input_image.png"
                  saving={saving}
                  onSave={handleSave}
                />
                <SaveButton
                  label="FFT entrada"
                  filename="input_fft.png"
                  saving={saving}
                  onSave={handleSave}
                />
                {generateVisuals && (
                  <>
                    <SaveButton
                      label="Residuo NLM"
                      filename="nlm_residue.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="FFT NLM"
                      filename="nlm_fft.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="Residuo mediana"
                      filename="median_residue.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="FFT mediana"
                      filename="median_fft.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                  </>
                )}
              </div>

              {referenceLr && referenceLr.success !== false && (
                <div style={{ marginTop: "1rem" }}>
                  <p style={{ margin: "0 0 0.5rem", fontSize: "0.8rem", color: "#6b7280" }}>
                    Artefatos da calibracao LR (populacao de referencia, CLLR, EER, graficos):
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    <SaveButton
                      label="Resumo LR (TXT)"
                      filename="lr_reference_summary.txt"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="Relatorio LR (JSON)"
                      filename="lr_reference_report.json"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="Tippett plot"
                      filename="lr_reference_tippett.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="Distribuicao LR"
                      filename="lr_reference_distribution.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                    <SaveButton
                      label="Funcao identidade"
                      filename="lr_reference_identity.png"
                      saving={saving}
                      onSave={handleSave}
                    />
                  </div>
                </div>
              )}

              {saveMessage && (
                <div style={{ marginTop: "0.75rem" }}>
                  <MessageBox type={saveMessage.type} text={saveMessage.text} />
                </div>
              )}
            </div>
          )}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}
