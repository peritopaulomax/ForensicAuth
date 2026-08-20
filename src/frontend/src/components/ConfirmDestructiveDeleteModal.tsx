import { useEffect, useMemo, useState } from "react";
import { deleteEvidences, getEvidenceDeletionPreview } from "@/services/evidence";
import { parseApiError } from "@/lib/apiErrors";
import {
  TYPED_CONFIRMATION_WORD,
  groupDependentsByPackage,
  requiresTypedConfirmation,
  summarizeNames,
  totalToDelete,
  typedConfirmationSatisfied,
  type DeletionScope,
} from "@/lib/deletionImpact";
import type { Evidence, EvidenceDeletionPreview, EvidenceDeletionResult } from "@/types/api";

export type DeleteTargetKind = "evidence" | "reference" | "derivative";

interface Props {
  open: boolean;
  caseId: string;
  targets: Evidence[];
  kind: DeleteTargetKind;
  onClose: () => void;
  onDeleted: (result: EvidenceDeletionResult) => void;
}

const KIND_TITLES: Record<DeleteTargetKind, string> = {
  evidence: "Excluir evidencia",
  reference: "Excluir referencia",
  derivative: "Excluir derivado",
};

const panelStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: "10px",
  padding: "1.4rem 1.5rem",
  maxWidth: "620px",
  width: "100%",
  maxHeight: "85vh",
  overflowY: "auto",
  boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
};

const noticeStyle: React.CSSProperties = {
  padding: "0.7rem 0.9rem",
  background: "#fef2f2",
  border: "1px solid #fecaca",
  borderRadius: "8px",
  fontSize: "0.83rem",
  color: "#991b1b",
  lineHeight: 1.5,
  marginBottom: "0.9rem",
};

const infoStyle: React.CSSProperties = {
  padding: "0.7rem 0.9rem",
  background: "#f8fafc",
  border: "1px solid #e2e8f0",
  borderRadius: "8px",
  fontSize: "0.82rem",
  color: "#334155",
  lineHeight: 1.5,
  marginBottom: "0.9rem",
};

