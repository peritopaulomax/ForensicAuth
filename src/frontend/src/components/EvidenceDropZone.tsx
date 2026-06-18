import { useRef, useState } from "react";

export interface EvidenceDropZoneProps {
  inputId: string;
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
  uploading?: boolean;
  hint?: string;
  subHint?: string;
  onFiles: (files: FileList) => void;
}

export default function EvidenceDropZone({
  inputId,
  accept,
  multiple = true,
  disabled = false,
  uploading = false,
  hint = "Clique para selecionar ou arraste arquivos aqui",
  subHint,
  onFiles,
}: EvidenceDropZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (disabled || uploading) return;
    if (e.dataTransfer.files?.length) {
      onFiles(e.dataTransfer.files);
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled && !uploading) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => {
        if (!disabled && !uploading) inputRef.current?.click();
      }}
      style={{
        border: `2px dashed ${dragOver ? "#0369a1" : "#d1d5db"}`,
        borderRadius: 8,
        padding: "1.25rem",
        textAlign: "center",
        cursor: disabled || uploading ? "not-allowed" : "pointer",
        background: dragOver ? "#eff6ff" : "#fff",
        opacity: disabled ? 0.6 : 1,
      }}
    >
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        multiple={multiple}
        accept={accept}
        style={{ display: "none" }}
        disabled={disabled || uploading}
        onChange={(e) => {
          if (e.target.files?.length) onFiles(e.target.files);
          e.target.value = "";
        }}
      />
      {uploading ? (
        <p style={{ margin: 0, color: "#6b7280", fontSize: "0.88rem" }}>Enviando e registrando na cadeia…</p>
      ) : (
        <>
          <div style={{ fontSize: "1.4rem", marginBottom: 6 }}>📁</div>
          <p style={{ margin: "0 0 0.25rem", color: "#374151", fontSize: "0.9rem" }}>
            <strong>{hint}</strong>
          </p>
          {subHint && (
            <p style={{ margin: 0, color: "#9ca3af", fontSize: "0.75rem" }}>{subHint}</p>
          )}
        </>
      )}
    </div>
  );
}
