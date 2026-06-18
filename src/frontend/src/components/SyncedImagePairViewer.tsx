import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

interface ZoomState {
  scale: number;
  translateX: number;
  translateY: number;
}

interface CrosshairState {
  relX: number;
  relY: number;
}

export interface SyncedImagePairViewerHandle {
  resetZoom: () => void;
}

interface SyncedImagePairViewerProps {
  title?: string;
  height?: number | string;
  leftLabel: string;
  rightLabel: string;
  leftSrc: string;
  rightSrc?: string | null;
  /** Imagem alternativa no painel direito (ex.: multi-fonte SAFIRE ao passar o mouse). */
  rightHoverSrc?: string | null;
  rightHoverLabel?: string;
  rightHoverTransitionMs?: number;
  rightPlaceholder?: ReactNode;
  rightImageStyle?: CSSProperties;
  actions?: ReactNode;
}

function CrosshairOverlay({ relX, relY }: CrosshairState) {
  const lineBase: CSSProperties = {
    position: "absolute",
    pointerEvents: "none",
    zIndex: 20,
    background: "rgba(250, 204, 21, 0.95)",
    boxShadow: "0 0 0 1px rgba(0, 0, 0, 0.45)",
  };

  return (
    <>
      <div
        style={{
          ...lineBase,
          left: `${relX * 100}%`,
          top: 0,
          bottom: 0,
          width: 1,
          transform: "translateX(-0.5px)",
        }}
      />
      <div
        style={{
          ...lineBase,
          top: `${relY * 100}%`,
          left: 0,
          right: 0,
          height: 1,
          transform: "translateY(-0.5px)",
        }}
      />
    </>
  );
}

function ImagePane({
  label,
  src,
  hoverSrc,
  hoverLabel,
  hoverTransitionMs = 220,
  placeholder,
  imageStyle,
  crosshair,
  transformStyle,
  paneRef,
  onMouseDown,
  onMouseMove,
  onMouseUp,
}: {
  label: string;
  src?: string | null;
  hoverSrc?: string | null;
  hoverLabel?: string;
  hoverTransitionMs?: number;
  placeholder?: ReactNode;
  imageStyle?: CSSProperties;
  crosshair: CrosshairState | null;
  transformStyle: CSSProperties;
  paneRef: React.RefObject<HTMLDivElement | null>;
  onMouseDown: (e: React.MouseEvent<HTMLDivElement>) => void;
  onMouseMove: (e: React.MouseEvent<HTMLDivElement>) => void;
  onMouseUp: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const showHover = Boolean(hovered && hoverSrc);
  const displayLabel = showHover && hoverLabel ? hoverLabel : label;

  return (
    <div
      ref={paneRef as React.RefObject<HTMLDivElement>}
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "8px",
        overflow: "hidden",
        background: "#1a1a2e",
        position: "relative",
        touchAction: "none",
        cursor: "crosshair",
      }}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
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
          transition: `opacity ${hoverTransitionMs}ms ease`,
        }}
      >
        {displayLabel}
      </div>

      {crosshair && <CrosshairOverlay relX={crosshair.relX} relY={crosshair.relY} />}

      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
          touchAction: "none",
          position: "relative",
          ...transformStyle,
        }}
      >
        {src ? (
          <>
            <img
              src={src}
              alt={label}
              style={{
                maxWidth: "100%",
                maxHeight: "100%",
                objectFit: "contain",
                pointerEvents: "none",
                opacity: showHover ? 0 : 1,
                transition: `opacity ${hoverTransitionMs}ms ease`,
                position: showHover ? "absolute" : "relative",
                ...imageStyle,
              }}
              draggable={false}
            />
            {hoverSrc && (
              <img
                src={hoverSrc}
                alt={hoverLabel || label}
                style={{
                  maxWidth: "100%",
                  maxHeight: "100%",
                  objectFit: "contain",
                  pointerEvents: "none",
                  opacity: showHover ? 1 : 0,
                  transition: `opacity ${hoverTransitionMs}ms ease`,
                  position: "absolute",
                  ...imageStyle,
                }}
                draggable={false}
              />
            )}
          </>
        ) : (
          placeholder
        )}
      </div>
    </div>
  );
}

