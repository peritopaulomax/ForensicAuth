import type { LineageGraph, LineageNode, LineageOperation } from "@/services/evidence";
import EvidenceThumbnail from "@/components/EvidenceThumbnail";
import { referenceGroupListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

function shortId(value: string | null | undefined, chars = 8): string | null {
  if (!value) return null;
  return value.length > chars ? `${value.slice(0, chars)}…` : value;
}

function nodeMetaLines(node: LineageNode): string[] {
  const lines: string[] = [];
  if (node.technique) lines.push(node.technique);
  if (node.derivation_step) lines.push(node.derivation_step);
  if (node.source_job_id) lines.push(`job ${shortId(node.source_job_id)}`);
  if (node.procedure_summary && node.is_derived) {
    const summary =
      node.procedure_summary.length > 72
        ? `${node.procedure_summary.slice(0, 70)}…`
        : node.procedure_summary;
    lines.push(summary);
  }
  const outputs = node.derivation_outputs;
  if (outputs?.meta_classifier) {
    lines.push(`meta: ${String(outputs.meta_classifier)}`);
  }
  if (outputs?.reference_population_count != null) {
    lines.push(`pop. LR: ${String(outputs.reference_population_count)} bases`);
  }
  if (outputs?.reference_lr && typeof outputs.reference_lr === "object") {
    const lr = outputs.reference_lr as Record<string, unknown>;
    if (lr.log10_lr != null) lines.push(`log10 LR: ${String(lr.log10_lr)}`);
  }
  return lines;
}

function NodeCard({ node, compact }: { node: LineageNode; compact?: boolean }) {
  const w = compact ? 96 : 124;
  const metaLines = nodeMetaLines(node);
  const borderColor = node.is_synthetic ? "#7c3aed" : node.is_derived ? "#0369a1" : "#e5e7eb";
  const bg = node.is_synthetic ? "#f5f3ff" : node.is_derived ? "#f0f9ff" : "#fff";
  return (
    <div
      style={{
        border: node.is_synthetic || node.is_derived ? `2px solid ${borderColor}` : "1px solid #e5e7eb",
        borderRadius: 8,
        padding: compact ? "0.4rem" : "0.6rem",
        background: bg,
        minWidth: w,
        maxWidth: w + 40,
        textAlign: "center",
      }}
    >
      {node.is_synthetic ? (
        <span style={{ fontSize: compact ? "1.5rem" : "2rem" }}>📊</span>
      ) : node.file_type === "imagem" || node.file_type === "video" ? (
        <EvidenceThumbnail
          evidenceId={node.evidence_id}
          fallback={node.is_derived ? "🧬" : "🖼"}
          size={compact ? 44 : 56}
          showPlayBadge={node.file_type === "video"}
        />
      ) : (
        <span style={{ fontSize: compact ? "1.5rem" : "2rem" }}>{node.is_derived ? "🧬" : "📎"}</span>
      )}
      <div
        style={{
          fontSize: compact ? "0.65rem" : "0.72rem",
          fontWeight: 600,
          color: "#1a1a2e",
          marginTop: "0.3rem",
          wordBreak: "break-word",
          lineHeight: 1.2,
        }}
      >
        {node.original_filename.length > 20
          ? node.original_filename.slice(0, 18) + "…"
          : node.original_filename}
      </div>
      {metaLines.map((line, idx) => (
        <div
          key={`${node.evidence_id}-meta-${idx}`}
          style={{
            fontSize: "0.6rem",
            color: idx === 0 && node.technique ? "#0369a1" : "#6b7280",
            marginTop: "0.12rem",
            lineHeight: 1.25,
            fontWeight: idx === 0 && node.technique ? 600 : 400,
          }}
        >
          {line}
        </div>
      ))}
      {node.legacy_provenance && (
        <div style={{ fontSize: "0.58rem", color: "#b45309", marginTop: "0.12rem" }}>proveniencia legada</div>
      )}
      {node.derivation_outputs?.pce != null && (
        <div style={{ fontSize: "0.62rem", color: "#0369a1", marginTop: "0.15rem", fontWeight: 600 }}>
          PCE={String(node.derivation_outputs.pce)}
        </div>
      )}
    </div>
  );
}

function OperationMergeBox({ op, inputNodes }: { op: LineageOperation; inputNodes: LineageNode[] }) {
  const outputs = op.outputs as Record<string, unknown> | undefined;
  const lr = outputs?.reference_lr as Record<string, unknown> | undefined;
  return (
    <div
      style={{
        border: "2px dashed #0369a1",
        borderRadius: 10,
        padding: "0.75rem 1rem",
        background: "#f0f9ff",
        maxWidth: 520,
        margin: "0 auto",
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "#0369a1", marginBottom: "0.5rem" }}>
        ⊕ {op.label}
      </div>
      {op.derivation_step && (
        <div style={{ fontSize: "0.72rem", color: "#6b7280", marginBottom: "0.35rem" }}>{op.derivation_step}</div>
      )}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "0.75rem",
          marginBottom: "0.5rem",
        }}
      >
        {inputNodes.length === 0 && (op.input_count ?? op.inputs.length) > 0 && (
          <p style={{ fontSize: "0.75rem", color: "#b45309", margin: "0 0 0.5rem" }}>
            {op.input_count ?? op.inputs.length} insumo(s) referenciados (detalhe indisponivel no grafo)
          </p>
        )}
        {inputNodes.map((n) => (
          <div key={n.evidence_id} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <NodeCard node={n} compact />
            <span style={{ fontSize: "0.65rem", color: "#6b7280", marginTop: 4 }}>
              {op.inputs.find((i) => i.evidence_id === n.evidence_id)?.label || "insumo"}
            </span>
          </div>
        ))}
      </div>
      {outputs && (
        <div style={{ fontSize: "0.78rem", color: "#374151", textAlign: "left", marginTop: "0.35rem" }}>
          {outputs.mode != null && <div>Modo: {String(outputs.mode)}</div>}
          {outputs.matrix_metric != null && <div>Metrica: {String(outputs.matrix_metric)}</div>}
          {outputs.questioned_count != null && outputs.reference_count != null && (
            <div>
              Matriz: {String(outputs.questioned_count)}×{String(outputs.reference_count || outputs.questioned_count)}
            </div>
          )}
          {outputs.input_count != null && outputs.questioned_count == null && (
            <div>Insumos: {String(outputs.input_count)}</div>
          )}
          {outputs.sigma != null && <div>σ: {String(outputs.sigma)}</div>}
          {outputs.pce != null && <div>PCE: {String(outputs.pce)}</div>}
          {outputs.p_value != null && <div>p-value: {String(outputs.p_value)}</div>}
          {outputs.meta_classifier != null && <div>Meta-classificador: {String(outputs.meta_classifier)}</div>}
          {outputs.reference_population_count != null && (
            <div>Populacao LR: {String(outputs.reference_population_count)} subgrupos</div>
          )}
          {outputs.use_augmented_reference === true && <div>Augmentacao de referencia: sim</div>}
          {lr?.log10_lr != null && <div>log10 LR: {String(lr.log10_lr)}</div>}
          {lr?.lr != null && <div>LR: {String(lr.lr)}</div>}
        </div>
      )}
      <div style={{ fontSize: "1.1rem", color: "#0369a1", marginTop: "0.35rem" }}>↓</div>
    </div>
  );
}

