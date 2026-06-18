import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import FileListViewHeader from "@/components/FileListViewHeader";
import DqtMatrixTooltipLayer from "@/components/jpeg/DqtMatrixTooltipLayer";
import JpegCompareGrid from "@/components/jpeg/JpegCompareGrid";
import JpegCompareErrorBoundary from "@/components/jpeg/JpegCompareErrorBoundary";
import JpegStructureMatchMatrix from "@/components/jpeg/JpegStructureMatchMatrix";
import JpegStructureMatrixSection, { type MatrixTab } from "@/components/jpeg/JpegStructureMatrixSection";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import { useDqtTooltip } from "@/hooks/useDqtTooltip";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { listCaseEvidences, saveDerivative } from "@/services/evidence";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import type { Evidence } from "@/types/api";
import { imageSelectorListMaxHeight } from "@/styles/listHeights";
import { slimStructuresList } from "@/utils/jpegComparePayload";
import {
  buildRefVsQuestionedCompare,
  filterJpegEvidences,
  recomputeComparisons,
  type JpegComparePayload,
} from "@/utils/jpegStructureCompare";
import { parseJpegStructureMatrix, type JpegStructureMatrixPayload } from "@/utils/jpegStructureMatrix";

export default function JpegStructureCompareAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [images, setImages] = useState<Evidence[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useFileListViewMode();
  const [matrixTab, setMatrixTab] = useState<MatrixTab>("with_reference");
  const [selectedRefIds, setSelectedRefIds] = useState<Set<string>>(new Set());
  const [matrixData, setMatrixData] = useState<JpegStructureMatrixPayload | null>(null);
  const [compareData, setCompareData] = useState<JpegComparePayload | null>(null);
  const [activeRefId, setActiveRefId] = useState<string | null>(null);
  const [expandedThumbs, setExpandedThumbs] = useState<Set<string>>(new Set());
  const [parseError, setParseError] = useState<string | null>(null);
  const [gridEpoch, setGridEpoch] = useState(0);
  const [matrixPngUrl, setMatrixPngUrl] = useState<string | null>(null);
  const [savingDerivative, setSavingDerivative] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const dqtTooltip = useDqtTooltip();
  const { running, currentJobId, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  const applyEvidence = useCallback(() => {}, []);
  const { embedded } = useGroupAwareEvidence(caseId!, applyEvidence);

  useEffect(() => {
    if (!caseId) return;
    listCaseEvidences(caseId)
      .then((evs) => {
        const list = filterJpegEvidences(filterForensicAuthEvidences(evs));
        setImages(list);
        setSelectedIds((prev) => {
          const valid = new Set(list.map((e) => e.id));
          const kept = [...prev].filter((id) => valid.has(id));
          return kept.length > 0 ? new Set(kept) : new Set(list.slice(0, Math.min(3, list.length)).map((e) => e.id));
        });
      })
      .catch(() => setImages([]));
  }, [caseId]);

  useEffect(
    () => () => {
      if (matrixPngUrl) URL.revokeObjectURL(matrixPngUrl);
    },
    [matrixPngUrl]
  );

  const selectedOrdered = useMemo(
    () => images.filter((img) => selectedIds.has(img.id)),
    [images, selectedIds]
  );

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setSelectedIds(new Set(images.map((e) => e.id)));
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  const clearResults = useCallback(() => {
    reset();
    setMatrixData(null);
    setCompareData(null);
    setActiveRefId(null);
    setExpandedThumbs(new Set());
    setParseError(null);
    setSaveMessage(null);
    setMatrixPngUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    dqtTooltip.dismiss();
    setGridEpoch((n) => n + 1);
  }, [reset, dqtTooltip.dismiss]);

  function handleTabChange(tab: MatrixTab) {
    setMatrixTab(tab);
    clearResults();
  }

  async function calculate() {
    if (!caseId) return;
    const questIds = selectedOrdered.map((e) => e.id);
    if (questIds.length === 0) return;

    clearResults();

    const artifactOpts = {
      retainResult: false,
      onArtifactsLoaded: async (jobId: string) => {
        try {
          const png = await fetchImage(jobId, "jpeg_structure_matrix.png");
          setMatrixPngUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return png;
          });
        } catch {
          setMatrixPngUrl(null);
        }
      },
    };

    try {
      if (matrixTab === "with_reference") {
        const refIds = [...selectedRefIds];
        if (refIds.length === 0) return;

        const { result } = await runAnalysis(
          questIds[0],
          "jpeg_structure_compare",
          {
            mode: "with_reference",
            case_id: caseId,
            reference_evidence_ids: refIds,
            questioned_evidence_ids: questIds,
          },
          artifactOpts
        );

        const parsed = result ? parseJpegStructureMatrix(result) : null;
        if (!parsed) {
          setParseError("Resposta da análise inválida ou incompleta.");
          return;
        }

        setMatrixData(parsed);
        const refStructs = slimStructuresList(parsed.reference_structures);
        const questStructs = slimStructuresList(parsed.questioned_structures);
        const firstRef = refIds[0];
        setActiveRefId(firstRef);
        setCompareData(buildRefVsQuestionedCompare(refStructs, questStructs, firstRef));
        setParseError(null);
        setGridEpoch((n) => n + 1);
      } else {
        if (questIds.length < 2) return;

        const { result } = await runAnalysis(
          questIds[0],
          "jpeg_structure_compare",
          {
            mode: "all_pairs",
            case_id: caseId,
            questioned_evidence_ids: questIds,
          },
          artifactOpts
        );

        const parsed = result ? parseJpegStructureMatrix(result) : null;
        if (!parsed) {
          setParseError("Resposta da análise inválida ou incompleta.");
          return;
        }

        setMatrixData(parsed);
        const questStructs = slimStructuresList(parsed.questioned_structures);
        if (questStructs.length > 0) {
          setCompareData(recomputeComparisons(questStructs, 0));
        }
        setActiveRefId(null);
        setParseError(null);
        setGridEpoch((n) => n + 1);
      }
    } catch {
      /* hook */
    }
  }

  function selectReferencePattern(evidenceId: string) {
    if (!matrixData || matrixTab !== "with_reference" || evidenceId === activeRefId) return;
    const refStructs = slimStructuresList(matrixData.reference_structures);
    const questStructs = slimStructuresList(matrixData.questioned_structures);
    if (!refStructs.length || !questStructs.length) return;

    setActiveRefId(evidenceId);
    setCompareData(buildRefVsQuestionedCompare(refStructs, questStructs, evidenceId));
    setExpandedThumbs(new Set());
    dqtTooltip.dismiss();
    setGridEpoch((n) => n + 1);
  }

  function promoteToReference(rowIndex: number) {
    if (!compareData || matrixTab === "with_reference") return;
    const reordered = [...compareData.structures];
    const [picked] = reordered.splice(rowIndex, 1);
    reordered.unshift(picked);
    const next = recomputeComparisons(reordered, 0);
    setCompareData(next);
    setExpandedThumbs(new Set());
    dqtTooltip.dismiss();
    setGridEpoch((n) => n + 1);
  }

  function toggleThumbExpand(key: string) {
    setExpandedThumbs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const derivativeLabelBase =
    matrixTab === "with_reference" ? "jpeg_estrutura_ref_x_quest" : "jpeg_estrutura_all_pairs";

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

  function renderMatrixDerivativeActions() {
    if (!currentJobId || !matrixData) return null;
    const suffix =
      matrixTab === "with_reference"
        ? `${matrixData.reference_count}r_${matrixData.questioned_count}q`
        : `${matrixData.questioned_count}x`;
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.85rem" }}>
        <button
          type="button"
          onClick={() =>
            handleSaveDerivative("jpeg_structure_matrix.json", `${derivativeLabelBase}_${suffix}_json`)
          }
          disabled={!!savingDerivative}
          style={btnPrimary}
        >
          {savingDerivative === "jpeg_structure_matrix.json" ? "Salvando…" : "Salvar matriz (JSON)"}
        </button>
        <button
          type="button"
          onClick={() =>
            handleSaveDerivative("jpeg_structure_matrix.png", `${derivativeLabelBase}_${suffix}_png`)
          }
          disabled={!!savingDerivative || !matrixPngUrl}
          style={btnPrimary}
        >
          {savingDerivative === "jpeg_structure_matrix.png" ? "Salvando…" : "Salvar matriz (PNG)"}
        </button>
        <button
          type="button"
          onClick={() =>
            handleSaveDerivative("jpeg_structure_report.txt", `${derivativeLabelBase}_${suffix}_txt`)
          }
          disabled={!!savingDerivative}
          style={btnPrimary}
        >
          {savingDerivative === "jpeg_structure_report.txt" ? "Salvando…" : "Salvar matriz (TXT)"}
        </button>
      </div>
    );
  }

  function renderGridDerivativeActions() {
    if (!currentJobId || !compareData) return null;
    const suffix =
      matrixTab === "with_reference"
        ? `${matrixData?.reference_count ?? 0}r_${matrixData?.questioned_count ?? 0}q`
        : `${matrixData?.questioned_count ?? compareData.file_count}x`;
    const gridBase =
      matrixTab === "with_reference" ? "jpeg_estrutura_grade_ref" : "jpeg_estrutura_grade_all";
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.85rem" }}>
        <button
          type="button"
          onClick={() => handleSaveDerivative("jpeg_structure_grid.json", `${gridBase}_${suffix}_json`)}
          disabled={!!savingDerivative}
          style={btnPrimary}
        >
          {savingDerivative === "jpeg_structure_grid.json" ? "Salvando…" : "Salvar grade (JSON)"}
        </button>
        <button
          type="button"
          onClick={() => handleSaveDerivative("jpeg_structure_grid.txt", `${gridBase}_${suffix}_txt`)}
          disabled={!!savingDerivative}
          style={btnPrimary}
        >
          {savingDerivative === "jpeg_structure_grid.txt" ? "Salvando…" : "Salvar grade (TXT)"}
        </button>
        <button type="button" onClick={() => navigate(`/cases/${caseId}?tab=derivados`)} style={btnSecondary}>
          Abrir derivados
        </button>
      </div>
    );
  }

  const canCalculate =
    selectedOrdered.length > 0 &&
    (matrixTab === "with_reference"
      ? selectedRefIds.size > 0
      : selectedOrdered.length >= 2);

  const calculateLabel = !canCalculate
    ? matrixTab === "with_reference"
      ? "Selecione questionados e padrões"
      : "Selecione ao menos 2 questionados"
    : "Calcular";

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.jpeg_structure_compare.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.jpeg_structure_compare} />}
      embedded={embedded}
    >
      <div data-testid="jpeg-structure-compare-page">
        <DqtMatrixTooltipLayer
          state={dqtTooltip.state}
          onMouseEnter={dqtTooltip.onTooltipEnter}
          onMouseLeave={dqtTooltip.onTooltipLeave}
        />

        <AnalysisPanel title="Seleção de imagens JPEG (questionados)">
          <p style={{ fontSize: "0.85rem", color: "#6b7280", margin: "0 0 0.75rem" }}>
            Selecione as evidências <strong>questionadas</strong> (.jpg, .jpeg, .jfif). No modo sem referência,
            a primeira linha da grade serve de referência posicional (duplo clique para trocar).
          </p>

          <FileListViewHeader viewMode={viewMode} onViewModeChange={setViewMode}>
            <span style={{ fontSize: "0.85rem", color: "#6b7280" }}>
              {images.length} JPEG · {selectedIds.size} selecionada(s)
              {" · "}
              <button
                type="button"
                style={{ background: "none", border: "none", color: "#0369a1", cursor: "pointer", padding: 0 }}
                onClick={selectAll}
                disabled={images.length === 0}
              >
                todas
              </button>
              {" / "}
              <button
                type="button"
                style={{ background: "none", border: "none", color: "#0369a1", cursor: "pointer", padding: 0 }}
                onClick={clearSelection}
                disabled={selectedIds.size === 0}
              >
                limpar
              </button>
            </span>
          </FileListViewHeader>

          {images.length === 0 ? (
            <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Nenhuma imagem JPEG encontrada neste caso.</p>
          ) : viewMode === "grid" ? (
            <EvidenceFileGrid
              items={images}
              selected={(item) => selectedIds.has(item.id)}
              onSelect={(item) => toggleSelect(item.id)}
              maxHeight={imageSelectorListMaxHeight}
            />
          ) : (
            <div className="jpeg-compare-select-list" style={{ maxHeight: imageSelectorListMaxHeight }}>
              {images.map((img) => (
                <label key={img.id} className="jpeg-compare-select-item">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(img.id)}
                    onChange={() => toggleSelect(img.id)}
                  />
                  <span className="jpeg-compare-select-item__name">{img.original_filename}</span>
                </label>
              ))}
            </div>
          )}
        </AnalysisPanel>

        <JpegStructureMatrixSection
          caseId={caseId}
          questionedEvidences={selectedOrdered}
          tab={matrixTab}
          onTabChange={handleTabChange}
          selectedRefIds={selectedRefIds}
          onSelectedRefIdsChange={setSelectedRefIds}
        />

        <div style={{ margin: "0 0 1.25rem" }}>
          <ProcessButton
            onClick={calculate}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            disabled={!canCalculate}
            label={calculateLabel}
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
        {parseError && <MessageBox type="err" text={parseError} />}

        {matrixData && (
          <AnalysisPanel title="Matriz de similaridade estrutural">
            <p style={{ margin: "0 0 0.5rem", fontSize: "0.88rem" }}>
              Modo: {matrixData.mode === "with_reference" ? "padrões × questionados" : "questionados × questionados"} ·
              Referências: {matrixData.reference_count} · Questionados: {matrixData.questioned_count}
            </p>
            {matrixData.errors && matrixData.errors.length > 0 && (
              <MessageBox type="err" text={matrixData.errors.join(" · ")} />
            )}
            <JpegStructureMatchMatrix data={matrixData} />
            {matrixPngUrl && (
              <div style={{ marginTop: "1rem" }}>
                <p style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#6b7280" }}>
                  Prévia exportável da matriz
                </p>
                <img
                  src={matrixPngUrl}
                  alt="Matriz de similaridade JPEG"
                  style={{ width: "100%", maxWidth: 480, border: "1px solid #e5e7eb", borderRadius: 8 }}
                />
              </div>
            )}
            {renderMatrixDerivativeActions()}
          </AnalysisPanel>
        )}

        {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}

        {compareData && (
          <AnalysisPanel title="Estruturas JPEG — grade posicional">
            <div className="jpeg-compare-legend">
              <span className="jpeg-compare-legend__item jpeg-compare-legend__item--match">Convergente</span>
              <span className="jpeg-compare-legend__item jpeg-compare-legend__item--diverge">Divergente</span>
              {matrixTab === "with_reference" && (
                <span className="jpeg-compare-legend__hint">
                  Clique em um padrão (PAD) para ativá-lo · APP+ expande thumbnail · passe o mouse em DQT = matrizes
                </span>
              )}
              {matrixTab === "all_pairs" && (
                <span className="jpeg-compare-legend__hint">
                  Duplo clique na linha = referência · APP+ expande thumbnail · passe o mouse em DQT = matrizes
                </span>
              )}
            </div>

            {compareData.all_match && (
              <MessageBox
                type="ok"
                text={`Todas as estruturas coincidem com a referência (${compareData.reference_label ?? "referência"}).`}
              />
            )}

            {compareData.errors && compareData.errors.length > 0 && (
              <MessageBox type="err" text={compareData.errors.join(" · ")} />
            )}

            <JpegCompareErrorBoundary key={gridEpoch}>
              <JpegCompareGrid
                data={compareData}
                expandedThumbs={expandedThumbs}
                onPromoteReference={promoteToReference}
                onToggleThumb={toggleThumbExpand}
                onSelectReferencePattern={
                  matrixTab === "with_reference" ? selectReferencePattern : undefined
                }
                dqtHover={dqtTooltip.handlers}
              />
            </JpegCompareErrorBoundary>
            {renderGridDerivativeActions()}
          </AnalysisPanel>
        )}
      </div>
    </AnalysisPageShell>
  );
}

const btnPrimary = {
  padding: "0.5rem 1rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontWeight: 600,
  fontSize: "0.85rem",
} as const;

const btnSecondary = {
  padding: "0.5rem 1rem",
  background: "#f3f4f6",
  color: "#374151",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
} as const;
