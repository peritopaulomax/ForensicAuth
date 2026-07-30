import type { ReactNode } from "react";
import { AnalysisPanel, MessageBox } from "@/components/AnalysisPageShell";
import TechniqueScaffold from "@/components/TechniqueScaffold";

export interface TechniqueUnavailableProps {
  caseId: string;
  techniqueId: string;
  embedded?: boolean;
  reason?: string | null;
  children?: ReactNode;
}

/**
 * Wrapper padrão para exibir indisponibilidade de runtime de uma técnica.
 * Preserva o shell da página (título, breadcrumb, intro) para não quebrar a navegação.
 */
export default function TechniqueUnavailable({
  caseId,
  techniqueId,
  embedded,
  reason,
  children,
}: TechniqueUnavailableProps) {
  return (
    <TechniqueScaffold caseId={caseId} techniqueId={techniqueId} embedded={embedded}>
      <AnalysisPanel title="Indisponivel">
        <MessageBox
          type="err"
          text={
            reason ||
            "A tecnica nao esta disponivel no ambiente atual. Verifique a instalacao dos modelos/bibliotecas de backend."
          }
        />
      </AnalysisPanel>
      {children}
    </TechniqueScaffold>
  );
}
