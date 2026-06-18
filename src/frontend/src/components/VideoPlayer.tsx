import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type VideoPlayerProps = {
  src: string | null;
  /** Frame index to seek (optional, from analysis results). */
  seekFrame?: number | null;
  fps?: number;
  className?: string;
  style?: React.CSSProperties;
};

/** Player HTML5 com seek por frame aproximado (fps configuravel). */
export default function VideoPlayer({
  src,
  seekFrame = null,
  fps = 25,
  className,
  style,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  const seekToFrame = useCallback(
    (frame: number) => {
      const el = videoRef.current;
      if (!el || !Number.isFinite(frame)) return;
      const t = Math.max(0, frame / Math.max(1, fps));
      el.currentTime = Math.min(t, el.duration || t);
    },
    [fps]
  );

  useEffect(() => {
    if (seekFrame != null && seekFrame >= 0) {
      seekToFrame(seekFrame);
    }
  }, [seekFrame, seekToFrame, src]);

  if (!src) {
    return (
      <div
        className={className}
        style={{
          ...style,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#111827",
          color: "#9ca3af",
          borderRadius: 8,
          minHeight: 200,
          fontSize: "0.85rem",
        }}
      >
        Selecione um video de evidencia
      </div>
    );
  }

  const frameApprox = Math.round(currentTime * fps);

  return (
    <div className={className} style={style}>
      <video
        ref={videoRef}
        src={src}
        controls
        style={{
          width: "100%",
          maxHeight: 360,
          borderRadius: 8,
          background: "#000",
        }}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
      />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: "0.35rem",
          fontSize: "0.75rem",
          color: "#6b7280",
        }}
      >
        <span>
          Frame ~{frameApprox} · {currentTime.toFixed(2)}s / {duration.toFixed(2)}s
        </span>
        <span>fps ref. {fps}</span>
      </div>
    </div>
  );
}

export function useVideoEvidenceUrl(evidenceId: string | null) {
  return useMemo(
    () => (evidenceId ? `/api/v1/evidences/${evidenceId}/file` : null),
    [evidenceId]
  );
}
