import { useCallback, useEffect, useRef, useState } from "react";
import {
  importCaseVcp,
  validateCaseVcp,
  type VcpImportProgress,
  type VcpValidationReport,
} from "@/services/cases";
import { parseApiError } from "@/lib/apiErrors";
import { isLikelyVcpFilename, probeVcpPackage } from "@/lib/vcpDetect";

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: (caseId: string) => void;
  initialFile?: File | null;
  autoValidate?: boolean;
}

const SERVER_TICK_MS = 500;

export default function CaseImportVcpModal({
  open,
  onClose,
  onImported,
  initialFile = null,
  autoValidate = false,
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<VcpValidationReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [localError, setLocalError] = useState("");
  const [probeHint, setProbeHint] = useState("");
  const [progress, setProgress] = useState<VcpImportProgress>({
    percent: 0,
    message: "",
    phase: "uploading",
  });
  const inputRef = useRef<HTMLInputElement>(null);
  const autoRan = useRef(false);
  const tickRef = useRef<number | null>(null);
  const onCloseRef = useRef(onClose);

  onCloseRef.current = onClose;

  const clearTick = useCallback(() => {
    if (tickRef.current != null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    clearTick();
    setFile(null);
    setReport(null);
    setLocalError("");
    setProbeHint("");
    setImporting(false);
    setBusy(false);
    setProgress({ percent: 0, message: "", phase: "uploading" });
    autoRan.current = false;
  }, [clearTick]);

  useEffect(() => {
    if (!open) {
      reset();
      return;
    }
    if (initialFile) {
      setFile(initialFile);
    }
  }, [open, initialFile, reset]);

  const startServerProgress = useCallback(
    (startPct: number, tombstone: boolean) => {
      clearTick();
      let simulated = startPct;
      tickRef.current = window.setInterval(() => {
        simulated = Math.min(simulated + 2, 94);
        let message = "Processando pacote no servidor…";
        let phase: VcpImportProgress["phase"] = "extracting";
        if (simulated < startPct + 8) {
          phase = tombstone ? "purging" : "validating";
          message = tombstone
            ? "Substituindo caso excluido (tombstone)…"
            : "Validando integridade forense…";
        } else if (simulated < startPct + 20) {
          phase = "extracting";
          message = "Extraindo arquivos de evidencia…";
        } else if (simulated < 88) {
          phase = "chain";
          message = "Gravando cadeia de custodia e assinaturas…";
        } else {
          message = "Finalizando importacao (pode levar alguns minutos)…";
        }
        setProgress({ percent: simulated, message, phase });
      }, SERVER_TICK_MS);
    },
    [clearTick]
  );

  const runValidate = useCallback(
    async (f: File) => {
      setBusy(true);
      setLocalError("");
      setReport(null);
      try {
        const probe = await probeVcpPackage(f);
        if (!probe.isZip) {
          setLocalError("O arquivo nao e um ZIP valido.");
          return;
        }
        if (!probe.looksLikeVcp) {
          setLocalError(
            "ZIP reconhecido, mas nao parece um Verification Case Package (VCP) do ForensicAuth (estrutura incompleta)."
          );
          return;
        }
        setProbeHint("Estrutura de VCP detectada — validacao forense completa no servidor…");
        const result = await validateCaseVcp(f, {
          onProgress: setProgress,
        });
        setReport(result);
        if (!result.valid) {
          setLocalError((result.issues || []).join("; ") || "Pacote invalido");
        }
      } catch (err: unknown) {
        setLocalError(parseApiError(err, "Erro na validacao do pacote"));
      } finally {
        setBusy(false);
        setProbeHint("");
        clearTick();
      }
    },
    [clearTick]
  );

  useEffect(() => {
    if (!open || !autoValidate || !file || autoRan.current) return;
    autoRan.current = true;
    void runValidate(file);
  }, [open, autoValidate, file, runValidate]);

  async function handleImport() {
    if (!file || !report?.valid) return;
    setImporting(true);
    setBusy(true);
    setLocalError("");
    setProgress({
      percent: 4,
      message: "Preparando importacao…",
      phase: "uploading",
    });

    const tombstone = !!report.conflicts?.replaceable_tombstone;
    startServerProgress(72, tombstone);

    try {
      const result = await importCaseVcp(file, {
        replaceableTombstone: tombstone,
        onProgress: (p) => {
          if (p.phase === "uploading") {
            setProgress(p);
          }
        },
      });
      clearTick();
      setProgress({
        percent: 100,
        message: "Caso importado com sucesso.",
        phase: "done",
      });
      window.setTimeout(() => {
        onImported(result.case_id);
        onCloseRef.current();
      }, 1200);
    } catch (err: unknown) {
      clearTick();
      setLocalError(parseApiError(err, "Erro na importacao do pacote VCP"));
      setProgress((prev) => ({ ...prev, phase: "error" }));
      setImporting(false);
      setBusy(false);
    }
  }

  async function onFilePicked(f: File | null) {
    setFile(f);
    setReport(null);
    setLocalError("");
    setProbeHint("");
    if (!f) return;
    if (!isLikelyVcpFilename(f.name)) {
      setLocalError("Use um arquivo .zip ou .vcp.zip (Verification Case Package) exportado pelo ForensicAuth.");
      return;
    }
    await runValidate(f);
  }

  if (!open) return null;

  const showImportOverlay = importing;
  const canCloseDialog = !importing && !busy;

  if (showImportOverlay) {
    return (
      <div
        role="dialog"
        aria-modal
        aria-labelledby="vcp-import-progress-title"
        aria-busy
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
        >
          <h2
            id="vcp-import-progress-title"
            style={{ margin: "0 0 0.5rem", color: "#1a1a2e", fontSize: "1.2rem" }}
          >
            Importando Verification Case Package (VCP)
          </h2>
          {file && (
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#6b7280" }}>
              <strong>{file.name}</strong> — {(file.size / (1024 * 1024)).toFixed(1)} MB
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
            Pacotes grandes podem levar varios minutos. Nao feche esta janela nem navegue para
            outra pagina ate a conclusao.
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
                background: progress.phase === "error" ? "#dc2626" : "#0f766e",
                borderRadius: "999px",
                transition: "width 0.35s ease",
              }}
            />
          </div>
          <p
            style={{
              margin: "0 0 1rem",
              fontSize: "0.88rem",
              color: localError ? "#991b1b" : "#374151",
              minHeight: "2.5rem",
              lineHeight: 1.45,
            }}
          >
            {localError || progress.message}
          </p>
          {localError && (
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => {
                  setImporting(false);
                  setBusy(false);
                  clearTick();
                }}
                style={{
                  padding: "0.5rem 1rem",
                  background: "#f3f4f6",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                Voltar
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal
      aria-labelledby="vcp-import-title"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 2000,
        padding: "1rem",
      }}
      onClick={() => canCloseDialog && onCloseRef.current()}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: "10px",
          padding: "1.5rem",
          maxWidth: "480px",
          width: "100%",
          maxHeight: "90vh",
          overflow: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="vcp-import-title" style={{ margin: "0 0 0.5rem", color: "#1a1a2e", fontSize: "1.2rem" }}>
          Importar Verification Case Package (VCP)
        </h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.88rem", color: "#4b5563", lineHeight: 1.5 }}>
          Restaura um caso exportado de outra instancia ForensicAuth. A validacao forense (cadeia,
          assinaturas e arquivos) roda no servidor antes de gravar na base.
        </p>

        <input
          ref={inputRef}
          type="file"
          accept=".zip,application/zip"
          style={{ display: "none" }}
          onChange={(e) => void onFilePicked(e.target.files?.[0] || null)}
        />

        <div
          style={{
            border: "2px dashed #d1d5db",
            borderRadius: "8px",
            padding: "1.25rem",
            textAlign: "center",
            marginBottom: "1rem",
            background: "#f9fafb",
          }}
        >
          {file ? (
            <p style={{ margin: 0, fontSize: "0.9rem", color: "#374151" }}>
              <strong>{file.name}</strong>
              <br />
              <span style={{ color: "#6b7280" }}>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
            </p>
          ) : (
            <p style={{ margin: 0, fontSize: "0.88rem", color: "#6b7280" }}>
              Arraste um .vcp.zip aqui ou escolha o arquivo
            </p>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            style={{
              marginTop: "0.75rem",
              padding: "0.45rem 0.9rem",
              background: "#f3f4f6",
              border: "1px solid #e5e7eb",
              borderRadius: "6px",
              cursor: busy ? "wait" : "pointer",
            }}
          >
            Escolher arquivo
          </button>
        </div>

        {busy && !importing && (
          <>
            <div
              style={{
                height: "8px",
                background: "#e5e7eb",
                borderRadius: "999px",
                overflow: "hidden",
                marginBottom: "0.5rem",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${Math.min(100, progress.percent)}%`,
                  background: "#0369a1",
                  borderRadius: "999px",
                  transition: "width 0.3s ease",
                }}
              />
            </div>
            <p style={{ fontSize: "0.85rem", color: "#0369a1", margin: "0 0 0.75rem" }}>
              {probeHint || progress.message || "Validando pacote…"}
            </p>
          </>
        )}

        {localError && !importing && (
          <div
            style={{
              padding: "0.65rem 0.85rem",
              background: "#fef2f2",
              color: "#991b1b",
              borderRadius: "6px",
              fontSize: "0.85rem",
              marginBottom: "0.75rem",
            }}
          >
            {localError}
          </div>
        )}

        {report && !importing && (
          <div
            style={{
              padding: "0.65rem 0.85rem",
              background: report.valid ? "#ecfdf5" : "#fef2f2",
              color: report.valid ? "#065f46" : "#991b1b",
              borderRadius: "6px",
              fontSize: "0.85rem",
              marginBottom: "0.75rem",
            }}
          >
            {report.valid ? (
              <>
                Pacote valido — protocolo <strong>{report.package.protocol_number}</strong>,{" "}
                {report.chain.records_checked} registro(s) na cadeia, {report.files.checked}{" "}
                arquivo(s) conferido(s).
                {report.conflicts?.replaceable_tombstone && (
                  <>
                    <br />
                    <span style={{ color: "#92400e" }}>
                      Este pacote substituira um caso excluido anteriormente (tombstone). A
                      substituicao ficara registrada na cadeia de custodia.
                    </span>
                  </>
                )}
              </>
            ) : (
              <>Validacao falhou: {(report.issues || []).join("; ")}</>
            )}
          </div>
        )}

        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button
            type="button"
            disabled={busy}
            onClick={() => onCloseRef.current()}
            style={{
              padding: "0.5rem 1rem",
              background: "#f3f4f6",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
            }}
          >
            Cancelar
          </button>
          {file && !report && !busy && (
            <button
              type="button"
              onClick={() => void runValidate(file)}
              style={{
                padding: "0.5rem 1rem",
                background: "#0369a1",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
              }}
            >
              Validar
            </button>
          )}
          <button
            type="button"
            disabled={!report?.valid || busy}
            onClick={() => void handleImport()}
            style={{
              padding: "0.5rem 1rem",
              background: report?.valid ? "#0f766e" : "#9ca3af",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: report?.valid && !busy ? "pointer" : "not-allowed",
            }}
          >
            Importar na base
          </button>
        </div>
      </div>
    </div>
  );
}
