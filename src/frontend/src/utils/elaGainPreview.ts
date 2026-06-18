/** Apply ELA gain/brilho on heatmap_base (gain=1.0) without a new backend job. */

import { BASE_ELA_SCALE } from "@/utils/elaConstants";

export function revokeBlobUrl(url: string | null | undefined): void {
  if (url?.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Falha ao carregar heatmap ELA"));
    img.src = src;
  });
}

/**
 * Scale heatmap_base (produced at gain=1) to the requested gain.
 * Mirrors backend ``materialize_ela_heatmap``.
 */
export async function buildElaGainBlobUrl(baseHeatmapUrl: string, gain: number): Promise<string> {
  const img = await loadImage(baseHeatmapUrl);
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("Canvas 2D indisponivel");
  }
  ctx.drawImage(img, 0, 0, w, h);
  const imageData = ctx.getImageData(0, 0, w, h);
  const g = Math.max(0.1, Math.min(10, gain));
  const pixels = imageData.data;
  for (let i = 0; i < pixels.length; i += 4) {
    for (let c = 0; c < 3; c += 1) {
      const base = pixels[i + c];
      const diffEst = base / BASE_ELA_SCALE;
      pixels[i + c] = Math.max(0, Math.min(255, Math.round(diffEst * g * BASE_ELA_SCALE)));
    }
    pixels[i + 3] = 255;
  }
  ctx.putImageData(imageData, 0, 0);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Falha ao gerar heatmap ELA"))), "image/png");
  });
  return URL.createObjectURL(blob);
}
