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

type GeneratorCatalog = { id: string; label: string; deploy_year: number | null };
type BaseCatalog = {
  id: string;
  label: string;
  description?: string;
  paper_title?: string | null;
  paper_url?: string | null;
  generators: GeneratorCatalog[];
};
type MacroCategory = {
  id: string;
  label: string;
  year_range: string;
  description: string;
  bases: BaseCatalog[];
};

type ReferencePopulationItem = { base_group: string; subgroup: string };
type ReferenceLrResult = {
  success?: boolean;
  error?: string;
  hypothesis_positive?: string;
  hypothesis_negative?: string;
  selected_count?: number;
  sample_rows?: number;
  test_metrics?: {
    rows?: number;
    real_rows?: number;
    fake_rows?: number;
    cllr?: number;
    min_cllr?: number;
    auc?: number;
    eer?: number;
    wrong_extreme_lr_count?: number;
  };
  identity_mse?: number;
  bigauss?: {
    eer?: number;
    sigma?: number;
    mu_fake?: number;
    mu_real?: number;
  };
  questioned?: {
    log10_lr?: number;
    lr?: number;
    logreg_z?: number;
    cdf_p?: number;
  };
  note?: string;
  meta_classifier?: string;
  meta_classifier_label?: string;
  augmented_reference?: boolean;
  sample_multiplier?: number;
};

function flattenCatalog(categories: MacroCategory[]): ReferencePopulationItem[] {
  return categories.flatMap((category) =>
    category.bases.flatMap((base) => base.generators.map((generator) => ({ base_group: base.id, subgroup: generator.id })))
  );
}

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