function ConnectorArrow({ label, sublabel }: { label: string; sublabel?: string }) {
  return (
    <div style={{ textAlign: "center", padding: "0.35rem 0" }}>
      <div style={{ fontSize: "1.15rem", color: "#0369a1", lineHeight: 1 }}>↓</div>
      <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "#374151", maxWidth: 320, margin: "0 auto" }}>
        {label}
      </div>
      {sublabel && (
        <div style={{ fontSize: "0.65rem", color: "#6b7280", maxWidth: 320, margin: "0.15rem auto 0" }}>
          {sublabel}
        </div>
      )}
    </div>
  );
}

export default function DerivationDagView({ graph }: { graph: LineageGraph }) {
  const nodeById = new Map(graph.nodes.map((n) => [n.evidence_id, n]));
  const maxLayer = Math.max(0, ...graph.nodes.map((n) => n.layer ?? 0));
  const phases = graph.phases?.length
    ? graph.phases
    : Array.from({ length: maxLayer + 1 }, (_, layer) => ({
        layer,
        label: `Camada ${layer + 1}`,
        node_ids: graph.nodes.filter((n) => (n.layer ?? 0) === layer).map((n) => n.evidence_id),
        node_count: graph.nodes.filter((n) => (n.layer ?? 0) === layer).length,
      }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {graph.legacy_notes && graph.legacy_notes.length > 0 && (
        <div
          style={{
            padding: "0.6rem 0.75rem",
            borderRadius: 8,
            background: "#fffbeb",
            border: "1px solid #fcd34d",
            fontSize: "0.78rem",
            color: "#92400e",
          }}
        >
          {graph.legacy_notes.map((note, idx) => (
            <div key={`legacy-${idx}`}>{note}</div>
          ))}
        </div>
      )}
      {graph.derivation_groups?.map((group) => (
        <div
          key={group.derivation_group_id}
          style={{
            padding: "0.6rem 0.75rem",
            borderRadius: 8,
            background: "#f8fafc",
            border: "1px solid #e2e8f0",
            fontSize: "0.78rem",
            color: "#334155",
          }}
        >
          <strong>Pacote do mesmo job</strong> ({group.member_count} artefato(s) promovidos)
          {group.siblings.length > 0 && (
            <ul style={{ margin: "0.35rem 0 0", paddingLeft: "1.1rem" }}>
              {group.siblings.map((sibling) => (
                <li key={sibling.evidence_id}>{sibling.original_filename}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
      {graph.layout_label && (
        <p style={{ margin: "0 0 0.5rem", fontSize: "0.85rem", color: "#374151", textAlign: "center" }}>
          {graph.layout_label}
        </p>
      )}

      {phases.map((phase, phaseIdx) => {
        const layerNodes = phase.node_ids
          .map((id) => nodeById.get(id))
          .filter((n): n is LineageNode => Boolean(n));
        const opsInPhase = (graph.operations ?? []).filter(
          (op) => (nodeById.get(op.to_evidence_id)?.layer ?? 0) === phase.layer
        );
        const opTargetIds = new Set(opsInPhase.map((o) => o.to_evidence_id));
        const inputIdsInPhaseOps = new Set(
          opsInPhase.flatMap((o) => o.inputs.map((i) => i.evidence_id))
        );
        const displayNodes = opsInPhase.length
          ? layerNodes.filter(
              (n) => opTargetIds.has(n.evidence_id) && !inputIdsInPhaseOps.has(n.evidence_id)
            )
          : layerNodes.filter((n) => !inputIdsInPhaseOps.has(n.evidence_id));
        const manySources = layerNodes.length > 6 && opsInPhase.length === 0;
        const phaseTitle =
          phase.node_count != null && phase.node_count > 0 && phase.layer === 0
            ? `${phase.label} (${phase.node_count})`
            : phase.label;

        const prevPhase = phases[phaseIdx - 1];
        const singleEdgeFromPrev =
          prevPhase &&
          opsInPhase.length === 0 &&
          displayNodes.length === 1 &&
          prevPhase.node_ids.length >= 1
            ? graph.edges.find(
                (e) =>
                  e.to_evidence_id === displayNodes[0].evidence_id &&
                  prevPhase.node_ids.includes(e.from_evidence_id)
              )
            : undefined;

        return (
          <section
            key={`phase-${phase.layer}`}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: "0.75rem",
              background: "#fafafa",
            }}
          >
            <h4 style={{ margin: "0 0 0.6rem", fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>
              {phaseTitle}
            </h4>

            {singleEdgeFromPrev && (
              <ConnectorArrow
                label={singleEdgeFromPrev.procedure_summary || singleEdgeFromPrev.technique || "Derivacao"}
                sublabel={
                  [
                    singleEdgeFromPrev.derivation_step,
                    singleEdgeFromPrev.source_job_id
                      ? `job ${shortId(singleEdgeFromPrev.source_job_id)}`
                      : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || undefined
                }
              />
            )}

            {opsInPhase.map((op) => {
              const inputNodes = op.inputs
                .map((inp) => nodeById.get(inp.evidence_id))
                .filter((n): n is LineageNode => Boolean(n));
              return <OperationMergeBox key={op.id} op={op} inputNodes={inputNodes} />;
            })}

            {displayNodes.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  justifyContent: "center",
                  gap: "0.5rem",
                  marginTop: opsInPhase.length ? "0.5rem" : 0,
                  ...(manySources
                    ? { ...scrollableListStyle, maxHeight: referenceGroupListMaxHeight }
                    : {}),
                }}
              >
                {displayNodes.map((n) => (
                  <NodeCard key={n.evidence_id} node={n} compact={manySources || opsInPhase.length > 0} />
                ))}
              </div>
            )}

            {!opsInPhase.length && !singleEdgeFromPrev && phaseIdx < phases.length - 1 && (
              <ConnectorArrow label="↓" />
            )}
          </section>
        );
      })}

      {graph.operations &&
        graph.operations.length === 0 &&
        graph.edges.length === 1 && (
          <ConnectorArrow
            label={graph.edges[0].procedure_summary || graph.edges[0].technique || "Derivacao"}
            sublabel={
              [
                graph.edges[0].derivation_step,
                graph.edges[0].source_job_id ? `job ${shortId(graph.edges[0].source_job_id)}` : null,
              ]
                .filter(Boolean)
                .join(" · ") || undefined
            }
          />
        )}
    </div>
  );
}
