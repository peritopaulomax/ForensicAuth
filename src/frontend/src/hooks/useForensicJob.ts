import { useCallback, useRef, useState } from "react";
import api from "@/services/api";

export interface ForensicJobState {
  running: boolean;
  currentJobId: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  progress: number;
  progressLabel: string;
}

export interface RunAnalysisOptions {
  /** Chamado apos o job completar (ex.: carregar PNGs/HTML) — progresso vai a 100% so depois. */
  onArtifactsLoaded?: (jobId: string, result: Record<string, unknown>) => Promise<void>;
  /** Tempo maximo de espera pelo job (ms). Padrao 4 min; audio usa 45 min. */
  maxWaitMs?: number;
  /** Se false, nao guarda o JSON completo no estado do hook (evita payloads enormes). */
  retainResult?: boolean;
}

const AUDIO_TECHNIQUES = new Set([
  "audio_spectrogram",
  "audio_enf",
  "audio_ltas",
  "audio_levels",
  "audio_dc_local",
]);

const ML_TECHNIQUES = new Set([
  "synthetic_image_detection",
  "deepfake_similarity",
  "safire",
  "noiseprint",
  "imdlbenco",
  "videofact",
  "distildire",
  "stil_video_detection",
  "lowres_fake_video",
]);

function defaultMaxWaitMs(technique: string): number {
  if (AUDIO_TECHNIQUES.has(technique)) {
    return 45 * 60 * 1000;
  }
  if (ML_TECHNIQUES.has(technique)) {
    return 30 * 60 * 1000;
  }
  return 4 * 60 * 1000;
}

function useSmoothProgress() {
  const [progress, setProgress] = useState(0);
  const displayRef = useRef(0);
  const targetRef = useRef(0);
  const rafRef = useRef<number | null>(null);

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
      if (next <= targetRef.current + 0.01 && next <= displayRef.current + 0.25) {
        targetRef.current = Math.max(targetRef.current, next);
        return;
      }
      targetRef.current = Math.max(targetRef.current, next);
      if (rafRef.current == null) {
        rafRef.current = requestAnimationFrame(tick);
      }
    },
    [tick]
  );

  const reset = useCallback(() => {
    stopLoop();
    displayRef.current = 0;
    targetRef.current = 0;
    setProgress(0);
  }, [stopLoop]);

  return { progress, setTarget, reset, stopLoop };
}

interface JobStatusPayload {
  status: string;
  progress?: number;
  progress_message?: string;
  error_message?: string | null;
  gpu_queue_position?: number | null;
  pending_gpu_jobs?: number | null;
  gpu_queue_message?: string | null;
}

