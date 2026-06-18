import { useCallback, useState, type CSSProperties, type ReactNode } from "react";
import PlotlyExpandButton from "@/components/PlotlyExpandButton";
import PlotlyFullscreenModal from "@/components/PlotlyFullscreenModal";

interface PlotlyChartFrameProps {
  title?: string;
  children: ReactNode;
  /** Conteúdo ampliado no modal; se omitido, reutiliza `children`. */
  fullscreenContent?: ReactNode;
  showExpand?: boolean;
}

export default function PlotlyChartFrame({
  title,
  children,
  fullscreenContent,
  showExpand = true,
}: PlotlyChartFrameProps) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  return (
    <>
      <div style={{ width: "100%" }}>
        {(title || showExpand) && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "0.5rem",
              marginBottom: title ? "0.35rem" : 0,
            }}
          >
            {title ? <p style={titleTextStyle}>{title}</p> : <span />}
            {showExpand && <PlotlyExpandButton onClick={() => setOpen(true)} />}
          </div>
        )}
        {children}
      </div>
      {open && (
        <PlotlyFullscreenModal title={title} onClose={close}>
          {fullscreenContent ?? children}
        </PlotlyFullscreenModal>
      )}
    </>
  );
}

const titleTextStyle: CSSProperties = {
  margin: 0,
  fontSize: "0.85rem",
  fontWeight: 600,
  color: "#374151",
};
