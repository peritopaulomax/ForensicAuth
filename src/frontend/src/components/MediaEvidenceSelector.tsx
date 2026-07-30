import { useEffect, useState } from "react";
import { listCaseDerivatives, listCaseEvidences } from "@/services/evidence";
import CollapsibleSection from "@/components/CollapsibleSection";
import GlobalReferencesSelector from "@/components/GlobalReferencesSelector";
import SelectableEvidenceList from "@/components/SelectableEvidenceList";
import PeritusAnalysisFileSection from "@/components/PeritusAnalysisFileSection";
import { resolvePeritusFileForAnalysis } from "@/services/peritus";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import type { AnalysisMediaType } from "@/lib/peritusAnalysis";
import type { Evidence } from "@/types/api";

export interface MediaEvidenceSelectorProps {
  caseId: string;
  fileType: AnalysisMediaType;
  selectedId: string | null;
  selectionSource?: "original" | "derivative";
  onSelect: (id: string, source: "original" | "derivative") => void;
  radioName?: string;
  title?: string;
  /** Nao lista derivados do mesmo tipo de midia */
  excludeDerivatives?: boolean;
}

const MEDIA_LABEL: Record<AnalysisMediaType, string> = {
  imagem: "imagem",
  audio: "audio",
  video: "video",
  pdf: "PDF",
};

export default function MediaEvidenceSelector({
  caseId,
  fileType,
  selectedId,
  selectionSource = "original",
  onSelect,
  radioName = "media-evidence",
  title = "Selecione a evidência",
  excludeDerivatives = false,
}: MediaEvidenceSelectorProps) {
  const [evidences, setEvidences] = useState<Evidence[]>([]);
  const [derivatives, setDerivatives] = useState<Evidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPeritusPath, setSelectedPeritusPath] = useState<string | null>(null);
  const [resolvingPeritus, setResolvingPeritus] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([listCaseEvidences(caseId), listCaseDerivatives(caseId)])
      .then(([evs, derivs]) => {
        if (cancelled) return;
        setEvidences(filterForensicAuthEvidences(evs).filter((e) => e.file_type === fileType));
        setDerivatives(derivs.filter((e) => e.file_type === fileType));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, fileType]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedPeritusPath(null);
    }
  }, [selectedId]);

  function handleSelectVa(id: string, source: "original" | "derivative") {
    setSelectedPeritusPath(null);
    onSelect(id, source);
  }

  async function handleSelectPeritus(path: string) {
    setResolvingPeritus(true);
    try {
      const resolved = await resolvePeritusFileForAnalysis(caseId, path);
      setSelectedPeritusPath(path);
      onSelect(resolved.evidence_id, "original");
    } finally {
      setResolvingPeritus(false);
    }
  }

  const showDerivatives = !excludeDerivatives;
  const vaSelectedId = selectedPeritusPath ? null : selectedId;
  const vaSelectionSource = selectedPeritusPath ? "original" : selectionSource;
  const typeLabel = MEDIA_LABEL[fileType] || fileType;

  return (
    <div style={{ marginBottom: "1rem" }}>
      <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 600 }}>
        {title}
      </h3>
      {loading ? (
        <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Carregando…</p>
      ) : (
        <SelectableEvidenceList
          sectionId={`media-${fileType}-${caseId}`}
          items={evidences}
          selectedId={vaSelectedId}
          selectionSource={vaSelectionSource}
          source="original"
          onSelect={handleSelectVa}
          radioName={radioName}
          emptyMessage={`Nenhuma evidência de ${typeLabel} neste caso.`}
        />
      )}

      <PeritusAnalysisFileSection
        caseId={caseId}
        fileType={fileType}
        selectedPath={selectedPeritusPath}
        onSelect={handleSelectPeritus}
        radioName={`${radioName}-peritus`}
        resolving={resolvingPeritus}
      />

      <GlobalReferencesSelector
        caseId={caseId}
        fileType={fileType}
        selectedId={vaSelectedId}
        onSelect={(id) => handleSelectVa(id, "original")}
        radioName={`${radioName}-global-reference`}
      />

      {showDerivatives && derivatives.length > 0 && (
        <CollapsibleSection
          title="Derivados (evidencias derivadas)"
          subtitle={`${typeLabel} derivados registrados na cadeia podem ser analisados da mesma forma.`}
          badgeCount={derivatives.length}
          defaultOpen={false}
          forceOpen={vaSelectionSource === "derivative" && !!vaSelectedId}
        >
          {loading ? (
            <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Carregando...</p>
          ) : (
            <SelectableEvidenceList
              sectionId={`media-${fileType}-derivatives-${caseId}`}
              items={derivatives}
              selectedId={vaSelectedId}
              selectionSource={vaSelectionSource}
              source="derivative"
              onSelect={handleSelectVa}
              radioName={`${radioName}-derivative`}
              badge="derivado"
              emptyMessage={`Nenhum derivado de ${typeLabel} neste caso.`}
            />
          )}
        </CollapsibleSection>
      )}
    </div>
  );
}
