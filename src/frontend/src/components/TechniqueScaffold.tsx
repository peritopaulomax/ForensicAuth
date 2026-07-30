import type { ReactNode } from "react";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton, ForensicProgressBar } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import type { ForensicTechniqueMeta } from "@/config/forensicTechniqueMeta";

export interface TechniqueScaffoldProps {
  caseId: string;
  techniqueId: string;
  /** Se true, não renderiza o seletor de evidência (quando embutido em grupo). */
  embedded?: boolean;
  /** Se true, usa layout com "Voltar ao caso" em vez de PageShell. */
  useReturnToCaseLayout?: boolean;
  /** Conteúdo do painel de evidência (seletor específico). */
  evidencePanel?: ReactNode;
  parametersPanel?: ReactNode;
  /** Conteúdo do painel de resultado. */
  resultPanel?: ReactNode;
  /** Se true, mostra botão de processar no final dos parâmetros. */
  showProcessButton?: boolean;
  /** Label do botão de processar. */
  processButtonLabel?: string;
  /** Se true, desabilita o botão de processar. */
  processButtonDisabled?: boolean;
  /** Se true, mostra spinner no botão de processar. */
  processButtonRunning?: boolean;
  /** Callback do botão de processar. */
  onProcess?: () => void;
  /** Se true, mostra barra de progresso. */
  showProgress?: boolean;
  /** Progresso (0-100). */
  progress?: number;
  /** Label do progresso. */
  progressLabel?: string;
  /** Se true, a barra de progresso está ativa. */
  progressRunning?: boolean;
  /** Mensagem de erro global. */
  error?: string | null;
  /** Mensagem de salvamento. */
  saveMessage?: { type: "ok" | "err"; text: string } | null;
  /** Metadados customizados (sobrescreve o padrão do techniqueId). */
  meta?: ForensicTechniqueMeta;
  /** Children adicionais (renderizados após os painéis padrão). */
  children?: ReactNode;
}

export default function TechniqueScaffold({
  caseId,
  techniqueId,
  embedded = false,
  evidencePanel,
  parametersPanel,
  resultPanel,
  showProcessButton = false,
  processButtonLabel = "Processar",
  processButtonDisabled = false,
  processButtonRunning = false,
  onProcess,
  showProgress = false,
  progress = 0,
  progressLabel = "",
  progressRunning = true,
  error,
  saveMessage,
  meta,
  children,
}: TechniqueScaffoldProps) {
  const techniqueMeta = meta || FORENSIC_TECHNIQUE_META[techniqueId];

  const content = (
    <>
      {evidencePanel && <AnalysisPanel title="Evidência">{evidencePanel}</AnalysisPanel>}

      {parametersPanel && (
        <AnalysisPanel title="Parâmetros">
          {parametersPanel}
          {showProcessButton && onProcess && (
            <ProcessButton
              onClick={onProcess}
              disabled={processButtonDisabled}
              running={processButtonRunning}
              label={processButtonLabel}
              progress={progress}
              progressLabel={progressLabel}
            />
          )}
        </AnalysisPanel>
      )}

      {showProgress && (
        <ForensicProgressBar
          progress={progress}
          progressLabel={progressLabel}
          running={progressRunning}
        />
      )}

      {error && <MessageBox type="err" text={error} />}
      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}

      {resultPanel && <AnalysisPanel title="Resultado">{resultPanel}</AnalysisPanel>}

      {children}
    </>
  );

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={techniqueMeta?.title || techniqueId}
      intro={<TechniqueReferenceIntro meta={techniqueMeta} techniqueId={techniqueId} />}
      embedded={embedded}
    >
      {content}
    </AnalysisPageShell>
  );
}
