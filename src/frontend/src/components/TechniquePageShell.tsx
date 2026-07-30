import type { ReactNode } from "react";
import { AnalysisPanel } from "@/components/AnalysisPageShell";
import TechniqueScaffold from "@/components/TechniqueScaffold";
import TechniqueUnavailable from "@/components/TechniqueUnavailable";
import EvidenceSelectorFactory, { type MediaType } from "@/components/EvidenceSelectorFactory";
import type { ForensicTechniqueMeta } from "@/config/forensicTechniqueMeta";

export interface TechniquePageShellState {
  evidenceId: string | null;
  selectionSource: "original" | "derivative";
  onSelectEvidence: (id: string, source: "original" | "derivative") => void;
  showEvidencePicker: boolean;
  running: boolean;
  error: string | null;
  progress: number;
  progressLabel: string;
  saveMessage: { type: "ok" | "err"; text: string } | null;
  runtimeOk: boolean | null;
  runtimeReason: string;
}

export interface TechniquePageShellProps extends Partial<TechniquePageShellState> {
  caseId: string;
  techniqueId: string;
  mediaType: MediaType;
  embedded?: boolean;
  /** Props extras para o seletor de evidência. */
  evidenceSelectorProps?: Record<string, unknown>;
  /** Conteúdo do painel de parâmetros. */
  parametersPanel?: ReactNode;
  /** Conteúdo do painel de resultado. */
  resultPanel?: ReactNode;
  /** Children adicionais (ex: painéis customizados). */
  children?: ReactNode;
  /** Metadados customizados (sobrescreve registry). */
  meta?: ForensicTechniqueMeta;
}

/**
 * Shell padronizado para páginas de técnica forense.
 * Combina TechniqueScaffold, seletor de evidência via factory e verificação de runtime.
 * Recebe o estado da página via props (use TechniquePage ou gerencie manualmente).
 */
export default function TechniquePageShell({
  caseId,
  techniqueId,
  mediaType,
  embedded = false,
  evidenceId,
  selectionSource = "original",
  onSelectEvidence,
  showEvidencePicker = true,
  running = false,
  error = null,
  progress = 0,
  progressLabel = "",
  saveMessage = null,
  runtimeOk = null,
  runtimeReason = "",
  evidenceSelectorProps,
  parametersPanel,
  resultPanel,
  children,
  meta,
}: TechniquePageShellProps) {
  if (runtimeOk === false) {
    return (
      <TechniqueUnavailable
        caseId={caseId}
        techniqueId={techniqueId}
        embedded={embedded}
        reason={runtimeReason}
      />
    );
  }

  const shouldShowPicker = showEvidencePicker && onSelectEvidence;

  return (
    <TechniqueScaffold
      caseId={caseId}
      techniqueId={techniqueId}
      embedded={embedded}
      error={error}
      saveMessage={saveMessage}
      showProgress={running}
      progress={progress}
      progressLabel={progressLabel}
      meta={meta}
    >
      {shouldShowPicker && (
        <AnalysisPanel title="Evidência">
          <EvidenceSelectorFactory
            mediaType={mediaType as never}
            caseId={caseId}
            selectedId={evidenceId || null}
            selectionSource={selectionSource}
            onSelect={onSelectEvidence as never}
            {...evidenceSelectorProps}
          />
        </AnalysisPanel>
      )}

      {parametersPanel && <AnalysisPanel title="Parâmetros">{parametersPanel}</AnalysisPanel>}
      {resultPanel && <AnalysisPanel title="Resultado">{resultPanel}</AnalysisPanel>}
      {children}
    </TechniqueScaffold>
  );
}
