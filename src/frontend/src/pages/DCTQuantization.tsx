import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { buildReturnToCaseAnalysesUrl } from "@/utils/caseAnalysisNav";
import { listCaseReferences, uploadReference, saveDerivative } from "@/services/evidence";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import EvidenceThumbnail from "@/components/EvidenceThumbnail";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import { ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import api from "@/services/api";
import type { Evidence } from "@/types/api";

const defaultMatrix: number[][] = Array(8)
  .fill(null)
  .map(() => Array(8).fill(16));

type DCTMode = "estimate" | "reference" | "custom";

const MODE_HELP: Record<DCTMode, string> = {
  estimate:
    "Modo 3: estima a matriz de quantizacao a partir da imagem analisada. Cuidado: nem sempre corresponde a matriz primaria original.",
  reference:
    "Modo 1: usa a matriz de quantizacao de uma imagem JPEG de referencia (via jpegio quando possivel) e compara com a evidencia.",
  custom:
    "Modo 2: aplica uma matriz 8x8 informada manualmente e compara com a matriz estimada da evidencia.",
};

function pickMatrix(result: Record<string, unknown>, keys: string[]): number[][] | null {
  for (const key of keys) {
    const value = result[key];
    if (Array.isArray(value) && value.length === 8) {
      return value as number[][];
    }
  }
  return null;
}

function MatrixValuesTable({
  matrix,
  title,
  emptyMessage,
}: {
  matrix: number[][] | null;
  title: string;
  emptyMessage: string;
}) {
  return (
    <div style={{ flex: "1 1 280px", minWidth: 0 }}>
      <h4 style={{ fontSize: "0.82rem", color: "#374151", marginBottom: "0.4rem", fontWeight: 600 }}>{title}</h4>
      {matrix ? (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", fontSize: "0.8rem" }}>
            <tbody>
              {matrix.map((row, i) => (
                <tr key={i}>
                  {row.map((val, j) => (
                    <td
                      key={j}
                      style={{
                        border: "1px solid #e5e7eb",
                        padding: "0.4rem 0.6rem",
                        textAlign: "center",
                        background: val === 0 ? "#f3f4f6" : "#fff",
                      }}
                    >
                      {val}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p style={{ fontSize: "0.8rem", color: "#6b7280", margin: 0, lineHeight: 1.45 }}>{emptyMessage}</p>
      )}
    </div>
  );
}

export default function DCTQuantization() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const [mode, setMode] = useState<DCTMode>("estimate");
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, reset: resetJob } =
    useForensicJob();
  const [matrixImageUrl, setMatrixImageUrl] = useState<string | null>(null);
  const [artifactImageUrl, setArtifactImageUrl] = useState<string | null>(null);
  const [originalImageUrl, setOriginalImageUrl] = useState<string | null>(null);
  const [savingDerivative, setSavingDerivative] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [runMessage, setRunMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const [customMatrix, setCustomMatrix] = useState<number[][]>(defaultMatrix.map((r) => [...r]));
  const [pasteText, setPasteText] = useState("");

  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [referenceEvidenceId, setReferenceEvidenceId] = useState<string | null>(null);
  const [referenceCandidates, setReferenceCandidates] = useState<Evidence[]>([]);
  const [referenceUploading, setReferenceUploading] = useState(false);
  const [referenceError, setReferenceError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);

  const gridRefs = useRef<(HTMLInputElement | null)[][]>(
    Array(8)
      .fill(null)
      .map(() => Array(8).fill(null))
  );

  function clearResults() {
    resetJob();
    setMatrixImageUrl(null);
    setArtifactImageUrl(null);
    setOriginalImageUrl(null);
    setSaveMessage(null);
    setRunMessage(null);
    viewerRef.current?.resetZoom();
  }

  const applyEvidence = useCallback(
    (_id: string, _source: "original" | "derivative") => {
      clearResults();
    },
    [resetJob],
  );

  const { showPageShell, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  const handleEvidenceLoaded = useCallback(
    (originals: Evidence[], derivs: Evidence[]) => {
      if (evidenceId) return;
      if (originals.length > 0) {
        onSelectEvidence(originals[0].id, "original");
      } else if (derivs.length > 0) {
        onSelectEvidence(derivs[0].id, "derivative");
      }
    },
    [evidenceId, onSelectEvidence],
  );

  function onModeChange(next: DCTMode) {
    setMode(next);
    clearResults();
    if (next !== "reference") {
      setReferenceFile(null);
      setReferenceEvidenceId(null);
    }
  }

  function canProcess(): boolean {
    if (!evidenceId) return false;
    if (mode === "reference" && !referenceEvidenceId) return false;
    return true;
  }

  const loadReferenceCandidates = useCallback(async () => {
    if (!caseId) return;
    const refsResponse = await listCaseReferences(caseId);
    const refs = refsResponse.groups
      .filter((g) => g.technique === "dct_quantization")
      .flatMap((g) => g.files)
      .filter((e) => e.file_type === "imagem");
    setReferenceCandidates(refs);
    if (!referenceEvidenceId && refs.length > 0) {
      setReferenceEvidenceId(refs[0].id);
    }
  }, [caseId, referenceEvidenceId]);

  useEffect(() => {
    loadReferenceCandidates().catch(() => {
      setReferenceCandidates([]);
    });
  }, [loadReferenceCandidates]);

  async function fetchResultFile(jobId: string, pathValue: string | undefined): Promise<string | null> {
    if (!pathValue) return null;
    const filename = pathValue.split(/[\\/]/).pop();
    if (!filename) return null;
    try {
      const res = await api.get(`/analysis/${jobId}/result/file?filename=${filename}`, {
        responseType: "blob",
      });
      return URL.createObjectURL(res.data);
    } catch {
      return null;
    }
  }

  async function runDCT() {
    if (!evidenceId || !canProcess()) return;

    const params: Record<string, unknown> = { mode };
    if (mode === "reference") {
      params.reference_evidence_id = referenceEvidenceId;
    } else if (mode === "custom") {
      params.quantization_matrix = customMatrix;
    }

    setMatrixImageUrl(null);
    setArtifactImageUrl(null);
    setOriginalImageUrl(null);
    setSaveMessage(null);
    setRunMessage(null);
    viewerRef.current?.resetZoom();

    try {
      await runAnalysis(evidenceId, "dct_quantization", params, {
        onArtifactsLoaded: async (jobId, data) => {
          const [matrixUrl, artifactUrl] = await Promise.all([
            fetchResultFile(
              jobId,
              (data.estimated_matrix_image_path as string | undefined) ||
                (data.matrix_image_path as string | undefined)
            ),
            fetchResultFile(jobId, data.artifact_image_path as string | undefined),
          ]);
          if (matrixUrl) setMatrixImageUrl(matrixUrl);
          if (artifactUrl) setArtifactImageUrl(artifactUrl);

          try {
            const origRes = await api.get(`/evidences/${evidenceId}/file`, { responseType: "blob" });
            setOriginalImageUrl(URL.createObjectURL(origRes.data));
          } catch {
            // ignore
          }
        },
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setRunMessage({
        type: "err",
        text: detail || (err instanceof Error ? err.message : "Erro ao executar DCT"),
      });
    }
  }

  async function handleSaveDerivative() {
    if (!currentJobId) return;
    const artifactPath = (result?.artifact_image_path as string | undefined) || "";
    const artifactFilename = artifactPath.split(/[\\/]/).pop() || "artifacts_upscaled.png";
    await handleSaveArtifact(artifactFilename, "Mapa de artefatos DCT");
  }

  async function handleSaveArtifact(artifactFilename: string, label: string) {
    if (!currentJobId) return;
    setSavingDerivative(true);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: artifactFilename,
      });
      setSaveMessage({
        type: "ok",
        text: `${res.message} (${label}). SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setSaveMessage({ type: "err", text: detail || "Erro ao salvar derivado" });
    } finally {
      setSavingDerivative(false);
    }
  }

  function matrixArtifactFilename(resultKey: string, fallback: string): string | null {
    const pathValue = (result?.[resultKey] as string | undefined) || "";
    return pathValue.split(/[\\/]/).pop() || fallback;
  }

  async function handleSaveEstimatedMatrix() {
    const filename = matrixArtifactFilename("estimated_matrix_image_path", "estimated_matrix.png");
    if (!filename) {
      setSaveMessage({ type: "err", text: "Imagem da matriz estimada nao encontrada" });
      return;
    }
    await handleSaveArtifact(filename, "Matriz estimada DCT");
  }

  async function handleSaveJpegioMatrix() {
    const filename = matrixArtifactFilename("jpegio_matrix_image_path", "jpegio_matrix.png");
    if (!filename) {
      setSaveMessage({ type: "err", text: "Imagem da matriz jpegio nao encontrada" });
      return;
    }
    await handleSaveArtifact(filename, "Matriz jpegio DCT");
  }

  function updateMatrixCell(row: number, col: number, value: string) {
    const num = parseInt(value) || 0;
    setCustomMatrix((prev) => {
      const next = prev.map((r) => [...r]);
      next[row][col] = Math.max(0, num);
      return next;
    });
    clearResults();
  }

  function handlePasteFromTextarea() {
    const values = pasteText
      .split(/[\s,;\t\n]+/)
      .map((s) => parseInt(s.trim()))
      .filter((n) => !isNaN(n));
    if (values.length === 0) return;
    setCustomMatrix((prev) => {
      const next = prev.map((r) => [...r]);
      for (let i = 0; i < 64 && i < values.length; i++) {
        next[Math.floor(i / 8)][i % 8] = Math.max(0, values[i]);
      }
      return next;
    });
    clearResults();
  }

  function handleGridPaste(e: React.ClipboardEvent, startRow: number, startCol: number) {
    e.preventDefault();
    const text = e.clipboardData.getData("text");
    const lines = text
      .split(/\n/)
      .map((line) =>
        line
          .split(/[\s,;\t]+/)
          .map((s) => parseInt(s.trim()))
          .filter((n) => !isNaN(n))
      )
      .filter((line) => line.length > 0);
    if (lines.length === 0) return;

    setCustomMatrix((prev) => {
      const next = prev.map((r) => [...r]);
      for (let r = 0; r < lines.length && startRow + r < 8; r++) {
        for (let c = 0; c < lines[r].length && startCol + c < 8; c++) {
          next[startRow + r][startCol + c] = Math.max(0, lines[r][c]);
        }
      }
      return next;
    });
    clearResults();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>, row: number, col: number) {
    let nextRow = row;
    let nextCol = col;
    switch (e.key) {
      case "ArrowUp":
        nextRow = Math.max(0, row - 1);
        e.preventDefault();
        break;
      case "ArrowDown":
        nextRow = Math.min(7, row + 1);
        e.preventDefault();
        break;
      case "ArrowLeft":
        nextCol = Math.max(0, col - 1);
        e.preventDefault();
        break;
      case "ArrowRight":
      case "Tab":
        nextCol = Math.min(7, col + 1);
        if (nextCol === col && row < 7) {
          nextCol = 0;
          nextRow = row + 1;
        }
        e.preventDefault();
        break;
      case "Enter":
        nextRow = Math.min(7, row + 1);
        nextCol = col;
        e.preventDefault();
        break;
      default:
        return;
    }
    gridRefs.current[nextRow]?.[nextCol]?.focus();
    gridRefs.current[nextRow]?.[nextCol]?.select();
  }

  async function handleReferenceUpload(file: File) {
    if (!caseId) return;
    setReferenceUploading(true);
    setReferenceFile(file);
    setReferenceError(null);
    clearResults();
    try {
      const ev = await uploadReference(caseId, file);
      setReferenceEvidenceId(ev.id);
      await loadReferenceCandidates();
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setReferenceError(detail || "Erro ao enviar imagem de referencia");
      setReferenceFile(null);
      await loadReferenceCandidates();
    } finally {
      setReferenceUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) {
      handleReferenceUpload(file);
    }
  }

  const estimatedMatrix = result
    ? pickMatrix(result, ["quantization_matrix", "evidence_matrix", "actual_matrix"])
    : null;

  const jpegioMatrix = result ? pickMatrix(result, ["jpegio_matrix", "evidence_jpegio_matrix"]) : null;

  const hasEstimatedMatrixImage = Boolean(
    result?.estimated_matrix_image_path || result?.matrix_image_path
  );
  const hasJpegioMatrixImage = Boolean(result?.jpegio_matrix_image_path);

  const processHint =
    mode === "reference" && !referenceEvidenceId
      ? "Envie a imagem de referencia antes de processar."
      : !evidenceId
        ? "Selecione uma evidencia ou derivado."
        : null;

  return (
    <div style={{ padding: "2rem" }}>
      {showPageShell && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
          <button
            onClick={() => navigate(buildReturnToCaseAnalysesUrl(caseId!, location.pathname))}
            style={{ background: "none", border: "none", color: "#6b7280", cursor: "pointer", fontSize: "0.9rem", padding: 0 }}
          >
            ← Voltar ao caso
          </button>
        </div>
      )}

      {showPageShell && (
        <h1 style={{ fontSize: "1.5rem", color: "#1a1a2e", marginBottom: "0.75rem" }}>
          {FORENSIC_TECHNIQUE_META.dct_quantization.title}
        </h1>
      )}
      <TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.dct_quantization} />

      {caseId && showEvidencePicker && (
        <ImageEvidenceSelector
          caseId={caseId}
          selectedId={evidenceId}
          selectionSource={selectionSource}
          onSelect={onSelectEvidence}
          excludeReferences
          onLoaded={handleEvidenceLoaded}
        />
      )}

      <div
        style={{
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: "8px",
          padding: "1.25rem",
          marginBottom: "1.5rem",
        }}
      >
        <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.75rem", fontWeight: 600 }}>
          Modo de operacao
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {(
            [
              ["estimate", "Estimar matriz de quantizacao da evidencia"],
              ["reference", "Comparar com imagem de referencia (upload JPEG)"],
              ["custom", "Matriz de quantizacao customizada (8x8)"],
            ] as const
          ).map(([value, label]) => (
            <label key={value} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
              <input
                type="radio"
                name="mode"
                value={value}
                checked={mode === value}
                onChange={() => onModeChange(value)}
                style={{ marginTop: "0.2rem" }}
              />
              <span>
                {label}
                {mode === value && (
                  <span style={{ display: "block", fontSize: "0.75rem", color: "#6b7280", marginTop: "0.15rem" }}>
                    {MODE_HELP[value]}
                  </span>
                )}
              </span>
            </label>
          ))}
        </div>

        {mode === "reference" && (
          <div style={{ marginTop: "1rem" }}>
            {referenceCandidates.length > 0 && (
              <div style={{ marginBottom: "0.75rem" }}>
                <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "0.25rem" }}>
                  Referencia ja registrada no caso
                </label>
                <select
                  value={referenceEvidenceId || ""}
                  onChange={(e) => {
                    setReferenceEvidenceId(e.target.value || null);
                    setReferenceError(null);
                    clearResults();
                  }}
                  style={{
                    width: "100%",
                    maxWidth: "520px",
                    padding: "0.45rem 0.6rem",
                    border: "1px solid #d1d5db",
                    borderRadius: "6px",
                    fontSize: "0.85rem",
                    color: "#1a1a2e",
                    background: "#fff",
                  }}
                >
                  <option value="">Selecione uma referencia existente...</option>
                  {referenceCandidates.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.original_filename}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <p style={{ fontSize: "0.85rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 500 }}>
              Imagem JPEG de referencia (matriz primaria conhecida ou alegada):
            </p>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => document.getElementById("ref-upload")?.click()}
              style={{
                border: `2px dashed ${dragOver ? "#3b82f6" : "#d1d5db"}`,
                borderRadius: "8px",
                padding: "1.5rem",
                textAlign: "center",
                cursor: "pointer",
                background: dragOver ? "#eff6ff" : "#fff",
              }}
            >
              <input
                id="ref-upload"
                type="file"
                accept="image/jpeg,image/jpg"
                style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleReferenceUpload(file);
                }}
              />
              {referenceUploading ? (
                <p style={{ color: "#6b7280", fontSize: "0.85rem" }}>Enviando referencia...</p>
              ) : referenceFile ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}>
                  {referenceEvidenceId && <EvidenceThumbnail evidenceId={referenceEvidenceId} fallback="📎" size={48} />}
                  <p style={{ color: "#1a1a2e", fontSize: "0.9rem", fontWeight: 500, margin: 0 }}>{referenceFile.name}</p>
                  <p style={{ color: "#6b7280", fontSize: "0.8rem", margin: 0 }}>
                    {referenceEvidenceId ? "Referencia registrada na cadeia de custodia" : "Salvando..."}
                  </p>
                </div>
              ) : (
                <div>
                  <p style={{ color: "#6b7280", fontSize: "0.9rem" }}>Clique ou arraste um JPEG aqui</p>
                  <p style={{ color: "#9ca3af", fontSize: "0.75rem" }}>
                    Preferencialmente JPEG para leitura da tabela Q via jpegio
                  </p>
                </div>
              )}
            </div>
            {referenceError && (
              <p
                style={{
                  marginTop: "0.5rem",
                  marginBottom: 0,
                  color: "#991b1b",
                  background: "#fef2f2",
                  border: "1px solid #fecaca",
                  borderRadius: "6px",
                  padding: "0.45rem 0.6rem",
                  fontSize: "0.8rem",
                  maxWidth: "760px",
                }}
              >
                {referenceError}
              </p>
            )}
          </div>
        )}

        {mode === "custom" && (
          <div style={{ marginTop: "1rem" }}>
            <p style={{ fontSize: "0.85rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 500 }}>
              Matriz 8x8 (64 coeficientes):
            </p>
            <div style={{ marginBottom: "0.75rem" }}>
              <textarea
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder="Cole 64 valores (espaco, virgula, tab ou nova linha)..."
                rows={2}
                style={{
                  width: "100%",
                  maxWidth: "400px",
                  padding: "0.4rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "4px",
                  fontSize: "0.8rem",
                }}
              />
              <button
                type="button"
                onClick={handlePasteFromTextarea}
                style={{
                  marginTop: "0.25rem",
                  padding: "0.3rem 0.75rem",
                  background: "#f3f4f6",
                  border: "1px solid #d1d5db",
                  borderRadius: "4px",
                  fontSize: "0.75rem",
                  cursor: "pointer",
                }}
              >
                Preencher grade
              </button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(8, 1fr)", gap: "0.25rem", maxWidth: "400px" }}>
              {customMatrix.map((row, i) =>
                row.map((val, j) => (
                  <input
                    key={`${i}-${j}`}
                    ref={(el) => {
                      if (!gridRefs.current[i]) gridRefs.current[i] = [];
                      gridRefs.current[i][j] = el;
                    }}
                    type="number"
                    min={0}
                    max={255}
                    value={val}
                    onFocus={(e) => e.currentTarget.select()}
                    onChange={(e) => updateMatrixCell(i, j, e.target.value)}
                    onPaste={(e) => handleGridPaste(e, i, j)}
                    onKeyDown={(e) => handleKeyDown(e, i, j)}
                    style={{
                      width: "100%",
                      padding: "0.3rem",
                      border: "1px solid #d1d5db",
                      borderRadius: "4px",
                      fontSize: "0.8rem",
                      textAlign: "center",
                    }}
                  />
                ))
              )}
            </div>
          </div>
        )}

        <div style={{ marginTop: "1.25rem" }}>
          <ProcessButton
            onClick={runDCT}
            disabled={!canProcess()}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Processar DCT"
          />
          {processHint && (
            <p style={{ fontSize: "0.8rem", color: "#6b7280", margin: "0.5rem 0 0" }}>{processHint}</p>
          )}
        </div>
        {error && !runMessage && (
          <p
            style={{
              marginTop: "0.6rem",
              marginBottom: 0,
              fontSize: "0.85rem",
              color: "#991b1b",
              background: "#fef2f2",
              border: "1px solid #fecaca",
              borderRadius: "6px",
              padding: "0.45rem 0.6rem",
              maxWidth: "760px",
            }}
          >
            {error}
          </p>
        )}
        {runMessage && (
          <p
            style={{
              marginTop: "0.6rem",
              marginBottom: 0,
              fontSize: "0.85rem",
              color: runMessage.type === "ok" ? "#065f46" : "#991b1b",
              background: runMessage.type === "ok" ? "#ecfdf5" : "#fef2f2",
              border: `1px solid ${runMessage.type === "ok" ? "#a7f3d0" : "#fecaca"}`,
              borderRadius: "6px",
              padding: "0.45rem 0.6rem",
              maxWidth: "760px",
            }}
          >
            {runMessage.text}
          </p>
        )}
      </div>

      {result && (
        <div>
          {originalImageUrl && artifactImageUrl && (
            <SyncedImagePairViewer
              ref={viewerRef}
              title="Original vs mapa de artefatos DCT (por bloco 8x8)"
              leftLabel="Original"
              rightLabel="Mapa de Artefatos DCT"
              leftSrc={originalImageUrl}
              rightSrc={artifactImageUrl}
              rightImageStyle={{ imageRendering: "pixelated" }}
              actions={
                <>
                  <button
                    type="button"
                    onClick={() => viewerRef.current?.resetZoom()}
                    style={{
                      padding: "0.5rem 1rem",
                      background: "#f3f4f6",
                      color: "#374151",
                      border: "none",
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontSize: "0.85rem",
                    }}
                  >
                    Reset Zoom
                  </button>

                  {currentJobId && (
                    <>
                      <button
                        type="button"
                        onClick={handleSaveDerivative}
                        disabled={savingDerivative}
                        style={{
                          padding: "0.5rem 1rem",
                          background: "#1a1a2e",
                          color: "#fff",
                          border: "none",
                          borderRadius: "6px",
                          cursor: savingDerivative ? "wait" : "pointer",
                          fontSize: "0.85rem",
                        }}
                      >
                        {savingDerivative ? "Salvando…" : "Salvar mapa como derivado"}
                      </button>
                      <button
                        type="button"
                        onClick={() => navigate(`/cases/${caseId}?tab=derivados`)}
                        style={{
                          padding: "0.5rem 1rem",
                          background: "#fff",
                          color: "#1a1a2e",
                          border: "1px solid #1a1a2e",
                          borderRadius: "6px",
                          cursor: "pointer",
                          fontSize: "0.85rem",
                        }}
                      >
                        Abrir aba Derivados
                      </button>
                    </>
                  )}
                </>
              }
            />
          )}
          {saveMessage && (
            <p
              style={{
                marginTop: "0.5rem",
                fontSize: "0.85rem",
                color: saveMessage.type === "ok" ? "#065f46" : "#991b1b",
              }}
            >
              {saveMessage.text}
            </p>
          )}

          {matrixImageUrl && mode === "estimate" && (
            <div style={{ marginBottom: "1.5rem" }}>
              <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 600 }}>
                Matriz estimada (visual)
              </h3>
              <img src={matrixImageUrl} alt="Matriz DCT" style={{ maxWidth: "100%", border: "1px solid #e5e7eb", borderRadius: "8px" }} />
            </div>
          )}

          <div style={{ marginBottom: "1.5rem" }}>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
              <h3 style={{ fontSize: "0.9rem", color: "#374151", margin: 0, fontWeight: 600 }}>
                Matrizes de quantizacao (lado a lado)
              </h3>
              {currentJobId && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {hasEstimatedMatrixImage && (
                    <button
                      type="button"
                      onClick={handleSaveEstimatedMatrix}
                      disabled={savingDerivative}
                      style={{
                        padding: "0.4rem 0.75rem",
                        background: "#1a1a2e",
                        color: "#fff",
                        border: "none",
                        borderRadius: "6px",
                        cursor: savingDerivative ? "wait" : "pointer",
                        fontSize: "0.8rem",
                      }}
                    >
                      {savingDerivative ? "Salvando…" : "Salvar matriz estimada"}
                    </button>
                  )}
                  {hasJpegioMatrixImage && (
                    <button
                      type="button"
                      onClick={handleSaveJpegioMatrix}
                      disabled={savingDerivative}
                      style={{
                        padding: "0.4rem 0.75rem",
                        background: "#1a1a2e",
                        color: "#fff",
                        border: "none",
                        borderRadius: "6px",
                        cursor: savingDerivative ? "wait" : "pointer",
                        fontSize: "0.8rem",
                      }}
                    >
                      {savingDerivative ? "Salvando…" : "Salvar matriz jpegio"}
                    </button>
                  )}
                </div>
              )}
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: "2rem",
                alignItems: "flex-start",
              }}
            >
              <MatrixValuesTable
                matrix={estimatedMatrix}
                title="Matriz estimada (estimativaq)"
                emptyMessage="Matriz estimada indisponivel para este resultado."
              />
              <MatrixValuesTable
                matrix={jpegioMatrix}
                title="Matriz lida do arquivo JPEG (jpegio)"
                emptyMessage="jpegio indisponivel: evidencia nao e JPEG ou tabela Q nao foi lida."
              />
            </div>
          </div>

          {typeof result.mean_difference === "number" && (
            <p style={{ fontSize: "0.85rem", color: "#374151" }}>
              Diferenca media entre matrizes: <strong>{result.mean_difference.toFixed(2)}</strong>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
