import { useCallback, useEffect, useState } from "react";
import DerivationGraphModal from "@/components/DerivationGraphModal";
import {
  listAuditRecords,
  verifyCaseChain,
  verifyCaseForensic,
  downloadForensicReport,
  downloadCustodyNarrativeReport,
  verifyRecord,
  RECORD_TYPE_LABELS,
  type CustodyRecord,
  type ForensicIntegrityReport,
} from "@/services/audit";
import { getPeritusCaseMeta, ensurePeritusFilesCustody, type PeritusCaseMeta } from "@/services/peritus";
import type { Evidence } from "@/types/api";

interface Props {
  caseId: string;
  evidences: Evidence[];
  isPeritusCase?: boolean;
  filterEvidenceId?: string | null;
  onClearFilter?: () => void;
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString("pt-BR");
  } catch {
    return iso;
  }
}

function truncateHash(hash: string | null, len = 12): string {
  if (!hash) return "—";
  if (hash.length <= len * 2) return hash;
  return `${hash.slice(0, len)}…${hash.slice(-len)}`;
}

function actorLabel(rec: CustodyRecord): string | null {
  const details = rec.details || {};
  const username = details.actor_username;
  if (typeof username === "string" && username.trim()) return username;
  return null;
}

function forensicFailureSummary(report: ForensicIntegrityReport): string | null {
  if (report.valid) return null;
  const parts: string[] = [];
  if (!report.chain.valid) parts.push("cadeia de custodia");
  const invalidSigs = report.signatures.invalid.length;
  if (invalidSigs > 0) {
    parts.push(
      `${invalidSigs} assinatura(s) Ed25519 invalida(s) (chave do sistema ou registro alterado)`
    );
  }
  if (report.files.missing.length > 0 || report.files.hash_mismatch.length > 0) {
    parts.push("arquivos de evidencia");
  }
  if (report.provenance.issues.length > 0) parts.push("proveniencia");
  const badClosures = report.closures.filter(
    (c) => !c.signatures_valid || !c.manifest_valid
  );
  if (badClosures.length > 0) parts.push("fechamento(s) do caso");
  return parts.length > 0 ? parts.join("; ") : "falha nao especificada";
}

