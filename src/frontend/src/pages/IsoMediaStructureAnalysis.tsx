import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import MediaEvidenceSelector from "@/components/MediaEvidenceSelector";
import { useForensicJob } from "@/hooks/useForensicJob";
import { listCaseEvidences, saveDerivative } from "@/services/evidence";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import type { Evidence } from "@/types/api";
import { scrollableListStyle } from "@/styles/listHeights";
import {
  collectRootPaths,
  computeIsoBmffTreeDiff,
  DIFF_ROW_BG,
  DIFF_ROW_BORDER,
  type NodeDiffStatus,
  type TreeDiffResult,
  type TreeNode,
} from "@/utils/isoBmffTreeDiff";

type ViewMode = "single" | "compare";
type DetailTab = "metadata" | "special";

type SpecialAtom = {
  id: string;
  path: string;
  offset: number;
  size: number;
  preview_mode?: string;
  preview?: string;
  preview_hex_dump?: string;
  preview_truncated?: boolean;
  fields?: Record<string, unknown>;
};

type ParsedIsoBmff = {
  tree: TreeNode[];
  metadata: Record<string, unknown>;
  udtaAtoms: SpecialAtom[];
  metaAtoms: SpecialAtom[];
  result: Record<string, unknown>;
  jobId: string;
};

const METADATA_SCROLL_HEIGHT = 380;
const META_ATOM_SCROLL_HEIGHT = 300;
const TREE_PANEL_HEIGHT = 460;

function parseJobResult(jobId: string, jobResult: Record<string, unknown>): ParsedIsoBmff {
  return {
    tree: Array.isArray(jobResult.tree) ? (jobResult.tree as TreeNode[]) : [],
    metadata:
      jobResult.metadata && typeof jobResult.metadata === "object"
        ? (jobResult.metadata as Record<string, unknown>)
        : {},
    udtaAtoms: Array.isArray(jobResult.udta_atoms) ? (jobResult.udta_atoms as SpecialAtom[]) : [],
    metaAtoms: Array.isArray(jobResult.meta_atoms) ? (jobResult.meta_atoms as SpecialAtom[]) : [],
    result: jobResult,
    jobId,
  };
}

function evidenceLabel(videos: Evidence[], id: string | null): string {
  if (!id) return "—";
  return videos.find((v) => v.id === id)?.original_filename || id.slice(0, 8);
}