function ReferencePopulationSelector({
  catalog,
  loading,
  error,
  selectedKeys,
  disabled,
  onToggleMacro,
  onToggleBase,
  onToggleItem,
  onSelectAll,
  onClear,
}: {
  catalog: MacroCategory[];
  loading: boolean;
  error: string | null;
  selectedKeys: Set<string>;
  disabled: boolean;
  onToggleMacro: (macroId: string, checked: boolean) => void;
  onToggleBase: (baseId: string, checked: boolean) => void;
  onToggleItem: (item: ReferencePopulationItem, checked: boolean) => void;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  const totalSelected = selectedKeys.size;
  const totalGenerators = catalog.reduce(
    (sum, category) =>
      sum + category.bases.reduce((baseSum, base) => baseSum + base.generators.length, 0),
    0
  );

  if (loading) {
    return (
      <p style={{ marginTop: "1rem", fontSize: "0.85rem", color: "#6b7280" }}>
        Carregando catálogo de população de referência…
      </p>
    );
  }

  if (error) {
    return (
      <p style={{ marginTop: "1rem", fontSize: "0.85rem", color: "#b91c1c" }}>
        Erro ao carregar catálogo: {error}
      </p>
    );
  }

  return (
    <details style={{ marginTop: "1rem", borderTop: "1px solid #e5e7eb", paddingTop: "1rem" }}>
      <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: "0.95rem", color: "#1a1a2e" }}>
        População de referência LR{" "}
        <span style={{ color: "#6b7280", fontWeight: 400, fontSize: "0.8rem" }}>
          ({totalSelected}/{totalGenerators} geradores selecionados)
        </span>
      </summary>
      <div style={{ marginTop: "0.75rem" }}>
        <p style={{ margin: "0 0 0.6rem", fontSize: "0.78rem", color: "#6b7280" }}>
          LR positiva favorece H1 = real/autêntica. Selecione macro-categorias, bases e modelos geradores
          usados na calibração.
        </p>
        <div style={{ display: "flex", gap: "0.4rem", marginBottom: "0.75rem" }}>
          <button type="button" onClick={onSelectAll} disabled={disabled} style={smallButtonStyle}>
            Marcar todas
          </button>
          <button type="button" onClick={onClear} disabled={disabled} style={smallButtonStyle}>
            Limpar
          </button>
        </div>
        <div style={{ display: "grid", gap: "0.55rem" }}>
          {catalog.map((category) => {
            const categoryKeys = category.bases.flatMap((base) =>
              base.generators.map((generator) => `${base.id}/${generator.id}`)
            );
            const categorySelectedCount = categoryKeys.filter((key) => selectedKeys.has(key)).length;
            const allCategorySelected = categorySelectedCount === categoryKeys.length && categoryKeys.length > 0;
            const partiallyCategorySelected = categorySelectedCount > 0 && !allCategorySelected;

            return (
              <details key={category.id} style={referenceGroupStyle}>
                <summary style={referenceSummaryStyle}>
                  <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <input
                      type="checkbox"
                      checked={allCategorySelected}
                      ref={(el) => {
                        if (el) el.indeterminate = partiallyCategorySelected;
                      }}
                      disabled={disabled}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => onToggleMacro(category.id, event.target.checked)}
                    />
                    <strong>
                      {category.label}{" "}
                      <span style={{ color: "#6b7280", fontWeight: 400, fontSize: "0.78rem" }}>
                        ({category.year_range})
                      </span>
                    </strong>
                  </span>
                  <span style={{ color: "#6b7280", fontSize: "0.75rem" }}>
                    {categorySelectedCount}/{categoryKeys.length} geradores
                  </span>
                </summary>
                <div style={{ marginTop: "0.45rem", fontSize: "0.76rem", color: "#6b7280", lineHeight: 1.4 }}>
                  {category.description}
                </div>
                <div style={{ display: "grid", gap: "0.35rem", marginTop: "0.55rem" }}>
                  {category.bases.map((base) => {
                    const baseKeys = base.generators.map((generator) => `${base.id}/${generator.id}`);
                    const baseSelectedCount = baseKeys.filter((key) => selectedKeys.has(key)).length;
                    const allBaseSelected = baseSelectedCount === baseKeys.length && baseKeys.length > 0;
                    const partiallyBaseSelected = baseSelectedCount > 0 && !allBaseSelected;

                    return (
                      <details key={base.id} style={{ ...referenceGroupStyle, background: "#fafafa" }}>
                        <summary style={{ ...referenceSummaryStyle, fontSize: "0.82rem", alignItems: "flex-start" }}>
                          <span style={{ display: "flex", alignItems: "flex-start", gap: "0.45rem", flex: 1, minWidth: 0 }}>
                            <input
                              type="checkbox"
                              checked={allBaseSelected}
                              ref={(el) => {
                                if (el) el.indeterminate = partiallyBaseSelected;
                              }}
                              disabled={disabled}
                              onClick={(event) => event.stopPropagation()}
                              onChange={(event) => onToggleBase(base.id, event.target.checked)}
                              style={{ marginTop: "0.15rem", flexShrink: 0 }}
                            />
                            <span style={{ display: "flex", flexDirection: "column", gap: "0.2rem", minWidth: 0 }}>
                              <strong>{base.label}</strong>
                              {(base.description || base.paper_url) && (
                                <span
                                  style={{
                                    fontSize: "0.72rem",
                                    color: "#6b7280",
                                    fontWeight: 400,
                                    lineHeight: 1.4,
                                  }}
                                >
                                  {base.description}
                                  {base.paper_url && (
                                    <>
                                      {base.description ? " " : ""}
                                      <a
                                        href={base.paper_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={(event) => event.stopPropagation()}
                                        style={{ color: "#1d4ed8", textDecoration: "none" }}
                                      >
                                        {base.paper_title || "Paper"}
                                      </a>
                                    </>
                                  )}
                                </span>
                              )}
                            </span>
                          </span>
                          <span style={{ color: "#6b7280", fontSize: "0.74rem", flexShrink: 0, marginLeft: "0.5rem" }}>
                            {baseSelectedCount}/{baseKeys.length} geradores
                          </span>
                        </summary>
                        <div style={referenceGridStyle}>
                          {base.generators.map((generator) => {
                            const item = { base_group: base.id, subgroup: generator.id };
                            const key = `${base.id}/${generator.id}`;
                            return (
                              <label key={key} style={referenceItemStyle}>
                                <input
                                  type="checkbox"
                                  checked={selectedKeys.has(key)}
                                  disabled={disabled}
                                  onChange={(event) => onToggleItem(item, event.target.checked)}
                                />
                                <span>{generator.label}</span>
                                {generator.deploy_year && (
                                  <span style={{ marginLeft: "auto", color: "#9ca3af", fontSize: "0.72rem" }}>
                                    {generator.deploy_year}
                                  </span>
                                )}
                              </label>
                            );
                          })}
                        </div>
                      </details>
                    );
                  })}
                </div>
              </details>
            );
          })}
        </div>
      </div>
    </details>
  );
}

