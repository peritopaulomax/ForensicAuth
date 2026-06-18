import { useEffect, useState } from "react";
import { buildMaskBlobUrl, revokeBlobUrl } from "@/utils/localizationMaskPreview";

/**
 * Atualiza a máscara binária no cliente quando o limiar muda,
 * a partir do mapa de scores já carregado (sem nova inferência).
 */
export function useLocalizationMaskPreview(
  scoreMapUrl: string | null,
  threshold: number,
  enabled: boolean
): string | null {
  const [maskUrl, setMaskUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !scoreMapUrl) {
      setMaskUrl((prev) => {
        revokeBlobUrl(prev);
        return null;
      });
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void buildMaskBlobUrl(scoreMapUrl, threshold)
        .then((url) => {
          if (cancelled) {
            revokeBlobUrl(url);
            return;
          }
          setMaskUrl((prev) => {
            revokeBlobUrl(prev);
            return url;
          });
        })
        .catch(() => {
          if (!cancelled) {
            setMaskUrl((prev) => {
              revokeBlobUrl(prev);
              return null;
            });
          }
        });
    }, 60);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [scoreMapUrl, threshold, enabled]);

  useEffect(
    () => () => {
      setMaskUrl((prev) => {
        revokeBlobUrl(prev);
        return null;
      });
    },
    []
  );

  return maskUrl;
}
