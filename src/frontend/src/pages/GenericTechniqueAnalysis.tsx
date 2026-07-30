/**
 * Página genérica para técnicas scaffolded (templates simple | medium).
 * Configuração vem do techniqueRegistry (parameterDefs + artifactManifest).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import TechniqueParameterForm, {
  initialParameterValues,
} from "@/components/TechniqueParameterForm";
import TechniqueArtifactViewer from "@/components/TechniqueArtifactViewer";
import { getTechniqueConfig } from "@/config/techniqueRegistry";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import api from "@/services/api";

export interface GenericTechniqueAnalysisProps {
  /** Quando embutido em image-group (URL sem :techniqueId). */
  techniqueId?: string;
}

const btnPrimary: React.CSSProperties = {
  padding: "0.5rem 1rem",
  background: "#0369a1",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
  fontWeight: 600,
};

export default function GenericTechniqueAnalysis({
  techniqueId: techniqueIdProp,
}: GenericTechniqueAnalysisProps = {}) {
  const { caseId, techniqueId: techniqueIdParam } = useParams<{
    caseId: string;
    techniqueId?: string;
  }>();
  const techniqueId = techniqueIdProp || techniqueIdParam || "";
  const config = techniqueId ? getTechniqueConfig(techniqueId) : undefined;

  const parameterDefs = config?.parameterDefs ?? [];
  const [params, setParams] = useState<Record<string, unknown>>({});

  useEffect(() => {
    setParams({
      ...(config?.defaultParameters ?? {}),
      ...initialParameterValues(config?.parameterDefs ?? []),
    });
  }, [techniqueId, config]);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime(techniqueId || "unknown");

  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  const applyEvidence = useCallback(
    (_id: string, _source: "original" | "derivative") => {
      reset();
      clearMessage();
    },
    [reset, clearMessage],
  );

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

  async function process() {
    if (!evidenceId || !techniqueId) return;
    if (runtimeOk === false) return;
    clearMessage();
    try {
      await runAnalysis(evidenceId, techniqueId, { ...params });
    } catch {
    }
  }

  if (!caseId) return null;
  if (!techniqueId || !config) {
    return <Navigate to={`/cases/${caseId}`} replace />;
  }
  if (config.template !== "simple" && config.template !== "medium") {
    return (
      <p style={{ padding: "1rem", color: "#991b1b" }}>
        GenericTechniqueAnalysis só cobre templates simple/medium (recebido: {config.template}).
      </p>
    );
  }

  const titleShort = config.meta.title || techniqueId;

  const parametersPanel = (
    <>
      <TechniqueParameterForm
        defs={parameterDefs}
        values={params}
        disabled={running}
        onChange={(name, value) => setParams((prev) => ({ ...prev, [name]: value }))}
      />
      <div style={{ marginTop: parameterDefs.length ? "1rem" : 0 }}>
        <button
          type="button"
          onClick={() => void process()}
          disabled={!evidenceId || running || runtimeOk === false}
          style={btnPrimary}
        >
          {running ? "Processando…" : `Processar ${titleShort}`}
        </button>
      </div>
    </>
  );

  const resultPanel = result ? (
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
