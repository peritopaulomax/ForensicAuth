/**
 * Página genérica para técnicas scaffolded (template ensemble).
 * Detectores + individual_results + painel LR; modo calibrated adiciona
 * gestão de população, tipicidade, aug e meta-classificador
 * (payload reference_population no job).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueParameterForm, {
  initialParameterValues,
} from "@/components/TechniqueParameterForm";
import TechniqueArtifactViewer from "@/components/TechniqueArtifactViewer";
import {
  MetaClassifierSelect,
  ReferenceLrFeatureWeightsPanel,
  ReferenceLrPanel,
  ReferencePopulationSelector,
  itemsToEntries,
  referencePopulationPayload,
  referenceSelectionCounts,
  type MacroCategory,
  type ReferenceLrResult,
  type ReferencePopulationEntry,
  type ReferencePopulationItem,
} from "@/components/LrReferencePanels";
import { getTechniqueConfig } from "@/config/techniqueRegistry";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import api from "@/services/api";

export interface GenericEnsembleAnalysisProps {
  techniqueId?: string;
}

const DEFAULT_HEADERS = [
  "Modelo",
  "Score +",
  "Score −",
  "Razão (Log)",
  "Classificação",
  "Dispositivo",
];

const LR_FILES = [
  "lr_reference_tippett.png",
  "lr_reference_distribution.png",
  "lr_reference_identity.png",
] as const;

const btnSecondary: React.CSSProperties = {
  padding: "0.45rem 0.9rem",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
};

function ResultsTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  if (!rows.length) return null;
  return (
    <div style={{ overflowX: "auto", marginTop: "0.75rem" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.82rem" }}>
        <thead>
          <tr>
            {headers.map((h) => (
              <th
                key={h}
                style={{
                  textAlign: "left",
                  padding: "0.4rem 0.5rem",
                  borderBottom: "2px solid #e5e7eb",
                  color: "#374151",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {headers.map((_, j) => (
                <td
                  key={j}
                  style={{ padding: "0.4rem 0.5rem", borderBottom: "1px solid #f3f4f6", color: "#111827" }}
                >
                  {row[j] ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScoreBadge({ label, value }: { label: string; value: unknown }) {
  if (value == null || value === "") return null;
  const num = typeof value === "number" ? value : Number(value);
  const text = Number.isFinite(num) ? num.toFixed(4) : String(value);
  return (
    <div
      style={{
        padding: "0.65rem 0.9rem",
        borderRadius: 8,
        border: "1px solid #e5e7eb",
        background: "#f8fafc",
        minWidth: 120,
      }}
    >
      <div style={{ fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#0f172a" }}>{text}</div>
    </div>
  );
}

function flattenDefaultItems(macros: MacroCategory[]): ReferencePopulationItem[] {
  const out: ReferencePopulationItem[] = [];
  for (const cat of macros) {
    for (const base of cat.bases || []) {
      for (const gen of base.generators || []) {
        out.push({ base_group: base.id, subgroup: gen.id });
      }
    }
  }
  return out;
}

export default function GenericEnsembleAnalysis({
  techniqueId: techniqueIdProp,
}: GenericEnsembleAnalysisProps = {}) {
  const { caseId, techniqueId: techniqueIdParam } = useParams<{
    caseId: string;
    techniqueId?: string;
  }>();
  const techniqueId = techniqueIdProp || techniqueIdParam || "";
  const config = techniqueId ? getTechniqueConfig(techniqueId) : undefined;
  const ens = config?.ensembleConfig;
  const detectors = ens?.detectors ?? [];
  const headers = ens?.resultHeaders?.length ? ens.resultHeaders : DEFAULT_HEADERS;
  const selectedParam = ens?.selectedParam || "selected_analyses";
  const scoreDisplay = ens?.scoreDisplay;
  const lrCfg = ens?.referenceLr;
  const lrEnabled = lrCfg?.enabled !== false;
  const calibrated = lrEnabled && lrCfg?.mode === "calibrated";
  const enableSplitRoles = lrCfg?.enableSplitRoles !== false;

  const parameterDefs = config?.parameterDefs ?? [];
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [selected, setSelected] = useState<Set<string>>(() => new Set(detectors.map((d) => d.id)));
  const [tippettUrl, setTippettUrl] = useState<string | null>(null);
  const [distributionUrl, setDistributionUrl] = useState<string | null>(null);
  const [identityUrl, setIdentityUrl] = useState<string | null>(null);

  const [referenceCatalog, setReferenceCatalog] = useState<MacroCategory[]>(lrCfg?.macros ?? []);
  const [referenceCatalogLoading, setReferenceCatalogLoading] = useState(false);
  const [referenceCatalogError, setReferenceCatalogError] = useState<string | null>(null);
  const [referenceEntries, setReferenceEntries] = useState<ReferencePopulationEntry[]>([]);
  const [metaClassifier, setMetaClassifier] = useState(
    lrCfg?.defaultMetaClassifier === "xgboost" ? "xgboost" : "logistic"
  );
  const [useAugmentedReference, setUseAugmentedReference] = useState(false);
  const [useLatentTypicality, setUseLatentTypicality] = useState(false);

  useEffect(() => {
    setParams({
      ...(config?.defaultParameters ?? {}),
      ...initialParameterValues(config?.parameterDefs ?? []),
    });
    setSelected(new Set((config?.ensembleConfig?.detectors ?? []).map((d) => d.id)));
    setMetaClassifier(
      config?.ensembleConfig?.referenceLr?.defaultMetaClassifier === "xgboost"
        ? "xgboost"
        : "logistic"
    );
    setUseAugmentedReference(false);
    setUseLatentTypicality(false);
  }, [techniqueId, config]);

  useEffect(() => {
    if (!calibrated) return;
    const inline = lrCfg?.macros ?? [];
    const endpoint = lrCfg?.catalogEndpoint;
    const defaults = lrCfg?.defaultReferenceItems;

    if (!endpoint) {
      setReferenceCatalog(inline);
      setReferenceCatalogLoading(false);
      setReferenceCatalogError(inline.length ? null : "Catálogo vazio: defina macros ou catalog_endpoint.");
      const seed = defaults?.length ? defaults : flattenDefaultItems(inline);
      setReferenceEntries(itemsToEntries(seed, "both"));
      return;
    }

    setReferenceCatalogLoading(true);
    setReferenceCatalogError(null);
    api
      .get<{
        categories: MacroCategory[];
        default_reference_items?: ReferencePopulationItem[];
      }>(endpoint)
      .then((res) => {
        const cats = res.data.categories?.length ? res.data.categories : inline;
        setReferenceCatalog(cats);
        const seed =
          res.data.default_reference_items?.length
            ? res.data.default_reference_items
            : defaults?.length
              ? defaults
              : flattenDefaultItems(cats);
        setReferenceEntries(itemsToEntries(seed, "both"));
        setReferenceCatalogLoading(false);
      })
      .catch((err: unknown) => {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || String(err);
        setReferenceCatalog(inline);
        setReferenceCatalogError(inline.length ? `API falhou (${message}); usando macros inline.` : message);
        const seed = defaults?.length ? defaults : flattenDefaultItems(inline);
        setReferenceEntries(itemsToEntries(seed, "both"));
        setReferenceCatalogLoading(false);
      });
  }, [calibrated, techniqueId, lrCfg?.catalogEndpoint, lrCfg?.macros, lrCfg?.defaultReferenceItems]);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime(techniqueId || "unknown");
  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  const applyEvidence = useCallback(() => {
    reset();
    clearMessage();
    setTippettUrl((u) => {
      if (u?.startsWith("blob:")) URL.revokeObjectURL(u);
      return null;
    });
    setDistributionUrl((u) => {
      if (u?.startsWith("blob:")) URL.revokeObjectURL(u);
      return null;
    });
    setIdentityUrl((u) => {
      if (u?.startsWith("blob:")) URL.revokeObjectURL(u);
      return null;
    });
  }, [reset, clearMessage]);

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId || "", applyEvidence);

  const fetchBlobUrl = useCallback(async (jobId: string, filename: string, mime = "text/html") => {
    try {
      const response = await api.get(`/analysis/${jobId}/result/file?filename=${encodeURIComponent(filename)}`, {
        responseType: "blob",
      });
      return URL.createObjectURL(new Blob([response.data], { type: mime }));
    } catch {
      return null;
    }
  }, []);

  const manifest = useMemo(() => config?.artifactManifest ?? [], [config]);

  const referenceCounts = useMemo(
    () => referenceSelectionCounts(referenceEntries, enableSplitRoles),
    [referenceEntries, enableSplitRoles]
  );
  const referencePayload = useMemo(
    () => referencePopulationPayload(referenceEntries, enableSplitRoles),
    [referenceEntries, enableSplitRoles]
  );
  const referenceSelectionValid =
    !calibrated || (referenceCounts.fit > 0 && referenceCounts.test > 0);

  function toggleDetector(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function process() {
    if (!evidenceId || !techniqueId || runtimeOk === false) return;
    if (selected.size === 0) return;
    if (!referenceSelectionValid) return;
    clearMessage();
    applyEvidence();
    try {
      const payload: Record<string, unknown> = {
        ...params,
        [selectedParam]: [...selected],
      };
      if (calibrated) {
        payload.reference_lr_enabled = true;
        payload.reference_population = referencePayload;
        if (lrCfg?.domain) payload.reference_lr_domain = lrCfg.domain;
        if (lrCfg?.allowMetaClassifier !== false) payload.meta_classifier = metaClassifier;
        if (lrCfg?.allowAugmented) payload.use_augmented_reference = useAugmentedReference;
        if (lrCfg?.allowTypicality) payload.use_latent_typicality = useLatentTypicality;
      }
      const needsLongCalibration =
        calibrated && (useLatentTypicality || useAugmentedReference);
      await runAnalysis(evidenceId, techniqueId, payload, {
        maxWaitMs: needsLongCalibration ? Number.POSITIVE_INFINITY : undefined,
        onArtifactsLoaded: async (jobId) => {
          if (!lrEnabled) return;
          const [t, d, i] = await Promise.all([
            fetchImage(jobId, LR_FILES[0]),
            fetchImage(jobId, LR_FILES[1]),
            fetchImage(jobId, LR_FILES[2]),
          ]);
          setTippettUrl(t);
          setDistributionUrl(d);
          setIdentityUrl(i);
        },
      });
    } catch {
    }
  }

  if (!caseId) return null;
  if (!techniqueId || !config) {
    return <Navigate to={`/cases/${caseId}`} replace />;
  }
  if (config.template !== "ensemble") {
    return (
      <p style={{ padding: "1rem", color: "#991b1b" }}>
        GenericEnsembleAnalysis só cobre template ensemble (recebido: {config.template}).
      </p>
    );
  }
  if (!ens || detectors.length === 0) {
    return (
      <p style={{ padding: "1rem", color: "#991b1b" }}>
        ensembleConfig.detectors[] é obrigatório no manifesto scaffold.
      </p>
    );
  }

  const titleShort = config.meta.title || techniqueId;
  const rows = Array.isArray(result?.individual_results)
    ? (result!.individual_results as unknown[][]).map((r) => r.map((c) => String(c ?? "")))
    : [];
  const lr = (result?.reference_lr as ReferenceLrResult | undefined) ?? null;
  const presetItems =
    lrCfg?.defaultReferenceItems?.length
      ? lrCfg.defaultReferenceItems
      : flattenDefaultItems(referenceCatalog);

  const parametersPanel = (
    <>
      <AnalysisPanel title="Detectores / análises">
        <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563" }}>
          Selecione ao menos um item. O job recebe <code>{selectedParam}</code>
          {calibrated && lrCfg?.domain ? (
            <>
              {" "}
              · domínio LR <code>{lrCfg.domain}</code>
            </>
          ) : null}
          .
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
          {detectors.map((d) => (
            <label
              key={d.id}
              style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.88rem" }}
            >
              <input
                type="checkbox"
                checked={selected.has(d.id)}
                disabled={running}
                onChange={() => toggleDetector(d.id)}
              />
              {d.label}
            </label>
          ))}
        </div>
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
          <button
            type="button"
            style={btnSecondary}
            onClick={() => setSelected(new Set(detectors.map((d) => d.id)))}
          >
            Selecionar todos
          </button>
          <button type="button" style={btnSecondary} onClick={() => setSelected(new Set())}>
            Limpar
          </button>
        </div>
      </AnalysisPanel>

      {calibrated && (
        <div style={{ marginTop: "1rem" }}>
          <ReferencePopulationSelector
            catalog={referenceCatalog}
            loading={referenceCatalogLoading}
            error={referenceCatalogError}
            entries={referenceEntries}
            onChange={setReferenceEntries}
            disabled={running}
            enableSplitRoles={enableSplitRoles}
            defaultPresetItems={presetItems}
            subgroupUnitLabel={lrCfg?.subgroupUnitLabel || "subgrupos"}
            hypothesisHint={
              lrCfg?.hypothesisHint ||
              "Defina subgrupos para treino/calibração e para avaliação (espelho áudio spoofing)."
            }
          />
          {!referenceSelectionValid && (
            <p style={{ margin: "0.55rem 0 0", fontSize: "0.78rem", color: "#b91c1c" }}>
              Selecione ao menos um subgrupo em treino/calibração e um em teste.
            </p>
          )}

          <div style={{ marginTop: "0.75rem" }}>
            {lrCfg?.allowMetaClassifier !== false && (
              <MetaClassifierSelect
                value={metaClassifier}
                disabled={running}
                onChange={setMetaClassifier}
              />
            )}
            {lrCfg?.allowAugmented && (
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
                  <span
                    style={{ display: "block", fontSize: "0.74rem", color: "#6b7280", marginTop: "0.15rem" }}
                  >
                    Requer features publicadas com coluna/variantes de augmentation no domínio.
                  </span>
                </span>
              </label>
            )}
            {lrCfg?.allowTypicality && (
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
                  Tipicidade latente (k-NN)
                  <span
                    style={{ display: "block", fontSize: "0.74rem", color: "#6b7280", marginTop: "0.15rem" }}
                  >
                    Usa embeddings publicados (<code>embeddings_path</code>) quando o pipeline implementar.
                  </span>
                </span>
              </label>
            )}
          </div>
        </div>
      )}

      {parameterDefs.length > 0 && (
        <div style={{ marginTop: "1rem" }}>
          <TechniqueParameterForm
            defs={parameterDefs}
            values={params}
            disabled={running}
            onChange={(name, value) => setParams((prev) => ({ ...prev, [name]: value }))}
          />
        </div>
      )}

      <div style={{ marginTop: "1rem" }}>
        <ProcessButton
          onClick={() => void process()}
          disabled={
            !evidenceId ||
            running ||
            runtimeOk === false ||
            selected.size === 0 ||
            !referenceSelectionValid
          }
          running={running}
          progress={progress}
          progressLabel={progressLabel}
          label={`Processar ${titleShort}`}
        />
      </div>
    </>
  );

  const resultPanel = result ? (
    <>
      {(scoreDisplay?.positiveKey || scoreDisplay?.negativeKey || scoreDisplay?.labelKey) && (
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1rem" }}>
          {scoreDisplay.positiveKey && (
            <ScoreBadge label={scoreDisplay.positiveKey} value={result[scoreDisplay.positiveKey]} />
          )}
          {scoreDisplay.negativeKey && (
            <ScoreBadge label={scoreDisplay.negativeKey} value={result[scoreDisplay.negativeKey]} />
          )}
          {scoreDisplay.labelKey && result[scoreDisplay.labelKey] != null && (
            <ScoreBadge label="Classe" value={result[scoreDisplay.labelKey]} />
          )}
        </div>
      )}

      <AnalysisPanel title="Resultados individuais">
        {rows.length === 0 ? (
          <MessageBox type="err" text="Resultado sem individual_results (matriz de linhas)." />
        ) : (
          <ResultsTable headers={headers} rows={rows} />
        )}
      </AnalysisPanel>

      {lrEnabled && (
        <div style={{ marginTop: "1rem" }}>
          <ReferenceLrPanel
            lr={lr}
            tippettUrl={tippettUrl}
            distributionUrl={distributionUrl}
            identityUrl={identityUrl}
            populationUnitLabel={lrCfg?.populationUnitLabel || "amostras"}
            lrPositiveLabel={lrCfg?.lrPositiveLabel || "real"}
          />
        </div>
      )}

      {manifest.length > 0 && (
        <div style={{ marginTop: "1rem" }}>
          <TechniqueArtifactViewer
            evidenceId={evidenceId}
            jobId={currentJobId}
            result={result}
            manifest={manifest}
            fetchImage={fetchImage}
            fetchBlobUrl={fetchBlobUrl}
            saving={saving}
            onSave={(filename, label) => {
              if (currentJobId) void save(currentJobId, filename, label);
            }}
          />
        </div>
      )}

      {lrEnabled && <ReferenceLrFeatureWeightsPanel lr={lr} />}
    </>
  ) : undefined;

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId={techniqueId}
      mediaType={config.mediaType}
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
      meta={config.meta}
      parametersPanel={parametersPanel}
      resultPanel={resultPanel}
    />
  );
}
