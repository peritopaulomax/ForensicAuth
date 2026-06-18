import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/services/api";
import { isTechniqueHiddenInMediaTab } from "@/utils/caseAnalysisNav";
import { resolveTechniqueLabel } from "@/config/forensicTechniqueMeta";

interface PluginInfo {
  name: string;
  supported_types: string[];
}

const mediaTypes = [
  { key: "imagem", label: "Imagem", icon: "🖼️", color: "#e0f2fe", textColor: "#0369a1" },
  { key: "audio", label: "Áudio", icon: "🎵", color: "#dcfce7", textColor: "#166534" },
  { key: "video", label: "Vídeo", icon: "🎬", color: "#fef3c7", textColor: "#b45309" },
  { key: "pdf", label: "PDF", icon: "📄", color: "#fee2e2", textColor: "#991b1b" },
];

export default function MediaPanels() {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [activeTab, setActiveTab] = useState("imagem");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    loadPlugins();
  }, []);

  async function loadPlugins() {
    try {
      const response = await api.get<PluginInfo[]>("/analysis/techniques");
      setPlugins(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao carregar técnicas");
    } finally {
      setLoading(false);
    }
  }

  const filteredPlugins = plugins.filter(
    (p) => p.supported_types.includes(activeTab) && !isTechniqueHiddenInMediaTab(p.name, activeTab)
  );

  return (
    <div style={{ padding: "2rem" }}>
      <h1 style={{ fontSize: "1.6rem", color: "#1a1a2e", marginBottom: "0.25rem" }}>
        Análises Forenses
      </h1>
      <p style={{ color: "#6b7280", fontSize: "0.9rem", marginBottom: "1.5rem" }}>
        Selecione o tipo de mídia e a técnica desejada
      </p>

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

      {/* Abas de tipo de mídia */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "1.5rem",
          borderBottom: "2px solid #e5e7eb",
          paddingBottom: "0.5rem",
        }}
      >
        {mediaTypes.map((mt) => (
          <button
            key={mt.key}
            onClick={() => setActiveTab(mt.key)}
            style={{
              padding: "0.6rem 1.2rem",
              background: activeTab === mt.key ? mt.color : "transparent",
              color: activeTab === mt.key ? mt.textColor : "#6b7280",
              border: "none",
              borderRadius: "6px 6px 0 0",
              cursor: "pointer",
              fontSize: "0.95rem",
              fontWeight: activeTab === mt.key ? 600 : 500,
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              borderBottom: activeTab === mt.key ? `2px solid ${mt.textColor}` : "2px solid transparent",
              marginBottom: "-0.5rem",
              transition: "all 0.15s ease",
            }}
          >
            <span>{mt.icon}</span>
            <span>{mt.label}</span>
          </button>
        ))}
      </div>

      {/* Painel de técnicas */}
      {loading ? (
        <p style={{ color: "#666" }}>Carregando técnicas...</p>
      ) : filteredPlugins.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "3rem",
            color: "#9ca3af",
            border: "1px dashed #e5e7eb",
            borderRadius: "8px",
          }}
        >
          <p style={{ margin: 0 }}>Nenhuma técnica disponível para {mediaTypes.find((m) => m.key === activeTab)?.label}.</p>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: "1rem",
          }}
        >
          {filteredPlugins.map((plugin) => (
            <div
              key={plugin.name}
              onClick={() => navigate(`/analysis/run?technique=${plugin.name}`)}
              style={{
                background: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                padding: "1.25rem",
                cursor: "pointer",
                transition: "box-shadow 0.15s ease, border-color 0.15s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.08)";
                e.currentTarget.style.borderColor = "#d1d5db";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.boxShadow = "none";
                e.currentTarget.style.borderColor = "#e5e7eb";
              }}
            >
              <h3
                style={{
                  margin: "0 0 0.5rem 0",
                  fontSize: "1rem",
                  color: "#1a1a2e",
                  fontWeight: 600,
                }}
              >
                {resolveTechniqueLabel(plugin.name)}
              </h3>
              <p style={{ margin: "0 0 0.75rem 0", fontSize: "0.8rem", color: "#6b7280" }}>
                {plugin.name}
              </p>
              <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                {plugin.supported_types.map((t) => (
                  <span
                    key={t}
                    style={{
                      fontSize: "0.7rem",
                      padding: "0.15rem 0.4rem",
                      borderRadius: "4px",
                      background: "#f3f4f6",
                      color: "#6b7280",
                      textTransform: "capitalize",
                    }}
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
