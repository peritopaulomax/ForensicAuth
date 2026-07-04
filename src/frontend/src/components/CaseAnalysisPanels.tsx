import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  IMAGE_ANALYSIS_GROUPS,
  isImageTechniqueVisible,
} from "@/config/imageAnalysisGroups";
import { useAuthStore } from "@/store/authStore";
import {
  parseAnalysesSearchParams,
  techniqueHasDedicatedPage,
  isTechniqueHiddenInMediaTab,
  navigateToDedicatedAnalysis,
} from "@/utils/caseAnalysisNav";
import api from "@/services/api";
import { resolvePeritusFileForAnalysis, type PeritusFileEntry } from "@/services/peritus";
import { filterPeritusAnalyzable } from "@/lib/peritusAnalysis";
import SelectableEvidenceList from "@/components/SelectableEvidenceList";
import SelectablePeritusFileList from "@/components/SelectablePeritusFileList";
import type { Evidence } from "@/types/api";
import {
  FORENSIC_TECHNIQUE_META,
  getTechniqueCardSubtitle,
  resolveTechniqueLabel,
} from "@/config/forensicTechniqueMeta";

interface PluginInfo {
  name: string;
  supported_types: string[];
  available?: boolean;
  unavailable_reason?: string | null;
}

const mediaTypeMeta: Record<string, { label: string; icon: string; color: string; textColor: string }> = {
  imagem: { label: "Imagem", icon: "🖼️", color: "#e0f2fe", textColor: "#0369a1" },
  audio: { label: "Áudio", icon: "🎵", color: "#dcfce7", textColor: "#166534" },
  video: { label: "Vídeo", icon: "🎬", color: "#fef3c7", textColor: "#b45309" },
  pdf: { label: "PDF", icon: "📄", color: "#fee2e2", textColor: "#991b1b" },
};

const techniqueSubtitles: Record<string, string> = {
  __audio_hub__: "Espectrograma, ENF, LTAS, DC e Níveis",
  __audio_spectral__: "Espectrograma, ENF e LTAS",
  __audio_levels__: "Níveis e DC local",
  synthetic_image_detection:
    "ai-image-detector-deploy, sdxl-flux-detector v1.1, B-Free/Bias-free e Corvi2023",
  jpeg_structure_compare: FORENSIC_TECHNIQUE_META.jpeg_structure_compare.cardSubtitle,
  jpeg_ghosts: FORENSIC_TECHNIQUE_META.jpeg_ghosts.cardSubtitle,
  dct_quantization: FORENSIC_TECHNIQUE_META.dct_quantization.cardSubtitle,
  double_compression: FORENSIC_TECHNIQUE_META.double_compression.cardSubtitle,
  ela: FORENSIC_TECHNIQUE_META.ela.cardSubtitle,
  bag_extraction: FORENSIC_TECHNIQUE_META.bag_extraction.cardSubtitle,
  zero_grid: FORENSIC_TECHNIQUE_META.zero_grid.cardSubtitle,
  resampling: FORENSIC_TECHNIQUE_META.resampling.cardSubtitle,
  patchmatch: FORENSIC_TECHNIQUE_META.patchmatch.cardSubtitle,
  copy_move_pca: FORENSIC_TECHNIQUE_META.copy_move_pca.cardSubtitle,
  wavelet_noise_residue: FORENSIC_TECHNIQUE_META.wavelet_noise_residue.cardSubtitle,
  prnu: FORENSIC_TECHNIQUE_META.prnu.cardSubtitle,
  safire: FORENSIC_TECHNIQUE_META.safire.cardSubtitle,
  noiseprint: FORENSIC_TECHNIQUE_META.noiseprint.cardSubtitle,
};

interface Props {
  evidences: Evidence[];
  peritusFiles?: PeritusFileEntry[];
}

