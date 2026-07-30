/** Formulário declarativo a partir de TechniqueParameterDef (scaffold simple/medium). */

import type { TechniqueParameterDef, TechniqueParamWidget } from "@/config/techniqueParameterTypes";

export interface TechniqueParameterFormProps {
  defs: TechniqueParameterDef[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
  disabled?: boolean;
}

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: "0.85rem",
  color: "#374151",
};

const inputStyle: React.CSSProperties = {
  padding: "0.35rem 0.5rem",
  borderRadius: 4,
  border: "1px solid #d1d5db",
  fontSize: "0.85rem",
  maxWidth: 220,
};

function resolveWidget(def: TechniqueParameterDef): TechniqueParamWidget {
  if (def.widget) return def.widget;
  if (def.type === "boolean") return "checkbox";
  if (def.type === "enum") return "select";
  if (def.type === "int" || def.type === "float") return "number";
  return "text";
}

function parseNumeric(def: TechniqueParameterDef, raw: string): number | unknown {
  const n = def.type === "int" ? parseInt(raw, 10) : parseFloat(raw);
  return Number.isFinite(n) ? n : def.default;
}

export default function TechniqueParameterForm({
  defs,
  values,
  onChange,
  disabled = false,
}: TechniqueParameterFormProps) {
  if (!defs.length) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem 1.5rem", alignItems: "flex-end" }}>
      {defs.map((def) => {
        const label = def.label || def.name;
        const raw = values[def.name] ?? def.default;
        const widget = resolveWidget(def);

        if (def.type === "boolean" || widget === "checkbox") {
          return (
            <label
              key={def.name}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                fontSize: "0.85rem",
                color: "#374151",
              }}
              title={def.description}
            >
              <input
                type="checkbox"
                checked={Boolean(raw)}
                disabled={disabled}
                onChange={(e) => onChange(def.name, e.target.checked)}
              />
              {label}
            </label>
          );
        }

        if (def.type === "enum" && def.options?.length && widget === "radio") {
          return (
            <fieldset
              key={def.name}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 6,
                margin: 0,
                padding: "0.5rem 0.75rem",
                minWidth: 0,
              }}
              title={def.description}
            >
              <legend style={{ fontSize: "0.85rem", color: "#374151", padding: "0 0.25rem" }}>
                {label}
              </legend>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.65rem 1rem" }}>
                {def.options.map((opt) => (
                  <label
                    key={opt}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.35rem",
                      fontSize: "0.85rem",
                      color: "#374151",
                      cursor: disabled ? "default" : "pointer",
                    }}
                  >
                    <input
                      type="radio"
                      name={def.name}
                      value={opt}
                      checked={String(raw ?? "") === opt}
                      disabled={disabled}
                      onChange={() => onChange(def.name, opt)}
                    />
                    {opt}
                  </label>
                ))}
              </div>
            </fieldset>
          );
        }

        if (def.type === "enum" && def.options?.length) {
          return (
            <label key={def.name} style={labelStyle} title={def.description}>
              {label}
              <select
                value={String(raw ?? "")}
                disabled={disabled}
                onChange={(e) => onChange(def.name, e.target.value)}
                style={inputStyle}
              >
                {def.options.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </label>
          );
        }

        if ((def.type === "int" || def.type === "float") && widget === "slider") {
          const min = def.min ?? 0;
          const max = def.max ?? 100;
          const step = def.step ?? (def.type === "int" ? 1 : 0.1);
          const num = typeof raw === "number" ? raw : Number(raw);
          const value = Number.isFinite(num) ? num : min;
          return (
            <label key={def.name} style={{ ...labelStyle, minWidth: 200 }} title={def.description}>
              <span style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                <span>{label}</span>
                <strong style={{ fontWeight: 600, color: "#0369a1" }}>{value}</strong>
              </span>
              <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={value}
                disabled={disabled}
                onChange={(e) => onChange(def.name, parseNumeric(def, e.target.value))}
                style={{ width: "100%", maxWidth: 280 }}
              />
            </label>
          );
        }

        if (def.type === "int" || def.type === "float") {
          return (
            <label key={def.name} style={labelStyle} title={def.description}>
              {label}
              <input
                type="number"
                value={raw === undefined || raw === null ? "" : Number(raw)}
                min={def.min}
                max={def.max}
                step={def.step ?? (def.type === "int" ? 1 : 0.1)}
                disabled={disabled}
                onChange={(e) => onChange(def.name, parseNumeric(def, e.target.value))}
                style={inputStyle}
              />
            </label>
          );
        }

        return (
          <label key={def.name} style={labelStyle} title={def.description}>
            {label}
            <input
              type="text"
              value={raw == null ? "" : String(raw)}
              disabled={disabled}
              onChange={(e) => onChange(def.name, e.target.value)}
              style={{ ...inputStyle, maxWidth: 320 }}
            />
          </label>
        );
      })}
    </div>
  );
}

export function initialParameterValues(defs: TechniqueParameterDef[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const def of defs) {
    if (def.default !== undefined) {
      out[def.name] = def.default;
    } else if (def.type === "boolean") {
      out[def.name] = false;
    } else if (def.type === "enum" && def.options?.[0] != null) {
      out[def.name] = def.options[0];
    }
  }
  return out;
}

export { resolveWidget };
