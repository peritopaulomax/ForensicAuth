import { useCallback, useEffect, useRef } from "react";

export interface ArtifactBlob {
  /** Identificador canônico do artefato (ex: "heatmap.png", "overlay.png"). */
  name: string;
  /** URL exibível (blob: ou caminho HTTP). */
  url: string;
  /** Label legível para botões/tabs. */
  label: string;
  /** Mimetype quando conhecido. */
  contentType?: string;
}

/**
 * Hook para gerenciar ObjectURLs criados a partir de Blobs.
 * Garante revogação automática no unmount e evita vazamento de memória.
 */
export function useArtifactBlobs() {
  const blobsRef = useRef<Set<string>>(new Set());

  const isBlobUrl = useCallback((url: string | null | undefined): url is string => {
    return Boolean(url?.startsWith("blob:"));
  }, []);

  const register = useCallback((url: string) => {
    if (isBlobUrl(url)) {
      blobsRef.current.add(url);
    }
    return url;
  }, [isBlobUrl]);

  const revoke = useCallback((url: string | null | undefined) => {
    if (!isBlobUrl(url)) return;
    URL.revokeObjectURL(url);
    blobsRef.current.delete(url);
  }, [isBlobUrl]);

  const revokeAll = useCallback(() => {
    blobsRef.current.forEach((url) => URL.revokeObjectURL(url));
    blobsRef.current.clear();
  }, []);

  const setUrl = useCallback(
    (setter: (prev: string | null) => string | null) => {
      // Helper opcional: revoga URL anterior ao trocar estado.
      // Contrato: o caller gerencia o estado; este hook só fornece revoke/register.
      return setter;
    },
    []
  );

  useEffect(() => {
    return () => {
      revokeAll();
    };
  }, [revokeAll]);

  return {
    register,
    revoke,
    revokeAll,
    isBlobUrl,
    setUrl,
  };
}