const SyncedImagePairViewer = forwardRef<SyncedImagePairViewerHandle, SyncedImagePairViewerProps>(
  function SyncedImagePairViewer(
    {
      title,
      height = 480,
      leftLabel,
      rightLabel,
      leftSrc,
      rightSrc,
      rightHoverSrc,
      rightHoverLabel,
      rightHoverTransitionMs,
      rightPlaceholder,
      rightImageStyle,
      actions,
    },
    ref
  ) {
    const [zoom, setZoom] = useState<ZoomState>({ scale: 1, translateX: 0, translateY: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const [crosshair, setCrosshair] = useState<CrosshairState | null>(null);
    const dragStart = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
    const zoomStart = useRef<ZoomState>({ scale: 1, translateX: 0, translateY: 0 });
    const previewLeftRef = useRef<HTMLDivElement>(null);
    const previewRightRef = useRef<HTMLDivElement>(null);
    const pairRef = useRef<HTMLDivElement>(null);

    const resetZoom = useCallback(() => {
      setZoom({ scale: 1, translateX: 0, translateY: 0 });
      setCrosshair(null);
      setIsDragging(false);
    }, []);

    useImperativeHandle(ref, () => ({ resetZoom }), [resetZoom]);

    useEffect(() => {
      const handler = (e: WheelEvent) => {
        const left = previewLeftRef.current;
        const right = previewRightRef.current;
        if (!left || !right) return;
        const target = e.target as Node;
        if (left.contains(target) || right.contains(target)) {
          e.preventDefault();
          const delta = e.deltaY > 0 ? 0.9 : 1.1;
          setZoom((prev) => ({
            ...prev,
            scale: Math.min(Math.max(prev.scale * delta, 0.5), 10),
          }));
        }
      };

      document.addEventListener("wheel", handler, { passive: false });
      return () => document.removeEventListener("wheel", handler);
    }, []);

    const handleMouseDown = useCallback(
      (e: React.MouseEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(true);
        setCrosshair(null);
        dragStart.current = { x: e.clientX, y: e.clientY };
        zoomStart.current = { ...zoom };
      },
      [zoom]
    );

    const updateCrosshair = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      setCrosshair({
        relX: Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
        relY: Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)),
      });
    }, []);

    const handleMouseMove = useCallback(
      (e: React.MouseEvent<HTMLDivElement>) => {
        if (isDragging) {
          const dx = e.clientX - dragStart.current.x;
          const dy = e.clientY - dragStart.current.y;
          setZoom((prev) => ({
            ...prev,
            translateX: zoomStart.current.translateX + dx,
            translateY: zoomStart.current.translateY + dy,
          }));
          return;
        }
        updateCrosshair(e);
      },
      [isDragging, updateCrosshair]
    );

    const handleMouseUp = useCallback(() => {
      setIsDragging(false);
    }, []);

    const handlePairMouseLeave = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
      const next = e.relatedTarget as Node | null;
      if (!next || !pairRef.current?.contains(next)) {
        setCrosshair(null);
        setIsDragging(false);
      }
    }, []);

    const transformStyle: CSSProperties = {
      transform: `translate(${zoom.translateX}px, ${zoom.translateY}px) scale(${zoom.scale})`,
      transformOrigin: "center center",
      cursor: isDragging ? "grabbing" : "crosshair",
    };

    return (
      <div style={{ marginBottom: actions ? "0.75rem" : "1.5rem" }}>
        {title && (
          <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 600 }}>{title}</h3>
        )}
        <div
          ref={pairRef}
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", height }}
          onMouseLeave={handlePairMouseLeave}
        >
          <ImagePane
            label={leftLabel}
            src={leftSrc}
            crosshair={crosshair}
            transformStyle={transformStyle}
            paneRef={previewLeftRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
          />
          <ImagePane
            label={rightLabel}
            src={rightSrc}
            hoverSrc={rightHoverSrc}
            hoverLabel={rightHoverLabel}
            hoverTransitionMs={rightHoverTransitionMs}
            placeholder={rightPlaceholder}
            imageStyle={rightImageStyle}
            crosshair={crosshair}
            transformStyle={transformStyle}
            paneRef={previewRightRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
          />
        </div>
        {actions && (
          <div style={{ marginTop: "0.75rem", display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
            {actions}
          </div>
        )}
      </div>
    );
  }
);

export default SyncedImagePairViewer;
