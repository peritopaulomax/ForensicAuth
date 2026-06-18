import { useCallback, useEffect, useRef, useState } from "react";
import { exportCasePeritus, type PeritusExportProgress } from "@/services/peritus";

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

export default function CaseExportPeritusModal({
  open,
  caseId,
  protocolNumber,
  onClose,
}: Props) {
  const [progress, setProgress] = useState<PeritusExportProgress>({
    percent: 0,
    message: "Iniciando exportacao Peritus…",
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
      setProgress({ percent: 0, message: "Iniciando exportacao Peritus…", phase: "preparing" });
      setError("");
      setDone(false);
      setBusy(false);
      return;
    }

    const runId = ++runIdRef.current;
    setBusy(true);
    setError("");
    setDone(false);
    setProgress({ percent: 4, message: "Preparando ZIP Peritus…", phase: "preparing" });

    const controller = new AbortController();
    abortRef.current = controller;

    let simulated = 8;
    tickRef.current = window.setInterval(() => {
      if (runId !== runIdRef.current) return;
      simulated = Math.min(simulated + 2, 88);
      setProgress((prev) => {
        if (prev.phase === "downloading" || prev.phase === "done") return prev;
        let message = "Empacotando arquivos e peritusCase.xml…";
        let phase = prev.phase;
        if (simulated < 40) {
          phase = "preparing";
          message = "Verificando integridade do pacote original…";
        } else if (simulated < 70) {
          phase = "packaging";
          message = "Gerando ZIP compativel com Peritus…";
        } else {
          phase = "waiting";
          message = "Aguardando servidor (casos grandes podem demorar)…";
        }
        return { percent: simulated, message, phase };
      });
    }, STAGE_TICK_MS);

    void (async () => {
      try {
        const { blob, filename } = await exportCasePeritus(caseId, {
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
          message: "Pacote Peritus pronto — download iniciado.",
          phase: "done",
        });
        triggerDownload(blob, filename);
        setDone(true);
        window.setTimeout(() => onCloseRef.current(), 1800);
      } catch (err: unknown) {
        if (runId !== runIdRef.current || controller.signal.aborted) return;
        clearTick();
        const msg =
          err && typeof err === "object" && "message" in err
            ? String((err as { message: string }).message)
            : "Erro ao exportar pacote Peritus";
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
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1.2rem" }}>Exportar caso Peritus</h2>
        {protocolNumber && (
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.88rem", color: "#6b7280" }}>
            Caso <strong>{protocolNumber}</strong>
          </p>
        )}
        <p
          style={{
            marginBottom: "1rem",
            padding: "0.75rem",
            background: "#eef2ff",
            borderRadius: "8px",
            fontSize: "0.85rem",
            color: "#3730a3",
          }}
        >
          Se o caso nao foi alterado, o ZIP exportado e <strong>identico</strong> ao importado
          (mesma cadeia Peritus e derived-files).
        </p>
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
              background: done ? "#059669" : error ? "#dc2626" : "#4338ca",
              borderRadius: "999px",
              transition: "width 0.35s ease",
            }}
          />
        </div>
        <p style={{ margin: "0 0 1rem", fontSize: "0.88rem", color: error ? "#991b1b" : "#374151" }}>
          {error || (done ? "Download iniciado." : progress.message)}
        </p>
        {error && (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button type="button" onClick={() => onCloseRef.current()}>
              Fechar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