function formatMetric(value: unknown, digits = 4): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function ReferenceLrPanel({
  lr,
  tippettUrl,
  distributionUrl,
  identityUrl,
}: {
  lr: ReferenceLrResult | null;
  tippettUrl: string | null;
  distributionUrl: string | null;
  identityUrl: string | null;
}) {
  if (!lr) return null;
  if (lr.success === false) {
    return (
      <MessageBox
        type="err"
        text={`LR por população de referência não calculada: ${lr.error || "erro desconhecido"}`}
      />
    );
  }
  const q = lr.questioned || {};
  const metrics = lr.test_metrics || {};
  return (
    <div style={{ marginTop: "1.5rem", borderTop: "1px solid #e5e7eb", paddingTop: "1rem" }}>
      <h4 style={{ margin: "0 0 0.25rem", fontSize: "0.95rem", color: "#1a1a2e" }}>
        LR calibrada por população de referência
      </h4>
      {lr.augmented_reference && (
        <p
          style={{
            margin: "0 0 0.75rem",
            fontSize: "0.78rem",
            color: "#1d4ed8",
            fontWeight: 500,
          }}
        >
          População aumentada ativa (multiplicador {lr.sample_multiplier ?? "—"}×) — inclui variações
          JPEG 85, WebP 80, crop+upscale e resize 50%.
        </p>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "0.6rem" }}>
        <MetricCard label="log10(LR real)" value={formatMetric(q.log10_lr)} />
        <MetricCard label="LR real" value={formatMetric(q.lr, 3)} />
        <MetricCard label="CLLR teste" value={formatMetric(metrics.cllr)} />
        <MetricCard label="minCLLR teste" value={formatMetric(metrics.min_cllr)} />
        <MetricCard label="EER teste" value={formatMetric(metrics.eer)} />
      </div>
      <p style={{ margin: "0 0 0.75rem", fontSize: "0.78rem", color: "#6b7280" }}>
        População usada: {lr.selected_count ?? "—"} subgrupos, {lr.sample_rows ?? "—"} imagens.{" "}
        Meta-classificador: {lr.meta_classifier_label || lr.meta_classifier || "—"}.{" "}
        {lr.note || "LR > 1 favorece real/autêntica."}
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "0.75rem" }}>
        <ForensicImage src={tippettUrl} label="Tippett plot" />
        <ForensicImage src={distributionUrl} label="Distribuição das LRs" />
        <ForensicImage src={identityUrl} label="Função identidade por KDE" />
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "0.6rem", background: "#f9fafb" }}>
      <div style={{ fontSize: "0.72rem", color: "#6b7280", marginBottom: "0.2rem" }}>{label}</div>
      <div style={{ fontSize: "1rem", color: "#111827", fontWeight: 700 }}>{value}</div>
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

