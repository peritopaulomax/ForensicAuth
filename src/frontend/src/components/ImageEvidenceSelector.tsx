import { useEffect, useRef, useState } from "react";
import { listCaseEvidences, listCaseDerivatives } from "@/services/evidence";
import CollapsibleSection from "@/components/CollapsibleSection";
import SelectableEvidenceList from "@/components/SelectableEvidenceList";
import PeritusAnalysisFileSection from "@/components/PeritusAnalysisFileSection";
import { resolvePeritusFileForAnalysis } from "@/services/peritus";
import { isVisualImageEvidence } from "@/lib/fileTypeIcons";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import type { Evidence } from "@/types/api";

export interface ImageEvidenceSelectorProps {
  caseId: string;
  selectedId: string | null;
  selectionSource: "original" | "derivative";
  onSelect: (id: string, source: "original" | "derivative") => void;
  /** Exclui imagens marcadas como referencia (ex.: DCT modo referencia) */
  excludeReferences?: boolean;
  /** Exclui fingerprints PRNU salvas como derivados */
  excludePrnuFingerprints?: boolean;
  /** Nao lista derivados de imagem (apenas evidencias originais do caso) */
  excludeDerivatives?: boolean;
  onLoaded?: (originals: Evidence[], derivatives: Evidence[]) => void;
  radioNamePrefix?: string;
}

export default function ImageEvidenceSelector({
  caseId,
  selectedId,
  selectionSource,
  onSelect,
  excludeReferences = false,
  excludePrnuFingerprints = true,
  excludeDerivatives = false,
  onLoaded,
  radioNamePrefix = "image-selector",
}: ImageEvidenceSelectorProps) {
  const [evidences, setEvidences] = useState<Evidence[]>([]);
  const [derivatives, setDerivatives] = useState<Evidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPeritusPath, setSelectedPeritusPath] = useState<string | null>(null);
  const [resolvingPeritus, setResolvingPeritus] = useState(false);
  const onLoadedRef = useRef(onLoaded);
  onLoadedRef.current = onLoaded;

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([listCaseEvidences(caseId), listCaseDerivatives(caseId)])
      .then(([evs, derivs]) => {
        if (cancelled) return;
        let imageEvs = filterForensicAuthEvidences(evs).filter((e) => e.file_type === "imagem");
        if (excludeReferences) {
          imageEvs = imageEvs.filter((e) => {
            const m = e.extra_metadata || {};
            return !(m.is_reference || m.prnu_reference || m.reference === true);
          });
        }
        let imageDerivs = derivs.filter((e) =>
          isVisualImageEvidence(e.file_type, e.original_filename, e.mime_type),
        );
        if (excludePrnuFingerprints) {
          imageDerivs = imageDerivs.filter((e) => e.extra_metadata?.artifact_role !== "prnu_fingerprint");
        }
        setEvidences(imageEvs);
        setDerivatives(imageDerivs);
        onLoadedRef.current?.(imageEvs, imageDerivs);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, excludeReferences, excludePrnuFingerprints]);

  const showDerivatives = !excludeDerivatives;
  const showInitialLoading = loading && evidences.length === 0 && derivatives.length === 0;

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

  const vaSelectedId = selectedPeritusPath ? null : selectedId;
  const vaSelectionSource = selectedPeritusPath ? "original" : selectionSource;

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 600 }}>
        Selecione a evidencia
      </h3>
      {showInitialLoading ? (
        <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Carregando...</p>
      ) : (
        <SelectableEvidenceList
          sectionId={`image-selector-originals-${caseId}`}
          items={evidences}
          selectedId={vaSelectedId}
          selectionSource={vaSelectionSource}
          source="original"
          onSelect={handleSelectVa}
          radioName={`${radioNamePrefix}-evidence`}
          emptyMessage="Nenhuma evidencia de imagem neste caso."
        />
      )}

      <PeritusAnalysisFileSection
        caseId={caseId}
        fileType="imagem"
        selectedPath={selectedPeritusPath}
        onSelect={handleSelectPeritus}
        radioName={`${radioNamePrefix}-peritus`}
        resolving={resolvingPeritus}
      />

      {showDerivatives && (
        <CollapsibleSection
          title="Derivados (evidencias derivadas)"
          subtitle="Imagens derivadas registradas na cadeia podem ser analisadas da mesma forma."
          badgeCount={derivatives.length}
          defaultOpen={false}
          forceOpen={vaSelectionSource === "derivative" && !!vaSelectedId}
        >
          {showInitialLoading ? (
            <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Carregando...</p>
          ) : (
            <SelectableEvidenceList
              sectionId={`image-selector-derivatives-${caseId}`}
              items={derivatives}
              selectedId={vaSelectedId}
              selectionSource={vaSelectionSource}
              source="derivative"
              onSelect={handleSelectVa}
              radioName={`${radioNamePrefix}-derivative-evidence`}
              badge="derivado"
              emptyMessage="Nenhum derivado de imagem neste caso."
            />
          )}
        </CollapsibleSection>
      )}
    </div>
  );
}
