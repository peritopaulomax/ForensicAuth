import { useCallback, useEffect, useRef, useState } from "react";
import {
  importCasePeritus,
  validateCasePeritus,
  type PeritusImportProgress,
  type PeritusValidationReport,
} from "@/services/peritus";
import { parseApiError } from "@/lib/apiErrors";
import { isLikelyPeritusFilename, probePeritusPackage } from "@/lib/peritusDetect";

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: (caseId: string) => void;
  initialFile?: File | null;
  autoValidate?: boolean;
}

const SERVER_TICK_MS = 500;

export default function CaseImportPeritusModal({
  open,
  onClose,
  onImported,
  initialFile = null,
  autoValidate = false,
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<PeritusValidationReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [localError, setLocalError] = useState("");
  const [probeHint, setProbeHint] = useState("");
  const [progress, setProgress] = useState<PeritusImportProgress>({
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
    (startPct: number) => {
      clearTick();
      let simulated = startPct;
      tickRef.current = window.setInterval(() => {
        simulated = Math.min(simulated + 2, 94);
        let message = "Processando pacote Peritus Desktop no servidor…";
        let phase: PeritusImportProgress["phase"] = "extracting";
        if (simulated < startPct + 10) {
          phase = "validating";
          message = "Validando peritusCase.xml e hashes SHA-256…";
        } else if (simulated < 88) {
          phase = "extracting";
          message = "Preservando arquivos e cadeia de calculos…";
        } else {
          message = "Finalizando importacao (pacotes grandes podem demorar)…";
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
        const probe = await probePeritusPackage(f);
        if (!probe.isZip) {
          setLocalError("O arquivo nao e um ZIP valido.");
          return;
        }
        if (!probe.looksLikePeritus) {
          setProbeHint(
            "Nao foi possivel detectar Peritus Desktop localmente (ZIP grande). Validando no servidor…"
          );
        } else {
          setProbeHint("Estrutura Peritus Desktop detectada — validacao completa no servidor…");
        }
        const result = await validateCasePeritus(f, { onProgress: setProgress });
        setReport(result);
        if (!result.valid) {
          setLocalError((result.issues || []).join("; ") || "Pacote invalido");
        }
      } catch (err: unknown) {
        setLocalError(parseApiError(err, "Erro na validacao do pacote Peritus Desktop"));
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
    setProgress({ percent: 4, message: "Preparando importacao Peritus Desktop…", phase: "uploading" });
    startServerProgress(72);

    try {
      const result = await importCasePeritus(file, {
        onProgress: (p) => {
          if (p.phase === "uploading") setProgress(p);
        },
      });
      clearTick();
      setProgress({ percent: 100, message: "Caso importado do Peritus Desktop.", phase: "done" });
      window.setTimeout(() => {
        onImported(result.case_id);
        onCloseRef.current();
      }, 1200);
    } catch (err: unknown) {
      clearTick();
      setLocalError(parseApiError(err, "Erro na importacao do pacote Peritus Desktop"));
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
    if (!isLikelyPeritusFilename(f.name)) {
      setLocalError("Use um arquivo .zip exportado do Peritus Desktop.");
      return;
    }
    await runValidate(f);
  }

  if (!open) return null;

  if (importing) {
    return (
      <div
        role="dialog"
        aria-modal
        aria-labelledby="peritus-import-progress-title"
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
          }}
        >
          <h2 id="peritus-import-progress-title" style={{ margin: "0 0 0.5rem", fontSize: "1.2rem" }}>
            Importando Peritus Desktop
          </h2>
          {file && (
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#6b7280" }}>
              <strong>{file.name}</strong> — {(file.size / (1024 * 1024)).toFixed(1)} MB
            </p>
          )}
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
                background: progress.phase === "error" ? "#dc2626" : "#4338ca",
                borderRadius: "999px",
                transition: "width 0.35s ease",
              }}
            />
          </div>
          <p style={{ margin: 0, fontSize: "0.88rem", color: localError ? "#991b1b" : "#374151" }}>
            {localError || progress.message}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal
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
      onClick={() => !busy && onCloseRef.current()}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: "10px",
          padding: "1.5rem",
          maxWidth: "500px",
          width: "100%",
          maxHeight: "90vh",
          overflow: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1.2rem", color: "#1a1a2e" }}>
          Importar Peritus Desktop
        </h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.88rem", color: "#4b5563", lineHeight: 1.5 }}>
          ZIP exportado do <strong>Peritus Desktop</strong> com <strong>peritusCase.xml</strong>, pastas de
          evidencias e <strong>derived-files/</strong>. A cadeia de calculos e o XML assinado sao preservados
          byte-a-byte para exportacao identica.
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
            border: "2px dashed #c7d2fe",
            borderRadius: "8px",
            padding: "1.25rem",
            textAlign: "center",
            marginBottom: "1rem",
            background: "#eef2ff",
          }}
        >
          {file ? (
            <p style={{ margin: 0, fontSize: "0.9rem" }}>
              <strong>{file.name}</strong>
              <br />
              <span style={{ color: "#6b7280" }}>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
            </p>
          ) : (
            <p style={{ margin: 0, fontSize: "0.88rem", color: "#6b7280" }}>
              Escolha o ZIP exportado do Peritus Desktop
            </p>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            style={{
              marginTop: "0.75rem",
              padding: "0.45rem 0.9rem",
              background: "#fff",
              border: "1px solid #c7d2fe",
              borderRadius: "6px",
              cursor: busy ? "wait" : "pointer",
            }}
          >
            Escolher arquivo
          </button>
        </div>

        {busy && (
          <p style={{ fontSize: "0.85rem", color: "#4338ca", margin: "0 0 0.75rem" }}>
            {probeHint || progress.message || "Validando…"}
          </p>
        )}

        {localError && (
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

        {report && (
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
                Pacote valido — <strong>{report.package.title}</strong> (
                {report.package.protocol_number}), {report.package.evidence_count} evidencia(s),{" "}
                {report.package.derived_count} derivado(s), {report.package.calculation_count}{" "}
                calculo(s), {report.files.checked} hash(es) conferido(s).
                {(report.files.orphan_count ?? 0) > 0 && (
                  <>
                    <br />
                    <span style={{ color: "#6b7280" }}>
                      {report.files.orphan_count} arquivo(s) extra(s) no ZIP (permitido pelo Peritus Desktop).
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
          <button
            type="button"
            disabled={!report?.valid || busy}
            onClick={() => void handleImport()}
            style={{
              padding: "0.5rem 1rem",
              background: report?.valid ? "#4338ca" : "#9ca3af",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: report?.valid && !busy ? "pointer" : "not-allowed",
            }}
          >
            Importar caso
          </button>
        </div>
      </div>
    </div>
  );
}
