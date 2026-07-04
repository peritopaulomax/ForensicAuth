import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import PlotlyHtmlFrame from "@/components/PlotlyHtmlFrame";
import MediaEvidenceSelector from "@/components/MediaEvidenceSelector";
import { useForensicJob } from "@/hooks/useForensicJob";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";

const PYVIS_INLINE_HEIGHT = 420;

export default function PDFStructureMetricsAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [graphUrl, setGraphUrl] = useState<string | null>(null);
  const [htmlUrl, setHtmlUrl] = useState<string | null>(null);
  const [savingDerivative, setSavingDerivative] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

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
    setSaveMessage(null);
  }

  async function handleSaveDerivative(artifactFilename: string, label: string) {
    if (!currentJobId) return;
    setSavingDerivative(artifactFilename);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: artifactFilename,
        label,
      });
      setSaveMessage({
        type: "ok",
        text: `${res.message} «${res.evidence.original_filename}». SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setSaveMessage({ type: "err", text: detail || "Erro ao salvar derivado" });
    } finally {
      setSavingDerivative(null);
    }
  }

  async function process() {
    if (!selectedId) return;
    setSaveMessage(null);
    try {
      await runAnalysis(selectedId, "pdf_structure_metrics", {}, {
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
      /* hook */
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
          onClick={() => handleSaveDerivative(artifactFilename, label)}
          disabled={!!savingDerivative}
          style={btnPrimary}
        >
          {savingDerivative === artifactFilename ? "Salvando…" : buttonLabel}
        </button>
        <button type="button" onClick={() => navigate(`/cases/${caseId}?tab=derivados`)} style={btnSecondary}>
          Abrir derivados
        </button>
      </div>
    );
  }

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="PDF — Estrutura e metricas (grafo)"
      subtitle="Grafo de objetos PDF: layout Graphviz dot TB (arvore hierarquica) no PNG e no HTML interativo."
    >
      <AnalysisPanel title="Evidencia PDF">
        <MediaEvidenceSelector
          caseId={caseId}
          fileType="pdf"
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            clearArtifacts();
          }}
          radioName="pdf-structure-metrics"
        />
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!selectedId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Gerar grafo"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Metricas">
          <p style={{ margin: 0, fontSize: "0.88rem" }}>
            Nos: {Number(result.node_count)} · Arestas: {Number(result.edge_count)}
            {result.layout_engine != null && (
              <> · Motor de layout: {String(result.layout_engine)}</>
            )}
          </p>
        </AnalysisPanel>
      )}

      {htmlUrl && (
        <AnalysisPanel title="Grafo interativo (PyVis)">
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
        </AnalysisPanel>
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
        <AnalysisPanel title="Grafo (PNG)">
          <img src={graphUrl} alt="Grafo PDF" style={{ width: "100%", maxWidth: 960 }} />
          {renderDerivativeActions(
            "structure_graph.png",
            "pdf_structure_graph_png",
            "Salvar em derivados"
          )}
        </AnalysisPanel>
      )}

      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
    </AnalysisPageShell>
  );
}

const btnSecondary = {
  padding: "0.45rem 0.9rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
} as const;

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
