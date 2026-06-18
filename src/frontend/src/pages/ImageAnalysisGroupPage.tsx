import { useCallback, useEffect, useMemo, useRef, useState, Suspense } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import DlManipulationBatchTab from "@/components/DlManipulationBatchTab";
import {
  getImageAnalysisGroup,
  IMAGE_BATCH_TAB_ID,
  isImageTechniqueBatchEligible,
  isImageTechniqueDisabled,
  isImageTechniqueVisible,
  resolveTechniqueTabLabel,
  techniqueEntryKey,
  type ImageTechniqueEntry,
} from "@/config/imageAnalysisGroups";
import { resolveImageTechniqueComponent, techniqueComponentProps } from "@/config/imageTechniqueRegistry";
import { ImageGroupSessionProvider } from "@/context/ImageGroupSessionContext";
import { buildCaseAnalysesUrl } from "@/utils/caseAnalysisNav";
import { getCase } from "@/services/cases";
import { useAuthStore } from "@/store/authStore";
import type { Evidence } from "@/types/api";

export default function ImageAnalysisGroupPage() {
  const { caseId, groupId } = useParams<{ caseId: string; groupId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const userRole = useAuthStore((s) => s.user?.role);
  const group = groupId ? getImageAnalysisGroup(groupId) : undefined;

  const [caseTitle, setCaseTitle] = useState<string | null>(null);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [selectionSource, setSelectionSource] = useState<"original" | "derivative">("original");
  const autoSelectedRef = useRef(false);

  const visibleTechniques = useMemo(
    () => (group?.techniques ?? []).filter((e) => isImageTechniqueVisible(e, userRole)),
    [group, userRole],
  );

  const batchTechniques = useMemo(
    () => visibleTechniques.filter((e) => isImageTechniqueBatchEligible(e)),
    [visibleTechniques],
  );

  const tabIds = useMemo(() => {
    const ids = visibleTechniques.map(techniqueEntryKey);
    if (group?.batchTab) ids.push(IMAGE_BATCH_TAB_ID);
    return ids;
  }, [visibleTechniques, group?.batchTab]);

  const activeTab = searchParams.get("tab") || tabIds[0] || "";
  const isBatchTab = activeTab === IMAGE_BATCH_TAB_ID;

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
  }, [caseId, groupId]);

  useEffect(() => {
    if (!tabIds.length) return;
    if (!tabIds.includes(activeTab)) {
      const next = new URLSearchParams(searchParams);
      next.set("tab", tabIds[0]);
      setSearchParams(next, { replace: true });
    }
  }, [activeTab, tabIds, searchParams, setSearchParams]);

  const onSelectEvidence = useCallback((id: string, source: "original" | "derivative") => {
    setEvidenceId(id);
    setSelectionSource(source);
  }, []);

  function handleEvidenceLoaded(originals: Evidence[], derivatives: Evidence[]) {
    if (autoSelectedRef.current) return;
    autoSelectedRef.current = true;
    if (originals.length > 0) {
      onSelectEvidence(originals[0].id, "original");
    } else if (derivatives.length > 0) {
      onSelectEvidence(derivatives[0].id, "derivative");
    }
  }

  function setActiveTab(tabId: string) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tabId);
    setSearchParams(next, { replace: true });
  }

  if (!caseId || !group) {
    return <Navigate to={caseId ? buildCaseAnalysesUrl(caseId, "imagem") : "/"} replace />;
  }

  const activeEntry: ImageTechniqueEntry | null =
    !isBatchTab && activeTab
      ? visibleTechniques.find((e) => techniqueEntryKey(e) === activeTab) ?? null
      : null;
  const TechniqueComponent = activeEntry ? resolveImageTechniqueComponent(activeEntry) : null;
  const techniqueProps = activeEntry ? techniqueComponentProps(activeEntry) : {};

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
        <Link to={buildCaseAnalysesUrl(caseId, "imagem")} style={{ color: "#0369a1" }}>
          Análises
        </Link>
        <span style={{ margin: "0 0.35rem" }}>›</span>
        <span style={{ color: "#374151" }}>{group.title}</span>
      </nav>

      <button
        type="button"
        onClick={() => navigate(buildCaseAnalysesUrl(caseId, "imagem"))}
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
        ← Voltar às análises de imagem
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
        <ImageEvidenceSelector
          caseId={caseId}
          selectedId={evidenceId}
          selectionSource={selectionSource}
          onSelect={onSelectEvidence}
          onLoaded={handleEvidenceLoaded}
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
          const tabId = techniqueEntryKey(entry);
          const selected = activeTab === tabId;
          const inactive = isImageTechniqueDisabled(entry);
          return (
            <button
              key={tabId}
              type="button"
              role="tab"
              aria-selected={selected}
              title={inactive ? "Em breve nesta versão" : undefined}
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
              {resolveTechniqueTabLabel(entry)}
              {inactive && (
                <span style={{ marginLeft: 6, fontSize: "0.68rem", fontWeight: 500 }}>(indisponível)</span>
              )}
            </button>
          );
        })}
        {group.batchTab && (
          <button
            type="button"
            role="tab"
            aria-selected={isBatchTab}
            onClick={() => setActiveTab(IMAGE_BATCH_TAB_ID)}
            style={{
              padding: "0.45rem 0.85rem",
              fontSize: "0.8rem",
              fontWeight: isBatchTab ? 600 : 500,
              borderRadius: "6px 6px 0 0",
              border: isBatchTab ? "2px solid #7c3aed" : "2px solid transparent",
              borderBottom: isBatchTab ? "2px solid #faf5ff" : "2px solid transparent",
              marginBottom: isBatchTab ? -2 : 0,
              background: isBatchTab ? "#f5f3ff" : "transparent",
              color: isBatchTab ? "#6d28d9" : "#4b5563",
              cursor: "pointer",
            }}
          >
            Executar todas
          </button>
        )}
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
          {isBatchTab ? (
            <DlManipulationBatchTab caseId={caseId} evidenceId={evidenceId} techniques={batchTechniques} />
          ) : TechniqueComponent ? (
            <Suspense
              fallback={
                <p style={{ fontSize: "0.85rem", color: "#6b7280" }}>Carregando técnica…</p>
              }
            >
              <TechniqueComponent {...techniqueProps} />
            </Suspense>
          ) : (
            <p style={{ fontSize: "0.85rem", color: "#9ca3af" }}>Selecione uma aba de técnica.</p>
          )}
        </ImageGroupSessionProvider>
      </div>
    </div>
  );
}
