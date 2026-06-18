import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createCase, getCase, updateCase } from "@/services/cases";
import type { Case } from "@/types/api";

export default function CaseForm() {
  const { caseId } = useParams<{ caseId: string }>();
  const isEdit = Boolean(caseId);
  const navigate = useNavigate();

  const [protocolNumber, setProtocolNumber] = useState("");
  const [inquiryNumber, setInquiryNumber] = useState("");
  const [processNumber, setProcessNumber] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<"aberto" | "fechado">("aberto");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isEdit && caseId) {
      loadCase(caseId);
    }
  }, [isEdit, caseId]);

  async function loadCase(id: string) {
    setLoading(true);
    try {
      const c: Case = await getCase(id);
      setProtocolNumber(c.protocol_number);
      setInquiryNumber(c.inquiry_number || "");
      setProcessNumber(c.process_number || "");
      setTitle(c.title);
      setDescription(c.description || "");
      setStatus(c.status === "fechado" ? "fechado" : "aberto");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao carregar caso");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSaving(true);

    try {
      if (isEdit && caseId) {
        await updateCase(caseId, {
          protocol_number: protocolNumber,
          inquiry_number: inquiryNumber || undefined,
          process_number: processNumber || undefined,
          title,
          description: description || undefined,
          status,
        });
      } else {
        await createCase({
          protocol_number: protocolNumber,
          inquiry_number: inquiryNumber || undefined,
          process_number: processNumber || undefined,
          title,
          description: description || undefined,
        });
      }
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao salvar caso");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div style={{ padding: "2rem" }}>
        <p style={{ color: "#666" }}>Carregando...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: "2rem", maxWidth: "720px" }}>
      <h1 style={{ fontSize: "1.75rem", color: "#1a1a2e", marginBottom: "1.5rem" }}>
        {isEdit ? "Editar Caso" : "Novo Caso"}
      </h1>

      {error && (
        <div
          style={{
            background: "#fee2e2",
            color: "#991b1b",
            padding: "0.75rem 1rem",
            borderRadius: "6px",
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "1rem" }}>
          <label
            style={{
              display: "block",
              marginBottom: "0.35rem",
              fontSize: "0.9rem",
              fontWeight: 500,
              color: "#374151",
            }}
          >
            Protocolo *
          </label>
          <input
            type="text"
            value={protocolNumber}
            onChange={(e) => setProtocolNumber(e.target.value)}
            required
            placeholder="Ex: 2024/001"
            style={{
              width: "100%",
              padding: "0.6rem 0.8rem",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              fontSize: "0.95rem",
              color: "#1a1a2e",
              background: "#fff",
            }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
          <div>
            <label style={{ display: "block", marginBottom: "0.35rem", fontSize: "0.9rem", fontWeight: 500, color: "#374151" }}>
              Numero do Inquerito
            </label>
            <input
              type="text"
              value={inquiryNumber}
              onChange={(e) => setInquiryNumber(e.target.value)}
              placeholder="Ex: 12345/2024"
              style={{
                width: "100%",
                padding: "0.6rem 0.8rem",
                border: "1px solid #d1d5db",
                borderRadius: "6px",
                fontSize: "0.95rem",
                color: "#1a1a2e",
                background: "#fff",
              }}
            />
          </div>
          <div>
            <label style={{ display: "block", marginBottom: "0.35rem", fontSize: "0.9rem", fontWeight: 500, color: "#374151" }}>
              Numero do Processo
            </label>
            <input
              type="text"
              value={processNumber}
              onChange={(e) => setProcessNumber(e.target.value)}
              placeholder="Ex: 0001234-12.2024.8.26.0100"
              style={{
                width: "100%",
                padding: "0.6rem 0.8rem",
                border: "1px solid #d1d5db",
                borderRadius: "6px",
                fontSize: "0.95rem",
                color: "#1a1a2e",
                background: "#fff",
              }}
            />
          </div>
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label style={{ display: "block", marginBottom: "0.35rem", fontSize: "0.9rem", fontWeight: 500, color: "#374151" }}>
            Titulo *
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Titulo descritivo do caso"
            style={{
              width: "100%",
              padding: "0.6rem 0.8rem",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              fontSize: "0.95rem",
              color: "#1a1a2e",
              background: "#fff",
            }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label style={{ display: "block", marginBottom: "0.35rem", fontSize: "0.9rem", fontWeight: 500, color: "#374151" }}>
            Descricao
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Descricao detalhada do caso..."
            style={{
              width: "100%",
              padding: "0.6rem 0.8rem",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              fontSize: "0.95rem",
              color: "#1a1a2e",
              background: "#fff",
              resize: "vertical",
            }}
          />
        </div>

        {isEdit && (
          <div style={{ marginBottom: "1rem" }}>
            <label style={{ display: "block", marginBottom: "0.35rem", fontSize: "0.9rem", fontWeight: 500, color: "#374151" }}>
              Status
            </label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as any)}
              style={{
                width: "100%",
                padding: "0.6rem 0.8rem",
                border: "1px solid #d1d5db",
                borderRadius: "6px",
                fontSize: "0.95rem",
                color: "#1a1a2e",
                background: "#fff",
              }}
            >
              <option value="aberto">Aberto</option>
              <option value="fechado">Fechado</option>
            </select>
          </div>
        )}

        <div style={{ display: "flex", gap: "0.75rem", marginTop: "1.5rem" }}>
          <button
            type="submit"
            disabled={saving}
            style={{
              padding: "0.65rem 1.5rem",
              background: "#1a1a2e",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: saving ? "not-allowed" : "pointer",
              fontSize: "0.95rem",
              fontWeight: 500,
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? "Salvando..." : isEdit ? "Salvar Alteracoes" : "Criar Caso"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/")}
            style={{
              padding: "0.65rem 1.5rem",
              background: "transparent",
              color: "#374151",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.95rem",
            }}
          >
            Cancelar
          </button>
        </div>
      </form>
    </div>
  );
}
