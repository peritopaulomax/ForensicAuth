import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DqtTooltipState } from "@/components/jpeg/DqtMatrixTooltipLayer";
import type { JpegMarkerDump } from "@/utils/jpegStructureCompare";
import { markerHasDqtTables } from "@/utils/jpegDqtMatrix";

export function useDqtTooltip() {
  const [state, setState] = useState<DqtTooltipState | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearHideTimer = useCallback(() => {
    if (hideTimer.current) {
      clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
  }, []);

  const onDqtEnter = useCallback(
    (marker: JpegMarkerDump, el: HTMLElement) => {
      if (!markerHasDqtTables(marker)) return;
      clearHideTimer();
      const rect = el.getBoundingClientRect();
      setState({
        marker,
        top: rect.top,
        left: rect.left + rect.width / 2,
      });
    },
    [clearHideTimer]
  );

  const onDqtLeave = useCallback(() => {
    clearHideTimer();
    hideTimer.current = setTimeout(() => setState(null), 140);
  }, [clearHideTimer]);

  const onTooltipEnter = useCallback(() => {
    clearHideTimer();
  }, [clearHideTimer]);

  const dismiss = useCallback(() => {
    clearHideTimer();
    setState(null);
  }, [clearHideTimer]);

  useEffect(() => () => clearHideTimer(), [clearHideTimer]);

  const handlers = useMemo(
    () => ({ onDqtEnter, onDqtLeave }),
    [onDqtEnter, onDqtLeave]
  );

  return {
    state,
    handlers,
    onTooltipEnter,
    onTooltipLeave: onDqtLeave,
    dismiss,
  };
}
