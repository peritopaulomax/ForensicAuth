import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  Suspense,
  type ComponentType,
} from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import EvidenceSelectorFactory from "@/components/EvidenceSelectorFactory";
import {
  getMediaAnalysisGroup,
  isMediaTechniqueDisabled,
  isMediaTechniqueVisible,
  mediaTechniqueEntryKey,
  resolveMediaTechniqueTabLabel,
  type AnalysisMedia,
  type MediaTechniqueEntry,
} from "@/config/mediaAnalysisGroups";
import { getTechniqueConfig } from "@/config/techniqueRegistry";
import { ImageGroupSessionProvider } from "@/context/ImageGroupSessionContext";
import { buildCaseAnalysesUrl } from "@/utils/caseAnalysisNav";
import { getCase } from "@/services/cases";
import { listCaseEvidences } from "@/services/evidence";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import { useAuthStore } from "@/store/authStore";

const MEDIA_LABEL: Record<Exclude<AnalysisMedia, "imagem">, string> = {
  audio: "áudio",
  video: "vídeo",
  pdf: "PDF",
};

function isAnalysisMedia(v: string | undefined): v is Exclude<AnalysisMedia, "imagem"> {
  return v === "audio" || v === "video" || v === "pdf";
}

/** Técnicas virtuais de áudio → hub embutido (grupo/aba opcionais). */
function resolveEmbedTarget(techniqueId: string): {
  registryId: string;
  forceAudioGroup?: "spectral" | "levels";
  forceAudioTab?: "spectrogram" | "levels";
} {
  if (techniqueId === "__audio_hub__") {
    return { registryId: "__audio_hub__" };
  }
  if (techniqueId === "__audio_spectral__") {
    return { registryId: "__audio_hub__", forceAudioGroup: "spectral", forceAudioTab: "spectrogram" };
  }
  if (techniqueId === "__audio_levels__") {
    return { registryId: "__audio_hub__", forceAudioGroup: "levels", forceAudioTab: "levels" };
  }
  return { registryId: techniqueId };
}

