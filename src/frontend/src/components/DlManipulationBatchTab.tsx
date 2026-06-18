import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/services/api";
import { ProcessButton, MessageBox } from "@/components/AnalysisPageShell";
import SyncedImagePairViewer from "@/components/SyncedImagePairViewer";
import {
  resolveTechniqueTabLabel,
  techniqueEntryKey,
  isImageTechniqueBatchEligible,
  type ImageTechniqueEntry,
} from "@/config/imageAnalysisGroups";

type BatchStatus = "idle" | "running" | "done" | "error";

interface SafireParams {
  mode: "binary" | "multi";
  cluster_type: "kmeans" | "dbscan";
  kmeans_cluster_num: number;
}

interface ImdlParams {
  threshold: number;
  mesorch_variant: string;
}

interface BatchItemState {
  entry: ImageTechniqueEntry;
  label: string;
  status: BatchStatus;
  error?: string;
  jobId?: string;
  result?: Record<string, unknown>;
  overlayUrl?: string | null;
  heatmapUrl?: string | null;
  /** SAFIRE: multi-fonte; IMDL: máscara binária (hover no painel direito). */
  rightHoverUrl?: string | null;
  rightHoverLabel?: string;
}

interface Props {
  caseId: string;
  evidenceId: string | null;
  techniques: ImageTechniqueEntry[];
}

function defaultSafireParams(): SafireParams {
  return { mode: "binary", cluster_type: "kmeans", kmeans_cluster_num: 3 };
}

function defaultImdlParams(): ImdlParams {
  return { threshold: 0.85, mesorch_variant: "standard" };
}

async function pollJob(jobId: string, maxWaitMs = 30 * 60 * 1000): Promise<Record<string, unknown>> {
  const intervalMs = 400;
  const maxAttempts = Math.ceil(maxWaitMs / intervalMs);
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const res = await api.get<{ status: string; error_message?: string }>(`/analysis/${jobId}`);
    if (res.data.status === "completed") {
      const detail = await api.get(`/analysis/${jobId}/result`);
      return detail.data as Record<string, unknown>;
    }
    if (res.data.status === "failed") {
      throw new Error(res.data.error_message || "Job falhou");
    }
  }
  throw new Error("Timeout aguardando resultado");
}

async function fetchArtifactUrl(jobId: string, filename: string): Promise<string | null> {
  try {
    const response = await api.get(`/analysis/${jobId}/result/file?filename=${encodeURIComponent(filename)}`, {
      responseType: "blob",
    });
    return URL.createObjectURL(response.data as Blob);
  } catch {
    return null;
  }
}

