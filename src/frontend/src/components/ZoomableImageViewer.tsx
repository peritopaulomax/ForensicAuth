import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

interface ZoomState {
  scale: number;
  translateX: number;
  translateY: number;
}

export interface ZoomableImageViewerHandle {
  resetZoom: () => void;
}

interface ZoomableImageViewerProps {
  title?: string;
  label?: string;
  src: string;
  alt?: string;
  height?: number | string;
  imageStyle?: CSSProperties;
  actions?: ReactNode;
  showResetButton?: boolean;
}

const ZoomableImageViewer = forwardRef<ZoomableImageViewerHandle, ZoomableImageViewerProps>(
  function ZoomableImageViewer(
    { title, label, src, alt, height = 420, imageStyle, actions, showResetButton = true },
    ref
  ) {
    const [zoom, setZoom] = useState<ZoomState>({ scale: 1, translateX: 0, translateY: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const dragStart = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
    const zoomStart = useRef<ZoomState>({ scale: 1, translateX: 0, translateY: 0 });
    const paneRef = useRef<HTMLDivElement>(null);

    const resetZoom = useCallback(() => {
      setZoom({ scale: 1, translateX: 0, translateY: 0 });
      setIsDragging(false);
    }, []);

    useImperativeHandle(ref, () => ({ resetZoom }), [resetZoom]);

    useEffect(() => {
      resetZoom();
    }, [src, resetZoom]);

    useEffect(() => {
      const handler = (e: WheelEvent) => {
        const pane = paneRef.current;
        if (!pane) return;
        const target = e.target as Node;
        if (!pane.contains(target)) return;
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        setZoom((prev) => ({
          ...prev,
          scale: Math.min(Math.max(prev.scale * delta, 0.5), 10),
        }));
      };

      document.addEventListener("wheel", handler, { passive: false });
      return () => document.removeEventListener("wheel", handler);
    }, []);

    const handleMouseDown = useCallback(
      (e: React.MouseEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(true);
        dragStart.current = { x: e.clientX, y: e.clientY };
        zoomStart.current = { ...zoom };
      },
      [zoom]
    );

    const handleMouseMove = useCallback(
      (e: React.MouseEvent<HTMLDivElement>) => {
        if (!isDragging) return;
        const dx = e.clientX - dragStart.current.x;
        const dy = e.clientY - dragStart.current.y;
        setZoom((prev) => ({
          ...prev,
          translateX: zoomStart.current.translateX + dx,
          translateY: zoomStart.current.translateY + dy,
        }));
      },
      [isDragging]
    );

    const handleMouseUp = useCallback(() => {
      setIsDragging(false);
    }, []);

    const transformStyle: CSSProperties = {
      transform: `translate(${zoom.translateX}px, ${zoom.translateY}px) scale(${zoom.scale})`,
      transformOrigin: "center center",
      cursor: isDragging ? "grabbing" : "grab",
    };

    return (
      <div style={{ marginBottom: "1rem" }}>
        {title && (
          <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 600 }}>{title}</h3>
        )}
        <div
          ref={paneRef}
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            overflow: "hidden",
            background: "#1a1a2e",
            position: "relative",
            touchAction: "none",
            height,
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          {label && (
            <div
              style={{
                position: "absolute",
                top: "0.5rem",
                left: "0.5rem",
                background: "rgba(0,0,0,0.6)",
                color: "#fff",
                padding: "0.25rem 0.5rem",
                borderRadius: "4px",
                fontSize: "0.75rem",
                zIndex: 10,
              }}
            >
              {label}
            </div>
          )}
          <div
            style={{
              width: "100%",
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              overflow: "hidden",
              touchAction: "none",
              ...transformStyle,
            }}
          >
            <img
              src={src}
              alt={alt ?? label ?? "Imagem"}
              style={{
                maxWidth: "100%",
                maxHeight: "100%",
                objectFit: "contain",
                pointerEvents: "none",
                ...imageStyle,
              }}
              draggable={false}
            />
          </div>
        </div>
        <div style={{ marginTop: "0.5rem", display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
          {showResetButton && (
            <button
              type="button"
              onClick={resetZoom}
              style={{
                padding: "0.45rem 0.9rem",
                background: "#f3f4f6",
                color: "#374151",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "0.82rem",
              }}
            >
              Reset zoom
            </button>
          )}
          {actions}
        </div>
        <p style={{ margin: "0.35rem 0 0", fontSize: "0.72rem", color: "#9ca3af" }}>
          Roda do mouse: zoom · Arrastar: pan
        </p>
      </div>
    );
  }
);

export default ZoomableImageViewer;
