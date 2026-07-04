import { useState, useEffect } from "react";

interface Props {
  technique: string;
  onChange: (params: Record<string, unknown>) => void;
}

const defaultParams: Record<string, Record<string, unknown>> = {
  ela: { quality: 95 },
  audio_spectrogram: { n_fft: 1024, hop_length: 256, window: "hann" },
  audio_ltas: { n_fft: 1024, hop_length: 256 },
  audio_enf: { frequency: 60, bandwidth: 0.5 },
  prnu: { threshold: 50 },
  jpeg_ghosts: { quality: 75 },
  metadata: {},
  dct_quantization: {},
  resampling: {},
  synthetic_image_detection: { generate_visuals: true, mode: "full" },
};

export default function TechniqueConfig({ technique, onChange }: Props) {
  const [params, setParams] = useState<Record<string, unknown>>({});

  useEffect(() => {
    const defs = defaultParams[technique] || {};
    setParams(defs);
    onChange(defs);
  }, [technique]);

  function update(key: string, value: unknown) {
    const next = { ...params, [key]: value };
    setParams(next);
    onChange(next);
  }

  const controlStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: "0.35rem",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: "0.8rem",
    fontWeight: 500,
    color: "#374151",
  };

  const inputStyle: React.CSSProperties = {
    padding: "0.4rem 0.6rem",
    border: "1px solid #d1d5db",
    borderRadius: "4px",
    fontSize: "0.85rem",
    color: "#1a1a2e",
    background: "#fff",
  };

  function renderControls() {
    switch (technique) {
      case "ela":
        return (
          <div style={controlStyle}>
            <label style={labelStyle}>Qualidade JPEG ({String(params.quality ?? 95)})</label>
            <input
              type="range"
              min={50}
              max={100}
              value={(params.quality as number) ?? 95}
              onChange={(e) => update("quality", parseInt(e.target.value))}
              style={{ width: "100%" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", color: "#9ca3af" }}>
              <span>50</span>
              <span>100</span>
            </div>
          </div>
        );

      case "audio_spectrogram":
      case "audio_ltas":
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={controlStyle}>
              <label style={labelStyle}>FFT Size (n_fft)</label>
              <select
                value={(params.n_fft as number) ?? 1024}
                onChange={(e) => update("n_fft", parseInt(e.target.value))}
                style={inputStyle}
              >
                <option value={256}>256</option>
                <option value={512}>512</option>
                <option value={1024}>1024</option>
                <option value={2048}>2048</option>
                <option value={4096}>4096</option>
              </select>
            </div>
            <div style={controlStyle}>
              <label style={labelStyle}>Hop Length</label>
              <select
                value={(params.hop_length as number) ?? 256}
                onChange={(e) => update("hop_length", parseInt(e.target.value))}
                style={inputStyle}
              >
                <option value={64}>64</option>
                <option value={128}>128</option>
                <option value={256}>256</option>
                <option value={512}>512</option>
              </select>
            </div>
            {technique === "audio_spectrogram" && (
              <div style={controlStyle}>
                <label style={labelStyle}>Janela</label>
                <select
                  value={(params.window as string) ?? "hann"}
                  onChange={(e) => update("window", e.target.value)}
                  style={inputStyle}
                >
                  <option value="hann">Hann</option>
                  <option value="hamming">Hamming</option>
                  <option value="blackman">Blackman</option>
                  <option value="bartlett">Bartlett</option>
                </select>
              </div>
            )}
          </div>
        );

      case "audio_enf":
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={controlStyle}>
              <label style={labelStyle}>Frequência Nominal (Hz)</label>
              <input
                type="number"
                step={1}
                value={(params.frequency as number) ?? 60}
                onChange={(e) => update("frequency", parseFloat(e.target.value))}
                style={inputStyle}
              />
            </div>
            <div style={controlStyle}>
              <label style={labelStyle}>Largura de Banda (Hz)</label>
              <input
                type="number"
                step={0.1}
                min={0.1}
                max={5}
                value={(params.bandwidth as number) ?? 0.5}
                onChange={(e) => update("bandwidth", parseFloat(e.target.value))}
                style={inputStyle}
              />
            </div>
          </div>
        );

      case "prnu":
        return (
          <div style={controlStyle}>
            <label style={labelStyle}>Threshold de Correlação ({String(params.threshold ?? 50)})</label>
            <input
              type="range"
              min={0}
              max={100}
              value={(params.threshold as number) ?? 50}
              onChange={(e) => update("threshold", parseInt(e.target.value))}
              style={{ width: "100%" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", color: "#9ca3af" }}>
              <span>0</span>
              <span>100</span>
            </div>
          </div>
        );

      case "jpeg_ghosts":
        return (
          <div style={controlStyle}>
            <label style={labelStyle}>Qualidade de Recompressão</label>
            <select
              value={(params.quality as number) ?? 75}
              onChange={(e) => update("quality", parseInt(e.target.value))}
              style={inputStyle}
            >
              <option value={50}>50</option>
              <option value={60}>60</option>
              <option value={70}>70</option>
              <option value={75}>75</option>
              <option value={80}>80</option>
              <option value={90}>90</option>
            </select>
          </div>
        );

      default:
        return (
          <p style={{ fontSize: "0.8rem", color: "#6b7280", margin: 0 }}>
            Nenhum parametro configuravel para esta tecnica.
          </p>
        );
    }
  }

  return (
    <div style={{ marginTop: "0.5rem" }}>
      <h5 style={{ margin: "0 0 0.5rem 0", fontSize: "0.85rem", color: "#374151", fontWeight: 600 }}>
        Parametros
      </h5>
      {renderControls()}
    </div>
  );
}
