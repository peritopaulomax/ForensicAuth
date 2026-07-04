import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Evidence } from "@/types/api";
import DerivationGraphModal from "@/components/DerivationGraphModal";
import { registerDerivativeSaveListener } from "@/services/evidence";

interface DerivativeSaveContextValue {
  notifySaved: (evidence: Evidence) => void;
  clearSaved: () => void;
}

const DerivativeSaveContext = createContext<DerivativeSaveContextValue | null>(null);

export function DerivativeSaveProvider({
  caseId,
  children,
}: {
  caseId: string;
  children: ReactNode;
}) {
  const [saved, setSaved] = useState<Evidence | null>(null);
  const [graphOpen, setGraphOpen] = useState(false);

  const notifySaved = useCallback((evidence: Evidence) => {
    setSaved(evidence);
    setGraphOpen(false);
  }, []);

  const clearSaved = useCallback(() => {
    setSaved(null);
    setGraphOpen(false);
  }, []);

  useEffect(() => {
    return registerDerivativeSaveListener(notifySaved);
  }, [notifySaved]);

  return (
    <DerivativeSaveContext.Provider value={{ notifySaved, clearSaved }}>
      {children}
      {saved && (
        <div
          style={{
            marginTop: "1rem",
            padding: "0.75rem 1rem",
            borderRadius: 8,
            border: "1px solid #86efac",
            background: "#ecfdf5",
            fontSize: "0.82rem",
            color: "#166534",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: "0.35rem" }}>
            Derivado salvo: {saved.original_filename}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            <button
              type="button"
              onClick={() => setGraphOpen(true)}
              style={{
                padding: "0.35rem 0.65rem",
                borderRadius: 6,
                border: "1px solid #166534",
                background: "#fff",
                color: "#166534",
                cursor: "pointer",
                fontSize: "0.78rem",
              }}
            >
              Ver grafo de derivacao
            </button>
            <Link
              to={`/cases/${caseId}?tab=derivados&graph=${saved.id}`}
              style={{
                padding: "0.35rem 0.65rem",
                borderRadius: 6,
                border: "1px solid #166534",
                background: "#fff",
                color: "#166534",
                textDecoration: "none",
                fontSize: "0.78rem",
              }}
            >
              Abrir na aba Derivados
            </Link>
            <button
              type="button"
              onClick={clearSaved}
              style={{
                padding: "0.35rem 0.65rem",
                borderRadius: 6,
                border: "none",
                background: "transparent",
                color: "#6b7280",
                cursor: "pointer",
                fontSize: "0.78rem",
              }}
            >
              Fechar
            </button>
          </div>
        </div>
      )}
      {saved && graphOpen && (
        <DerivationGraphModal
          evidenceId={saved.id}
          evidenceName={saved.original_filename}
          onClose={() => setGraphOpen(false)}
        />
      )}
    </DerivativeSaveContext.Provider>
  );
}

export function useDerivativeSaveNotifier() {
  return useContext(DerivativeSaveContext);
}
