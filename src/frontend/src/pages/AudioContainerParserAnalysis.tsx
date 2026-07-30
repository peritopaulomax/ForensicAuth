import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import { MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import { scrollableListStyle } from "@/styles/listHeights";

type ParserTechnique = "mp3_parser" | "opus_parser";

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((v) => String(v)).filter(Boolean);
}

export default function AudioContainerParserAnalysis({
  techniqueId = "mp3_parser",
}: {
  techniqueId?: string;
}) {
  const technique = (techniqueId === "opus_parser" ? "opus_parser" : "mp3_parser") as ParserTechnique;
  const { caseId } = useParams<{ caseId: string }>();
  const [report, setReport] = useState("");
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime(technique);

  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  function clearResults() {
    reset();
    setReport("");
    clearMessage();
  }

  const applyEvidence = useCallback((_id: string) => {
    clearResults();
  }, []);

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId || "", applyEvidence);

  useEffect(() => {
    clearResults();
  }, [technique]);

  async function process() {
    if (!evidenceId || runtimeOk === false) return;
    clearMessage();
    setReport("");
    try {
      await runAnalysis(evidenceId, technique, {}, {
        onArtifactsLoaded: async (_jobId, jobResult) => {
          setReport(String(jobResult?.report || ""));
        },
      });
    } catch {
      /* erro já em useForensicJob */
    }
  }

  const findings = useMemo(() => {
    if (!result) return [] as string[];
    if (technique === "mp3_parser") return asStringList(result.findings);
    return [...asStringList(result.errors), ...asStringList(result.warnings)];
  }, [result, technique]);

  const summaryChips = useMemo(() => {
    if (!result) return [] as { label: string; value: string }[];
    if (technique === "mp3_parser") {
      return [
        { label: "Frames", value: String(result.frame_count ?? "—") },
        { label: "Encoder", value: String(result.encoder ?? "—") },
        {
          label: "Bitrates",
          value: Array.isArray(result.bitrates_kbps)
            ? (result.bitrates_kbps as number[]).join(", ") || "—"
            : "—",
        },
      ];
    }
    return [
      { label: "Páginas Ogg", value: String(result.page_count ?? "—") },
      {
        label: "Duração (s)",
        value: result.duration_seconds != null ? String(result.duration_seconds) : "—",
      },
      { label: "Plataforma", value: String(result.platform_hint ?? "—") },
      { label: "TOC", value: String(result.toc_count ?? "—") },
    ];
  }, [result, technique]);

  if (!caseId) return null;

  const processLabel = technique === "mp3_parser" ? "Analisar MP3" : "Analisar Opus";

  const parametersPanel = (
    <>
      <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563", lineHeight: 1.45 }}>
        {technique === "mp3_parser"
          ? "Disseca frames MPEG, tags ID3 e headers VBR (Xing/VBRI) sem decodificar o áudio."
          : "Disseca páginas Ogg, OpusHead/OpusTags, TOC e assinaturas de origem/plataforma."}
      </p>
      <ProcessButton
        onClick={process}
        disabled={!evidenceId || runtimeOk === false}
        running={running}
        progress={progress}
        progressLabel={progressLabel}
        label={processLabel}
      />
    </>
  );

  const resultPanel = (
    <>
      {summaryChips.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
          {summaryChips.map((chip) => (
            <div
              key={chip.label}
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                padding: "0.45rem 0.7rem",
                minWidth: 120,
              }}
            >
              <div style={{ fontSize: "0.68rem", color: "#64748b", textTransform: "uppercase" }}>
                {chip.label}
              </div>
              <div style={{ fontSize: "0.86rem", color: "#0f172a", fontWeight: 600, marginTop: 2 }}>
                {chip.value}
              </div>
            </div>
          ))}
        </div>
      )}

      {findings.length > 0 && (
        <div style={{ marginBottom: "0.85rem" }}>
          <p style={{ margin: "0 0 0.35rem", fontSize: "0.82rem", fontWeight: 600, color: "#1e293b" }}>
            {technique === "mp3_parser" ? "Achados" : "Avisos e inconsistências"}
          </p>
          <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.85rem", color: "#334155" }}>
            {findings.map((item) => (
              <li key={item} style={{ marginBottom: "0.35rem" }}>
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report && (
        <pre
          style={{
            ...scrollableListStyle,
            maxHeight: 520,
            margin: 0,
            padding: "0.85rem 1rem",
            background: "#0b1220",
            color: "#e2e8f0",
            borderRadius: 8,
            fontSize: "0.78rem",
            lineHeight: 1.45,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          }}
        >
          {report}
        </pre>
      )}

      {currentJobId && report && (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
          <button
            type="button"
            disabled={!!saving}
            onClick={() => save(currentJobId, "container_parser_report.txt", `${technique}_report`)}
            style={btnPrimary}
          >
            {saving ? "Salvando…" : "Salvar relatório nos derivados"}
          </button>
          <button
            type="button"
            disabled={!!saving}
            onClick={() => save(currentJobId, "container_parser_summary.json", `${technique}_summary`)}
            style={btnPrimary}
          >
            {saving ? "Salvando…" : "Salvar resumo JSON"}
          </button>
        </div>
      )}

      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId={technique}
      mediaType="audio"
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
      resultPanel={result || report ? resultPanel : undefined}
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
