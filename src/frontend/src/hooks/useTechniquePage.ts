import { useCallback } from "react";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
import type { MediaType } from "@/components/EvidenceSelectorFactory";

export type EvidenceSelectionHandler = (id: string, source: "original" | "derivative") => void;

export interface UseTechniquePageOptions {
  caseId: string;
  techniqueId: string;
  mediaType: MediaType;
  onSelectEvidence?: EvidenceSelectionHandler;
}

/**
 * Hook que orquestra o ciclo de vida comum de uma página de técnica:
 * evidência, job, salvamento, runtime check.
 * Permite que a página foque apenas nos parâmetros e visualização de resultado.
 */
export function useTechniquePage({
  caseId,
  techniqueId,
  mediaType: _mediaType,
  onSelectEvidence: externalOnSelectEvidence,
}: UseTechniquePageOptions) {
  const forensicJob = useForensicJob();
  const derivativeSave = useDerivativeSave();
  const runtime = useTechniqueRuntime(techniqueId);

  const internalApplyEvidence = useCallback(
    (id: string, source: "original" | "derivative") => {
      forensicJob.reset();
      derivativeSave.clearMessage();
      externalOnSelectEvidence?.(id, source);
    },
    [forensicJob.reset, derivativeSave.clearMessage, externalOnSelectEvidence]
  );

  const evidence = useGroupAwareEvidence(caseId, internalApplyEvidence);

  return {
    ...forensicJob,
    ...derivativeSave,
    ...evidence,
    ...runtime,
    runtimeOk: runtime.status?.available ?? null,
    runtimeReason: runtime.status?.reason || "",
  };
}
