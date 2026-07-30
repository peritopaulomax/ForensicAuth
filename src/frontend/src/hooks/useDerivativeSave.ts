import { useCallback, useState } from "react";
import { saveDerivative } from "@/services/evidence";
import type { SaveDerivativeResult } from "@/services/evidence";

export interface DerivativeSaveMessage {
  type: "ok" | "err";
  text: string;
}

export interface UseDerivativeSaveOptions {
  /** Extrai o identificador curto para exibição (default: evidence.sha256 ou evidence.id). */
  formatSuccess?: (result: SaveDerivativeResult, label: string) => string;
}

export function useDerivativeSave(options?: UseDerivativeSaveOptions) {
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<DerivativeSaveMessage | null>(null);

  const formatSuccess = useCallback(
    (result: SaveDerivativeResult, label: string) => {
      if (options?.formatSuccess) {
        return options.formatSuccess(result, label);
      }
      const hash = result.evidence?.sha256 || result.evidence?.id || "";
      const short = hash ? hash.slice(0, 16) : "";
      return short ? `${label} na custódia. SHA-256: ${short}…` : `${label} na custódia.`;
    },
    [options]
  );

  const save = useCallback(
    async (
      jobId: string | null,
      filename: string,
      label: string,
      effectiveParameters?: Record<string, unknown>
    ): Promise<boolean> => {
      if (!jobId) {
        setSaveMessage({ type: "err", text: "Nenhum job em execução." });
        return false;
      }
      setSaving(true);
      setSaveMessage(null);
      try {
        const result = await saveDerivative({
          job_id: jobId,
          artifact_filename: filename,
          label,
          effective_parameters: effectiveParameters,
        });
        setSaveMessage({
          type: "ok",
          text: formatSuccess(result, label),
        });
        return true;
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          (err instanceof Error ? err.message : "Erro ao salvar");
        setSaveMessage({ type: "err", text: msg });
        return false;
      } finally {
        setSaving(false);
      }
    },
    [formatSuccess]
  );

  const clearMessage = useCallback(() => {
    setSaveMessage(null);
  }, []);

  return {
    saving,
    saveMessage,
    save,
    clearMessage,
  };
}