export default function IsoMediaStructureAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [videos, setVideos] = useState<Evidence[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("single");

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [leftId, setLeftId] = useState<string | null>(null);
  const [rightId, setRightId] = useState<string | null>(null);

  const [parsedSingle, setParsedSingle] = useState<ParsedIsoBmff | null>(null);
  const [parsedLeft, setParsedLeft] = useState<ParsedIsoBmff | null>(null);
  const [parsedRight, setParsedRight] = useState<ParsedIsoBmff | null>(null);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [detailTab, setDetailTab] = useState<DetailTab>("metadata");

  const [savingDerivative, setSavingDerivative] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const leftTreeRef = useRef<HTMLDivElement>(null);
  const rightTreeRef = useRef<HTMLDivElement>(null);

  const singleJob = useForensicJob();
  const leftJob = useForensicJob();
  const rightJob = useForensicJob();

  useEffect(() => {
    if (!caseId) return;
    listCaseEvidences(caseId)
      .then((evs) => {
        const list = filterForensicAuthEvidences(evs).filter((e) => e.file_type === "video");
        setVideos(list);
        if (list.length > 0) {
          setSelectedId(list[0].id);
          setLeftId(list[0].id);
          setRightId(list.length > 1 ? list[1].id : list[0].id);
        }
      })
      .catch(() => setVideos([]));
  }, [caseId]);

  const clearResults = useCallback(() => {
    singleJob.reset();
    leftJob.reset();
    rightJob.reset();
    setParsedSingle(null);
    setParsedLeft(null);
    setParsedRight(null);
    setExpanded(new Set());
    setSaveMessage(null);
  }, [singleJob, leftJob, rightJob]);

  function switchViewMode(mode: ViewMode) {
    setViewMode(mode);
    clearResults();
  }

  async function processSingle() {
    if (!selectedId) return;
    clearResults();
    try {
      const { jobId, result: jobResult } = await singleJob.runAnalysis(selectedId, "isomedia_parser", {});
      if (!jobResult) return;
      const parsed = parseJobResult(jobId, jobResult);
      setParsedSingle(parsed);
      setExpanded(new Set(collectRootPaths(parsed.tree)));
    } catch {
      /* handled by hook */
    }
  }

  async function processCompare() {
    if (!leftId || !rightId) return;
    clearResults();
    try {
      const [resA, resB] = await Promise.all([
        leftJob.runAnalysis(leftId, "isomedia_parser", {}),
        rightJob.runAnalysis(rightId, "isomedia_parser", {}),
      ]);
      if (!resA.result || !resB.result) return;
      const left = parseJobResult(resA.jobId, resA.result);
      const right = parseJobResult(resB.jobId, resB.result);
      setParsedLeft(left);
      setParsedRight(right);
      setExpanded(new Set([...collectRootPaths(left.tree), ...collectRootPaths(right.tree)]));
    } catch {
      /* handled by hooks */
    }
  }

  const toggleNode = useCallback(
    (path: string) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        return next;
      });
    },
    []
  );

  const scrollToPath = useCallback((path: string, side: "left" | "right") => {
    const container = side === "left" ? rightTreeRef.current : leftTreeRef.current;
    if (!container) return;
    const el = container.querySelector(`[data-tree-path="${CSS.escape(path)}"]`);
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, []);

  const treeDiff: TreeDiffResult | null = useMemo(() => {
    if (!parsedLeft || !parsedRight) return null;
    return computeIsoBmffTreeDiff(parsedLeft.tree, parsedRight.tree);
  }, [parsedLeft, parsedRight]);

  const compareRunning = leftJob.running || rightJob.running;
  const compareProgress = Math.round((leftJob.progress + rightJob.progress) / 2);
  const compareProgressLabel =
    leftJob.progressLabel && rightJob.progressLabel
      ? `${leftJob.progressLabel} · ${rightJob.progressLabel}`
      : leftJob.progressLabel || rightJob.progressLabel || "Processando…";
  const compareError = leftJob.error || rightJob.error;

  async function handleSaveDerivative(jobId: string, artifactFilename: string, label: string) {
    if (!jobId) return;
    const key = `${jobId}:${artifactFilename}`;
    setSavingDerivative(key);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: jobId,
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

  function derivativeActions(
    jobId: string | null,
    artifactFilename: string,
    label: string,
    text = "Salvar em derivados"
  ) {
    if (!jobId) return null;
    const key = `${jobId}:${artifactFilename}`;
    return (
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
        <button
          type="button"
          style={btnPrimary}
          disabled={!!savingDerivative}
          onClick={() => handleSaveDerivative(jobId, artifactFilename, label)}
        >
          {savingDerivative === key ? "Salvando…" : text}
        </button>
        <button type="button" style={btnSecondary} onClick={() => navigate(`/cases/${caseId}?tab=derivados`)}>
          Abrir derivados
        </button>
      </div>
    );
  }

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="Video — Parser ISO BMFF"
      subtitle="Extracao da arvore de atoms/boxes, metadados amplos, udta/meta e comparacao lado a lado."
    >
      <AnalysisPanel title="Modo de visualizacao">
        <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap", alignItems: "center" }}>
          <label style={radioLabelStyle}>
            <input
              type="radio"
              name="isom-view-mode"
              checked={viewMode === "single"}
              onChange={() => switchViewMode("single")}
            />
            Uma evidencia
          </label>
          <label style={radioLabelStyle}>
            <input
              type="radio"
              name="isom-view-mode"
              checked={viewMode === "compare"}
              onChange={() => switchViewMode("compare")}
            />
            Comparar lado a lado
          </label>
        </div>
      </AnalysisPanel>

      {viewMode === "single" ? (
        <>
          <AnalysisPanel title="Evidencia de video">
            <MediaEvidenceSelector
              caseId={caseId}
              fileType="video"
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                clearResults();
              }}
              radioName="isomedia-single"
            />
            <div style={{ marginTop: "1rem" }}>
              <ProcessButton
                onClick={processSingle}
                disabled={!selectedId}
                running={singleJob.running}
                progress={singleJob.progress}
                progressLabel={singleJob.progressLabel}
                label="Extrair estrutura ISO BMFF"
              />
            </div>
            {singleJob.error && <MessageBox type="err" text={singleJob.error} />}
          </AnalysisPanel>

          {parsedSingle && (
            <>
              <SummaryPanel result={parsedSingle.result} udtaCount={parsedSingle.udtaAtoms.length} metaCount={parsedSingle.metaAtoms.length} />
              <AnalysisPanel title="Arvore hierarquica de atoms/boxes">
                <p style={hintStyle}>Clique no triangulo para expandir/recolher. Offsets e tamanhos em bytes.</p>
                <div style={treeScrollBoxStyle}>
                  {parsedSingle.tree.map((node) => (
                    <TreeNodeRow key={node.path} node={node} depth={0} expanded={expanded} onToggle={toggleNode} />
                  ))}
                </div>
                {derivativeActions(parsedSingle.jobId, "isom_tree.txt", "isomedia_parser_tree_txt", "Salvar arvore TXT")}
                {derivativeActions(parsedSingle.jobId, "isom_tree.json", "isomedia_parser_tree_json", "Salvar arvore JSON")}
              </AnalysisPanel>

              <AnalysisPanel title="Metadados estruturais">
                <div style={metadataScrollBoxStyle}>
                  <pre style={metadataPreStyle}>{JSON.stringify(parsedSingle.metadata, null, 2) || "(sem conteudo)"}</pre>
                </div>
                {derivativeActions(parsedSingle.jobId, "isom_metadata.txt", "isomedia_parser_metadata_txt", "Salvar metadados TXT")}
                {derivativeActions(parsedSingle.jobId, "isom_metadata.json", "isomedia_parser_metadata_json", "Salvar metadados JSON")}
              </AnalysisPanel>

              <AnalysisPanel title="Busca em atoms udta e meta">
                <AtomSection title="Atoms udta" atoms={parsedSingle.udtaAtoms} />
                <AtomSection title="Atoms meta" atoms={parsedSingle.metaAtoms} maxHeight={META_ATOM_SCROLL_HEIGHT} />
                {derivativeActions(parsedSingle.jobId, "udta_atoms.json", "isomedia_parser_udta_atoms", "Salvar relatorio udta")}
                {derivativeActions(parsedSingle.jobId, "meta_atoms.json", "isomedia_parser_meta_atoms", "Salvar relatorio meta")}
                {derivativeActions(parsedSingle.jobId, "isom_structure_graph.json", "isomedia_parser_graph_json", "Salvar grafo JSON")}
              </AnalysisPanel>
            </>
          )}
        </>
      ) : (
        <>
          <AnalysisPanel title="Comparar duas evidencias">
            <div style={compareSelectGrid}>
              <div>
                <MediaEvidenceSelector
                  caseId={caseId}
                  fileType="video"
                  selectedId={leftId}
                  onSelect={(id) => {
                    setLeftId(id);
                    clearResults();
                  }}
                  radioName="isomedia-left"
                  title="Arquivo A (esquerda)"
                />
              </div>
              <div>
                <MediaEvidenceSelector
                  caseId={caseId}
                  fileType="video"
                  selectedId={rightId}
                  onSelect={(id) => {
                    setRightId(id);
                    clearResults();
                  }}
                  radioName="isomedia-right"
                  title="Arquivo B (direita)"
                />
              </div>
            </div>

            {leftId && rightId && leftId === rightId && (
              <p style={infoBannerStyle}>
                Mesma evidencia selecionada nos dois lados — a comparacao estrutural deve ser identica (util para
                verificar reprodutibilidade).
              </p>
            )}

            <div style={{ marginTop: "1rem" }}>
              <ProcessButton
                onClick={processCompare}
                disabled={!leftId || !rightId}
                running={compareRunning}
                progress={compareProgress}
                progressLabel={compareProgressLabel}
                label="Comparar estruturas ISO BMFF"
              />
            </div>
            {compareError && <MessageBox type="err" text={compareError} />}
          </AnalysisPanel>

          {parsedLeft && parsedRight && treeDiff && (
            <>
              <AnalysisPanel title="Resumo da comparacao">
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem 1.25rem", fontSize: "0.88rem" }}>
                  <span>
                    <DiffBadge status="only_a" /> {treeDiff.summary.onlyA} so em A
                  </span>
                  <span>
                    <DiffBadge status="only_b" /> {treeDiff.summary.onlyB} so em B
                  </span>
                  <span>
                    <DiffBadge status="size_diff" /> {treeDiff.summary.sizeDiff} tamanho diferente
                  </span>
                  <span style={{ color: "#6b7280" }}>{treeDiff.summary.same} identicos (path + size)</span>
                </div>
                <div style={{ marginTop: "0.75rem", fontSize: "0.78rem", color: "#6b7280" }}>
                  Expandir/recolher afeta os dois paineis ao mesmo tempo. Clique numa linha para rolar o painel oposto
                  ate o mesmo path.
                </div>
              </AnalysisPanel>

              <AnalysisPanel title="Arvores lado a lado">
                <div style={compareTreeGrid}>
                  <div>
                    <h4 style={columnTitleStyle}>A — {evidenceLabel(videos, leftId)}</h4>
                    <p style={hintStyle}>
                      Boxes: {Number(parsedLeft.result.box_count || 0)} · udta: {parsedLeft.udtaAtoms.length} · meta:{" "}
                      {parsedLeft.metaAtoms.length}
                    </p>
                    <div ref={leftTreeRef} style={treeScrollBoxStyle}>
                      {parsedLeft.tree.map((node) => (
                        <TreeNodeRow
                          key={node.path}
                          node={node}
                          depth={0}
                          expanded={expanded}
                          onToggle={toggleNode}
                          diffLookup={treeDiff.leftStatus}
                          onAlignPath={(path) => scrollToPath(path, "left")}
                        />
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 style={columnTitleStyle}>B — {evidenceLabel(videos, rightId)}</h4>
                    <p style={hintStyle}>
                      Boxes: {Number(parsedRight.result.box_count || 0)} · udta: {parsedRight.udtaAtoms.length} · meta:{" "}
                      {parsedRight.metaAtoms.length}
                    </p>
                    <div ref={rightTreeRef} style={treeScrollBoxStyle}>
                      {parsedRight.tree.map((node) => (
                        <TreeNodeRow
                          key={node.path}
                          node={node}
                          depth={0}
                          expanded={expanded}
                          onToggle={toggleNode}
                          diffLookup={treeDiff.rightStatus}
                          onAlignPath={(path) => scrollToPath(path, "right")}
                        />
                      ))}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.75rem" }}>
                  {derivativeActions(parsedLeft.jobId, "isom_tree.json", "isomedia_parser_tree_json_a", "Salvar arvore A (JSON)")}
                  {derivativeActions(parsedRight.jobId, "isom_tree.json", "isomedia_parser_tree_json_b", "Salvar arvore B (JSON)")}
                </div>
              </AnalysisPanel>

              <AnalysisPanel title="Detalhes">
                <div style={tabBarStyle}>
                  <button
                    type="button"
                    style={detailTab === "metadata" ? tabActiveStyle : tabInactiveStyle}
                    onClick={() => setDetailTab("metadata")}
                  >
                    Metadados
                  </button>
                  <button
                    type="button"
                    style={detailTab === "special" ? tabActiveStyle : tabInactiveStyle}
                    onClick={() => setDetailTab("special")}
                  >
                    udta / meta
                  </button>
                </div>

                {detailTab === "metadata" ? (
                  <div style={compareTreeGrid}>
                    <div>
                      <h4 style={columnTitleStyle}>Metadados A</h4>
                      <div style={metadataScrollBoxStyle}>
                        <pre style={metadataPreStyle}>{JSON.stringify(parsedLeft.metadata, null, 2) || "(vazio)"}</pre>
                      </div>
                    </div>
                    <div>
                      <h4 style={columnTitleStyle}>Metadados B</h4>
                      <div style={metadataScrollBoxStyle}>
                        <pre style={metadataPreStyle}>{JSON.stringify(parsedRight.metadata, null, 2) || "(vazio)"}</pre>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={compareTreeGrid}>
                    <div>
                      <AtomSection title="Atoms udta (A)" atoms={parsedLeft.udtaAtoms} maxHeight={200} />
                      <AtomSection title="Atoms meta (A)" atoms={parsedLeft.metaAtoms} maxHeight={META_ATOM_SCROLL_HEIGHT} />
                    </div>
                    <div>
                      <AtomSection title="Atoms udta (B)" atoms={parsedRight.udtaAtoms} maxHeight={200} />
                      <AtomSection title="Atoms meta (B)" atoms={parsedRight.metaAtoms} maxHeight={META_ATOM_SCROLL_HEIGHT} />
                    </div>
                  </div>
                )}
              </AnalysisPanel>
            </>
          )}
        </>
      )}

      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
    </AnalysisPageShell>
  );
}

function SummaryPanel({
  result,
  udtaCount,
  metaCount,
}: {
  result: Record<string, unknown>;
  udtaCount: number;
  metaCount: number;
}) {
  return (
    <AnalysisPanel title="Resumo">
      <p style={{ margin: 0, fontSize: "0.88rem" }}>
        Boxes: {Number(result.box_count || 0)} · Profundidade: {Number(result.depth || 0)} · udta: {udtaCount} · meta:{" "}
        {metaCount}
      </p>
    </AnalysisPanel>
  );
}

function DiffBadge({ status }: { status: NodeDiffStatus }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: 2,
        marginRight: 4,
        verticalAlign: "middle",
        background: DIFF_ROW_BG[status] === "transparent" ? "#f3f4f6" : DIFF_ROW_BG[status],
        border: `1px solid ${DIFF_ROW_BORDER[status] === "transparent" ? "#d1d5db" : DIFF_ROW_BORDER[status]}`,
      }}
    />
  );
}

