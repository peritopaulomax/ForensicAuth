import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import {
  MessageBox,
  ProcessButton,
  formatInferenceDevice,
  parseDeviceFromProgress,
} from "@/components/AnalysisPageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import api from "@/services/api";
import {
  ForensicImage,
  MacroCategory,
  MetaClassifierSelect,
  capStyle,
  placeholderStyle,
  ReferenceLrFeatureWeightsPanel,
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
import {
  SYNTHETIC_LR_POPULATION_DISCLAIMER_BODY,
  SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY,
  SYNTHETIC_LR_POPULATION_DISCLAIMER_TITLE,
} from "@/lib/syntheticLrPopulationDisclaimer";

/** Product default: Difusão Transformer + CNN moderna + AIGI Bench Social (role both). */
const DEFAULT_SYNTHETIC_REFERENCE: ReferencePopulationEntry[] = itemsToEntries(
  [
    { base_group: "AIGIBench_no_SocialRF", subgroup: "SD3" },
    { base_group: "AIGIBench_no_SocialRF", subgroup: "FLUX1-dev" },
    { base_group: "OpenSDI", subgroup: "sd3" },
    { base_group: "OpenSDI", subgroup: "flux" },
    { base_group: "Defactify", subgroup: "SD3" },
    { base_group: "BFree_extended_synthbuster", subgroup: "FLUX" },
    { base_group: "AIGIBench_SocialRF", subgroup: "SocialRF" },
    { base_group: "MLLMGenerated", subgroup: "gpt_image2" },
    { base_group: "MLLMGenerated", subgroup: "nano_banana2" },
    { base_group: "MeiGenTrending", subgroup: "gptimage" },
    { base_group: "MeiGenTrending", subgroup: "nanobanana" },
  ],
  "both"
);

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
  { id: "corvi2023", label: "DMImageDetection (Corvi2023)" },
  { id: "safe", label: "SAFE (KDD 2025)" },
];

interface DetectorCatalogRow {
  id: SyntheticAnalysisId;
  label: string;
  description?: string;
  paper?: string;
  paper_title?: string;
  paper_url?: string;
  repo_url?: string;
  available?: boolean;
  unavailable_reason?: string | null;
}

const DEFAULT_SYNTHETIC_ANALYSES: SyntheticAnalysisId[] = SYNTHETIC_ANALYSIS_OPTIONS.map(
  (option) => option.id
);

const INDIVIDUAL_HEADERS = [
  "Modelo",
  "Logit AI",
  "Logit Real",
  "Δ log10 (real−AI)",
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
            <li
              key={stage.min}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.45rem",
                color,
                fontWeight: weight,
              }}
            >
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
              const cells = [
                ...row,
                ...Array(Math.max(0, INDIVIDUAL_HEADERS.length - row.length)).fill("—"),
              ];
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

