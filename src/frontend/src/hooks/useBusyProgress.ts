import { useCallback, useEffect, useRef, useState } from "react";

/** Progresso suave para operacoes sincronas sem endpoint de status (ex.: geracao PRNU). */
export function useBusyProgress() {
  const [progress, setProgress] = useState(0);
  const [label, setLabel] = useState("");
  const displayRef = useRef(0);
  const targetRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopLoop = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const tick = useCallback(() => {
    const target = targetRef.current;
    const current = displayRef.current;
    const diff = target - current;
    if (Math.abs(diff) < 0.25) {
      displayRef.current = target;
      setProgress(target);
      rafRef.current = null;
      return;
    }
    displayRef.current += diff * 0.15;
    setProgress(displayRef.current);
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const setTarget = useCallback(
    (value: number) => {
      const next = Math.max(0, Math.min(100, value));
      targetRef.current = Math.max(targetRef.current, next);
      if (rafRef.current == null) {
        rafRef.current = requestAnimationFrame(tick);
      }
    },
    [tick]
  );

  const reset = useCallback(() => {
    stopLoop();
    if (tickRef.current != null) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    displayRef.current = 0;
    targetRef.current = 0;
    setProgress(0);
    setLabel("");
  }, [stopLoop]);

  const start = useCallback(
    (initialLabel: string) => {
      reset();
      setLabel(initialLabel);
      setTarget(5);
      tickRef.current = setInterval(() => {
        if (targetRef.current < 88) {
          setTarget(targetRef.current + 1.5);
        }
      }, 350);
    },
    [reset, setTarget]
  );

  const finish = useCallback(() => {
    if (tickRef.current != null) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    setTarget(100);
    setLabel("Concluido");
  }, [setTarget]);

  useEffect(() => () => reset(), [reset]);

  return { progress, label, setLabel, setTarget, start, finish, reset, stopLoop };
}