function TreeNodeRow({
  node,
  depth,
  expanded,
  onToggle,
  diffLookup,
  onAlignPath,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  diffLookup?: Map<string, NodeDiffStatus>;
  onAlignPath?: (path: string) => void;
}) {
  const children = node.children || [];
  const hasChildren = children.length > 0;
  const isOpen = expanded.has(node.path);
  const indent = depth * 18;
  const diffStatus = diffLookup?.get(node.path);
  const rowBg = diffStatus ? DIFF_ROW_BG[diffStatus] : "transparent";
  const rowBorder = diffStatus ? DIFF_ROW_BORDER[diffStatus] : "transparent";

  return (
    <div>
      <div
        data-tree-path={node.path}
        role={onAlignPath ? "button" : undefined}
        tabIndex={onAlignPath ? 0 : undefined}
        onClick={onAlignPath ? () => onAlignPath(node.path) : undefined}
        onKeyDown={
          onAlignPath
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") onAlignPath(node.path);
              }
            : undefined
        }
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
          fontSize: "0.77rem",
          padding: "2px 4px",
          marginLeft: indent,
          borderRadius: 4,
          background: depth === 0 && !diffStatus ? "#f9fafb" : rowBg,
          border: diffStatus && diffStatus !== "same" ? `1px solid ${rowBorder}` : "1px solid transparent",
          cursor: onAlignPath ? "pointer" : "default",
        }}
        title={onAlignPath ? "Clique para alinhar painel oposto" : undefined}
      >
        <button
          type="button"
          disabled={!hasChildren}
          onClick={(e) => {
            e.stopPropagation();
            if (hasChildren) onToggle(node.path);
          }}
          style={{
            border: "none",
            background: "transparent",
            cursor: hasChildren ? "pointer" : "default",
            width: 18,
            textAlign: "center",
            color: "#4b5563",
            padding: 0,
          }}
          title={hasChildren ? "Expandir/recolher" : "Sem filhos"}
        >
          {hasChildren ? (isOpen ? "▼" : "▶") : "·"}
        </button>
        <span style={{ fontWeight: 700 }}>{node.type}</span>
        <span style={{ color: "#6b7280" }}>offset={node.offset}</span>
        <span style={{ color: "#6b7280" }}>size={node.size}</span>
      </div>
      {hasChildren &&
        isOpen &&
        children.map((child) => (
          <TreeNodeRow
            key={child.path}
            node={child}
            depth={depth + 1}
            expanded={expanded}
            onToggle={onToggle}
            diffLookup={diffLookup}
            onAlignPath={onAlignPath}
          />
        ))}
    </div>
  );
}