export default function ConfirmDestructiveDeleteModal({
  open,
  caseId,
  targets,
  kind,
  onClose,
  onDeleted,
}: Props) {
  const [preview, setPreview] = useState<EvidenceDeletionPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [scope, setScope] = useState<DeletionScope>("targets_only");
  const [typed, setTyped] = useState("");
  const [error, setError] = useState("");
  const [previewFailed, setPreviewFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const targetIds = useMemo(() => targets.map((ev) => ev.id), [targets]);
  const targetKey = targetIds.join(",");

  useEffect(() => {
    if (!open || targetIds.length === 0) return;
    let active = true;
    setLoading(true);
    setError("");
    setPreviewFailed(false);
    setPreview(null);
    setScope("targets_only");
    setTyped("");
    void (async () => {
      try {
        const data = await getEvidenceDeletionPreview(caseId, targetIds);
        if (active) setPreview(data);
      } catch (err) {
        if (!active) return;
        setPreviewFailed(true);
        setError(parseApiError(err, "Erro ao calcular impacto da exclusao"));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
    // targetKey identifica o conjunto de alvos sem re-disparar por nova referencia de array
  }, [open, caseId, targetKey, reloadKey]);

  if (!open) return null;

  const cascadeCount = preview?.cascade_count ?? 0;
  const retained = preview?.dependents.filter((item) => !item.exclusive) ?? [];
  const cascadePackages = groupDependentsByPackage(
    preview?.dependents.filter((item) => item.exclusive) ?? []
  );
  const total = totalToDelete(preview, scope);
  const needsTyped = requiresTypedConfirmation(total);
  const canConfirm =
    !!preview && !loading && !busy && typedConfirmationSatisfied(total, typed);

  const names = summarizeNames(targets.map((ev) => ev.original_filename));

  async function handleConfirm() {
    setBusy(true);
    setError("");
    try {
      const result = await deleteEvidences(
        caseId,
        targetIds,
        scope === "with_dependents"
      );
      onDeleted(result);
      if (result.failed.length === 0) onClose();
      else setError(result.failed.map((f) => f.detail).join("; "));
    } catch (err) {
      setError(parseApiError(err, "Erro ao excluir"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal
      aria-labelledby="confirm-delete-title"
      data-testid="confirm-delete-modal"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 2600,
        padding: "1rem",
      }}
      onClick={() => !busy && onClose()}
    >
      <div style={panelStyle} onClick={(e) => e.stopPropagation()}>
        <h2
          id="confirm-delete-title"
          style={{ margin: "0 0 0.9rem", color: "#1a1a2e", fontSize: "1.15rem" }}
        >
          {targets.length > 1 ? `Excluir ${targets.length} itens` : KIND_TITLES[kind]}
        </h2>

        <div style={noticeStyle}>
          O arquivo sai do disco e a acao nao pode ser desfeita. A exclusao fica registrada na
          cadeia de custodia (elo <code>evidence_deleted</code>), com autor e SHA-256.
        </div>

        {kind === "derivative" && (
          <div style={infoStyle}>
            Este artefato consta na cadeia como <code>derivative_saved</code>. O elo permanece
            verificavel; apenas o arquivo derivado deixa de existir.
          </div>
        )}

        <p style={{ margin: "0 0 0.4rem", fontSize: "0.85rem", color: "#6b7280" }}>
          Sera excluido:
        </p>
        <ul
          style={{
            margin: "0 0 1rem",
            paddingLeft: "1.1rem",
            fontSize: "0.85rem",
            color: "#1f2937",
          }}
        >
          {names.visible.map((name, index) => (
            <li key={`${name}-${index}`}>{name}</li>
          ))}
          {names.hidden > 0 && <li style={{ color: "#6b7280" }}>e mais {names.hidden}</li>}
        </ul>

        {loading && (
          <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Calculando impacto…</p>
        )}

        {previewFailed && !loading && (
          <div data-testid="preview-failed" style={infoStyle}>
            Nao foi possivel calcular o impacto desta exclusao, entao ela fica bloqueada — excluir
            sem saber quais derivados dependem do item seria arriscado. Resposta do servidor:{" "}
            <strong>{error}</strong>.
            {error.toLowerCase().includes("not found") && (
              <>
                {" "}
                A rota de impacto respondeu 404: a API em execucao provavelmente e anterior a este
                recurso. Reinicie o servico (uvicorn) e tente de novo.
              </>
            )}
            <div style={{ marginTop: "0.5rem" }}>
              <button
                type="button"
                data-testid="retry-preview"
                onClick={() => setReloadKey((key) => key + 1)}
                style={{
                  padding: "0.35rem 0.7rem",
                  background: "#fff",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontSize: "0.8rem",
                }}
              >
                Tentar novamente
              </button>
            </div>
          </div>
        )}

        {preview && (
          <>
            {preview.dependent_count === 0 ? (
              <p
                data-testid="no-dependents"
                style={{ fontSize: "0.84rem", color: "#6b7280", margin: "0 0 1rem" }}
              >
                Nenhum derivado depende deste conteudo.
              </p>
            ) : (
              <div style={{ marginBottom: "1rem" }}>
                <p
                  data-testid="dependents-summary"
                  style={{ margin: "0 0 0.5rem", fontSize: "0.86rem", color: "#1f2937" }}
                >
                  <strong>{preview.dependent_count}</strong> derivado(s) dependem deste conteudo
                  {preview.package_count > 0 && ` em ${preview.package_count} pacote(s)`}.
                </p>

                <label
                  style={{
                    display: "block",
                    fontSize: "0.85rem",
                    marginBottom: "0.35rem",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="radio"
                    name="deletion-scope"
                    checked={scope === "targets_only"}
                    onChange={() => setScope("targets_only")}
                    style={{ marginRight: "0.4rem" }}
                  />
                  Excluir apenas o(s) item(ns) selecionado(s)
                </label>

                <label
                  style={{
                    display: "block",
                    fontSize: "0.85rem",
                    marginBottom: "0.5rem",
                    cursor: cascadeCount > 0 ? "pointer" : "not-allowed",
                    color: cascadeCount > 0 ? undefined : "#9ca3af",
                  }}
                >
                  <input
                    type="radio"
                    name="deletion-scope"
                    data-testid="scope-with-dependents"
                    disabled={cascadeCount === 0}
                    checked={scope === "with_dependents"}
                    onChange={() => setScope("with_dependents")}
                    style={{ marginRight: "0.4rem" }}
                  />
                  Excluir tambem {cascadeCount} derivado(s) dependente(s)
                </label>

                {scope === "with_dependents" && cascadePackages.length > 0 && (
                  <ul
                    style={{
                      margin: "0 0 0.6rem",
                      paddingLeft: "1.1rem",
                      fontSize: "0.8rem",
                      color: "#374151",
                    }}
                  >
                    {cascadePackages.map((pkg) => (
                      <li key={pkg.group_id}>
                        {pkg.label}: {pkg.items.map((item) => item.original_filename).join(", ")}
                      </li>
                    ))}
                  </ul>
                )}

                {retained.length > 0 && (
                  <div style={infoStyle}>
                    {retained.length} derivado(s) serao mantidos porque tambem derivam de insumos
                    preservados:
                    <ul style={{ margin: "0.35rem 0 0", paddingLeft: "1.1rem" }}>
                      {retained.map((item) => (
                        <li key={item.evidence_id}>
                          {item.original_filename}
                          {item.retained_parents.length > 0 &&
                            ` (tambem deriva de ${item.retained_parents.join(", ")})`}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {needsTyped && (
          <div style={{ marginBottom: "1rem" }}>
            <label
              htmlFor="typed-confirmation"
              style={{ display: "block", fontSize: "0.83rem", marginBottom: "0.3rem" }}
            >
              Sao {total} itens. Digite <strong>{TYPED_CONFIRMATION_WORD}</strong> para confirmar:
            </label>
            <input
              id="typed-confirmation"
              data-testid="typed-confirmation"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              style={{
                width: "100%",
                padding: "0.45rem 0.6rem",
                border: "1px solid #d1d5db",
                borderRadius: "6px",
                fontSize: "0.9rem",
              }}
            />
          </div>
        )}

        {error && !previewFailed && (
          <p style={{ color: "#991b1b", fontSize: "0.84rem", margin: "0 0 0.8rem" }}>{error}</p>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            style={{
              padding: "0.5rem 1rem",
              background: "#f3f4f6",
              border: "none",
              borderRadius: "6px",
              cursor: busy ? "not-allowed" : "pointer",
            }}
          >
            Cancelar
          </button>
          <button
            type="button"
            data-testid="confirm-delete"
            onClick={handleConfirm}
            disabled={!canConfirm}
            style={{
              padding: "0.5rem 1.1rem",
              background: canConfirm ? "#dc2626" : "#fca5a5",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              fontWeight: 600,
              cursor: canConfirm ? "pointer" : "not-allowed",
            }}
          >
            {busy ? "Excluindo…" : "Excluir definitivamente"}
          </button>
        </div>
      </div>
    </div>
  );
}
