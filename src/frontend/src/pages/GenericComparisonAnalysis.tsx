/**
 * Página genérica para técnicas scaffolded (template comparison).
 * Contrato de submit: mode, case_id, questioned_evidence_ids[, reference_evidence_ids].
 * Resultado: resumo (counts) + imagens do artifactManifest + matriz numérica opcional.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import TechniqueParameterForm, {
  initialParameterValues,
} from "@/components/TechniqueParameterForm";
import {
  getTechniqueConfig,
  type ComparisonMode,
  type ArtifactManifestItem,
} from "@/config/techniqueRegistry";
import {
  COMPARISON_IMAGE_ROLES,
  DOWNLOAD_ROLES,
  isImageFilename,
  normalizeArtifactRole,
} from "@/config/artifactRoles";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import {
  listCaseEvidences,
  listCaseReferences,
  type GlobalReferenceGroup,
} from "@/services/evidence";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import type { Evidence } from "@/types/api";
import { imageSelectorListMaxHeight } from "@/styles/listHeights";

export interface GenericComparisonAnalysisProps {
  techniqueId?: string;
}

const IMAGE_EXT = /\.(png|jpe?g|webp|gif|bmp)$/i;

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

function toggleId(set: Set<string>, id: string): Set<string> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

function imageArtifacts(manifest: ArtifactManifestItem[]): ArtifactManifestItem[] {
  return manifest.filter((m) => {
    const role = normalizeArtifactRole(m.role);
    if (DOWNLOAD_ROLES.has(role)) return false;
    if (COMPARISON_IMAGE_ROLES.has(role)) return true;
    return IMAGE_EXT.test(m.filename) || isImageFilename(m.filename);
  });
}

function downloadArtifacts(manifest: ArtifactManifestItem[]): ArtifactManifestItem[] {
  return manifest.filter((m) => {
    const role = normalizeArtifactRole(m.role);
    if (DOWNLOAD_ROLES.has(role)) return true;
    if (role === "other" && !isImageFilename(m.filename) && !m.filename.endsWith(".html")) {
      return true;
    }
    return false;
  });
}

function ScoreMatrixTable({
  matrix,
  rowLabels,
  colLabels,
}: {
  matrix: number[][];
  rowLabels: string[];
  colLabels: string[];
}) {
  if (!matrix.length) return null;
  return (
    <div style={{ overflowX: "auto", marginTop: "0.75rem" }}>
      <table style={{ borderCollapse: "collapse", fontSize: "0.78rem" }}>
        <thead>
          <tr>
            <th style={{ padding: 4, border: "1px solid #e5e7eb" }} />
            {colLabels.map((c) => (
              <th key={c} style={{ padding: 4, border: "1px solid #e5e7eb", maxWidth: 120 }}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={rowLabels[i] ?? i}>
              <th style={{ padding: 4, border: "1px solid #e5e7eb", textAlign: "left" }}>
                {rowLabels[i] ?? i}
              </th>
              {row.map((cell, j) => (
                <td key={j} style={{ padding: 4, border: "1px solid #e5e7eb", textAlign: "center" }}>
                  {typeof cell === "number" ? cell.toFixed(3) : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function extractNumericMatrices(
  result: Record<string, unknown>,
): Array<{ title: string; matrix: number[][]; rowLabels: string[]; colLabels: string[] }> {
  const out: Array<{
    title: string;
    matrix: number[][];
    rowLabels: string[];
    colLabels: string[];
  }> = [];

  const top = result.matrix;
  if (top && typeof top === "object" && !Array.isArray(top)) {
    const m = top as Record<string, unknown>;
    if (Array.isArray(m.matrix) || Array.isArray(m.rows)) {
      const matrix = (m.matrix as number[][]) || (m.rows as number[][]);
      if (Array.isArray(matrix?.[0]) && typeof matrix[0][0] === "number") {
        out.push({
          title: "Matriz",
          matrix,
          rowLabels: (m.row_labels as string[]) || matrix.map((_, i) => String(i)),
          colLabels: (m.col_labels as string[]) || (matrix[0]?.map((_, j) => String(j)) ?? []),
        });
      }
    }
  }

  const metrics = result.metrics;
  if (metrics && typeof metrics === "object") {
    for (const [name, block] of Object.entries(metrics as Record<string, unknown>)) {
      if (!block || typeof block !== "object") continue;
      const b = block as Record<string, unknown>;
      if (!Array.isArray(b.matrix) || !Array.isArray(b.matrix[0])) continue;
      if (typeof (b.matrix as number[][])[0][0] !== "number") continue;
      out.push({
        title: name,
        matrix: b.matrix as number[][],
        rowLabels: (b.row_labels as string[]) || [],
        colLabels: (b.col_labels as string[]) || [],
      });
    }
  }

  return out;
}

export default function GenericComparisonAnalysis({
  techniqueId: techniqueIdProp,
}: GenericComparisonAnalysisProps = {}) {
  const { caseId, techniqueId: techniqueIdParam } = useParams<{
    caseId: string;
    techniqueId?: string;
  }>();
  const navigate = useNavigate();
  const techniqueId = techniqueIdProp || techniqueIdParam || "";
  const config = techniqueId ? getTechniqueConfig(techniqueId) : undefined;

  const cmp = config?.comparisonConfig ?? {};
  const modes: ComparisonMode[] =
    cmp.modes?.length ? cmp.modes : ["with_reference", "all_pairs"];
  const referenceSource = cmp.referenceSource ?? "case_evidences";
  const minQuestioned = cmp.minQuestioned ?? 1;
  const minReferences = cmp.minReferences ?? 1;
  const fileType = config?.mediaType ?? "imagem";

  const [mode, setMode] = useState<ComparisonMode>(modes[0] ?? "with_reference");
  const [caseItems, setCaseItems] = useState<Evidence[]>([]);
  const [refItems, setRefItems] = useState<Evidence[]>([]);
  /** Grupos globais do caso filtrados pelo tipo de mídia da técnica. */
  const [globalRefGroups, setGlobalRefGroups] = useState<GlobalReferenceGroup[]>([]);
  const [selectedRotulo, setSelectedRotulo] = useState<string>("");
  const [selectedQuestIds, setSelectedQuestIds] = useState<Set<string>>(new Set());
  const [selectedRefIds, setSelectedRefIds] = useState<Set<string>>(new Set());
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [artifactUrls, setArtifactUrls] = useState<Record<string, string | null>>({});
  const urlsRef = useRef<Record<string, string | null>>({});

  const parameterDefs = config?.parameterDefs ?? [];
  const manifest = useMemo(() => config?.artifactManifest ?? [], [config]);
  const heatmaps = useMemo(() => imageArtifacts(manifest), [manifest]);
  const fileDownloads = useMemo(() => downloadArtifacts(manifest), [manifest]);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime(techniqueId || "unknown");
  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  useEffect(() => {
    setParams({
      ...(config?.defaultParameters ?? {}),
      ...initialParameterValues(config?.parameterDefs ?? []),
    });
  }, [techniqueId, config]);

  useEffect(() => {
    if (!modes.includes(mode)) setMode(modes[0] ?? "with_reference");
  }, [modes, mode]);

  const loadCaseItems = useCallback(async () => {
    if (!caseId || !fileType) return;
    try {
      const evs = await listCaseEvidences(caseId);
      const list = filterForensicAuthEvidences(evs).filter((e) => e.file_type === fileType);
      setCaseItems(list);
      setSelectedQuestIds((prev) => new Set([...prev].filter((id) => list.some((e) => e.id === id))));
      if (referenceSource === "case_evidences") {
        setRefItems(list);
        setSelectedRefIds((prev) => new Set([...prev].filter((id) => list.some((e) => e.id === id))));
      }
    } catch {
      setCaseItems([]);
    }
  }, [caseId, fileType, referenceSource]);

  const loadGlobalReferences = useCallback(async () => {
    if (!caseId || referenceSource !== "case_references") return;
    try {
      const data = await listCaseReferences(caseId);
      const groups = (data.global_groups || []).filter(
        (g) => (g.reference_type || "").toLowerCase() === String(fileType).toLowerCase(),
      );
      setGlobalRefGroups(groups);
      setSelectedRotulo((prev) => {
        if (prev && groups.some((g) => g.group_label === prev)) return prev;
        return groups[0]?.group_label ?? "";
      });
    } catch {
      setGlobalRefGroups([]);
      setSelectedRotulo("");
      setRefItems([]);
      setSelectedRefIds(new Set());
    }
  }, [caseId, referenceSource, fileType]);

  /** Arquivos do rótulo global ativo — ao trocar o rótulo, seleciona o grupo inteiro. */
  useEffect(() => {
    if (referenceSource !== "case_references") return;
    const group = globalRefGroups.find((g) => g.group_label === selectedRotulo);
    const files = group?.files ?? [];
    setRefItems(files);
    setSelectedRefIds(new Set(files.map((f) => f.id)));
  }, [referenceSource, globalRefGroups, selectedRotulo]);

  useEffect(() => {
    void loadCaseItems();
    void loadGlobalReferences();
  }, [loadCaseItems, loadGlobalReferences]);

  const revokeArtifacts = useCallback(() => {
    for (const u of Object.values(urlsRef.current)) {
      if (u?.startsWith("blob:")) URL.revokeObjectURL(u);
    }
    urlsRef.current = {};
    setArtifactUrls({});
  }, []);

  useEffect(() => () => revokeArtifacts(), [revokeArtifacts]);

  const clearResults = useCallback(() => {
    reset();
    clearMessage();
    revokeArtifacts();
  }, [reset, clearMessage, revokeArtifacts]);

  const canProcess =
    mode === "with_reference"
      ? selectedRefIds.size >= minReferences && selectedQuestIds.size >= minQuestioned
      : selectedQuestIds.size >= Math.max(2, minQuestioned);

  async function process() {
    if (!caseId || !techniqueId || runtimeOk === false || !canProcess) return;
    clearResults();
    const questIds = [...selectedQuestIds];
    const payload: Record<string, unknown> = {
      ...params,
      mode,
      case_id: caseId,
      questioned_evidence_ids: questIds,
    };
    if (mode === "with_reference") {
      payload.reference_evidence_ids = [...selectedRefIds];
    }
    try {
      await runAnalysis(questIds[0], techniqueId, payload, {
        onArtifactsLoaded: async (jobId) => {
          const next: Record<string, string | null> = {};
          for (const item of heatmaps) {
            next[item.filename] = await fetchImage(jobId, item.filename);
          }
          revokeArtifacts();
          urlsRef.current = next;
          setArtifactUrls(next);
        },
      });
    } catch {
    }
  }

  if (!caseId) return null;
  if (!techniqueId || !config) {
    return <Navigate to={`/cases/${caseId}`} replace />;
  }
  if (config.template !== "comparison") {
    return (
      <p style={{ padding: "1rem", color: "#991b1b" }}>
        GenericComparisonAnalysis só cobre template comparison (recebido: {config.template}).
      </p>
    );
  }

  const titleShort = config.meta.title || techniqueId;
  const matrices = result ? extractNumericMatrices(result) : [];

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId={techniqueId}
      mediaType={config.mediaType}
      showEvidencePicker={false}
      running={running}
      error={error}
      progress={progress}
      progressLabel={progressLabel}
      saveMessage={saveMessage}
      runtimeOk={runtimeOk}
      runtimeReason={runtimeReason}
      meta={config.meta}
    >
      {modes.length > 1 && (
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
          {modes.includes("with_reference") && (
            <button
              type="button"
              style={tabStyle(mode === "with_reference")}
              onClick={() => {
                setMode("with_reference");
                clearResults();
              }}
            >
              Com referência
            </button>
          )}
          {modes.includes("all_pairs") && (
            <button
              type="button"
              style={tabStyle(mode === "all_pairs")}
              onClick={() => {
                setMode("all_pairs");
                clearResults();
              }}
            >
              Todas × todas
            </button>
          )}
        </div>
      )}

      {mode === "with_reference" && (
        <AnalysisPanel
          title={
            referenceSource === "case_references"
              ? "Referências globais (por rótulo)"
              : "Referências (evidências do caso)"
          }
        >
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563" }}>
            Selecione ao menos {minReferences} referência(s).{" "}
            {referenceSource === "case_references"
              ? `Fonte: referências globais do caso (tipo «${fileType}»), agrupadas por rótulo — as mesmas da aba Referências.`
              : "Fonte: evidências do caso (mesmo tipo de mídia)."}
          </p>

          {referenceSource === "case_references" && (
            <div style={{ marginBottom: "0.75rem" }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.85rem" }}>
                Rótulo
                <select
                  value={selectedRotulo}
                  disabled={globalRefGroups.length === 0}
                  onChange={(e) => {
                    setSelectedRotulo(e.target.value);
                    clearResults();
                  }}
                  style={{
                    ...btnSecondary,
                    maxWidth: 360,
                    padding: "0.4rem 0.5rem",
                  }}
                >
                  {globalRefGroups.length === 0 ? (
                    <option value="">Nenhum grupo global deste tipo</option>
                  ) : (
                    globalRefGroups.map((g) => (
                      <option key={g.group_label} value={g.group_label}>
                        {g.display_label || g.group_label} ({g.files.length})
                      </option>
                    ))
                  )}
                </select>
              </label>
            </div>
          )}

          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
            <button
              type="button"
              style={btnSecondary}
              onClick={() => setSelectedRefIds(new Set(refItems.map((e) => e.id)))}
            >
              Selecionar todas
            </button>
            <button type="button" style={btnSecondary} onClick={() => setSelectedRefIds(new Set())}>
              Limpar
            </button>
          </div>
          {refItems.length === 0 ? (
            <MessageBox
              type="err"
              text={
                referenceSource === "case_references"
                  ? `Nenhuma referência global do tipo «${fileType}». Cadastre na aba Referências do caso (ex.: Imagens-Rotulo1).`
                  : "Nenhuma referência disponível."
              }
            />
          ) : (
            <EvidenceFileGrid
              items={refItems}
              selected={(item) => selectedRefIds.has(item.id)}
              onSelect={(item) => setSelectedRefIds((prev) => toggleId(prev, item.id))}
              maxHeight={imageSelectorListMaxHeight}
            />
          )}
        </AnalysisPanel>
      )}

      <AnalysisPanel
        title={mode === "with_reference" ? "Evidências questionadas" : "Evidências a comparar"}
      >
        <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563" }}>
          {mode === "with_reference"
            ? `Selecione ao menos ${minQuestioned} evidência(s) questionada(s).`
            : "Selecione ao menos 2 evidências para a matriz todas × todas."}
        </p>
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
          <button
            type="button"
            style={btnSecondary}
            onClick={() => setSelectedQuestIds(new Set(caseItems.map((e) => e.id)))}
          >
            Selecionar todas
          </button>
          <button type="button" style={btnSecondary} onClick={() => setSelectedQuestIds(new Set())}>
            Limpar
          </button>
        </div>
        {caseItems.length === 0 ? (
          <MessageBox type="err" text={`Nenhuma evidência do tipo «${fileType}» neste caso.`} />
        ) : (
          <EvidenceFileGrid
            items={caseItems}
            selected={(item) => selectedQuestIds.has(item.id)}
            onSelect={(item) => setSelectedQuestIds((prev) => toggleId(prev, item.id))}
            maxHeight={imageSelectorListMaxHeight}
          />
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
            disabled={!canProcess || runtimeOk === false}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label={`Processar ${titleShort}`}
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Resultado">
          <p style={{ margin: 0, fontSize: "0.88rem" }}>
            Modo: {String(result.mode ?? mode)} · Referências:{" "}
            {Number(result.reference_count ?? selectedRefIds.size)} · Questionados:{" "}
            {Number(result.questioned_count ?? selectedQuestIds.size)}
            {result.success === false && result.error != null
              ? ` · Erro: ${String(result.error)}`
              : ""}
          </p>

          {heatmaps.map((item) => {
            const url = artifactUrls[item.filename];
            if (!url) return null;
            return (
              <div key={item.filename} style={{ marginTop: "1rem" }}>
                <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.9rem" }}>{item.label}</h4>
                <img
                  src={url}
                  alt={item.label}
                  style={{ maxWidth: "100%", border: "1px solid #e5e7eb", borderRadius: 6 }}
                />
                {currentJobId && (
                  <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
                    <button
                      type="button"
                      style={btnSecondary}
                      disabled={!!saving}
                      onClick={() => void save(currentJobId, item.filename, item.label)}
                    >
                      {saving ? "Salvando…" : "Salvar em derivados"}
                    </button>
                    <button
                      type="button"
                      style={btnSecondary}
                      onClick={() => navigate(`/cases/${caseId}?tab=derivados`)}
                    >
                      Abrir derivados
                    </button>
                  </div>
                )}
              </div>
            );
          })}

          {matrices.map((m) => (
            <div key={m.title} style={{ marginTop: "1rem" }}>
              <h4 style={{ margin: "0 0 0.35rem", fontSize: "0.9rem" }}>{m.title}</h4>
              <ScoreMatrixTable matrix={m.matrix} rowLabels={m.rowLabels} colLabels={m.colLabels} />
            </div>
          ))}

          {fileDownloads.length > 0 && currentJobId && (
            <div
              style={{
                marginTop: "1rem",
                padding: "0.75rem 1rem",
                border: "1px solid #e5e7eb",
                borderRadius: 8,
                background: "#f9fafb",
              }}
            >
              <div style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                Salvar em derivados
              </div>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.75rem", color: "#6b7280" }}>
                Sem download direto do job — salve o derivado para registrar na cadeia de custódia.
              </p>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {fileDownloads.map((item) => (
                  <button
                    key={item.filename}
                    type="button"
                    style={btnSecondary}
                    disabled={!!saving}
                    onClick={() => void save(currentJobId, item.filename, item.label)}
                  >
                    {saving ? "Salvando…" : `Salvar ${item.label}`}
                  </button>
                ))}
              </div>
            </div>
          )}
        </AnalysisPanel>
      )}
    </TechniquePageShell>
  );
}
