import { Link, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState, type ReactNode } from "react";
import { DerivativeSaveProvider } from "@/components/DerivativeSaveNotifier";
import { getCase } from "@/services/cases";
import {
  buildCaseAnalysesUrl,
  buildReturnToCaseAnalysesUrl,
  getAnalysisRouteMeta,
} from "@/utils/caseAnalysisNav";

interface Props {
  caseId: string;
  title: string;
  /** Subtítulo curto (legado). Omita quando usar `intro`. */
  subtitle?: string;
  /** Bloco bibliográfico / intro abaixo do título (substitui o subtítulo descritivo). */
  intro?: ReactNode;
  /** Modo embutido na página de grupo — sem breadcrumb, voltar ou título. */
  embedded?: boolean;
  children: ReactNode;
}

export default function AnalysisPageShell({
  caseId,
  title,
  subtitle,
  intro,
  embedded = false,
  children,
}: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const routeMeta = getAnalysisRouteMeta(location.pathname);
  const [caseTitle, setCaseTitle] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCase(caseId)
      .then((data) => {
        if (!cancelled) setCaseTitle(data.title);
      })
      .catch(() => {
        if (!cancelled) setCaseTitle(null);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  const analysesHref = routeMeta
    ? buildCaseAnalysesUrl(caseId, routeMeta.media)
    : buildReturnToCaseAnalysesUrl(caseId, location.pathname);

  if (embedded) {
    return (
      <DerivativeSaveProvider caseId={caseId}>
        <div className="analysis-page-shell analysis-page-shell--embedded">
          {intro}
          {children}
        </div>
      </DerivativeSaveProvider>
    );
  }

  return (
    <DerivativeSaveProvider caseId={caseId}>
    <div className="analysis-page-shell">
      <nav className="analysis-breadcrumb" aria-label="Navegação">
        <Link to="/">Casos</Link>
        <span className="analysis-breadcrumb__sep">›</span>
        <Link to={`/cases/${caseId}`}>{caseTitle || `Caso ${caseId.slice(0, 8)}…`}</Link>
        <span className="analysis-breadcrumb__sep">›</span>
        <Link to={analysesHref}>Análises</Link>
        <span className="analysis-breadcrumb__sep">›</span>
        <span aria-current="page">{title}</span>
      </nav>

      <button
        type="button"
        onClick={() => navigate(analysesHref)}
        style={{
          background: "none",
          border: "none",
          color: "#0369a1",
          cursor: "pointer",
          fontSize: "0.85rem",
          marginBottom: "0.75rem",
          padding: 0,
        }}
      >
        ← Voltar as analises do caso
      </button>

      <h1 className="analysis-page-shell__title">{title}</h1>
      {intro ?? (subtitle ? <p className="analysis-page-shell__subtitle">{subtitle}</p> : null)}
      {children}
    </div>
    </DerivativeSaveProvider>
  );
}

export function AnalysisPanel({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={["analysis-panel", className].filter(Boolean).join(" ")}>
      {title && <h3 className="analysis-panel__title">{title}</h3>}
      {children}
    </div>
  );
}

export function parseDeviceFromProgress(message?: string): string | null {
  if (!message) return null;
  if (/\bem GPU\b|GPU\/CPU \(cuda\)|\(cuda\)|CUDA/i.test(message)) return "GPU";
  if (/\bCPU\b|fallback VRAM|recarregando em CPU/i.test(message)) return "CPU";
  return null;
}

export function formatInferenceDevice(value: unknown): string | null {
  if (value == null || value === "") return null;
  const raw = String(value).toLowerCase();
  if (raw === "cuda" || raw === "gpu") return "GPU";
  if (raw === "cpu") return "CPU";
  return String(value).toUpperCase();
}

export function ForensicProgressBar({
  progress = 0,
  progressLabel,
  running = true,
  inferenceDevice,
}: {
  progress?: number;
  progressLabel?: string;
  running?: boolean;
  /** GPU / CPU — exibido ao lado da barra durante o processamento. */
  inferenceDevice?: string | null;
}) {
  if (!running) return null;
  const pct = Math.round(Math.min(100, Math.max(0, progress)));
  const device = inferenceDevice ?? parseDeviceFromProgress(progressLabel);

  return (
    <div style={{ width: "100%", maxWidth: 640, marginTop: "0.65rem" }} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.35rem",
          fontSize: "0.78rem",
          color: "#4b5563",
          gap: "0.75rem",
        }}
      >
        <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
          {progressLabel || "Processando…"}
        </span>
        {device && (
          <span
            style={{
              flexShrink: 0,
              padding: "0.12rem 0.45rem",
              borderRadius: 4,
              fontSize: "0.68rem",
              fontWeight: 700,
              letterSpacing: "0.02em",
              background: device === "GPU" ? "#dbeafe" : "#f3f4f6",
              color: device === "GPU" ? "#1d4ed8" : "#6b7280",
            }}
            title={device === "CPU" ? "Inferencia em CPU (mais lenta que GPU)" : "Inferencia acelerada por GPU"}
          >
            {device}
          </span>
        )}
        <span style={{ flexShrink: 0, fontWeight: 600 }}>{pct}%</span>
      </div>
      <div
        style={{
          height: 7,
          background: "#e5e7eb",
          borderRadius: 999,
          overflow: "hidden",
          boxShadow: "inset 0 1px 2px rgba(0,0,0,0.06)",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            borderRadius: 999,
            background: "linear-gradient(90deg, #1a1a2e 0%, #0369a1 45%, #0ea5e9 100%)",
            backgroundSize: "200% 100%",
            transition: "width 0.25s ease-out",
            animation: running ? "va-progress-shimmer 1.8s ease-in-out infinite" : undefined,
          }}
        />
      </div>
      <style>{`
        @keyframes va-progress-shimmer {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
      `}</style>
    </div>
  );
}

export function ProcessButton({
  onClick,
  disabled,
  running,
  label = "Processar",
  progress,
  progressLabel,
  inferenceDevice,
}: {
  onClick: () => void;
  disabled?: boolean;
  running?: boolean;
  label?: string;
  /** 0–100; exibido ao lado do botao quando `running`. */
  progress?: number;
  progressLabel?: string;
  inferenceDevice?: string | null;
}) {
  const showBar = Boolean(running);
  const pct = Math.round(Math.min(100, Math.max(0, progress ?? 0)));

  return (
    <div style={{ width: "100%", maxWidth: 640 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={onClick}
          disabled={disabled || running}
          style={{
            padding: "0.6rem 1.5rem",
            background: "#1a1a2e",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: disabled || running ? "not-allowed" : "pointer",
            fontSize: "0.9rem",
            fontWeight: 500,
            opacity: disabled || running ? 0.85 : 1,
            flexShrink: 0,
          }}
        >
          {running ? "Processando…" : label}
        </button>
      </div>
      <ForensicProgressBar
        progress={pct}
        progressLabel={progressLabel}
        running={showBar}
        inferenceDevice={inferenceDevice}
      />
    </div>
  );
}

export function MessageBox({ type, text }: { type: "ok" | "err"; text: string }) {
  return (
    <div
      style={{
        marginTop: "0.75rem",
        padding: "0.6rem 0.75rem",
        background: type === "ok" ? "#dcfce7" : "#fee2e2",
        color: type === "ok" ? "#166534" : "#991b1b",
        borderRadius: "6px",
        fontSize: "0.85rem",
      }}
    >
      {text}
    </div>
  );
}
