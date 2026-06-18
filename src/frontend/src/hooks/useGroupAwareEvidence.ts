import { useCallback, useEffect, useRef, useState } from "react";
import { useImageGroupSession } from "@/context/ImageGroupSessionContext";

/**
 * Evidência local (página dedicada) ou compartilhada (aba dentro do grupo de imagem).
 * Quando embutido, chama `applyEvidence` sempre que a evidência do grupo mudar.
 */
export function useGroupAwareEvidence(
  caseId: string,
  applyEvidence: (id: string, source: "original" | "derivative") => void,
) {
  const groupSession = useImageGroupSession();
  const embedded = groupSession != null;

  const [localEvidence, setLocalEvidence] = useState<string | null>(null);
  const [localSource, setLocalSource] = useState<"original" | "derivative">("original");

  const evidenceId = embedded ? groupSession.evidenceId : localEvidence;
  const selectionSource = embedded ? groupSession.selectionSource : localSource;

  const appliedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!embedded || !groupSession.evidenceId) return;
    const key = `${groupSession.evidenceId}:${groupSession.selectionSource}`;
    if (appliedKeyRef.current === key) return;
    appliedKeyRef.current = key;
    applyEvidence(groupSession.evidenceId, groupSession.selectionSource);
  }, [embedded, groupSession?.evidenceId, groupSession?.selectionSource, applyEvidence]);

  const onSelectEvidence = useCallback(
    (id: string, source: "original" | "derivative" = "original") => {
      if (embedded) return;
      setLocalEvidence(id);
      setLocalSource(source);
      applyEvidence(id, source);
    },
    [embedded, applyEvidence],
  );

  useEffect(() => {
    if (!embedded) {
      setLocalEvidence(null);
      setLocalSource("original");
      appliedKeyRef.current = null;
    }
  }, [caseId, embedded]);

  return {
    embedded,
    showEvidencePicker: !embedded,
    showPageShell: !embedded,
    evidenceId,
    selectionSource,
    onSelectEvidence,
    groupId: groupSession?.groupId ?? null,
  };
}
