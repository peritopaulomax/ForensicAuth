/** Area real da imagem pintada dentro de um <img> com object-fit: contain. */

export interface ImageContentLayout {
  /** Offset do conteudo em relacao ao canto superior-esquerdo do elemento img (px). */
  offsetX: number;
  offsetY: number;
  /** Tamanho do conteudo visivel (px). */
  width: number;
  height: number;
  naturalWidth: number;
  naturalHeight: number;
}

export function getImageContentLayout(img: HTMLImageElement): ImageContentLayout | null {
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  if (!nw || !nh) return null;

  const elW = img.clientWidth;
  const elH = img.clientHeight;
  if (elW < 1 || elH < 1) return null;

  const imageAspect = nw / nh;
  const boxAspect = elW / elH;

  let width: number;
  let height: number;
  let offsetX: number;
  let offsetY: number;

  if (imageAspect > boxAspect) {
    width = elW;
    height = elW / imageAspect;
    offsetX = 0;
    offsetY = (elH - height) / 2;
  } else {
    height = elH;
    width = elH * imageAspect;
    offsetX = (elW - width) / 2;
    offsetY = 0;
  }

  return { offsetX, offsetY, width, height, naturalWidth: nw, naturalHeight: nh };
}

export function clientToNatural(
  img: HTMLImageElement,
  clientX: number,
  clientY: number
): { x: number; y: number } | null {
  const layout = getImageContentLayout(img);
  if (!layout) return null;

  const rect = img.getBoundingClientRect();
  const lx = clientX - rect.left - layout.offsetX;
  const ly = clientY - rect.top - layout.offsetY;

  if (lx < 0 || ly < 0 || lx > layout.width || ly > layout.height) return null;

  const x = Math.round((lx / layout.width) * layout.naturalWidth);
  const y = Math.round((ly / layout.height) * layout.naturalHeight);

  const clampedX = Math.max(0, Math.min(layout.naturalWidth - 1, x));
  const clampedY = Math.max(0, Math.min(layout.naturalHeight - 1, y));
  return { x: clampedX, y: clampedY };
}

export function naturalToContent(
  layout: ImageContentLayout,
  x: number,
  y: number
): { x: number; y: number } {
  return {
    x: (x / layout.naturalWidth) * layout.width,
    y: (y / layout.naturalHeight) * layout.height,
  };
}