export default function MediaAnalysisGroupPage() {
  const { caseId, media: mediaParam, groupId } = useParams<{
    caseId: string;
    media: string;
    groupId: string;
  }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const userRole = useAuthStore((s) => s.user?.role);
  const media = isAnalysisMedia(mediaParam) ? mediaParam : undefined;
  const group = media && groupId ? getMediaAnalysisGroup(media, groupId) : undefined;

  const [caseTitle, setCaseTitle] = useState<string | null>(null);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [selectionSource, setSelectionSource] = useState<"original" | "derivative">("original");
  const autoSelectedRef = useRef(false);

  // Redireciona IDs de grupo de áudio obsoletos para o card canônico audio-forense.
  useEffect(() => {
    if (!caseId || media !== "audio" || !groupId || !group) return;
    if (groupId === group.id) return;
    const qs = searchParams.toString();
    navigate(
      `/cases/${caseId}/analysis/media-group/${media}/${group.id}${qs ? `?${qs}` : ""}`,
      { replace: true },
    );
  }, [caseId, media, groupId, group, navigate, searchParams]);

  const visibleTechniques = useMemo(
    () => (group?.techniques ?? []).filter((e) => isMediaTechniqueVisible(e, userRole)),
    [group, userRole],
  );

  const tabIds = useMemo(
    () => visibleTechniques.map(mediaTechniqueEntryKey),
    [visibleTechniques],
  );

  const activeTab = searchParams.get("tab") || tabIds[0] || "";

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    getCase(caseId)
      .then((data) => {
        if (!cancelled) setCaseTitle(data.title);
      })
      .catch(() => {
        if (!cancelled) setCaseTitle(null);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  useEffect(() => {
    autoSelectedRef.current = false;
    setEvidenceId(null);
    setSelectionSource("original");
  }, [caseId, groupId, media]);

  useEffect(() => {
    if (!tabIds.length) return;
    if (!tabIds.includes(activeTab)) {
      const next = new URLSearchParams(searchParams);
      next.set("tab", tabIds[0]);
      setSearchParams(next, { replace: true });
    }
  }, [activeTab, tabIds, searchParams, setSearchParams]);

  useEffect(() => {
    if (!caseId || !media || autoSelectedRef.current) return;
    let cancelled = false;
    listCaseEvidences(caseId)
      .then((evs) => {
        if (cancelled || autoSelectedRef.current) return;
        const filtered = filterForensicAuthEvidences(evs).filter((e) => e.file_type === media);
        if (filtered.length > 0) {
          autoSelectedRef.current = true;
          setEvidenceId(filtered[0].id);
          setSelectionSource("original");
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [caseId, media]);

  const onSelectEvidence = useCallback((id: string, source: "original" | "derivative" = "original") => {
    setEvidenceId(id);
    setSelectionSource(source);
  }, []);

  function setActiveTab(tabId: string) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tabId);
    setSearchParams(next, { replace: true });
  }

  if (!caseId || !media || !group) {
    return (
      <Navigate
        to={caseId ? buildCaseAnalysesUrl(caseId, mediaParam || "audio") : "/"}
        replace
      />
    );
  }

  const activeEntry: MediaTechniqueEntry | null = activeTab
    ? visibleTechniques.find((e) => mediaTechniqueEntryKey(e) === activeTab) ?? null
    : null;

  const activeTechniqueId = activeEntry ? mediaTechniqueEntryKey(activeEntry) : null;
  const embedTarget = activeTechniqueId ? resolveEmbedTarget(activeTechniqueId) : null;
  const techniqueConfig = embedTarget ? getTechniqueConfig(embedTarget.registryId) : null;
  const TechniqueComponent = (techniqueConfig?.component ?? null) as ComponentType<{
    techniqueId?: string;
    forceAudioGroup?: "spectral" | "levels";
    forceAudioTab?: "spectrogram" | "levels";
  }> | null;

  const techniqueProps = {
    ...(embedTarget && embedTarget.registryId !== "__audio_hub__"
      ? { techniqueId: embedTarget.registryId }
      : {}),
    ...(embedTarget?.forceAudioGroup ? { forceAudioGroup: embedTarget.forceAudioGroup } : {}),
    ...(embedTarget?.forceAudioTab ? { forceAudioTab: embedTarget.forceAudioTab } : {}),
  };

  const sessionValue = useMemo(
    () => ({ groupId: group.id, evidenceId, selectionSource }),
    [group.id, evidenceId, selectionSource],
  );

  return (
    <div style={{ padding: "2rem" }}>
      <nav
        aria-label="Navegação"
        style={{ fontSize: "0.82rem", color: "#6b7280", marginBottom: "0.75rem" }}
      >
        <Link to="/" style={{ color: "#0369a1" }}>
          Casos
        </Link>
        <span style={{ margin: "0 0.35rem" }}>›</span>
        <Link to={`/cases/${caseId}`} style={{ color: "#0369a1" }}>
          {caseTitle || `Caso ${caseId.slice(0, 8)}…`}
        </Link>
        <span style={{ margin: "0 0.35rem" }}>›</span>
        <Link to={buildCaseAnalysesUrl(caseId, media)} style={{ color: "#0369a1" }}>
          Análises
        </Link>
        <span style={{ margin: "0 0.35rem" }}>›</span>
        <span style={{ color: "#374151" }}>{group.title}</span>
      </nav>

      <button
        type="button"
        onClick={() => navigate(buildCaseAnalysesUrl(caseId, media))}
        style={{
          background: "none",
          border: "none",
          color: "#0369a1",
          cursor: "pointer",
          fontSize: "0.85rem",
          marginBottom: "0.75rem",
          padding: 0,
        }}
      >
        ← Voltar às análises de {MEDIA_LABEL[media]}
      </button>

      <h1 style={{ fontSize: "1.45rem", color: "#1a1a2e", margin: "0 0 0.5rem" }}>{group.title}</h1>
      <p style={{ margin: "0 0 1.25rem", fontSize: "0.9rem", color: "#4b5563", maxWidth: 720, lineHeight: 1.5 }}>
        {group.description}
      </p>

      <div
        style={{
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: "10px",
          padding: "1.15rem 1.25rem",
          marginBottom: "1.25rem",
        }}
      >
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem", color: "#1a1a2e", fontWeight: 600 }}>
          Evidência
        </h2>
        <EvidenceSelectorFactory
          mediaType={media}
          caseId={caseId}
          selectedId={evidenceId}
          selectionSource={selectionSource}
          onSelect={onSelectEvidence}
        />
        {!evidenceId && (
          <p style={{ margin: "0.75rem 0 0", fontSize: "0.82rem", color: "#9ca3af" }}>
            Selecione uma evidência para habilitar o processamento nas abas abaixo.
          </p>
        )}
      </div>

      <div
        role="tablist"
        aria-label="Técnicas do grupo"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.35rem",
          marginBottom: "1rem",
          borderBottom: "2px solid #e5e7eb",
          paddingBottom: "0.5rem",
        }}
      >
        {visibleTechniques.map((entry) => {
          const tabId = mediaTechniqueEntryKey(entry);
          const selected = activeTab === tabId;
          const inactive = isMediaTechniqueDisabled(entry);
          return (
            <button
              key={tabId}
              type="button"
              role="tab"
              aria-selected={selected}
              title={inactive ? "Indisponível nesta versão" : undefined}
              onClick={() => setActiveTab(tabId)}
              style={{
                padding: "0.45rem 0.85rem",
                fontSize: "0.8rem",
                fontWeight: selected ? 600 : 500,
                borderRadius: "6px 6px 0 0",
                border: selected ? "2px solid #0369a1" : "2px solid transparent",
                borderBottom: selected ? "2px solid #f8fafc" : "2px solid transparent",
                marginBottom: selected ? -2 : 0,
                background: selected ? "#f0f9ff" : inactive ? "#f9fafb" : "transparent",
                color: selected ? "#0369a1" : inactive ? "#9ca3af" : "#4b5563",
                cursor: "pointer",
                opacity: inactive ? 0.75 : 1,
              }}
            >
              {resolveMediaTechniqueTabLabel(entry)}
              {inactive && (
                <span style={{ marginLeft: 6, fontSize: "0.68rem", fontWeight: 500 }}>(indisponível)</span>
              )}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        style={{
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: "10px",
          padding: "1.25rem",
          minHeight: 200,
        }}
      >
        <ImageGroupSessionProvider value={sessionValue}>
          {TechniqueComponent ? (
            <Suspense
              fallback={
                <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Carregando técnica…</p>
              }
            >
              <TechniqueComponent {...techniqueProps} />
            </Suspense>
          ) : (
            <p style={{ fontSize: "0.85rem", color: "#9ca3af" }}>
              Selecione uma aba de técnica
              {activeTechniqueId ? ` (sem componente para ${activeTechniqueId})` : ""}.
            </p>
          )}
        </ImageGroupSessionProvider>
      </div>
    </div>
  );
}
