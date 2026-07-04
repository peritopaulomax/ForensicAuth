import { useCallback, useEffect, useRef, useState } from "react";
import {
  clientToNatural,
  getImageContentLayout,
  naturalToContent,
  type ImageContentLayout,
} from "@/utils/imageDisplayRect";

export interface RectRoi {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Props {
  imageUrl: string;
  rect: RectRoi | null;
  onRectChange: (rect: RectRoi | null) => void;
  maxHeight?: number;
}

export default function RectRoiCanvas({ imageUrl, rect, onRectChange, maxHeight = 480 }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const layoutRef = useRef<ImageContentLayout | null>(null);
  const draggingRef = useRef(false);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const currentRef = useRef<{ x: number; y: number } | null>(null);
  const [, setPaintTick] = useState(0);
  const [loadError, setLoadError] = useState(false);

  const updateLayout = useCallback(() => {
    const img = imgRef.current;
    if (!img?.complete || !img.naturalWidth) return null;
    const layout = getImageContentLayout(img);
    layoutRef.current = layout;
    if (!layout) return null;

    const canvas = canvasRef.current;
    if (!canvas) return layout;

    const w = Math.round(layout.width);
    const h = Math.round(layout.height);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    canvas.style.left = `${layout.offsetX}px`;
    canvas.style.top = `${layout.offsetY}px`;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    return layout;
  }, []);

  const paintOverlay = useCallback(
    (start: { x: number; y: number } | null, current: { x: number; y: number } | null, finalRect: RectRoi | null) => {
      const layout = updateLayout();
      const canvas = canvasRef.current;
      if (!layout || !canvas) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Overlay escuro/hachurado em toda a imagem
      ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const drawRect = (r: RectRoi, stroke = "#0369a1", fill?: string) => {
        const topLeft = naturalToContent(layout, r.x, r.y);
        const bottomRight = naturalToContent(layout, r.x + r.width, r.y + r.height);
        const x = Math.min(topLeft.x, bottomRight.x);
        const y = Math.min(topLeft.y, bottomRight.y);
        const w = Math.abs(bottomRight.x - topLeft.x);
        const h = Math.abs(bottomRight.y - topLeft.y);

        ctx.save();
        ctx.beginPath();
        ctx.rect(x, y, w, h);
        // "Corta" o overlay escuro para revelar a regiao selecionada
        ctx.globalCompositeOperation = "destination-out";
        ctx.fill();
        ctx.globalCompositeOperation = "source-over";
        if (fill) {
          ctx.fillStyle = fill;
          ctx.fill();
        }
        ctx.strokeStyle = stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
      };

      if (finalRect) {
        drawRect(finalRect, "#0369a1", "rgba(3, 105, 161, 0.12)");
      }

      if (start && current && draggingRef.current) {
        const x = Math.min(start.x, current.x);
        const y = Math.min(start.y, current.y);
        const w = Math.abs(current.x - start.x);
        const h = Math.abs(current.y - start.y);
        if (w > 0 && h > 0) {
          drawRect({ x, y, width: w, height: h }, "#f59e0b", "rgba(245, 158, 11, 0.15)");
        }
      }
    },
    [updateLayout]
  );

  useEffect(() => {
    setLoadError(false);
    layoutRef.current = null;
    startRef.current = null;
    currentRef.current = null;
    draggingRef.current = false;
  }, [imageUrl]);

  useEffect(() => {
    paintOverlay(startRef.current, currentRef.current, rect);
    const onResize = () => paintOverlay(startRef.current, currentRef.current, rect);
    window.addEventListener("resize", onResize);
    const ro =
      wrapRef.current && typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(onResize)
        : null;
    if (ro && wrapRef.current) ro.observe(wrapRef.current);
    return () => {
      window.removeEventListener("resize", onResize);
      ro?.disconnect();
    };
  }, [rect, paintOverlay]);

  function toNatural(clientX: number, clientY: number): { x: number; y: number } | null {
    const img = imgRef.current;
    if (!img) return null;
    return clientToNatural(img, clientX, clientY);
  }

  function onImgLoad() {
    requestAnimationFrame(() => paintOverlay(startRef.current, currentRef.current, rect));
  }

  function onPointerDown(e: React.PointerEvent) {
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const p = toNatural(e.clientX, e.clientY);
    if (!p) return;

    onRectChange(null);
    draggingRef.current = true;
    startRef.current = p;
    currentRef.current = p;
    paintOverlay(startRef.current, currentRef.current, null);
    setPaintTick((t) => t + 1);
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!draggingRef.current || !startRef.current) return;
    const p = toNatural(e.clientX, e.clientY);
    if (!p) return;
    currentRef.current = p;
    paintOverlay(startRef.current, currentRef.current, null);
  }

  function onPointerUp(e: React.PointerEvent) {
    if (!draggingRef.current || !startRef.current || !currentRef.current) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    draggingRef.current = false;

    const x = Math.min(startRef.current.x, currentRef.current.x);
    const y = Math.min(startRef.current.y, currentRef.current.y);
    const width = Math.abs(currentRef.current.x - startRef.current.x);
    const height = Math.abs(currentRef.current.y - startRef.current.y);

    startRef.current = null;
    currentRef.current = null;

    if (width < 2 || height < 2) {
      onRectChange(null);
      paintOverlay(null, null, null);
      setPaintTick((t) => t + 1);
      return;
    }

    const newRect: RectRoi = { x, y, width, height };
    onRectChange(newRect);
    paintOverlay(null, null, newRect);
    setPaintTick((t) => t + 1);
  }

  return (
    <div>
      <div
        ref={wrapRef}
        style={{
          position: "relative",
          display: "block",
          maxWidth: "100%",
          width: "100%",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          overflow: "hidden",
          background: "#f3f4f6",
          minHeight: 120,
        }}
      >
        {loadError ? (
          <p style={{ padding: "2rem", color: "#b91c1c", fontSize: "0.9rem" }}>
            Nao foi possivel carregar a imagem.
          </p>
        ) : (
          <>
            <img
              ref={imgRef}
              src={imageUrl}
              alt="Imagem para selecao de regiao"
              onLoad={onImgLoad}
              onError={() => setLoadError(true)}
              style={{
                display: "block",
                width: "100%",
                maxHeight,
                height: "auto",
                objectFit: "contain",
                userSelect: "none",
              }}
              draggable={false}
            />
            <canvas
              ref={canvasRef}
              style={{
                position: "absolute",
                cursor: "crosshair",
                touchAction: "none",
                pointerEvents: "auto",
              }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
            />
          </>
        )}
      </div>
      <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
          Clique e arraste para selecionar a regiao retangular. O restante da imagem fica escurecido.
        </span>
        {rect && (
          <button
            type="button"
            onClick={() => {
              onRectChange(null);
              paintOverlay(null, null, null);
            }}
            style={{
              padding: "0.25rem 0.6rem",
              fontSize: "0.78rem",
              border: "1px solid #d1d5db",
              borderRadius: 4,
              background: "#fff",
              cursor: "pointer",
            }}
          >
            Limpar regiao
          </button>
        )}
      </div>
    </div>
  );
}
