import { memo, useCallback, useEffect, useState } from "react";
import {
  verifyCaseForensic,
  forensicFailureSummary,
  type ForensicIntegrityReport,
} from "@/services/audit";

interface Props {
  caseId: string;
  /** Increment to re-run verification (upload, fechamento, etc.). */
  refreshToken?: number;
  /** Wait until case metadata is loaded before hashing files on the server. */
  enabled?: boolean;
  onOpenCustody: () => void;
}

function ForensicIntegrityBanner({
  caseId,
  refreshToken = 0,
  enabled = true,
  onOpenCustody,
}: Props) {
  const [report, setReport] = useState<ForensicIntegrityReport | null>(null);
  const [loading, setLoading] = useState(false);

  const runVerification = useCallback(async () => {
    if (!caseId || !enabled) return;
    setLoading(true);
    try {
      const next = await verifyCaseForensic(caseId);
      // Ignore incomplete payloads (proxy/mock/error bodies) to avoid UI crash.
      if (!next || typeof next.valid !== "boolean") {
        setReport(null);
        return;
      }
      setReport(next);
    } catch {
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [caseId, enabled]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setReport(null);
      return;
    }

    setLoading(true);
    let cancelled = false;
    const start = () => {
      if (!cancelled) void runVerification();
    };

    const idleId =
      typeof window.requestIdleCallback === "function"
        ? window.requestIdleCallback(start, { timeout: 2000 })
        : null;
    const timeoutId = idleId == null ? window.setTimeout(start, 250) : null;

    return () => {
      cancelled = true;
      if (idleId != null && typeof window.cancelIdleCallback === "function") {
        window.cancelIdleCallback(idleId);
      }
      if (timeoutId != null) window.clearTimeout(timeoutId);
    };
  }, [runVerification, refreshToken, enabled]);

  if (!enabled || (!loading && !report)) return null;

  return (
    <div
      data-testid="forensic-integrity-banner"
      style={{
        marginBottom: "1rem",
        padding: "0.75rem 1rem",
        borderRadius: "6px",
        fontSize: "0.85rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "1rem",
        flexWrap: "wrap",
        background: loading ? "#fffbeb" : report?.valid ? "#ecfdf5" : "#fef2f2",
        color: loading ? "#92400e" : report?.valid ? "#065f46" : "#991b1b",
        border: `1px solid ${
          loading ? "#fde68a" : report?.valid ? "#a7f3d0" : "#fecaca"
        }`,
      }}
    >
      <span>
        {loading ? (
          "Verificando integridade forense do caso…"
        ) : report?.valid ? (
          <>
            <strong>Integridade verificada</strong>
            {" — "}
            cadeia, assinaturas e arquivos conferidos
            {report.generated_at && (
              <> ({new Date(report.generated_at).toLocaleString("pt-BR")})</>
            )}
          </>
        ) : (
          <>
            <strong>Integridade comprometida:</strong>{" "}
            {report ? forensicFailureSummary(report) : "falha na verificacao"}
          </>
        )}
      </span>
      {!loading && report && !report.valid && (
        <button
          type="button"
          onClick={onOpenCustody}
          style={{
            padding: "0.35rem 0.75rem",
            background: "#fff",
            color: "#991b1b",
            border: "1px solid #fecaca",
            borderRadius: "6px",
            cursor: "pointer",
            fontSize: "0.8rem",
            fontWeight: 600,
          }}
        >
          Ver custodia
        </button>
      )}
    </div>
  );
}

export default memo(ForensicIntegrityBanner);
