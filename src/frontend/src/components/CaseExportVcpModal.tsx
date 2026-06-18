import { useCallback, useEffect, useRef, useState } from "react";
import { exportCaseVcp, type VcpExportProgress } from "@/services/cases";

interface Props {
  open: boolean;
  caseId: string;
  protocolNumber?: string;
  onClose: () => void;
}

const STAGE_TICK_MS = 450;

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function CaseExportVcpModal({
  open,
  caseId,
  protocolNumber,
  onClose,
}: Props) {
  const [progress, setProgress] = useState<VcpExportProgress>({
    percent: 0,
    message: "Iniciando exportacao…",
    phase: "preparing",
  });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const onCloseRef = useRef(onClose);
  const tickRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const runIdRef = useRef(0);

  onCloseRef.current = onClose;

  const clearTick = useCallback(() => {
    if (tickRef.current != null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!open) {
      clearTick();
      abortRef.current?.abort();
      abortRef.current = null;
      runIdRef.current += 1;
      setProgress({ percent: 0, message: "Iniciando exportacao…", phase: "preparing" });
      setError("");
      setDone(false);
      setBusy(false);
      return;
    }

    const runId = ++runIdRef.current;
    setBusy(true);
    setError("");
    setDone(false);
    setProgress({ percent: 4, message: "Coletando metadados do caso…", phase: "preparing" });

    const controller = new AbortController();
    abortRef.current = controller;

    let simulated = 8;
    tickRef.current = window.setInterval(() => {
      if (runId !== runIdRef.current) return;
      simulated = Math.min(simulated + 2, 88);
      setProgress((prev) => {
        if (prev.phase === "downloading" || prev.phase === "done") return prev;
        let message = prev.message;
        let phase = prev.phase;
        if (simulated < 20) {
          phase = "preparing";
          message = "Coletando metadados do caso…";
        } else if (simulated < 45) {
          phase = "packaging";
          message = "Incluindo evidencias e arquivos…";
        } else if (simulated < 60) {
          phase = "chain";
          message = "Serializando cadeia de custodia…";
        } else if (simulated < 78) {
          phase = "zip";
          message = "Gerando pacote ZIP no servidor…";
        } else {
          phase = "waiting";
          message =
            "Aguardando resposta do servidor (casos grandes podem levar alguns minutos)…";
        }
        return { percent: simulated, message, phase };
      });
    }, STAGE_TICK_MS);

    void (async () => {
      try {
        const { blob, filename } = await exportCaseVcp(caseId, {
          signal: controller.signal,
          onProgress: (p) => {
            if (runId !== runIdRef.current) return;
            setProgress(p);
          },
        });
        if (runId !== runIdRef.current || controller.signal.aborted) return;
        clearTick();
        setProgress({
          percent: 100,
          message: "Pacote pronto — iniciando download…",
          phase: "done",
        });
        triggerDownload(blob, filename);
        setDone(true);
        window.setTimeout(() => onCloseRef.current(), 1800);
      } catch (err: unknown) {
        if (runId !== runIdRef.current || controller.signal.aborted) return;
        clearTick();
        const msg =
          err &&
          typeof err === "object" &&
          "message" in err &&
          typeof (err as { message: unknown }).message === "string"
            ? (err as { message: string }).message
            : "Erro ao exportar VCP";
        setError(msg);
        setProgress((prev) => ({ ...prev, phase: "error" }));
      } finally {
        if (runId === runIdRef.current) setBusy(false);
      }
    })();

    return () => {
      clearTick();
      controller.abort();
    };
  }, [open, caseId, clearTick]);

  if (!open) return null;

  const canClose = !busy || !!error || done;

  return (
    <div
      role="dialog"
      aria-modal
      aria-labelledby="vcp-export-title"
      aria-busy={busy}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 2500,
        padding: "1rem",
      }}
      onClick={() => canClose && onCloseRef.current()}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: "10px",
          padding: "1.5rem",
          maxWidth: "520px",
          width: "100%",
          boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="vcp-export-title"
          style={{ margin: "0 0 0.5rem", color: "#1a1a2e", fontSize: "1.2rem" }}
        >
          Exportando Verification Case Package (VCP)
        </h2>

        {protocolNumber && (
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.88rem", color: "#6b7280" }}>
            Caso <strong>{protocolNumber}</strong>
          </p>
        )}

        <div
          style={{
            marginBottom: "1rem",
            padding: "0.75rem 1rem",
            background: "#fffbeb",
            border: "1px solid #fde68a",
            borderRadius: "8px",
            fontSize: "0.85rem",
            color: "#92400e",
            lineHeight: 1.5,
          }}
        >
          A exportacao inclui todos os arquivos, a cadeia de custodia e assinaturas. Em casos com
          muitas evidencias, o processo pode levar alguns minutos. Aguarde ate a conclusao — nao
          clique novamente em exportar.
        </div>

        <div
          style={{
            height: "10px",
            background: "#e5e7eb",
            borderRadius: "999px",
            overflow: "hidden",
            marginBottom: "0.65rem",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${Math.min(100, progress.percent)}%`,
              background: done ? "#059669" : error ? "#dc2626" : "#0f766e",
              borderRadius: "999px",
              transition: "width 0.35s ease",
            }}
          />
        </div>

        <p
          style={{
            margin: "0 0 1rem",
            fontSize: "0.88rem",
            color: done ? "#065f46" : error ? "#991b1b" : "#374151",
            minHeight: "2.5rem",
            lineHeight: 1.45,
          }}
        >
          {error ||
            (done
              ? "Download iniciado. Esta janela fechara em instantes."
              : progress.message)}
        </p>

        {error ? (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={() => onCloseRef.current()}
              style={{
                padding: "0.5rem 1rem",
                background: "#f3f4f6",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
              }}
            >
              Fechar
            </button>
          </div>
        ) : (
          <p style={{ margin: 0, fontSize: "0.78rem", color: "#9ca3af", textAlign: "center" }}>
            {busy ? "Nao feche esta janela nem navegue para outra pagina." : ""}
          </p>
        )}
      </div>
    </div>
  );
}
