import { useEffect, useMemo, useState, type CSSProperties } from "react";
import UnderlineTabBar from "@/components/metadata/UnderlineTabBar";

export interface XmpSemanticProperty {
  name: string;
  value: string;
  hint?: string | null;
}

export interface XmpSemanticGroup {
  namespace_uri: string;
  namespace_label: string;
  properties: XmpSemanticProperty[];
}

export interface XmpStructuralNode {
  name: string;
  display_name?: string;
  node_type?: "element" | "property" | "container";
  namespace_uri?: string;
  namespace_label?: string;
  meta_attributes?: Record<string, string>;
  value?: string | null;
  hint?: string | null;
  path: string;
  children?: XmpStructuralNode[];
}

function nodeChildren(node: XmpStructuralNode): XmpStructuralNode[] {
  return Array.isArray(node.children) ? node.children : [];
}

function collectDefaultExpanded(node: XmpStructuralNode, acc = new Set<string>()): Set<string> {
  const children = nodeChildren(node);
  if (children.length === 0) return acc;
  acc.add(node.path);
  for (const child of children) {
    if (child.node_type !== "property") {
      collectDefaultExpanded(child, acc);
    }
  }
  return acc;
}

export interface XmpStructured {
  available?: boolean;
  source?: string | null;
  packet_xml?: string | null;
  packet_sha256?: string | null;
  structural_tree?: XmpStructuralNode | null;
  semantic_groups?: XmpSemanticGroup[];
  property_count?: number;
  warnings?: string[];
}

type XmpViewMode = "structural" | "semantic";