function ForensicImage({
  src,
  label,
  imageStyle,
  placeholderStyle: placeholderOverride,
  captionStyle,
}: {
  src: string | null;
  label: string;
  imageStyle?: React.CSSProperties;
  placeholderStyle?: React.CSSProperties;
  captionStyle?: React.CSSProperties;
}) {
  const cap = captionStyle ?? capStyle;
  if (!src) {
    return (
      <figure style={{ margin: 0, width: "100%" }}>
        <div style={{ ...placeholderStyle, ...placeholderOverride }}>—</div>
        <figcaption style={cap}>{label}</figcaption>
      </figure>
    );
  }
  return (
    <figure style={{ margin: 0, width: "100%" }}>
      <img src={src} alt={label} style={{ ...imgStyle, ...imageStyle }} />
      <figcaption style={cap}>{label}</figcaption>
    </figure>
  );
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
  const [referencePopulation, setReferencePopulation] = useState<ReferencePopulationItem[]>([]);
  const [metaClassifier, setMetaClassifier] = useState<string>("logistic");
  const [useAugmentedReference, setUseAugmentedReference] = useState(false);

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
        setReferencePopulation(flattenCatalog(categories));
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

  const referenceKey = useCallback((item: ReferencePopulationItem) => `${item.base_group}/${item.subgroup}`, []);

  const selectedReferenceKeys = new Set(referencePopulation.map(referenceKey));
  const referenceSelectionCount = referencePopulation.length;

  const setReferenceMacro = useCallback(
    (macroId: string, checked: boolean) => {
      const category = referenceCatalog.find((item) => item.id === macroId);
      if (!category) return;
      const macroItems = category.bases.flatMap((base) =>
        base.generators.map((generator) => ({ base_group: base.id, subgroup: generator.id }))
      );
      setReferencePopulation((current) => {
        const macroKeys = new Set(macroItems.map((item) => `${item.base_group}/${item.subgroup}`));
        const rest = current.filter((item) => !macroKeys.has(`${item.base_group}/${item.subgroup}`));
        return checked ? [...rest, ...macroItems] : rest;
      });
    },
    [referenceCatalog]
  );

  const setReferenceBase = useCallback(
    (baseId: string, checked: boolean) => {
      const baseItems: ReferencePopulationItem[] = [];
      referenceCatalog.forEach((category) => {
        const base = category.bases.find((b) => b.id === baseId);
        if (base) {
          base.generators.forEach((generator) => {
            baseItems.push({ base_group: base.id, subgroup: generator.id });
          });
        }
      });
      setReferencePopulation((current) => {
        const baseKeys = new Set(baseItems.map((item) => `${item.base_group}/${item.subgroup}`));
        const rest = current.filter((item) => !baseKeys.has(`${item.base_group}/${item.subgroup}`));
        return checked ? [...rest, ...baseItems] : rest;
      });
    },
    [referenceCatalog]
  );

  const toggleReferenceItem = useCallback((item: ReferencePopulationItem, checked: boolean) => {
    const key = `${item.base_group}/${item.subgroup}`;
    setReferencePopulation((current) => {
      const exists = current.some((candidate) => `${candidate.base_group}/${candidate.subgroup}` === key);
      if (checked) return exists ? current : [...current, item];
      return current.filter((candidate) => `${candidate.base_group}/${candidate.subgroup}` !== key);
    });
  }, []);

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
          reference_population: { items: referencePopulation },
          meta_classifier: metaClassifier,
          use_augmented_reference: useAugmentedReference,
        },
        {
          maxWaitMs: 15 * 60 * 1000,
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
          selectedKeys={selectedReferenceKeys}
          disabled={running}
          onToggleMacro={setReferenceMacro}
          onToggleBase={setReferenceBase}
          onToggleItem={toggleReferenceItem}
          onSelectAll={() => setReferencePopulation(flattenCatalog(referenceCatalog))}
          onClear={() => setReferencePopulation([])}
        />
        {referenceSelectionCount === 0 && (
          <p style={{ margin: "0.55rem 0 0", fontSize: "0.78rem", color: "#b91c1c" }}>
            Selecione pelo menos um gerador/subgrupo para a população de referência.
          </p>
        )}
        <div style={{ marginTop: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.88rem" }}>
            <label htmlFor="meta-classifier" style={{ color: "#374151" }}>
              Meta-classificador LR:
            </label>
            <select
              id="meta-classifier"
              value={metaClassifier}
              disabled={running}
              onChange={(e) => setMetaClassifier(e.target.value)}
              style={{
                padding: "0.35rem 0.6rem",
                borderRadius: 6,
                border: "1px solid #d1d5db",
                background: "#fff",
                fontSize: "0.85rem",
                color: "#1f2937",
              }}
            >
              <option value="logistic">Regressao Logistica</option>
              <option value="logistic_poly2">Regressao Logistica (grau 2)</option>
              <option value="xgboost">XGBoost</option>
              <option value="gradient_boosting">Gradient Boosting</option>
              <option value="random_forest">Random Forest</option>
              <option value="extra_trees">Extra Trees</option>
              <option value="svm_rbf">SVM (RBF)</option>
              <option value="mlp">MLP (rede neural)</option>
              <option value="kde_naive_bayes">KDE Naive Bayes</option>
            </select>
          </div>
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

function SaveButton({
  label,
  filename,
  saving,
  onSave,
  primary,
}: {
  label: string;
  filename: string;
  saving: string | null;
  onSave: (filename: string, label: string) => void;
  primary?: boolean;
}) {
  const busy = saving === filename;
  return (
    <button
      type="button"
      disabled={!!saving}
      onClick={() => onSave(filename, label)}
      style={{
        padding: "0.45rem 0.85rem",
        fontSize: "0.8rem",
        borderRadius: 6,
        border: primary ? "none" : "1px solid #d1d5db",
        background: primary ? "#1a1a2e" : "#fff",
        color: primary ? "#fff" : "#374151",
        cursor: saving ? "not-allowed" : "pointer",
        opacity: saving && !busy ? 0.6 : 1,
      }}
    >
      {busy ? "Salvando…" : label}
    </button>
  );
}

const imgStyle: React.CSSProperties = {
  width: "100%",
  borderRadius: 6,
  border: "1px solid #e5e7eb",
  display: "block",
};
const capStyle: React.CSSProperties = { fontSize: "0.78rem", color: "#6b7280", marginTop: 4, textAlign: "center" };
const smallButtonStyle: React.CSSProperties = {
  padding: "0.35rem 0.6rem",
  fontSize: "0.75rem",
  borderRadius: 6,
  border: "1px solid #d1d5db",
  background: "#fff",
  color: "#374151",
  cursor: "pointer",
};
const referenceGroupStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  background: "#fff",
  padding: "0.45rem 0.6rem",
};
const referenceSummaryStyle: React.CSSProperties = {
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "0.75rem",
  fontSize: "0.84rem",
  color: "#374151",
};
const referenceGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "0.35rem",
  marginTop: "0.55rem",
  paddingTop: "0.5rem",
  borderTop: "1px solid #f3f4f6",
};
const referenceItemStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.4rem",
  fontSize: "0.78rem",
  color: "#374151",
  padding: "0.25rem 0.35rem",
  borderRadius: 4,
  background: "#f9fafb",
};
const placeholderStyle: React.CSSProperties = {
  aspectRatio: "1",
  minHeight: 180,
  background: "#f3f4f6",
  borderRadius: 6,
  border: "1px solid #e5e7eb",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#9ca3af",
  fontSize: "0.8rem",
};
