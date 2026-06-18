import { useCallback, useEffect, useState } from "react";
import {
  createCaseShare,
  listCaseShares,
  listUsersForSharing,
  revokeCaseShare,
  type CaseShare,
  type ShareableUser,
} from "@/services/caseShares";

interface Props {
  caseId: string;
  canManage: boolean;
  caseClosed: boolean;
}

export default function CaseSharePanel({ caseId, canManage, caseClosed }: Props) {
  const [shares, setShares] = useState<CaseShare[]>([]);
  const [users, setUsers] = useState<ShareableUser[]>([]);
  const [targetUserId, setTargetUserId] = useState("");
  const [role, setRole] = useState<"viewer" | "editor">("viewer");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [s, u] = await Promise.all([
        listCaseShares(caseId),
        canManage ? listUsersForSharing() : Promise.resolve([]),
      ]);
      setShares(s);
      setUsers(u);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(typeof msg === "string" ? msg : "Erro ao carregar compartilhamentos");
    } finally {
      setLoading(false);
    }
  }, [caseId, canManage]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleShare() {
    if (!targetUserId) return;
    try {
      await createCaseShare(caseId, targetUserId, role);
      setTargetUserId("");
      await load();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(typeof msg === "string" ? msg : "Erro ao compartilhar");
    }
  }

  async function handleRevoke(shareId: string) {
    if (!confirm("Revogar este compartilhamento?")) return;
    try {
      await revokeCaseShare(caseId, shareId);
      await load();
    } catch {
      setError("Erro ao revogar compartilhamento");
    }
  }

  return (
    <div
      style={{
        marginTop: "1rem",
        padding: "1rem",
        border: "1px solid #e5e7eb",
        borderRadius: "8px",
        background: "#fafafa",
      }}
    >
      <h3 style={{ margin: "0 0 0.5rem", fontSize: "1rem", color: "#1a1a2e" }}>
        Compartilhamento
      </h3>
      {loading ? (
        <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Carregando…</p>
      ) : (
        <>
          {error && (
            <p style={{ color: "#991b1b", fontSize: "0.85rem", marginBottom: "0.5rem" }}>{error}</p>
          )}
          {shares.length === 0 ? (
            <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Nenhum compartilhamento ativo.</p>
          ) : (
            <ul style={{ margin: "0 0 0.75rem", paddingLeft: "1.25rem", fontSize: "0.85rem" }}>
              {shares.map((s) => (
                <li key={s.id} style={{ marginBottom: "0.35rem" }}>
                  {s.shared_with_username || s.shared_with_user_id.slice(0, 8)} —{" "}
                  <strong>{s.role === "editor" ? "Editor" : "Visualizador"}</strong>
                  {canManage && !caseClosed && (
                    <button
                      type="button"
                      onClick={() => handleRevoke(s.id)}
                      style={{
                        marginLeft: "0.5rem",
                        fontSize: "0.75rem",
                        background: "#fee2e2",
                        border: "none",
                        borderRadius: "4px",
                        cursor: "pointer",
                        padding: "0.15rem 0.4rem",
                      }}
                    >
                      Revogar
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {canManage && !caseClosed && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
              <select
                value={targetUserId}
                onChange={(e) => setTargetUserId(e.target.value)}
                style={{ padding: "0.4rem", borderRadius: "4px", border: "1px solid #ddd", minWidth: "180px" }}
              >
                <option value="">Selecione usuario…</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.username} ({u.role})
                  </option>
                ))}
              </select>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as "viewer" | "editor")}
                style={{ padding: "0.4rem", borderRadius: "4px", border: "1px solid #ddd" }}
              >
                <option value="viewer">Visualizador</option>
                <option value="editor">Editor</option>
              </select>
              <button
                type="button"
                onClick={handleShare}
                disabled={!targetUserId}
                style={{
                  padding: "0.4rem 0.75rem",
                  background: "#1a1a2e",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  cursor: targetUserId ? "pointer" : "not-allowed",
                  fontSize: "0.85rem",
                }}
              >
                Compartilhar
              </button>
            </div>
          )}
          {caseClosed && (
            <p style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.5rem" }}>
              Caso fechado — novos compartilhamentos bloqueados.
            </p>
          )}
        </>
      )}
    </div>
  );
}