export function useForensicJob() {
  const [running, setRunning] = useState(false);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progressLabel, setProgressLabel] = useState("");
  const { progress, setTarget, reset: resetProgress, stopLoop } = useSmoothProgress();

  const applyBackendProgress = useCallback(
    (data: JobStatusPayload) => {
      const pct = typeof data.progress === "number" ? data.progress : 0;
      setTarget(pct);
      if (data.status === "pending" && data.gpu_queue_message) {
        setProgressLabel(data.gpu_queue_message);
      } else if (data.progress_message) {
        setProgressLabel(data.progress_message);
      }
    },
    [setTarget]
  );

  const fetchResultBlob = useCallback(async (jobId: string, filename: string): Promise<Blob | null> => {
    try {
      const response = await api.get(
        `/analysis/${jobId}/result/file?filename=${encodeURIComponent(filename)}`,
        { responseType: "blob" }
      );
      return response.data as Blob;
    } catch {
      return null;
    }
  }, []);

  const fetchResultText = useCallback(
    async (jobId: string, filename: string): Promise<string | null> => {
      const blob = await fetchResultBlob(jobId, filename);
      if (!blob) return null;
      try {
        return await blob.text();
      } catch {
        return null;
      }
    },
    [fetchResultBlob]
  );

  const fetchResultJson = useCallback(
    async <T>(jobId: string, filename: string): Promise<T | null> => {
      const text = await fetchResultText(jobId, filename);
      if (!text) return null;
      try {
        return JSON.parse(text) as T;
      } catch {
        return null;
      }
    },
    [fetchResultText]
  );

  const fetchImage = useCallback(
    async (jobId: string, filename: string): Promise<string | null> => {
      const blob = await fetchResultBlob(jobId, filename);
      if (!blob) return null;
      return URL.createObjectURL(blob);
    },
    [fetchResultBlob]
  );

  const pollResult = useCallback(
    async (jobId: string, maxWaitMs = 4 * 60 * 1000, pollIntervalMs = 400): Promise<Record<string, unknown> | null> => {
      const intervalMs = pollIntervalMs;
      const maxAttempts = Math.max(1, Math.ceil(maxWaitMs / intervalMs));
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise((r) => setTimeout(r, intervalMs));
        const res = await api.get<JobStatusPayload>(`/analysis/${jobId}`);
        applyBackendProgress(res.data);

        if (res.data.status === "completed") {
          setTarget(99);
          const detail = await api.get(`/analysis/${jobId}/result`);
          return detail.data as Record<string, unknown>;
        }
        if (res.data.status === "failed") {
          throw new Error(res.data.error_message || "Job falhou");
        }
      }
      throw new Error(
        `Timeout aguardando resultado (${Math.round(maxWaitMs / 60000)} min). ` +
          "Para audio longo, use reamostragem (8–16 kHz) ou FFT menor."
      );
    },
    [applyBackendProgress, setTarget]
  );

  const runAnalysis = useCallback(
    async (
      evidenceId: string,
      technique: string,
      parameters: Record<string, unknown>,
      options?: RunAnalysisOptions
    ) => {
      setRunning(true);
      setError(null);
      setResult(null);
      setCurrentJobId(null);
      resetProgress();
      setProgressLabel("Enviando analise…");
      setTarget(3);

      try {
        const response = await api.post("/analysis", {
          evidence_id: evidenceId,
          technique,
          parameters,
        });
        const jobId = response.data.job_id as string;
        setCurrentJobId(jobId);

        if (typeof response.data.progress === "number") {
          setTarget(response.data.progress);
        }
        if (response.data.progress_message) {
          setProgressLabel(response.data.progress_message);
        } else {
          setProgressLabel("Aguardando inicio do processamento…");
        }

        const waitMs = options?.maxWaitMs ?? defaultMaxWaitMs(technique);
        const pollMs = ML_TECHNIQUES.has(technique) ? 250 : 400;
        const jobResult = await pollResult(jobId, waitMs, pollMs);

        if (jobResult?.success === false) {
          throw new Error(String(jobResult.error || "Analise falhou"));
        }

        setProgressLabel("Carregando resultados na interface…");
        setTarget(99);

        if (options?.onArtifactsLoaded && jobResult) {
          await options.onArtifactsLoaded(jobId, jobResult);
        }

        if (options?.retainResult !== false) {
          setResult(jobResult);
        } else {
          setResult(null);
        }
        setTarget(100);
        setProgressLabel("Concluido");

        await new Promise((r) => setTimeout(r, 350));

        return { jobId, result: jobResult };
      } catch (err: unknown) {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          (err instanceof Error ? err.message : "Erro ao executar analise");
        setError(message);
        throw err;
      } finally {
        setRunning(false);
        stopLoop();
        setTimeout(() => {
          resetProgress();
          setProgressLabel("");
        }, 700);
      }
    },
    [pollResult, resetProgress, setTarget, stopLoop]
  );

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
    setCurrentJobId(null);
    resetProgress();
    setProgressLabel("");
  }, [resetProgress]);

  /** Limpa estado da execução atual sem apagar histórico por aba no hub. */
  const clearRunDisplay = useCallback(() => {
    setResult(null);
    setError(null);
    setCurrentJobId(null);
  }, []);

  return {
    running,
    currentJobId,
    result,
    error,
    progress,
    progressLabel,
    runAnalysis,
    fetchImage,
    fetchResultText,
    fetchResultJson,
    reset,
    clearRunDisplay,
    setError,
  };
}
