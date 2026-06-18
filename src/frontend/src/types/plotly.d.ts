export {};

declare global {
  interface PlotlyApi {
    newPlot: (
      root: HTMLElement,
      data: unknown[],
      layout?: Record<string, unknown>,
      config?: Record<string, unknown>
    ) => Promise<void>;
    react: (
      root: HTMLElement,
      data: unknown[],
      layout?: Record<string, unknown>,
      config?: Record<string, unknown>
    ) => Promise<void>;
    restyle: (root: HTMLElement, update: Record<string, unknown>, traces?: number[]) => Promise<void>;
    purge: (root: HTMLElement) => void;
    toImage: (
      root: HTMLElement,
      opts: { format: string; width?: number; height?: number; scale?: number }
    ) => Promise<string>;
    Plots: {
      resize: (root: HTMLElement) => void;
    };
  }

  interface Window {
    Plotly?: PlotlyApi;
  }
}
