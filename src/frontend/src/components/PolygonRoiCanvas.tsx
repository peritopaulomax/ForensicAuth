import { useCallback, useEffect, useRef, useState } from "react";
import {
  clientToNatural,
  getImageContentLayout,
  naturalToContent,
  type ImageContentLayout,
} from "@/utils/imageDisplayRect";

export interface PolygonPoint {
  x: number;
  y: number;
}

interface Props {
  imageUrl: string;
  polygon: PolygonPoint[] | null;
  onPolygonChange: (polygon: PolygonPoint[] | null) => void;
  maxHeight?: number;
}

/** Reduz pontos do traco sem alterar a forma (distancia minima entre vertices). */
function simplifyPath(points: PolygonPoint[], minDist = 3): PolygonPoint[] {
  if (points.length <= 2) return points;
  const out: PolygonPoint[] = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const last = out[out.length - 1];
    if (Math.hypot(points[i].x - last.x, points[i].y - last.y) >= minDist) {
      out.push(points[i]);
    }
  }
  out.push(points[points.length - 1]);
  return out.length >= 3 ? out : points;
}

/**
 * Poligono livre: segue o traco do mouse e fecha ao soltar (formas concavas, ex. "M").
 */
export default function PolygonRoiCanvas({ imageUrl, polygon, onPolygonChange, maxHeight = 480 }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const layoutRef = useRef<ImageContentLayout | null>(null);
  const drawingRef = useRef(false);
  const strokeRef = useRef<PolygonPoint[]>([]);
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
    (activeStroke: PolygonPoint[], showFinalPolygon: PolygonPoint[] | null) => {
      const layout = updateLayout();
      const canvas = canvasRef.current;
      if (!layout || !canvas) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const drawPolyline = (pts: PolygonPoint[], color: string, width: number) => {
        if (pts.length < 1) return;
        ctx.beginPath();
        const first = naturalToContent(layout, pts[0].x, pts[0].y);
        ctx.moveTo(first.x, first.y);
        if (pts.length === 1) {
          ctx.arc(first.x, first.y, width / 2, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
          return;
        }
        for (let i = 1; i < pts.length; i++) {
          const p = naturalToContent(layout, pts[i].x, pts[i].y);
          ctx.lineTo(p.x, p.y);
        }
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();
      };

      const drawClosed = (pts: PolygonPoint[], fill: string, stroke: string, lineWidth = 2) => {
        if (pts.length < 3) return;
        ctx.beginPath();
        const first = naturalToContent(layout, pts[0].x, pts[0].y);
        ctx.moveTo(first.x, first.y);
        for (let i = 1; i < pts.length; i++) {
          const p = naturalToContent(layout, pts[i].x, pts[i].y);
          ctx.lineTo(p.x, p.y);
        }
        ctx.closePath();
        ctx.fillStyle = fill;
        ctx.fill();
        ctx.strokeStyle = stroke;
        ctx.lineWidth = lineWidth;
        ctx.stroke();
      };

      if (showFinalPolygon && showFinalPolygon.length >= 3 && !drawingRef.current) {
        drawClosed(showFinalPolygon, "rgba(3, 105, 161, 0.4)", "#0369a1");
      }

      if (activeStroke.length > 0 && drawingRef.current) {
        if (activeStroke.length >= 3) {
          drawClosed(activeStroke, "rgba(245, 158, 11, 0.18)", "#f59e0b", 1.5);
        }
        drawPolyline(activeStroke, "#f59e0b", 2.5);
      }
    },
    [updateLayout]
  );

  useEffect(() => {
    setLoadError(false);
    layoutRef.current = null;
    strokeRef.current = [];
    drawingRef.current = false;
  }, [imageUrl]);

  useEffect(() => {
    paintOverlay(strokeRef.current, polygon);
    const onResize = () => paintOverlay(strokeRef.current, polygon);
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
  }, [polygon, paintOverlay]);

  function toNatural(clientX: number, clientY: number): PolygonPoint | null {
    const img = imgRef.current;
    if (!img) return null;
    return clientToNatural(img, clientX, clientY);
  }

  function onImgLoad() {
    requestAnimationFrame(() => paintOverlay(strokeRef.current, polygon));
  }

  function onPointerDown(e: React.PointerEvent) {
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const p = toNatural(e.clientX, e.clientY);
    if (!p) return;

    onPolygonChange(null);
    drawingRef.current = true;
    strokeRef.current = [p];
    paintOverlay(strokeRef.current, null);
    setPaintTick((t) => t + 1);
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!drawingRef.current) return;
    const p = toNatural(e.clientX, e.clientY);
    if (!p) return;

    const last = strokeRef.current[strokeRef.current.length - 1];
    if (last && Math.hypot(p.x - last.x, p.y - last.y) < 2) return;

    strokeRef.current = [...strokeRef.current, p];
    paintOverlay(strokeRef.current, null);
  }

  function onPointerUp(e: React.PointerEvent) {
    if (!drawingRef.current) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    drawingRef.current = false;

    const p = toNatural(e.clientX, e.clientY);
    const points = p ? [...strokeRef.current, p] : [...strokeRef.current];
    strokeRef.current = [];

    if (points.length < 3) {
      onPolygonChange(null);
      paintOverlay([], null);
      setPaintTick((t) => t + 1);
      return;
    }

    const closed = simplifyPath(points);
    onPolygonChange(closed);
    paintOverlay([], closed);
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
          <p style={{ padding: "2rem", color: "#b91c1c", fontSize: "0.9rem" }}>Nao foi possivel carregar a imagem.</p>
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
          Desenhe o contorno com o mouse; ao soltar, o poligono fecha pelo traco (formas concavas permitidas).
        </span>
        {polygon && (
          <button
            type="button"
            onClick={() => {
              onPolygonChange(null);
              strokeRef.current = [];
              paintOverlay([], null);
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