export default function CaseAnalysisPanels({
  evidences,
  peritusFiles = [],
}: Props) {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const techniquesRef = useRef<HTMLDivElement>(null);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedTech, setSelectedTech] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);
  const [selectedPeritusPath, setSelectedPeritusPath] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string>("");
  const userRole = useAuthStore((s) => s.user?.role);

  const peritusAnalyzable = filterPeritusAnalyzable(peritusFiles);

  const typesInCase = Array.from(
    new Set([
      ...evidences.map((e) => e.file_type),
      ...peritusAnalyzable.map((f) => f.file_type),
    ])
  ).filter((t) => mediaTypeMeta[t]);
  const [activeType, setActiveType] = useState(typesInCase[0] || "imagem");

  useEffect(() => {
    if (typesInCase.length > 0 && !typesInCase.includes(activeType)) {
      setActiveType(typesInCase[0]);
    }
  }, [typesInCase, activeType]);

  useEffect(() => {
    const { media, technique } = parseAnalysesSearchParams(searchParams);
    if (media && typesInCase.includes(media)) {
      setActiveType(media);
    }
    if (
      technique &&
      !techniqueHasDedicatedPage(technique) &&
      !(media && isTechniqueHiddenInMediaTab(technique, media))
    ) {
      setSelectedTech(technique);
      setSelectedEvidence(null);
      setSelectedPeritusPath(null);
      setResult("");
      requestAnimationFrame(() => {
        techniquesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } else {
      setSelectedTech(null);
      setSelectedEvidence(null);
      setResult("");
    }
  }, [searchParams, typesInCase]);

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

  const AUDIO_CORE = new Set([
    "audio_spectrogram",
    "audio_enf",
    "audio_ltas",
    "audio_levels",
    "audio_dc_local",
  ]);

  const filteredPlugins = plugins.filter(
    (p) => p.supported_types.includes(activeType) && !isTechniqueHiddenInMediaTab(p.name, activeType)
  );

  const displayPlugins =
    activeType === "audio"
      ? (() => {
          const core = filteredPlugins.filter((p) => AUDIO_CORE.has(p.name));
          const rest = filteredPlugins.filter((p) => !AUDIO_CORE.has(p.name));
          if (core.length === 0) return filteredPlugins;
          const hubReason = core.find((p) => p.unavailable_reason)?.unavailable_reason;
          const spectralAvail = core.some(
            (p) =>
              ["audio_spectrogram", "audio_enf", "audio_ltas"].includes(p.name) && p.available !== false
          );
          const levelsAvail = core.some(
            (p) =>
              ["audio_levels", "audio_dc_local"].includes(p.name) && p.available !== false
          );
          return [
            {
              name: "__audio_spectral__",
              supported_types: ["audio"],
              available: spectralAvail,
              unavailable_reason: spectralAvail ? null : hubReason,
            },
            {
              name: "__audio_levels__",
              supported_types: ["audio"],
              available: levelsAvail,
              unavailable_reason: levelsAvail ? null : hubReason,
            },
            ...rest,
          ];
        })()
      : filteredPlugins;

  const evidencesOfType = evidences.filter((e) => e.file_type === activeType);
  const peritusOfType = peritusAnalyzable.filter((f) => f.file_type === activeType);

  function clearSelection() {
    setSelectedEvidence(null);
    setSelectedPeritusPath(null);
  }

  function handleSelectVaEvidence(id: string) {
    setSelectedEvidence(id);
    setSelectedPeritusPath(null);
  }

  function handleSelectPeritusPath(path: string) {
    setSelectedPeritusPath(path);
    setSelectedEvidence(null);
  }

  function handlePluginClick(plugin: PluginInfo) {
    if (plugin.available === false) return;
    if (caseId && navigateToDedicatedAnalysis(navigate, caseId, plugin.name)) {
      return;
    }
    setSelectedTech(plugin.name);
    clearSelection();
    setResult("");
  }

  function handleImageGroupClick(groupId: string) {
    if (!caseId) return;
    navigate(`/cases/${caseId}/analysis/image-group/${groupId}`);
  }

  function renderImageCategoryCards() {
    return (
      <div
        ref={techniquesRef}
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: "1rem",
          scrollMarginTop: "1rem",
        }}
      >
        {IMAGE_ANALYSIS_GROUPS.map((group) => {
          const visible = group.techniques.filter((entry) => isImageTechniqueVisible(entry, userRole));
          if (visible.length === 0) return null;
          return (
            <button
              key={group.id}
              type="button"
              onClick={() => handleImageGroupClick(group.id)}
              style={{
                textAlign: "left",
                background: "linear-gradient(180deg, #f8fafc 0%, #ffffff 55%)",
                border: "1px solid #e2e8f0",
                borderRadius: "14px",
                padding: "1.35rem 1.5rem",
                cursor: "pointer",
                boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 16px rgba(15, 23, 42, 0.03)",
                transition: "border-color 0.15s ease, box-shadow 0.15s ease",
              }}
            >
              <h3
                style={{
                  margin: "0 0 0.5rem",
                  fontSize: "0.98rem",
                  fontWeight: 600,
                  color: "#1e293b",
                  lineHeight: 1.35,
                }}
              >
                {group.title}
              </h3>
              <p style={{ margin: "0 0 0.75rem", fontSize: "0.8rem", color: "#64748b", lineHeight: 1.45 }}>
                {group.description}
              </p>
              <span style={{ fontSize: "0.72rem", color: "#0369a1", fontWeight: 600 }}>
                {visible.length} técnica{visible.length !== 1 ? "s" : ""} →
              </span>
            </button>
          );
        })}
      </div>
    );
  }

  function renderTechniqueCard(plugin: PluginInfo) {
    const inactive = plugin.available === false;
    return (
      <div
        key={plugin.name}
        title={inactive ? plugin.unavailable_reason || "Indisponivel neste servidor" : undefined}
        onClick={() => handlePluginClick(plugin)}
        style={{
          background: inactive ? "#f3f4f6" : selectedTech === plugin.name ? "#f0f9ff" : "#fff",
          border: `2px solid ${inactive ? "#e5e7eb" : selectedTech === plugin.name ? "#0369a1" : "#e5e7eb"}`,
          borderRadius: "8px",
          padding: "1rem",
          cursor: inactive ? "not-allowed" : "pointer",
          opacity: inactive ? 0.5 : 1,
          transition: "all 0.15s ease",
        }}
      >
        <h4 style={{ margin: "0 0 0.25rem 0", fontSize: "0.95rem", color: "#1a1a2e", fontWeight: 600 }}>
          {resolveTechniqueLabel(plugin.name)}
          {inactive && (
            <span style={{ marginLeft: 8, fontSize: "0.7rem", color: "#9ca3af", fontWeight: 500 }}>
              (indisponivel)
            </span>
          )}
        </h4>
        <p style={{ margin: 0, fontSize: "0.75rem", color: "#6b7280" }}>
          {techniqueSubtitles[plugin.name] || getTechniqueCardSubtitle(plugin.name) || plugin.name}
        </p>
        {inactive && plugin.unavailable_reason && (
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.72rem", color: "#9ca3af", lineHeight: 1.35 }}>
            {plugin.unavailable_reason}
          </p>
        )}
      </div>
    );
  }

  async function runAnalysis() {
    if (!selectedTech || (!selectedEvidence && !selectedPeritusPath) || !caseId) return;
    setRunning(true);
    setResult("");
    try {
      let evidenceId = selectedEvidence;
      if (selectedPeritusPath) {
        const resolved = await resolvePeritusFileForAnalysis(caseId, selectedPeritusPath);
        evidenceId = resolved.evidence_id;
      }
      if (!evidenceId) return;
      const response = await api.post("/analysis", {
        evidence_id: evidenceId,
        technique: selectedTech,
        parameters: {},
      });
      setResult(`Análise submetida com sucesso! Job ID: ${response.data.id || response.data.job_id || "N/A"}`);
    } catch (err: any) {
      setResult(`Erro: ${err.response?.data?.detail || err.message}`);
    } finally {
      setRunning(false);
    }
  }

  const hasAnySource = evidences.length > 0 || peritusAnalyzable.length > 0;

  if (!hasAnySource) {
    return (
      <div style={{ textAlign: "center", padding: "3rem", color: "#9ca3af" }}>
        <p>
          Adicione evidências ForensicAuth ou importe um pacote Peritus Desktop para visualizar as técnicas de
          análise disponíveis.
        </p>
      </div>
    );
  }

  if (typesInCase.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: "3rem", color: "#9ca3af" }}>
        <p>Nenhum tipo de mídia reconhecido nas evidências deste caso.</p>
      </div>
    );
  }

  return (
    <div>
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

      {/* Abas de tipo de mídia presentes no caso */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "1.5rem",
          borderBottom: "2px solid #e5e7eb",
          paddingBottom: "0.5rem",
        }}
      >
        {typesInCase.map((t) => {
          const meta = mediaTypeMeta[t];
          return (
            <button
              key={t}
              onClick={() => {
                setActiveType(t);
                clearSelection();
                setResult("");
                const next = new URLSearchParams(searchParams);
                next.set("tab", "analises");
                next.set("media", t);
                next.delete("technique");
                setSearchParams(next, { replace: true });
              }}
              style={{
                padding: "0.6rem 1.2rem",
                background: activeType === t ? meta.color : "transparent",
                color: activeType === t ? meta.textColor : "#6b7280",
                border: "none",
                borderRadius: "6px 6px 0 0",
                cursor: "pointer",
                fontSize: "0.95rem",
                fontWeight: activeType === t ? 600 : 500,
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                borderBottom: activeType === t ? `2px solid ${meta.textColor}` : "2px solid transparent",
                marginBottom: "-0.5rem",
              }}
            >
              <span>{meta.icon}</span>
              <span>{meta.label}</span>
              <span
                style={{
                  fontSize: "0.7rem",
                  background: activeType === t ? "rgba(255,255,255,0.5)" : "#f3f4f6",
                  padding: "0.1rem 0.35rem",
                  borderRadius: "10px",
                  marginLeft: "0.2rem",
                }}
              >
                {evidences.filter((e) => e.file_type === t).length +
                  peritusAnalyzable.filter((f) => f.file_type === t).length}
              </span>
            </button>
          );
        })}
      </div>

      {loading ? (
        <p style={{ color: "#666" }}>Carregando técnicas...</p>
      ) : displayPlugins.length === 0 ? (
        <div style={{ textAlign: "center", padding: "2rem", color: "#9ca3af" }}>
          <p>Nenhuma técnica disponível para {mediaTypeMeta[activeType]?.label}.</p>
        </div>
      ) : activeType === "imagem" ? (
        <div style={{ marginBottom: "1.5rem" }}>{renderImageCategoryCards()}</div>
      ) : (
        <div
          ref={techniquesRef}
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: "0.75rem",
            marginBottom: "1.5rem",
            scrollMarginTop: "1rem",
          }}
        >
          {displayPlugins.map(renderTechniqueCard)}
        </div>
      )}

      {/* Seleção de evidência e execução */}
      {selectedTech && (
        <div
          style={{
            background: "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            padding: "1.25rem",
          }}
        >
          <h4 style={{ margin: "0 0 0.75rem 0", fontSize: "0.95rem", color: "#1a1a2e" }}>
            Executar: {resolveTechniqueLabel(selectedTech)}
          </h4>

          {evidencesOfType.length === 0 && peritusOfType.length === 0 ? (
            <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>
              Nenhuma fonte do tipo {mediaTypeMeta[activeType]?.label} disponivel.
            </p>
          ) : (
            <>
              {evidencesOfType.length > 0 && (
                <div style={{ marginBottom: "1rem" }}>
                  <p style={{ margin: "0 0 0.5rem 0", fontSize: "0.85rem", color: "#374151", fontWeight: 600 }}>
                    Evidencias ForensicAuth
                  </p>
                  <SelectableEvidenceList
                    sectionId={`case-analyses-${caseId ?? "case"}-${selectedTech}-va`}
                    items={evidencesOfType}
                    selectedId={selectedEvidence}
                    selectionSource="original"
                    source="original"
                    onSelect={(id) => handleSelectVaEvidence(id)}
                    radioName="case-analysis-evidence"
                  />
                </div>
              )}

              {peritusOfType.length > 0 && (
                <div style={{ marginBottom: "1rem" }}>
                  <p style={{ margin: "0 0 0.5rem 0", fontSize: "0.85rem", color: "#4338ca", fontWeight: 600 }}>
                    Arquivos Peritus importados
                  </p>
                  <SelectablePeritusFileList
                    caseId={caseId!}
                    files={peritusOfType}
                    selectedPath={selectedPeritusPath}
                    onSelect={handleSelectPeritusPath}
                    radioName="case-analysis-peritus"
                  />
                </div>
              )}

              <button
                onClick={runAnalysis}
                disabled={(!selectedEvidence && !selectedPeritusPath) || running}
                style={{
                  padding: "0.6rem 1.5rem",
                  background: "#1a1a2e",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  cursor: !selectedEvidence && !selectedPeritusPath || running ? "not-allowed" : "pointer",
                  fontSize: "0.9rem",
                  fontWeight: 500,
                  opacity: !selectedEvidence && !selectedPeritusPath || running ? 0.6 : 1,
                }}
              >
                {running ? "Executando..." : "Executar Analise"}
              </button>

              {result && (
                <div
                  style={{
                    marginTop: "0.75rem",
                    padding: "0.6rem 0.75rem",
                    background: result.startsWith("Erro") ? "#fee2e2" : "#dcfce7",
                    color: result.startsWith("Erro") ? "#991b1b" : "#166534",
                    borderRadius: "6px",
                    fontSize: "0.85rem",
                  }}
                >
                  {result}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

