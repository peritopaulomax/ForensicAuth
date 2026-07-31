/** Cache em memoria de blob URLs de thumbnails por evidenceId (evita re-fetch ao remontar). */

const cache = new Map<string, string>();
const inflight = new Map<string, Promise<string>>();

export function getCachedEvidenceThumbnailUrl(evidenceId: string): string | undefined {
  return cache.get(evidenceId);
}

export async function fetchEvidenceThumbnailUrl(
  evidenceId: string,
  loader: () => Promise<Blob>,
): Promise<string> {
  const cached = cache.get(evidenceId);
  if (cached) return cached;

  let pending = inflight.get(evidenceId);
  if (!pending) {
    pending = loader()
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        cache.set(evidenceId, url);
        inflight.delete(evidenceId);
        return url;
      })
      .catch((err) => {
        inflight.delete(evidenceId);
        throw err;
      });
    inflight.set(evidenceId, pending);
  }
  return pending;
}

export function clearEvidenceThumbnailCache(evidenceId?: string): void {
  if (evidenceId) {
    const url = cache.get(evidenceId);
    if (url) URL.revokeObjectURL(url);
    cache.delete(evidenceId);
    inflight.delete(evidenceId);
    return;
  }
  for (const url of cache.values()) {
    URL.revokeObjectURL(url);
  }
  cache.clear();
  inflight.clear();
}
