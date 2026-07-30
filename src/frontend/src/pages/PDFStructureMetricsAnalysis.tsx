import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import { MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import PlotlyHtmlFrame from "@/components/PlotlyHtmlFrame";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import api from "@/services/api";

const PYVIS_INLINE_HEIGHT = 420;

export default function PDFStructureMetricsAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [graphUrl, setGraphUrl] = useState<string | null>(null);
  const [htmlUrl, setHtmlUrl] = useState<string | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime("pdf_structure_metrics");

  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  useEffect(
    () => () => {
      if (htmlUrl) URL.revokeObjectURL(htmlUrl);
    },
    [htmlUrl]
  );

  function clearArtifacts() {
    reset();
    setGraphUrl(null);
    if (htmlUrl) URL.revokeObjectURL(htmlUrl);
    setHtmlUrl(null);
    clearMessage();
  }

  const applyEvidence = useCallback(
    (_id: string) => {
      clearArtifacts();
    },
    []
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    clearMessage();
    try {
      await runAnalysis(evidenceId, "pdf_structure_metrics", {}, {
        onArtifactsLoaded: async (jobId) => {
          const png = await fetchImage(jobId, "structure_graph.png");
          setGraphUrl(png);
          try {
            const hres = await api.get(`/analysis/${jobId}/result/file?filename=structure_graph.html`, {
              responseType: "blob",
            });
            if (htmlUrl) URL.revokeObjectURL(htmlUrl);
            setHtmlUrl(URL.createObjectURL(new Blob([hres.data], { type: "text/html" })));
          } catch {
            setHtmlUrl(null);
          }
        },
      });
    } catch {
    }
  }

  function renderDerivativeActions(
    artifactFilename: string,
    label: string,
    buttonLabel: string
  ) {
    if (!currentJobId) return null;
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
        <button
          type="button"
          onClick={() => save(currentJobId, artifactFilename, label)}
          disabled={!!saving}
          style={btnPrimary}
        >
          {saving ? "Salvando…" : buttonLabel}
        </button>
      </div>
    );
  }

  if (!caseId) return null;

  const parametersPanel = (
    <div style={{ marginTop: "1rem" }}>
      <ProcessButton
        onClick={process}
        disabled={!evidenceId || runtimeOk === false}
        running={running}
        progress={progress}
        progressLabel={progressLabel}
        label="Gerar grafo"
      />
    </div>
  );

  const resultPanel = (
    <>
      {result && (
        <p style={{ margin: 0, fontSize: "0.88rem" }}>
          Nos: {Number(result.node_count)} · Arestas: {Number(result.edge_count)}
          {result.layout_engine != null && (
            <> · Motor de layout: {String(result.layout_engine)}</>
          )}
        </p>
      )}

      {htmlUrl && (
        <>
          <p style={{ fontSize: "0.82rem", color: "#6b7280", marginTop: 0 }}>
            Mesma arvore hierarquica do PNG (Graphviz dot) ao carregar. Arraste nos e use zoom; no canto do grafo,
            o icone de engrenagem abre o painel PyVis (fisica hierarquica/gravitacional, interacao, layout). Ao
            ativar fisica o layout pode mudar — esperado. Expanda em tela cheia para usar o painel com mais espaco.
          </p>
          <PlotlyHtmlFrame
            url={htmlUrl}
            title="Grafo PDF (PyVis)"
            height={PYVIS_INLINE_HEIGHT}
          />
          {renderDerivativeActions(
            "structure_graph.html",
            "pdf_structure_graph_html",
            "Salvar em derivados"
          )}
        </>
      )}

      {!htmlUrl && result && (
        <MessageBox
          type="err"
          text={
            typeof result.structure_graph_html_error === "string"
              ? `${result.structure_graph_html_error} Reinicie o backend apos instalar e clique em Gerar grafo novamente.`
              : result.structure_graph_html_path
                ? "HTML foi gerado no servidor mas nao carregou no navegador. Tente Gerar grafo de novo."
                : "Grafo interativo nao gerado. No terminal: conda activate forensicauth && pip install pyvis. Reinicie o backend e processe de novo."
          }
        />
      )}

      {graphUrl && (
        <>
          <img src={graphUrl} alt="Grafo PDF" style={{ width: "100%", maxWidth: 960 }} />
          {renderDerivativeActions(
            "structure_graph.png",
            "pdf_structure_graph_png",
            "Salvar em derivados"
          )}
        </>
      )}

      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="pdf_structure_metrics"
      mediaType="pdf"
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

const btnPrimary = {
  padding: "0.45rem 0.9rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
  fontWeight: 500,
} as const;
