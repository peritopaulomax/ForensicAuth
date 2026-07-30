import MetadataTagTable, { type MetadataTag } from "@/components/metadata/MetadataTagTable";

export interface C2paStructured {
  available?: boolean;
  present?: boolean;
  engine?: string | null;
  reason?: string;
  error?: string;
  is_valid?: boolean | null;
  validation_state?: string | null;
  validation_codes?: string[];
  claim_generator?: string | null;
  title?: string | null;
  format?: string | null;
  active_manifest?: string | null;
  manifest_count?: number;
  ingredient_count?: number;
  actions?: Array<{
    action?: string;
    software_agent?: string;
    digital_source_type?: string;
    when?: string;
  }>;
  signature_info?: {
    alg?: string | null;
    issuer?: string | null;
    common_name?: string | null;
    time?: string | null;
  };
  sdk_version?: string | null;
  trust_anchors_configured?: boolean;
}

function statusLabel(structured: C2paStructured): { text: string; color: string } {
  if (!structured.available) {
    return { text: "Motor indisponível", color: "#b45309" };
  }
  if (!structured.present) {
    return { text: "Ausente", color: "#6b7280" };
  }
  if (structured.is_valid === false) {
    return { text: "Inválido", color: "#b91c1c" };
  }
  const state = String(structured.validation_state || "");
  if (state.toLowerCase() === "valid" || structured.is_valid) {
    const untrusted = (structured.validation_codes || []).some((c) =>
      String(c).toLowerCase().includes("untrusted")
    );
    if (untrusted) {
      return { text: "Válido (cert. não confiável)", color: "#b45309" };
    }
    return { text: state || "Válido", color: "#166534" };
  }
  return { text: state || "Presente", color: "#0369a1" };
}

export default function C2paViewer({
  structured,
  entries,
}: {
  structured: C2paStructured;
  entries: MetadataTag[];
}) {
  const status = statusLabel(structured);
  const actions = structured.actions || [];
  const sig = structured.signature_info || {};

  return (
    <div>
      <div
        style={{
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          padding: "0.85rem 1rem",
          marginBottom: "1rem",
          background: "#fff",
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem 1.25rem", alignItems: "baseline" }}>
          <div>
            <div style={{ fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase" }}>Status</div>
            <div style={{ fontWeight: 700, color: status.color }}>{status.text}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase" }}>
              Claim generator
            </div>
            <div style={{ fontSize: "0.9rem", color: "#1f2937" }}>
              {structured.claim_generator || "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase" }}>Título</div>
            <div style={{ fontSize: "0.9rem", color: "#1f2937" }}>{structured.title || "—"}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.72rem", color: "#6b7280", textTransform: "uppercase" }}>Manifestos</div>
            <div style={{ fontSize: "0.9rem", color: "#1f2937" }}>
              {structured.manifest_count ?? 0}
              {structured.ingredient_count != null ? ` · ${structured.ingredient_count} ingredient(s)` : ""}
            </div>
          </div>
        </div>
        {(sig.issuer || sig.alg || sig.time) && (
          <p style={{ margin: "0.75rem 0 0", fontSize: "0.82rem", color: "#4b5563" }}>
            Assinatura: {sig.issuer || "—"}
            {sig.alg ? ` · ${sig.alg}` : ""}
            {sig.time ? ` · ${sig.time}` : ""}
          </p>
        )}
        {structured.reason && (
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.82rem", color: "#b45309" }}>{structured.reason}</p>
        )}
        {structured.error && (
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.82rem", color: "#b91c1c" }}>{structured.error}</p>
        )}
        <p style={{ margin: "0.65rem 0 0", fontSize: "0.75rem", color: "#9ca3af" }}>
          C2PA (Content Credentials) embute proveniência criptografada. Presença ≠ autenticidade; confira o
          status de validação.
          {structured.sdk_version ? ` · SDK ${structured.sdk_version}` : ""}
          {structured.trust_anchors_configured ? " · trust anchors ativos" : ""}
        </p>
      </div>

      {actions.length > 0 && (
        <>
          <h4 style={{ fontSize: "0.9rem", margin: "0 0 0.5rem" }}>Ações declaradas</h4>
          <ul style={{ margin: "0 0 1rem", paddingLeft: "1.1rem", fontSize: "0.85rem", color: "#374151" }}>
            {actions.map((a, i) => (
              <li key={`${a.action}-${i}`} style={{ marginBottom: "0.35rem" }}>
                <strong>{a.action || "?"}</strong>
                {a.software_agent ? ` · ${a.software_agent}` : ""}
                {a.digital_source_type ? (
                  <span style={{ color: "#6b7280" }}> · {a.digital_source_type}</span>
                ) : null}
                {a.when ? <span style={{ color: "#6b7280" }}> · {a.when}</span> : null}
              </li>
            ))}
          </ul>
        </>
      )}

      {(structured.validation_codes || []).length > 0 && (
        <>
          <h4 style={{ fontSize: "0.9rem", margin: "0 0 0.5rem" }}>Códigos de validação</h4>
          <ul style={{ margin: "0 0 1rem", paddingLeft: "1.1rem", fontSize: "0.82rem", color: "#4b5563" }}>
            {(structured.validation_codes || []).map((code) => (
              <li key={code}>{code}</li>
            ))}
          </ul>
        </>
      )}

      <h4 style={{ fontSize: "0.9rem", margin: "0 0 0.5rem" }}>Campos C2PA / JUMBF</h4>
      <MetadataTagTable
        entries={entries}
        emptyMessage="Nenhum campo C2PA/JUMBF listado."
        hintLayout="stacked"
      />
    </div>
  );
}
