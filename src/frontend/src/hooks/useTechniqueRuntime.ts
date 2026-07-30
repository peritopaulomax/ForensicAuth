import { useEffect, useState } from "react";
import api from "@/services/api";

export interface TechniqueRuntimeStatus {
  available: boolean;
  reason: string | null;
}

export function useTechniqueRuntime(techniqueId: string) {
  const [status, setStatus] = useState<TechniqueRuntimeStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    api
      .get<{ name: string; available?: boolean; unavailable_reason?: string | null }[]>("/analysis/techniques")
      .then((response) => {
        if (cancelled) return;
        const technique = response.data.find((t) => t.name === techniqueId);
        setStatus({
          available: technique?.available ?? true,
          reason: technique?.unavailable_reason ?? null,
        });
      })
      .catch(() => {
        if (!cancelled) {
          // Em caso de erro, assume disponível para não bloquear a UI
          setStatus({ available: true, reason: null });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [techniqueId]);

  return { status, loading };
}