function AtomSection({ title, atoms, maxHeight = 220 }: { title: string; atoms: SpecialAtom[]; maxHeight?: number }) {
  return (
    <div style={{ marginBottom: "1rem" }}>
      <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.9rem", color: "#374151" }}>
        {title} ({atoms.length})
      </h4>
      {atoms.length === 0 ? (
        <p style={{ margin: 0, fontSize: "0.82rem", color: "#9ca3af" }}>Nenhum atom encontrado.</p>
      ) : (
        <div style={{ ...scrollableListStyle, maxHeight, border: "1px solid #e5e7eb", borderRadius: 6, padding: 8 }}>
          {atoms.map((atom) => (
            <div key={atom.id} style={{ marginBottom: 10, paddingBottom: 8, borderBottom: "1px dashed #e5e7eb" }}>
              <div style={{ fontSize: "0.8rem", color: "#374151", marginBottom: 4 }}>
                <strong>{atom.path}</strong> · offset={atom.offset} · size={atom.size}
                {atom.preview_mode === "text" && atom.preview ? (
                  <span style={{ display: "block", marginTop: 4, color: "#6b7280" }}>
                    Texto: {atom.preview}
                  </span>
                ) : null}
              </div>
              {atom.preview_hex_dump ? (
                <pre style={hexDumpStyle}>{atom.preview_hex_dump}</pre>
              ) : (
                <pre style={atomPreviewStyle}>
                  [{atom.preview_mode || "n/a"}] {atom.preview || "(vazio)"}
                </pre>
              )}
              {atom.preview_truncated ? (
                <p style={{ margin: "4px 0 0", fontSize: "0.75rem", color: "#9ca3af" }}>
                  Amostra truncada — veja udta_atoms.json nos derivados para dump completo.
                </p>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const hintStyle = { fontSize: "0.82rem", color: "#6b7280", marginTop: 0, marginBottom: "0.5rem" } as const;

const radioLabelStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  fontSize: "0.88rem",
  cursor: "pointer",
} as const;

const infoBannerStyle = {
  margin: "0.75rem 0 0",
  padding: "0.55rem 0.75rem",
  background: "#eff6ff",
  color: "#1e40af",
  borderRadius: 6,
  fontSize: "0.84rem",
} as const;

const compareSelectGrid = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: "1rem",
} as const;

const compareTreeGrid = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: "1rem",
  alignItems: "start",
} as const;

const columnTitleStyle = { margin: "0 0 0.35rem", fontSize: "0.88rem", color: "#111827" } as const;

const treeScrollBoxStyle = {
  ...scrollableListStyle,
  maxHeight: TREE_PANEL_HEIGHT,
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  padding: 8,
} as const;

const metadataScrollBoxStyle = {
  ...scrollableListStyle,
  maxHeight: METADATA_SCROLL_HEIGHT,
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  background: "#f9fafb",
} as const;

const metadataPreStyle = {
  margin: 0,
  padding: "0.85rem 1rem",
  fontSize: "0.76rem",
  lineHeight: 1.45,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  whiteSpace: "pre-wrap" as const,
  wordBreak: "break-word" as const,
} as const;

const tabBarStyle = { display: "flex", gap: 8, marginBottom: "0.75rem" } as const;

const tabActiveStyle = {
  padding: "0.35rem 0.75rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
} as const;

const tabInactiveStyle = {
  padding: "0.35rem 0.75rem",
  background: "#f3f4f6",
  color: "#374151",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
} as const;

const atomPreviewStyle = {
  margin: 0,
  padding: "0.55rem 0.65rem",
  fontSize: "0.74rem",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  background: "#f9fafb",
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  whiteSpace: "pre-wrap" as const,
  wordBreak: "break-word" as const,
} as const;

const hexDumpStyle = {
  margin: 0,
  padding: "0.6rem 0.75rem",
  fontSize: "0.72rem",
  lineHeight: 1.35,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  whiteSpace: "pre" as const,
  overflowX: "auto" as const,
  background: "#1e293b",
  color: "#e2e8f0",
  border: "1px solid #334155",
  borderRadius: 6,
} as const;

const btnPrimary = {
  padding: "0.45rem 0.9rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
} as const;

const btnSecondary = {
  padding: "0.45rem 0.9rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
} as const;
