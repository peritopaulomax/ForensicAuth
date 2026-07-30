import { useCallback, useState } from "react";
import { useDerivativeSave } from "./useDerivativeSave";
import { useArtifactBlobs } from "./useArtifactBlobs";

export interface ArtifactGalleryItem {
  /** Nome canônico do arquivo no job (ex: "heatmap.png"). */
  filename: string;
  /** Label para botão de salvar. */
  label: string;
  /** URL exibível, se já carregada. */
  url?: string | null;
}

export interface UseArtifactGalleryOptions {
  /** Se true, limpa a mensagem de salvamento ao iniciar novo job. */
  clearOnStart?: boolean;
}

/**
 * Combina gerenciamento de blobs de artefatos com salvamento em lote de derivados.
 * Ideal para páginas Template A/B que produzem 1-N imagens/artefatos salváveis.
 */
export function useArtifactGallery(options?: UseArtifactGalleryOptions) {
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { register, revoke, revokeAll, isBlobUrl } = useArtifactBlobs();
  const [items, setItems] = useState<ArtifactGalleryItem[]>([]);

  const clear = useCallback(() => {
    setItems((prev) => {
      prev.forEach((it) => {
        if (it.url) revoke(it.url);
      });
      return [];
    });
    clearMessage();
  }, [revoke, clearMessage]);

  const registerItems = useCallback(
    (newItems: ArtifactGalleryItem[]) => {
      // Revoga URLs antigas antes de substituir
      setItems((prev) => {
        prev.forEach((it) => {
          if (it.url) revoke(it.url);
        });
        return newItems.map((it) => ({
          ...it,
          url: it.url ? register(it.url) : it.url,
        }));
      });
    },
    [register, revoke]
  );

  const updateUrl = useCallback(
    (filename: string, url: string | null) => {
      setItems((prev) =>
        prev.map((it) => {
          if (it.filename !== filename) return it;
          if (it.url) revoke(it.url);
          return { ...it, url: url ? register(url) : url };
        })
      );
    },
    [register, revoke]
  );

  const saveItem = useCallback(
    async (jobId: string | null, filename: string, label: string) => {
      return save(jobId, filename, label);
    },
    [save]
  );

  const startNewJob = useCallback(() => {
    if (options?.clearOnStart !== false) {
      clear();
    }
  }, [clear, options?.clearOnStart]);

  return {
    items,
    saving,
    saveMessage,
    registerItems,
    updateUrl,
    saveItem,
    save,
    clear,
    startNewJob,
    revokeAll,
    isBlobUrl,
  };
}
