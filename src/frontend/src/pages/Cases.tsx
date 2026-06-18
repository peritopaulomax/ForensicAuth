import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { listCases, deleteCase } from "@/services/cases";
import type { CaseDetail } from "@/types/api";
import { useAuthStore } from "@/store/authStore";
import CaseImportVcpModal from "@/components/CaseImportVcpModal";
import CaseImportPeritusModal from "@/components/CaseImportPeritusModal";
import { isLikelyVcpFilename, probeVcpPackage } from "@/lib/vcpDetect";
import { isLikelyPeritusFilename, probePeritusPackage } from "@/lib/peritusDetect";

const statusLabels: Record<string, string> = {
  aberto: "Aberto",
  em_andamento: "Aberto",
  fechamento_pendente: "Fechamento pendente",
  fechado: "Fechado",
};

const statusColors: Record<string, string> = {
  aberto: "#e0f2fe",
  em_andamento: "#e0f2fe",
  fechamento_pendente: "#ffedd5",
  fechado: "#fee2e2",
};

const statusTextColors: Record<string, string> = {
  aberto: "#0369a1",
  em_andamento: "#0369a1",
  fechamento_pendente: "#c2410c",
  fechado: "#991b1b",
};

type ListScope = "all" | "mine" | "shared";

export default function Cases() {
  const [cases, setCases] = useState<CaseDetail[]>([]);
  const [listScope, setListScope] = useState<ListScope>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importPeritusOpen, setImportPeritusOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importAutoValidate, setImportAutoValidate] = useState(false);
  const [dragDepth, setDragDepth] = useState(0);
  const [dropHint, setDropHint] = useState("");
  const dragDepthRef = useRef(0);
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const canImport = Boolean(user);

  useEffect(() => {
    loadCases();
  }, [listScope]);

  async function loadCases() {
    setLoading(true);
    setError("");
    try {
      const data = await listCases(listScope === "all" ? undefined : listScope);
      setCases(data);
    } catch (err: unknown) {
      const detail =
        err &&
        typeof err === "object" &&
        "response" in err &&
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Erro ao carregar casos");
    } finally {
      setLoading(false);
    }
  }

  function canDeleteCase(c: CaseDetail) {
    if (!user) return false;
    if (user.role === "admin") return true;
    return c.created_by === user.id;
  }

  async function handleDelete(c: CaseDetail) {
    const msg =
      "Excluir este caso inteiro?\n\n" +
      "• Todos os arquivos (evidencias, derivados, resultados de analise) serao apagados do disco.\n" +
      "• A cadeia de custodia (logs) sera preservada com registro de exclusao.\n" +
      "• Esta acao nao pode ser desfeita.\n\n" +
      `Caso: ${c.protocol_number} — ${c.title}`;
    if (!confirm(msg)) return;
    try {
      await deleteCase(c.id);
      setCases((prev) => prev.filter((x) => x.id !== c.id));
    } catch (err: unknown) {
      const detail =
        err &&
        typeof err === "object" &&
        "response" in err &&
        (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ")
            : "Erro ao excluir caso";
      setError(msg || "Erro ao excluir caso");
    }
  }

  const openImportModal = useCallback((file: File | null, autoValidate: boolean) => {
    setImportFile(file);
    setImportAutoValidate(autoValidate);
    setImportOpen(true);
  }, []);

  const openImportPeritusModal = useCallback((file: File | null, autoValidate: boolean) => {
    setImportFile(file);
    setImportAutoValidate(autoValidate);
    setImportPeritusOpen(true);
  }, []);

  const handlePageDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (!canImport) return;
      e.preventDefault();
      dragDepthRef.current += 1;
      setDragDepth(dragDepthRef.current);
    },
    [canImport]
  );

  const handlePageDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (!canImport) return;
      e.preventDefault();
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      setDragDepth(dragDepthRef.current);
    },
    [canImport]
  );

  const handlePageDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!canImport) return;
      e.preventDefault();
    },
    [canImport]
  );

  const handlePageDrop = useCallback(
    async (e: React.DragEvent) => {
      if (!canImport) return;
      e.preventDefault();
      dragDepthRef.current = 0;
      setDragDepth(0);

      const dropped = e.dataTransfer.files?.[0];
      if (!dropped) return;

      if (!isLikelyVcpFilename(dropped.name) && !isLikelyPeritusFilename(dropped.name)) {
        setDropHint("Solte um arquivo .zip (VCP ou Peritus Desktop).");
        setTimeout(() => setDropHint(""), 4000);
        return;
      }

      const peritusProbe = await probePeritusPackage(dropped);
      if (peritusProbe.isZip && (peritusProbe.looksLikePeritus || dropped.size > 50 * 1024 * 1024)) {
        openImportPeritusModal(dropped, true);
        return;
      }

      const probe = await probeVcpPackage(dropped);
      if (!probe.isZip) {
        setDropHint("Arquivo invalido — nao e um ZIP.");
        setTimeout(() => setDropHint(""), 4000);
        return;
      }
      if (!probe.looksLikeVcp) {
        setDropHint("ZIP detectado, mas nao parece um Verification Case Package (VCP) do ForensicAuth.");
        setTimeout(() => setDropHint(""), 5000);
        return;
      }

      openImportModal(dropped, true);
    },
    [canImport, openImportModal, openImportPeritusModal]
  );

  const filtered = cases.filter(
    (c) =>
      c.protocol_number.toLowerCase().includes(search.toLowerCase()) ||
      c.title.toLowerCase().includes(search.toLowerCase()) ||
      (c.inquiry_number && c.inquiry_number.toLowerCase().includes(search.toLowerCase())) ||
      (c.process_number && c.process_number.toLowerCase().includes(search.toLowerCase()))
  );

  const showDropOverlay = canImport && dragDepth > 0;

  return (
    <div
      style={{ padding: "2rem", position: "relative", minHeight: "100%" }}
      onDragEnter={handlePageDragEnter}
      onDragLeave={handlePageDragLeave}
      onDragOver={handlePageDragOver}
      onDrop={handlePageDrop}
    >
      {showDropOverlay && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1500,
            background: "rgba(15, 118, 110, 0.12)",
            border: "3px dashed #0f766e",
            pointerEvents: "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              background: "#fff",
              padding: "1.25rem 2rem",
              borderRadius: "10px",
              boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
              fontSize: "1rem",
              color: "#0f766e",
              fontWeight: 600,
            }}
          >
            Solte um Verification Case Package (VCP) ou pacote Peritus Desktop para importar
          </div>
        </div>
      )}

      <CaseImportPeritusModal
        open={importPeritusOpen}
        onClose={() => {
          setImportPeritusOpen(false);
          setImportFile(null);
          setImportAutoValidate(false);
        }}
        initialFile={importFile}
        autoValidate={importAutoValidate}
        onImported={async (caseId) => {
          await loadCases();
          navigate(`/cases/${caseId}`);
        }}
      />

      <CaseImportVcpModal
        open={importOpen}
        onClose={() => {
          setImportOpen(false);
          setImportFile(null);
          setImportAutoValidate(false);
        }}
        initialFile={importFile}
        autoValidate={importAutoValidate}
        onImported={async (caseId) => {
          await loadCases();
          navigate(`/cases/${caseId}`);
        }}
      />

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <h1 style={{ margin: 0, fontSize: "1.75rem", color: "#1a1a2e" }}>
          Casos
        </h1>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {canImport && (
            <>
            <button
              type="button"
              onClick={() => openImportPeritusModal(null, false)}
              style={{
                padding: "0.6rem 1.2rem",
                background: "#fff",
                color: "#4338ca",
                border: "1px solid #4338ca",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "0.95rem",
                fontWeight: 500,
              }}
            >
              Importar Peritus Desktop
            </button>
            <button
              type="button"
              onClick={() => openImportModal(null, false)}
              style={{
                padding: "0.6rem 1.2rem",
                background: "#fff",
                color: "#0f766e",
                border: "1px solid #0f766e",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "0.95rem",
                fontWeight: 500,
              }}
            >
              Importar VCP…
            </button>
            </>
          )}
          <button
            type="button"
            onClick={() => navigate("/cases/new")}
            style={{
              padding: "0.6rem 1.2rem",
              background: "#1a1a2e",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.95rem",
              fontWeight: 500,
            }}
          >
            + Novo Caso
          </button>
        </div>
      </div>

      {canImport && (
        <p style={{ margin: "0 0 1rem", fontSize: "0.8rem", color: "#6b7280" }}>
          Dica: arraste um <strong>.zip</strong> do Peritus Desktop ou <strong>.vcp.zip</strong> sobre esta pagina.
        </p>
      )}

      {dropHint && (
        <div
          style={{
            marginBottom: "1rem",
            padding: "0.6rem 1rem",
            background: "#fff7ed",
            color: "#9a3412",
            borderRadius: "6px",
            fontSize: "0.85rem",
          }}
        >
          {dropHint}
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        {(
          [
            ["all", "Todos"],
            ["mine", "Meus casos"],
            ["shared", "Compartilhados comigo"],
          ] as const
        ).map(([scope, label]) => (
          <button
            key={scope}
            type="button"
            onClick={() => setListScope(scope)}
            style={{
              padding: "0.4rem 0.85rem",
              borderRadius: "6px",
              border: listScope === scope ? "2px solid #1a1a2e" : "1px solid #e5e7eb",
              background: listScope === scope ? "#f3f4f6" : "#fff",
              cursor: "pointer",
              fontSize: "0.85rem",
              fontWeight: listScope === scope ? 600 : 400,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ marginBottom: "1.5rem" }}>
        <input
          type="text"
          placeholder="Buscar por protocolo, titulo, inquerito ou processo..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: "100%",
            maxWidth: "500px",
            padding: "0.6rem 0.9rem",
            border: "1px solid #ddd",
            borderRadius: "6px",
            fontSize: "0.95rem",
            color: "#1a1a2e",
            background: "#fff",
          }}
        />
      </div>

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

      {loading ? (
        <p style={{ color: "#666" }}>Carregando...</p>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "#666" }}>
          <p>Nenhum caso encontrado.</p>
          <button
            type="button"
            onClick={() => navigate("/cases/new")}
            style={{
              marginTop: "1rem",
              padding: "0.5rem 1rem",
              background: "transparent",
              color: "#1a1a2e",
              border: "1px solid #1a1a2e",
              borderRadius: "6px",
              cursor: "pointer",
            }}
          >
            Criar primeiro caso
          </button>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: "1rem",
          }}
        >
          {filtered.map((c) => (
            <div
              key={c.id}
              onClick={() => navigate(`/cases/${c.id}`)}
              style={{
                background: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                padding: "1.25rem",
                cursor: "pointer",
                transition: "box-shadow 0.15s ease",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.08)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.boxShadow = "none")
              }
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  marginBottom: "0.75rem",
                }}
              >
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.02em",
                    padding: "0.25rem 0.5rem",
                    borderRadius: "4px",
                    background: statusColors[c.status] || "#f3f4f6",
                    color: statusTextColors[c.status] || "#374151",
                  }}
                >
                  {statusLabels[c.status] || c.status}
                </span>
                <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
                  {c.is_shared && (
                    <span
                      style={{
                        fontSize: "0.65rem",
                        padding: "0.15rem 0.4rem",
                        background: "#ede9fe",
                        color: "#5b21b6",
                        borderRadius: "4px",
                        fontWeight: 600,
                      }}
                    >
                      Compartilhado
                    </span>
                  )}
                  {c.storage_mode === "peritus" && (
                    <span
                      style={{
                        fontSize: "0.65rem",
                        padding: "0.15rem 0.4rem",
                        background: "#eef2ff",
                        color: "#4338ca",
                        borderRadius: "4px",
                        fontWeight: 600,
                      }}
                    >
                      Peritus Desktop
                    </span>
                  )}
                  <span style={{ fontSize: "0.8rem", color: "#9ca3af" }}>
                    {new Date(c.created_at).toLocaleDateString("pt-BR")}
                  </span>
                </div>
              </div>

              <h3
                style={{
                  margin: "0 0 0.4rem 0",
                  fontSize: "1.05rem",
                  color: "#1a1a2e",
                  fontWeight: 600,
                }}
              >
                {c.title}
              </h3>

              <p
                style={{
                  margin: "0 0 0.5rem 0",
                  fontSize: "0.85rem",
                  color: "#6b7280",
                  fontWeight: 500,
                }}
              >
                Protocolo: {c.protocol_number}
              </p>

              {c.inquiry_number && (
                <p style={{ margin: "0 0 0.25rem 0", fontSize: "0.8rem", color: "#6b7280" }}>
                  Inquerito: {c.inquiry_number}
                </p>
              )}
              {c.process_number && (
                <p style={{ margin: "0 0 0.25rem 0", fontSize: "0.8rem", color: "#6b7280" }}>
                  Processo: {c.process_number}
                </p>
              )}

              {c.description && (
                <p
                  style={{
                    margin: "0.5rem 0 0 0",
                    fontSize: "0.85rem",
                    color: "#4b5563",
                    lineHeight: 1.45,
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {c.description}
                </p>
              )}

              <div
                style={{
                  marginTop: "1rem",
                  display: "flex",
                  gap: "0.5rem",
                  justifyContent: "flex-end",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => navigate(`/cases/${c.id}/edit`)}
                  style={{
                    padding: "0.35rem 0.7rem",
                    fontSize: "0.8rem",
                    background: "#f3f4f6",
                    color: "#374151",
                    border: "none",
                    borderRadius: "4px",
                    cursor: "pointer",
                  }}
                >
                  Editar
                </button>
                {canDeleteCase(c) && (
                  <button
                    type="button"
                    onClick={() => handleDelete(c)}
                    style={{
                      padding: "0.35rem 0.7rem",
                      fontSize: "0.8rem",
                      background: "#fee2e2",
                      color: "#991b1b",
                      border: "none",
                      borderRadius: "4px",
                      cursor: "pointer",
                    }}
                  >
                    Excluir caso
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