export default function CustodyPanel({
  caseId,
  evidences,
  isPeritusCase = false,
  filterEvidenceId,
  onClearFilter,
}: Props) {
  const [records, setRecords] = useState<CustodyRecord[]>([]);
  const [peritusMeta, setPeritusMeta] = useState<PeritusCaseMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [chainValid, setChainValid] = useState<boolean | null>(null);
  const [chainVerifyDetail, setChainVerifyDetail] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [forensicReport, setForensicReport] = useState<ForensicIntegrityReport | null>(null);
  const [forensicLoading, setForensicLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [narrativeExporting, setNarrativeExporting] = useState(false);
  const [graphEvidenceId, setGraphEvidenceId] = useState<string | null>(null);
  const [graphEvidenceName, setGraphEvidenceName] = useState("");

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listAuditRecords({
        case_id: caseId,
        evidence_id: filterEvidenceId || undefined,
      });
      setRecords(data);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(msg || "Erro ao carregar cadeia de custodia");
    } finally {
      setLoading(false);
    }
  }, [caseId, filterEvidenceId]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  useEffect(() => {
    if (!isPeritusCase) {
      setPeritusMeta(null);
      return;
    }
    ensurePeritusFilesCustody(caseId)
      .then(() => getPeritusCaseMeta(caseId))
      .then((meta) => {
        setPeritusMeta(meta);
        return loadRecords();
      })
      .catch(() => setPeritusMeta(null));
  }, [caseId, isPeritusCase]);

  async function handleForensicVerify() {
    setForensicLoading(true);
    setForensicReport(null);
    try {
      const report = await verifyCaseForensic(caseId);
      setForensicReport(report);
    } catch {
      setError("Erro na verificacao forense completa");
    } finally {
      setForensicLoading(false);
    }
  }

  async function handleExportNarrative(format: "html" | "md") {
    setNarrativeExporting(true);
    try {
      const blob = await downloadCustodyNarrativeReport(caseId, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cadeia-custodia-${caseId.slice(0, 8)}.${format === "md" ? "md" : "html"}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Erro ao exportar relatorio narrativo");
    } finally {
      setNarrativeExporting(false);
    }
  }

  async function handleExportReport(format: "json" | "html") {
    try {
      const blob = await downloadForensicReport(caseId, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `forensic-report-${caseId}.${format === "html" ? "html" : "json"}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Erro ao exportar relatorio");
    }
  }

  async function handleVerifyChain() {
    setVerifying(true);
    setChainValid(null);
    setChainVerifyDetail(null);
    try {
      const result = await verifyCaseChain(caseId);
      setChainValid(result.valid);
      if (!result.valid) {
        const idHint = result.first_invalid
          ? ` ${result.first_invalid.slice(0, 8)}…`
          : "";
        const reasonLine =
          result.reason === "previous_record_hash_mismatch"
            ? `Quebra de encadeamento no registro${idHint}.`
            : result.reason === "chain_sequence_gap"
              ? `Sequencia da cadeia inconsistente no registro${idHint}.`
              : result.reason === "record_hash_mismatch"
                ? `Hash invalido no registro${idHint} — conteudo alterado ou adulterado.`
                : result.reason === "invalid_genesis"
                  ? `Genesis da cadeia invalido (deve haver exatamente um registro inicial).`
                  : result.reason === "unlinked_custody_records"
                    ? `Registro(s) fora da cadeia criptografica${idHint}.`
                    : result.reason === "broken_chain_or_orphan"
                    ? `Cadeia incompleta ou registro orfao${idHint}.`
                    : result.reason === "chain_cycle"
                      ? `Ciclo detectado na cadeia${idHint}.`
                      : `Registro invalido${idHint}.`;
        setChainVerifyDetail(
          `${reasonLine} A cadeia nao e reparavel pela aplicacao; trate como indicio de corrupcao ou adulteracao.`
        );
      }
    } catch {
      setError("Erro ao verificar cadeia");
    } finally {
      setVerifying(false);
    }
  }

  async function handleVerifyRecord(recordId: string) {
    try {
      const result = await verifyRecord(recordId);
      if (!result.valid) {
        setError(`Registro ${recordId.slice(0, 8)}… falhou na verificacao`);
      } else {
        setError("");
      }
    } catch {
      setError("Erro ao verificar registro");
    }
  }

  const evidenceName = (id: string | null) => {
    if (!id) return null;
    const ev = evidences.find((e) => e.id === id);
    return ev?.original_filename || id.slice(0, 8) + "…";
  };

  if (loading) {
    return <p style={{ color: "#6b7280", padding: "1rem 0" }}>Carregando cadeia de custodia…</p>;
  }

  return (
    <div>
      {isPeritusCase && peritusMeta && (
        <div
          style={{
            marginBottom: "1.25rem",
            padding: "1rem 1.1rem",
            background: "#eef2ff",
            border: "1px solid #c7d2fe",
            borderRadius: "8px",
            fontSize: "0.85rem",
            color: "#312e81",
            lineHeight: 1.55,
          }}
        >
          <strong style={{ display: "block", marginBottom: "0.35rem" }}>
            Caso importado do Peritus Desktop
          </strong>
          <p style={{ margin: "0 0 0.5rem 0" }}>
            A cadeia ForensicAuth inicia com o registro de importacao. A ancora forense Peritus e o{" "}
            <strong>SHA-256 do peritusCase.xml</strong> (manifesto do pacote; assinatura ICP verificavel
            no Peritus). O ZIP original e preservado para export bit-identico.
          </p>
          {peritusMeta.imported_at && (
            <div>
              Importado em:{" "}
              <span style={{ fontFamily: "monospace" }}>{formatTimestamp(peritusMeta.imported_at)}</span>
            </div>
          )}
          {peritusMeta.peritus_chain_anchor && (
            <div>
              Ancora XML (SHA-256):{" "}
              <span style={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                {peritusMeta.peritus_chain_anchor}
              </span>
            </div>
          )}
          {peritusMeta.original_zip_sha256 && (
            <div>
              ZIP original (SHA-256):{" "}
              <span style={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                {peritusMeta.original_zip_sha256}
              </span>
            </div>
          )}
          {peritusMeta.custody_files_registered != null && (
            <div style={{ marginTop: "0.35rem" }}>
              Arquivos encadeados na importacao:{" "}
              <strong>{peritusMeta.custody_files_registered}</strong>
            </div>
          )}
        </div>
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "0.75rem",
          marginBottom: "1rem",
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: "1.15rem", color: "#1a1a2e" }}>
            Cadeia de Custodia
          </h2>
          <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
            {records.length} registro(s) imutavel(is) encadeados por SHA-256
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {filterEvidenceId && onClearFilter && (
            <button
              onClick={onClearFilter}
              style={{
                padding: "0.4rem 0.75rem",
                background: "#f3f4f6",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "0.8rem",
              }}
            >
              Limpar filtro
            </button>
          )}
          <button
            onClick={handleVerifyChain}
            disabled={verifying || records.length === 0}
            style={{
              padding: "0.4rem 0.75rem",
              background: "#1a1a2e",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: verifying ? "wait" : "pointer",
              fontSize: "0.8rem",
            }}
          >
            {verifying ? "Verificando…" : "Verificar cadeia"}
          </button>
          <button
            type="button"
            onClick={() => handleExportNarrative("html")}
            disabled={narrativeExporting || records.length === 0}
            title="Relatorio em linguagem natural, ordem cronologica da cadeia"
            style={{
              padding: "0.4rem 0.75rem",
              background: "#0f766e",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: narrativeExporting ? "wait" : "pointer",
              fontSize: "0.8rem",
            }}
          >
            {narrativeExporting ? "Gerando…" : "Relatorio narrativo"}
          </button>
          <button
            type="button"
            onClick={() => handleExportNarrative("md")}
            disabled={narrativeExporting || records.length === 0}
            style={{
              padding: "0.4rem 0.75rem",
              background: "#f3f4f6",
              border: "none",
              borderRadius: "6px",
              cursor: narrativeExporting ? "wait" : "pointer",
              fontSize: "0.8rem",
            }}
          >
            Exportar MD
          </button>
          <button
            onClick={handleForensicVerify}
            disabled={forensicLoading || records.length === 0}
            style={{
              padding: "0.4rem 0.75rem",
              background: "#0369a1",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: forensicLoading ? "wait" : "pointer",
              fontSize: "0.8rem",
            }}
          >
            {forensicLoading ? "Verificando…" : "Verificacao forense"}
          </button>
          {forensicReport && (
            <>
              <button
                type="button"
                onClick={() => handleExportReport("json")}
                style={{
                  padding: "0.4rem 0.75rem",
                  background: "#f3f4f6",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                }}
              >
                Exportar JSON
              </button>
              <button
                type="button"
                onClick={() => handleExportReport("html")}
                style={{
                  padding: "0.4rem 0.75rem",
                  background: "#f3f4f6",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                }}
              >
                Exportar HTML
              </button>
            </>
          )}
          <button
            onClick={loadRecords}
            style={{
              padding: "0.4rem 0.75rem",
              background: "#f3f4f6",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.8rem",
            }}
          >
            Atualizar
          </button>
        </div>
      </div>

      {forensicReport && (() => {
        const failureDetail = forensicFailureSummary(forensicReport);
        return (
        <div
          style={{
            padding: "0.75rem 1rem",
            borderRadius: "6px",
            marginBottom: "1rem",
            background: forensicReport.valid ? "#ecfdf5" : "#fef2f2",
            fontSize: "0.85rem",
          }}
        >
          <strong>
            {forensicReport.valid
              ? "Verificacao forense integra"
              : "Verificacao forense com falhas"}
          </strong>
          {!forensicReport.valid && failureDetail && (
            <p style={{ margin: "0.35rem 0 0", color: "#991b1b" }}>
              {failureDetail}
            </p>
          )}
          <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.25rem" }}>
            <li>Cadeia: {forensicReport.chain.valid ? "OK" : "Falha"}</li>
            <li>
              Assinaturas Ed25519:{" "}
              {forensicReport.signatures.invalid.length === 0
                ? forensicReport.signatures.checked > 0
                  ? `OK (${forensicReport.signatures.checked} conferida(s))`
                  : "Nenhuma assinatura no registro"
                : `${forensicReport.signatures.invalid.length} invalida(s) de ${forensicReport.signatures.checked}`}
            </li>
            <li>
              Arquivos: {forensicReport.files.hash_mismatch.length} divergencia(s),{" "}
              {forensicReport.files.missing.length} ausente(s)
            </li>
            <li>Proveniência: {forensicReport.provenance.issues.length} problema(s)</li>
            <li>
              Fechamentos: {forensicReport.closures.length} verificado(s)
            </li>
          </ul>
          {forensicReport.warnings.length > 0 && (
            <p style={{ marginTop: "0.5rem", color: "#6b7280" }}>
              {forensicReport.warnings.join(" ")}
            </p>
          )}
        </div>
        );
      })()}

      {chainValid !== null && (
        <div
          style={{
            padding: "0.6rem 1rem",
            borderRadius: "6px",
            marginBottom: "1rem",
            background: chainValid ? "#ecfdf5" : "#fef2f2",
            color: chainValid ? "#065f46" : "#991b1b",
            fontSize: "0.85rem",
          }}
        >
          {chainValid
            ? "Cadeia integra — encadeamento e hashes conferem; nenhuma alteracao detectada."
            : chainVerifyDetail || "Cadeia comprometida — possivel adulteracao ou corrupcao."}
        </div>
      )}

      {error && (
        <div
          style={{
            background: "#fee2e2",
            color: "#991b1b",
            padding: "0.6rem 1rem",
            borderRadius: "6px",
            marginBottom: "1rem",
            fontSize: "0.85rem",
          }}
        >
          {error}
        </div>
      )}

      {filterEvidenceId && (
        <p style={{ fontSize: "0.8rem", color: "#6b7280", marginBottom: "1rem" }}>
          Filtrando: <strong>{evidenceName(filterEvidenceId)}</strong>
        </p>
      )}

      {records.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "2.5rem",
            color: "#9ca3af",
            border: "1px dashed #e5e7eb",
            borderRadius: "8px",
          }}
        >
          Nenhum registro de custodia ainda. Faca upload de evidencias para iniciar a cadeia.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {records.map((rec, idx) => {
            const isExpanded = expandedId === rec.id;
            const typeLabel = RECORD_TYPE_LABELS[rec.record_type] || rec.record_type;
            return (
              <div
                key={rec.id}
                style={{
                  border: "1px solid #e5e7eb",
                  borderRadius: "8px",
                  background: "#fff",
                  overflow: "hidden",
                }}
              >
                <button
                  type="button"
                  onClick={() => setExpandedId(isExpanded ? null : rec.id)}
                  style={{
                    width: "100%",
                    display: "grid",
                    gridTemplateColumns: "24px 1fr auto",
                    gap: "0.75rem",
                    alignItems: "center",
                    padding: "0.75rem 1rem",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    textAlign: "left",
                  }}
                >
                  <span
                    style={{
                      width: "10px",
                      height: "10px",
                      borderRadius: "50%",
                      background: idx === 0 ? "#1a1a2e" : "#9ca3af",
                      margin: "0 auto",
                    }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.9rem", color: "#1a1a2e" }}>
                      {typeLabel}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: "0.15rem" }}>
                      {formatTimestamp(rec.timestamp)}
                      {actorLabel(rec) && (
                        <> · <strong style={{ color: "#374151" }}>{actorLabel(rec)}</strong></>
                      )}
                      {rec.evidence_id && (
                        <> · {evidenceName(rec.evidence_id)}</>
                      )}
                      {typeof rec.details.original_filename === "string" && (
                        <> · {rec.details.original_filename as string}</>
                      )}
                    </div>
                  </div>
                  <span style={{ fontSize: "0.7rem", color: "#9ca3af", fontFamily: "monospace" }}>
                    {truncateHash(rec.record_hash, 6)}
                  </span>
                </button>

                {isExpanded && (
                  <div
                    style={{
                      padding: "0 1rem 1rem 2.5rem",
                      fontSize: "0.8rem",
                      color: "#374151",
                      borderTop: "1px solid #f3f4f6",
                    }}
                  >
                    <dl style={{ margin: "0.75rem 0 0", display: "grid", gap: "0.35rem" }}>
                      <div>
                        <dt style={{ color: "#9ca3af", display: "inline" }}>SHA entrada: </dt>
                        <dd style={{ display: "inline", fontFamily: "monospace", fontSize: "0.75rem" }}>
                          {rec.sha256_input || "—"}
                        </dd>
                      </div>
                      {rec.sha256_output && (
                        <div>
                          <dt style={{ color: "#9ca3af", display: "inline" }}>SHA saida: </dt>
                          <dd style={{ display: "inline", fontFamily: "monospace", fontSize: "0.75rem" }}>
                            {rec.sha256_output}
                          </dd>
                        </div>
                      )}
                      {rec.sha256_params && (
                        <div>
                          <dt style={{ color: "#9ca3af", display: "inline" }}>SHA params: </dt>
                          <dd style={{ display: "inline", fontFamily: "monospace", fontSize: "0.75rem" }}>
                            {rec.sha256_params}
                          </dd>
                        </div>
                      )}
                      <div>
                        <dt style={{ color: "#9ca3af", display: "inline" }}>Hash anterior: </dt>
                        <dd style={{ display: "inline", fontFamily: "monospace", fontSize: "0.75rem" }}>
                          {rec.previous_record_hash || "(primeiro registro)"}
                        </dd>
                      </div>
                      <div>
                        <dt style={{ color: "#9ca3af", display: "inline" }}>Hash registro: </dt>
                        <dd style={{ display: "inline", fontFamily: "monospace", fontSize: "0.75rem" }}>
                          {rec.record_hash}
                        </dd>
                      </div>
                      {rec.job_id && (
                        <div>
                          <dt style={{ color: "#9ca3af", display: "inline" }}>Job: </dt>
                          <dd style={{ display: "inline", fontFamily: "monospace", fontSize: "0.75rem" }}>
                            {rec.job_id}
                          </dd>
                        </div>
                      )}
                      {Object.keys(rec.details).length > 0 && (
                        <div>
                          <dt style={{ color: "#9ca3af" }}>Detalhes:</dt>
                          <dd style={{ margin: "0.25rem 0 0" }}>
                            <pre
                              style={{
                                margin: 0,
                                padding: "0.5rem",
                                background: "#f9fafb",
                                borderRadius: "4px",
                                fontSize: "0.7rem",
                                overflow: "auto",
                                maxHeight: "120px",
                              }}
                            >
                              {JSON.stringify(rec.details, null, 2)}
                            </pre>
                          </dd>
                        </div>
                      )}
                    </dl>
                    {rec.record_type === "derivative_saved" && rec.evidence_id && (
                      <button
                        type="button"
                        onClick={() => {
                          const name =
                            (typeof rec.details.original_filename === "string"
                              ? rec.details.original_filename
                              : evidenceName(rec.evidence_id)) || "derivado";
                          setGraphEvidenceId(rec.evidence_id);
                          setGraphEvidenceName(name);
                        }}
                        style={{
                          marginTop: "0.5rem",
                          padding: "0.35rem 0.65rem",
                          borderRadius: 6,
                          border: "1px solid #1a1a2e",
                          background: "#fff",
                          cursor: "pointer",
                          fontSize: "0.78rem",
                        }}
                      >
                        Ver grafo de derivacao
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleVerifyRecord(rec.id)}
                      style={{
                        marginTop: "0.5rem",
                        padding: "0.25rem 0.5rem",
                        fontSize: "0.75rem",
                        background: "#f3f4f6",
                        border: "none",
                        borderRadius: "4px",
                        cursor: "pointer",
                      }}
                    >
                      Verificar este registro
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {graphEvidenceId && (
        <DerivationGraphModal
          evidenceId={graphEvidenceId}
          evidenceName={graphEvidenceName}
          onClose={() => setGraphEvidenceId(null)}
        />
      )}
    </div>
  );
}
