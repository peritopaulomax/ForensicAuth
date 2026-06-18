import { useEffect, useState, type ReactNode } from "react";

interface CollapsibleSectionProps {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  badgeCount?: number;
  forceOpen?: boolean;
  children: ReactNode;
}

export default function CollapsibleSection({
  title,
  subtitle,
  defaultOpen = false,
  badgeCount,
  forceOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    if (forceOpen) setOpen(true);
  }, [forceOpen]);

  return (
    <div style={{ marginTop: "1.25rem" }}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.45rem",
          width: "100%",
          padding: "0.45rem 0",
          border: "none",
          background: "transparent",
          cursor: "pointer",
          textAlign: "left",
          color: "#374151",
        }}
      >
        <span style={{ fontSize: "0.75rem", color: "#6b7280", width: "0.75rem" }}>
          {open ? "▼" : "▶"}
        </span>
        <span style={{ fontSize: "0.9rem", fontWeight: 600 }}>{title}</span>
        {badgeCount !== undefined && (
          <span
            style={{
              fontSize: "0.7rem",
              background: "#f3f4f6",
              color: "#6b7280",
              padding: "0.1rem 0.4rem",
              borderRadius: 10,
            }}
          >
            {badgeCount}
          </span>
        )}
      </button>
      {subtitle && (
        <p style={{ fontSize: "0.78rem", color: "#6b7280", margin: "0 0 0.5rem 1.2rem" }}>
          {open ? subtitle : `${subtitle} Clique para expandir.`}
        </p>
      )}
      {open && <div style={{ marginTop: "0.25rem" }}>{children}</div>}
    </div>
  );
}