export default function XmpViewer({ structured }: { structured: XmpStructured }) {
  const [mode, setMode] = useState<XmpViewMode>("structural");
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["0"]));
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (structured.structural_tree) {
      setExpanded(collectDefaultExpanded(structured.structural_tree));
    }
  }, [structured.structural_tree]);

  const hasPacket = Boolean(structured.available && structured.packet_xml);
  const semanticGroups = structured.semantic_groups || [];
  const warnings = structured.warnings || [];

  const filteredGroups = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return semanticGroups;
    return semanticGroups
      .map((group) => ({
        ...group,
        properties: group.properties.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            p.value.toLowerCase().includes(q) ||
            (p.hint || "").toLowerCase().includes(q) ||
            group.namespace_label.toLowerCase().includes(q)
        ),
      }))
      .filter((g) => g.properties.length > 0);
  }, [semanticGroups, filter]);

  function toggle(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  if (!hasPacket) {
    return (
      <p style={{ color: "#9ca3af", fontSize: "0.85rem", margin: 0 }}>
        Nenhum pacote XMP encontrado neste arquivo.
      </p>
    );
  }

  return (
    <div>
      {warnings.length > 0 && (
        <div style={warnBoxStyle}>
          {warnings.map((w, i) => (
            <p key={i} style={{ margin: i ? "0.35rem 0 0" : 0 }}>
              {w}
            </p>
          ))}
        </div>
      )}

      <UnderlineTabBar
        groupLabel="Vista XMP"
        activeId={mode}
        onChange={(id) => setMode(id as XmpViewMode)}
        items={[
          {
            id: "structural",
            label: "Estrutural (árvore XML)",
            icon: "⎇",
            accentColor: "#1e40af",
          },
          {
            id: "semantic",
            label: "Semântica (por namespace)",
            icon: "◫",
            count: semanticGroups.length || undefined,
            accentColor: "#7c3aed",
          },
        ]}
      />

      {hasPacket && (
        <div
          style={{
            display: "flex",
            gap: "1rem",
            flexWrap: "wrap",
            fontSize: "0.78rem",
            color: "#6b7280",
            marginBottom: "0.75rem",
          }}
        >
          <span>
            Propriedades no pacote: <strong>{structured.property_count ?? 0}</strong>
          </span>
          {structured.source && (
            <span>
              Fonte: <strong>{structured.source}</strong>
            </span>
          )}
          {structured.packet_sha256 && (
            <span title={structured.packet_sha256}>
              SHA-256: <code style={codeStyle}>{structured.packet_sha256.slice(0, 16)}…</code>
            </span>
          )}
        </div>
      )}

      {mode === "semantic" && (
        <div>
          <input
            type="search"
            placeholder="Filtrar namespace ou propriedade…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={searchStyle}
          />
          {filteredGroups.length === 0 ? (
            <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>
              Nenhuma propriedade semântica corresponde ao filtro.
            </p>
          ) : (
            filteredGroups.map((group) => (
              <div key={group.namespace_uri || group.namespace_label} style={groupBoxStyle}>
                <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.88rem", color: "#1e3a5f" }}>
                  {group.namespace_label}
                </h4>
                <p style={{ margin: "0 0 0.5rem", fontSize: "0.72rem", color: "#9ca3af", wordBreak: "break-all" }}>
                  {group.namespace_uri}
                </p>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                  <thead>
                    <tr style={{ background: "#f9fafb" }}>
                      <th style={thStyle}>Propriedade</th>
                      <th style={thStyle}>Valor</th>
                      <th style={thStyle}>Significado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.properties.map((prop) => (
                      <tr key={`${group.namespace_uri}-${prop.name}`} style={{ borderTop: "1px solid #f3f4f6" }}>
                        <td style={{ ...tdStyle, fontFamily: "monospace", color: "#1e40af" }}>{prop.name}</td>
                        <td style={{ ...tdStyle, wordBreak: "break-word" }}>{prop.value}</td>
                        <td style={{ ...tdStyle, color: "#6b7280", fontSize: "0.75rem" }}>{prop.hint || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          )}
        </div>
      )}

      {mode === "structural" && (
        <div>
          {!hasPacket ? (
            <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Pacote XMP indisponível.</p>
          ) : (
            <>
              <div className="metadata-tree-toolbar">
                <span className="metadata-tree-toolbar__hint">
                  Árvore RDF/XML — atributos e elementos aninhados como nós separados
                </span>
                <div className="metadata-tree-toolbar__actions">
                  <button
                    type="button"
                    className="metadata-tree-toolbar__btn metadata-tree-toolbar__btn--primary"
                    onClick={() =>
                      structured.structural_tree &&
                      setExpanded(collectDefaultExpanded(structured.structural_tree))
                    }
                  >
                    ⊞ Expandir tudo
                  </button>
                  <button
                    type="button"
                    className="metadata-tree-toolbar__btn metadata-tree-toolbar__btn--secondary"
                    onClick={() => setExpanded(new Set(["0"]))}
                  >
                    ⊟ Recolher
                  </button>
                </div>
              </div>
              <div style={treeScrollStyle}>
                {structured.structural_tree && (
                  <StructuralNodeRow
                    node={structured.structural_tree}
                    depth={0}
                    expanded={expanded}
                    onToggle={toggle}
                  />
                )}
              </div>
              <h4 style={{ fontSize: "0.88rem", margin: "1rem 0 0.5rem", color: "#374151" }}>
                XML do pacote XMP (formatado)
              </h4>
              {structured.packet_sha256 && (
                <p style={{ fontSize: "0.75rem", color: "#6b7280", margin: "0 0 0.5rem" }}>
                  SHA-256 do pacote: <code style={codeStyle}>{structured.packet_sha256}</code>
                </p>
              )}
              <pre style={xmlPreStyle}>{structured.packet_xml}</pre>
            </>
          )}
        </div>
      )}

    </div>
  );
}

function StructuralNodeRow({
  node,
  depth,
  expanded,
  onToggle,
}: {
  node: XmpStructuralNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
}) {
  const isProperty = node.node_type === "property";
  const children = nodeChildren(node);
  const hasChildren = children.length > 0;
  const isOpen = expanded.has(node.path);
  const label = node.display_name || node.name;
  const isLeafValue = !isProperty && !hasChildren && Boolean(node.value);

  if (isProperty || isLeafValue) {
    return (
      <div
        style={{
          marginLeft: depth * 16 + 22,
          padding: "3px 6px",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
          fontSize: "0.76rem",
          borderLeft: "2px solid #dbeafe",
        }}
      >
        <div style={propertyRowStyle}>
          <span style={propertyLabelStyle}>{label}</span>
          <span style={{ color: "#9ca3af", flexShrink: 0 }}>→</span>
          <span style={propertyValueStyle}>{node.value}</span>
        </div>
        {node.hint && <div style={propertyHintStyle}>{node.hint}</div>}
      </div>
    );
  }

  const nodeColor =
    node.node_type === "container" ? "#b45309" : node.name === "Description" ? "#7c3aed" : "#0f766e";

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 6,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
          fontSize: "0.77rem",
          padding: "3px 4px",
          marginLeft: depth * 16,
          borderRadius: 4,
          background: depth === 0 ? "#f9fafb" : "transparent",
        }}
      >
        <button
          type="button"
          disabled={!hasChildren}
          onClick={() => hasChildren && onToggle(node.path)}
          style={{
            border: "none",
            background: "transparent",
            cursor: hasChildren ? "pointer" : "default",
            width: 16,
            textAlign: "center",
            color: "#4b5563",
            padding: 0,
            flexShrink: 0,
          }}
        >
          {hasChildren ? (isOpen ? "▼" : "▶") : "·"}
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span style={{ color: nodeColor, fontWeight: 600 }}>{label}</span>
          {node.namespace_label && node.namespace_label !== node.namespace_uri && (
            <span style={{ color: "#9ca3af", marginLeft: 6, fontSize: "0.72rem" }}>
              ({node.namespace_label})
            </span>
          )}
          {node.node_type === "container" && (
            <span style={{ color: "#b45309", marginLeft: 6, fontSize: "0.7rem" }}>[container]</span>
          )}
          {Object.entries(node.meta_attributes || {}).map(([k, v]) => (
            <span key={k} style={{ color: "#0369a1", marginLeft: 6, fontSize: "0.72rem" }}>
              @{k}="{v.length > 48 ? `${v.slice(0, 48)}…` : v}"
            </span>
          ))}
          {node.value && (
            <span style={{ color: "#166534", marginLeft: 6 }}>= {node.value}</span>
          )}
          {node.hint && node.name !== "Description" && (
            <div style={{ color: "#6b7280", fontSize: "0.7rem", marginTop: 2 }}>{node.hint}</div>
          )}
          {hasChildren && (
            <span style={{ color: "#9ca3af", marginLeft: 8, fontSize: "0.68rem" }}>
              ({children.length} {children.length === 1 ? "filho" : "filhos"})
            </span>
          )}
        </div>
      </div>
      {hasChildren &&
        isOpen &&
        children.map((child) => (
          <StructuralNodeRow
            key={child.path}
            node={child}
            depth={depth + 1}
            expanded={expanded}
            onToggle={onToggle}
          />
        ))}
    </div>
  );
}

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "0.45rem 0.6rem",
  fontWeight: 600,
  color: "#374151",
};

const tdStyle: CSSProperties = {
  padding: "0.4rem 0.6rem",
  verticalAlign: "top",
};

const searchStyle: CSSProperties = {
  width: "100%",
  maxWidth: 360,
  marginBottom: "0.75rem",
  padding: "0.45rem 0.65rem",
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  fontSize: "0.85rem",
};

const groupBoxStyle: CSSProperties = {
  marginBottom: "1rem",
  padding: "0.75rem",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  background: "#fafafa",
};

const warnBoxStyle: CSSProperties = {
  background: "#fffbeb",
  border: "1px solid #fcd34d",
  borderRadius: 8,
  padding: "0.65rem 0.85rem",
  marginBottom: "0.75rem",
  fontSize: "0.82rem",
  color: "#92400e",
};

const treeScrollStyle: CSSProperties = {
  maxHeight: 420,
  overflow: "auto",
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  padding: "0.5rem",
  marginBottom: "0.75rem",
  background: "#fff",
};

const propertyRowStyle: CSSProperties = {
  display: "flex",
  gap: 8,
  alignItems: "baseline",
  flexWrap: "nowrap",
  minWidth: 0,
};

const propertyLabelStyle: CSSProperties = {
  color: "#1d4ed8",
  fontWeight: 600,
  flexShrink: 0,
  whiteSpace: "nowrap",
};

const propertyValueStyle: CSSProperties = {
  color: "#166534",
  whiteSpace: "nowrap",
  overflowX: "auto",
  minWidth: 0,
  flex: "1 1 auto",
};

const propertyHintStyle: CSSProperties = {
  color: "#9ca3af",
  fontSize: "0.68rem",
  marginTop: 2,
  paddingLeft: 2,
};

const xmlPreStyle: CSSProperties = {
  maxHeight: 360,
  overflow: "auto",
  background: "#0f172a",
  color: "#e2e8f0",
  padding: "0.85rem",
  borderRadius: 6,
  fontSize: "0.75rem",
  lineHeight: 1.45,
  margin: 0,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const codeStyle: CSSProperties = {
  fontFamily: "ui-monospace, monospace",
  fontSize: "0.72rem",
  background: "#f3f4f6",
  padding: "0.1rem 0.3rem",
  borderRadius: 4,
};