export default function DlManipulationBatchTab({ evidenceId, techniques }: Props) {
  const [safireParams, setSafireParams] = useState<SafireParams>(defaultSafireParams);
  const [imdlParams, setImdlParams] = useState<Record<string, ImdlParams>>({});
  const [running, setRunning] = useState(false);
  const [progressLabel, setProgressLabel] = useState("");
  const [batchItems, setBatchItems] = useState<BatchItemState[]>([]);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const techniqueList = useMemo(
    () =>
      techniques
        .filter((entry) => isImageTechniqueBatchEligible(entry))
        .map((entry) => ({
          entry,
          key: techniqueEntryKey(entry),
          label: resolveTechniqueTabLabel(entry),
        })),
    [techniques],
  );

  useEffect(() => {
    const next: Record<string, ImdlParams> = {};
    for (const { key, entry } of techniqueList) {
      if (entry.kind === "imdl") {
        next[key] = imdlParams[key] ?? defaultImdlParams();
      }
    }
    setImdlParams((prev) => ({ ...next, ...prev }));
  }, [techniqueList]);

  const getImdlParam = (key: string): ImdlParams => imdlParams[key] ?? defaultImdlParams();

  const runBatch = useCallback(async () => {
    if (!evidenceId) return;
    setRunning(true);
    setGlobalError(null);
    setProgressLabel("Preparando execução em lote…");

    const initial: BatchItemState[] = techniqueList.map(({ entry, label }) => ({
      entry,
      label,
      status: "idle",
    }));
    setBatchItems(initial);

    for (let i = 0; i < techniqueList.length; i++) {
      const { entry, key, label } = techniqueList[i];
      setProgressLabel(`Executando ${i + 1}/${techniqueList.length}: ${label}…`);
      setBatchItems((prev) =>
        prev.map((item, idx) => (idx === i ? { ...item, status: "running", error: undefined } : item)),
      );

      try {
        let technique: string;
        let parameters: Record<string, unknown>;

        if (entry.kind === "plugin" && entry.id === "safire") {
          technique = "safire";
          parameters = { ...safireParams };
        } else if (entry.kind === "imdl") {
          technique = "imdlbenco";
          const p = getImdlParam(key);
          parameters = { method: entry.id, threshold: p.threshold };
          if (entry.id === "mesorch") {
            parameters.mesorch_variant = p.mesorch_variant;
          }
        } else {
          throw new Error("Técnica não suportada no lote");
        }

        const response = await api.post("/analysis", {
          evidence_id: evidenceId,
          technique,
          parameters,
        });
        const jobId = response.data.job_id as string;
        const result = await pollJob(jobId);
        if (result?.success === false) {
          throw new Error(String(result.error || "Análise falhou"));
        }

        const overlayUrl = await fetchArtifactUrl(jobId, "overlay.png");
        const heatmapUrl = await fetchArtifactUrl(jobId, "heatmap.png");

        let rightHoverUrl: string | null = null;
        let rightHoverLabel: string | undefined;
        if (entry.kind === "plugin" && entry.id === "safire") {
          rightHoverUrl = await fetchArtifactUrl(jobId, "safire_multi_segment.png");
          rightHoverLabel = "Particionamento multi-fonte";
        } else if (entry.kind === "imdl") {
          rightHoverUrl = await fetchArtifactUrl(jobId, "mask.png");
          rightHoverLabel = "Máscara (limiar aplicado)";
        }

        setBatchItems((prev) =>
          prev.map((item, idx) =>
            idx === i
              ? {
                  ...item,
                  status: "done",
                  jobId,
                  result,
                  overlayUrl,
                  heatmapUrl,
                  rightHoverUrl,
                  rightHoverLabel,
                }
              : item,
          ),
        );
      } catch (err: unknown) {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          (err instanceof Error ? err.message : "Erro desconhecido");
        setBatchItems((prev) =>
          prev.map((item, idx) => (idx === i ? { ...item, status: "error", error: message } : item)),
        );
      }
    }

    setProgressLabel("Lote concluído");
    setRunning(false);
  }, [evidenceId, techniqueList, safireParams, imdlParams]);

  return (
    <div>
      <p style={{ margin: "0 0 1rem", fontSize: "0.88rem", color: "#4b5563", lineHeight: 1.5 }}>
        Configure os parâmetros de cada técnica e execute todas em sequência. Os resultados aparecem
        separadamente ao final — sem misturar visualizações entre métodos.
      </p>

      <div style={{ display: "grid", gap: "1rem", marginBottom: "1.25rem" }}>
        {techniqueList.map(({ entry, key, label }, index) => (
          <details
            key={key}
            open={index === 0}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              padding: "0.85rem 1rem",
              background: "#fafafa",
            }}
          >
            <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: "0.88rem", color: "#1a1a2e" }}>
              {label}
            </summary>
            <div style={{ marginTop: "0.75rem", display: "grid", gap: "0.65rem", maxWidth: 480 }}>
              {entry.kind === "plugin" && entry.id === "safire" && (
                <>
                  <label style={{ fontSize: "0.82rem" }}>
                    Modo
                    <select
                      value={safireParams.mode}
                      onChange={(e) =>
                        setSafireParams((p) => ({ ...p, mode: e.target.value as SafireParams["mode"] }))
                      }
                      style={{ display: "block", width: "100%", marginTop: 4, padding: "0.35rem" }}
                    >
                      <option value="binary">Localização binária (heatmap)</option>
                      <option value="multi">Particionamento multi-fonte</option>
                    </select>
                  </label>
                  {safireParams.mode === "multi" && (
                    <>
                      <label style={{ fontSize: "0.82rem" }}>
                        Clustering
                        <select
                          value={safireParams.cluster_type}
                          onChange={(e) =>
                            setSafireParams((p) => ({
                              ...p,
                              cluster_type: e.target.value as SafireParams["cluster_type"],
                            }))
                          }
                          style={{ display: "block", width: "100%", marginTop: 4, padding: "0.35rem" }}
                        >
                          <option value="kmeans">k-means</option>
                          <option value="dbscan">DBSCAN</option>
                        </select>
                      </label>
                      {safireParams.cluster_type === "kmeans" && (
                        <label style={{ fontSize: "0.82rem" }}>
                          Número de clusters (k)
                          <input
                            type="number"
                            min={2}
                            max={8}
                            value={safireParams.kmeans_cluster_num}
                            onChange={(e) =>
                              setSafireParams((p) => ({
                                ...p,
                                kmeans_cluster_num: Number(e.target.value),
                              }))
                            }
                            style={{ display: "block", width: "100%", marginTop: 4 }}
                          />
                        </label>
                      )}
                    </>
                  )}
                </>
              )}
              {entry.kind === "imdl" && (
                <>
                  <label style={{ fontSize: "0.82rem" }}>
                    Limiar da máscara ({getImdlParam(key).threshold.toFixed(2)})
                    <input
                      type="range"
                      min={0.1}
                      max={0.95}
                      step={0.05}
                      value={getImdlParam(key).threshold}
                      onChange={(e) =>
                        setImdlParams((prev) => ({
                          ...prev,
                          [key]: { ...getImdlParam(key), threshold: Number(e.target.value) },
                        }))
                      }
                      style={{ display: "block", width: "100%", marginTop: 4 }}
                    />
                  </label>
                  {entry.id === "mesorch" && (
                    <label style={{ fontSize: "0.82rem" }}>
                      Variante Mesorch
                      <select
                        value={getImdlParam(key).mesorch_variant}
                        onChange={(e) =>
                          setImdlParams((prev) => ({
                            ...prev,
                            [key]: { ...getImdlParam(key), mesorch_variant: e.target.value },
                          }))
                        }
                        style={{ display: "block", width: "100%", marginTop: 4, padding: "0.35rem" }}
                      >
                        <option value="standard">Standard</option>
                        <option value="iml_vit">IML-ViT</option>
                      </select>
                    </label>
                  )}
                </>
              )}
            </div>
          </details>
        ))}
      </div>

      <ProcessButton
        running={running}
        progressLabel={progressLabel}
        disabled={!evidenceId || running}
        onClick={runBatch}
        label="Executar todas"
      />
      {globalError && <MessageBox type="err" text={globalError} />}

      {batchItems.length > 0 && (
        <div style={{ marginTop: "1.5rem", display: "grid", gap: "1.25rem" }}>
          <h3 style={{ margin: 0, fontSize: "1rem", color: "#1a1a2e" }}>Resultados</h3>
          {batchItems.map((item) => (
            <section
              key={techniqueEntryKey(item.entry)}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 10,
                padding: "1rem",
                background: item.status === "error" ? "#fef2f2" : "#fff",
              }}
            >
              <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                <strong style={{ fontSize: "0.92rem", color: "#1a1a2e" }}>{item.label}</strong>
                <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                  {item.status === "idle" && "Aguardando"}
                  {item.status === "running" && "Processando…"}
                  {item.status === "done" && "Concluído"}
                  {item.status === "error" && "Erro"}
                </span>
              </header>

              {item.status === "error" && item.error && (
                <p style={{ margin: "0.5rem 0 0", fontSize: "0.82rem", color: "#991b1b" }}>{item.error}</p>
              )}

              {item.status === "done" && item.result && (
                <div style={{ marginTop: "0.75rem" }}>
                  <p style={{ margin: "0 0 0.75rem", fontSize: "0.84rem", color: "#4b5563" }}>
                    {item.result.integrity_score != null && (
                      <>
                        Score integridade:{" "}
                        <strong>{Number(item.result.integrity_score).toFixed(3)}</strong>
                        {" · "}
                      </>
                    )}
                    {item.result.mean_manipulation_score != null && (
                      <>
                        Média localização:{" "}
                        <strong>{Number(item.result.mean_manipulation_score).toFixed(4)}</strong>
                        {" · "}
                      </>
                    )}
                    {item.result.mean_forgery_score != null && (
                      <>
                        Score médio mapa:{" "}
                        <strong>{Number(item.result.mean_forgery_score).toFixed(4)}</strong>
                        {" · "}
                      </>
                    )}
                    {item.result.inference_device != null && (
                      <>
                        Dispositivo: <strong>{String(item.result.inference_device).toUpperCase()}</strong>
                      </>
                    )}
                  </p>
                  {item.overlayUrl && item.heatmapUrl && (
                    <>
                      <SyncedImagePairViewer
                        height={360}
                        leftSrc={item.overlayUrl}
                        rightSrc={item.heatmapUrl}
                        rightHoverSrc={item.rightHoverUrl}
                        rightHoverLabel={item.rightHoverLabel}
                        leftLabel="Overlay"
                        rightLabel="Heatmap"
                      />
                      {item.rightHoverUrl && (
                        <p style={{ margin: "0.5rem 0 0", fontSize: "0.78rem", color: "#6b7280" }}>
                          Passe o mouse sobre o heatmap à direita para ver{" "}
                          {item.entry.kind === "plugin" && item.entry.id === "safire"
                            ? "a partição multi-fonte colorida"
                            : "a máscara binária após o limiar"}
                          .
                        </p>
                      )}
                    </>
                  )}
                  {item.jobId && (
                    <p style={{ margin: "0.5rem 0 0", fontSize: "0.75rem", color: "#9ca3af" }}>
                      Job: {item.jobId}
                    </p>
                  )}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
