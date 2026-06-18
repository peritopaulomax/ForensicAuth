/** Binariza mapa de scores [0,1] (PNG em escala de cinza) para máscara local. */

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
    img.onerror = () => reject(new Error("Falha ao carregar mapa de scores"));
    img.src = src;
  });
}

/**
 * Gera URL blob de máscara binária: pixel com score >= threshold fica branco.
 * Espera PNG em escala de cinza (valor 0–255 proporcional a 0–1).
 */
export async function buildMaskBlobUrl(scoreMapUrl: string, threshold: number): Promise<string> {
  const img = await loadImage(scoreMapUrl);
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
  const thrByte = Math.round(Math.max(0, Math.min(1, threshold)) * 255);
  const pixels = imageData.data;
  for (let i = 0; i < pixels.length; i += 4) {
    const score = pixels[i];
    const on = score >= thrByte ? 255 : 0;
    pixels[i] = on;
    pixels[i + 1] = on;
    pixels[i + 2] = on;
    pixels[i + 3] = 255;
  }
  ctx.putImageData(imageData, 0, 0);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Falha ao gerar mascara"))), "image/png");
  });
  return URL.createObjectURL(blob);
}