function DetectorOptionInfo({ detector }: { detector: DetectorCatalogRow }) {
  const paperUrl = detector.paper_url || (detector.paper?.startsWith("http") ? detector.paper : undefined);
  const paperTitle = detector.paper_title || detector.paper;

  return (
    <span>
      <strong style={{ display: "block", color: "#1f2937" }}>{detector.label}</strong>
      {detector.description && (
        <span
          style={{
            display: "block",
            marginTop: "0.25rem",
            fontSize: "0.74rem",
            color: "#4b5563",
            lineHeight: 1.35,
          }}
        >
          {detector.description}
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
        {paperUrl && (
          <a
            href={paperUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#1d4ed8", textDecoration: "none" }}
            onClick={(e) => e.stopPropagation()}
          >
            📄 {paperTitle || "Paper"}
          </a>
        )}
        {detector.repo_url && (
          <a
            href={detector.repo_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#0369a1", textDecoration: "none" }}
            onClick={(e) => e.stopPropagation()}
          >
            🔗 {detector.repo_url.includes("huggingface.co") ? "HuggingFace" : "Repositório"}
          </a>
        )}
      </span>
      {detector.available === false && detector.unavailable_reason && (
        <span style={{ display: "block", color: "#b45309", fontSize: "0.75rem", marginTop: "0.25rem" }}>
          {detector.unavailable_reason}
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
  const [detectorCatalog, setDetectorCatalog] = useState<DetectorCatalogRow[]>([]);
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
  const [referenceEntries, setReferenceEntries] =
    useState<ReferencePopulationEntry[]>(DEFAULT_SYNTHETIC_REFERENCE);
  const [metaClassifier, setMetaClassifier] = useState<string>("logistic");
  const [useAugmentedReference, setUseAugmentedReference] = useState(false);
  const [useLatentTypicality, setUseLatentTypicality] = useState(false);

  const [savingFile, setSavingFile] = useState<string | null>(null);
  const { saveMessage, save, clearMessage } = useDerivativeSave();

  const [liveInferenceDevice, setLiveInferenceDevice] = useState<string | null>(null);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  const { status: runtimeStatus } = useTechniqueRuntime("synthetic_image_detection");
  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

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
      .get<DetectorCatalogRow[]>("/analysis/synthetic-image-detectors")
      .then((res) => {
        setDetectorCatalog(res.data);
      })
      .catch(() => {
        setDetectorCatalog(SYNTHETIC_ANALYSIS_OPTIONS.map((o) => ({ ...o, available: true })));
      });

    api
      .get<{
        categories: MacroCategory[];
        default_reference_items?: { base_group: string; subgroup: string }[];
      }>("/analysis/synthetic-reference-catalog")
      .then((res) => {
        setReferenceCatalog(res.data.categories);
        if (res.data.default_reference_items?.length) {
          setReferenceEntries(itemsToEntries(res.data.default_reference_items, "both"));
        }
        setReferenceCatalogLoading(false);
      })
      .catch((err: unknown) => {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || String(err);
        setReferenceCatalogError(message);
        setReferenceCatalogLoading(false);
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
      clearMessage();
      void loadEvidencePreview(id);
    },
    [reset, revokeBlobs, loadEvidencePreview, clearMessage]
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

  const referenceCounts = referenceSelectionCounts(referenceEntries, true);
  const referencePayload = referencePopulationPayload(referenceEntries, true);
  const referenceSelectionValid = referenceCounts.fit > 0 && referenceCounts.test > 0;

  async function handleSave(filename: string, label: string) {
    if (!currentJobId) return;
    setSavingFile(filename);
    try {
      await save(currentJobId, filename, label);
    } finally {
      setSavingFile(null);
    }
  }

  async function process() {
    if (!evidenceId || !runtimeOk || selectedAnalyses.length === 0 || !referenceSelectionValid) {
      return;
    }
    clearVisuals();
    clearMessage();
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
    }
  }

  if (!caseId) return null;

  const individualRows = (result?.individual_results as ResultRow[]) || [];
  const referenceLr = (result?.reference_lr as ReferenceLrResult | undefined) || null;
  const detectorRows: DetectorCatalogRow[] = detectorCatalog.length
    ? detectorCatalog
    : SYNTHETIC_ANALYSIS_OPTIONS.map((o) => ({ ...o, available: true }));

  const parametersPanel = (
    <>
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
            <h4 style={{ margin: 0, fontSize: "0.9rem", color: "#374151" }}>Análises a executar</h4>
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
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: "0.45rem",
          }}
        >
          {detectorRows.map((detector) => (
            <label
              key={detector.id}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.5rem",
                border: "1px solid #e5e7eb",
                borderRadius: 6,
                padding: "0.55rem 0.65rem",
                background: selectedAnalyses.includes(detector.id) ? "#f8fafc" : "#fff",
                fontSize: "0.83rem",
                color: "#374151",
                opacity: detector.available === false ? 0.72 : 1,
              }}
            >
              <input
                type="checkbox"
                checked={selectedAnalyses.includes(detector.id)}
                disabled={running || detector.available === false}
                onChange={(e) => toggleAnalysis(detector.id, e.target.checked)}
                style={{ marginTop: "0.15rem" }}
              />
              <DetectorOptionInfo detector={detector} />
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
        enableSplitRoles
        defaultPresetItems={DEFAULT_SYNTHETIC_REFERENCE.map(({ base_group, subgroup }) => ({
          base_group,
          subgroup,
        }))}
        subgroupUnitLabel="subgrupos"
        hypothesisHint="Defina subgrupos para treino/calibração (splits 1–2) e para avaliação (split 3). LR positiva favorece H1 = real/autêntica."
        editDisclaimer={{
          title: SYNTHETIC_LR_POPULATION_DISCLAIMER_TITLE,
          body: SYNTHETIC_LR_POPULATION_DISCLAIMER_BODY,
          storageKey: SYNTHETIC_LR_POPULATION_DISCLAIMER_STORAGE_KEY,
        }}
      />
      {!referenceSelectionValid && (
        <p style={{ margin: "0.55rem 0 0", fontSize: "0.78rem", color: "#b91c1c" }}>
          Selecione pelo menos um subgrupo em treino/calibração e um em teste.
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
            !evidenceId || runtimeOk !== true || selectedAnalyses.length === 0 || !referenceSelectionValid
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
    </>
  );

  const resultPanel = (evidenceId || result) && (
    <>
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
              saving={savingFile}
              onSave={handleSave}
              primary
            />
            <SaveButton
              label="Imagem de entrada"
              filename="input_image.png"
              saving={savingFile}
              onSave={handleSave}
            />
            <SaveButton
              label="FFT entrada"
              filename="input_fft.png"
              saving={savingFile}
              onSave={handleSave}
            />
            {generateVisuals && (
              <>
                <SaveButton
                  label="Residuo NLM"
                  filename="nlm_residue.png"
                  saving={savingFile}
                  onSave={handleSave}
                />
                <SaveButton
                  label="FFT NLM"
                  filename="nlm_fft.png"
                  saving={savingFile}
                  onSave={handleSave}
                />
                <SaveButton
                  label="Residuo mediana"
                  filename="median_residue.png"
                  saving={savingFile}
                  onSave={handleSave}
                />
                <SaveButton
                  label="FFT mediana"
                  filename="median_fft.png"
                  saving={savingFile}
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
                  saving={savingFile}
                  onSave={handleSave}
                />
                <SaveButton
                  label="Relatorio LR (JSON)"
                  filename="lr_reference_report.json"
                  saving={savingFile}
                  onSave={handleSave}
                />
                <SaveButton
                  label="Tippett plot"
                  filename="lr_reference_tippett.png"
                  saving={savingFile}
                  onSave={handleSave}
                />
                <SaveButton
                  label="Distribuicao LR"
                  filename="lr_reference_distribution.png"
                  saving={savingFile}
                  onSave={handleSave}
                />
                <SaveButton
                  label="Funcao identidade"
                  filename="lr_reference_identity.png"
                  saving={savingFile}
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

      <ReferenceLrFeatureWeightsPanel lr={referenceLr} />
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="synthetic_image_detection"
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
