import { useEffect, useMemo, useState } from "react";
import CollapsibleSection from "@/components/CollapsibleSection";
import FileListSortToggle from "@/components/FileListSortToggle";
import FileListViewHeader from "@/components/FileListViewHeader";
import SelectableEvidenceList from "@/components/SelectableEvidenceList";
import { useFileListSortMode } from "@/lib/fileListSortMode";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import { listCaseReferences, type GlobalReferenceGroup } from "@/services/evidence";

interface Props {
  caseId: string;
  fileType: "imagem" | "video" | "audio" | "pdf";
  selectedId: string | null;
  onSelect: (id: string) => void;
  radioName?: string;
  title?: string;
}

export default function GlobalReferencesSelector({
  caseId,
  fileType,
  selectedId,
  onSelect,
  radioName = "global-reference",
  title = "Referencias globais",
}: Props) {
  const [groups, setGroups] = useState<GlobalReferenceGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useFileListViewMode();
  const [sortMode, setSortMode] = useFileListSortMode();

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    listCaseReferences(caseId)
      .then((data) => {
        setGroups(data.global_groups.filter((g) => g.reference_type === fileType));
      })
      .finally(() => setLoading(false));
  }, [caseId, fileType]);

  const totalCount = useMemo(
    () => groups.reduce((count, group) => count + group.files.length, 0),
    [groups],
  );

  const hasSelectedReference = useMemo(
    () => groups.some((group) => group.files.some((file) => file.id === selectedId)),
    [groups, selectedId],
  );

  if (loading) return null;
  if (groups.length === 0) return null;

  return (
    <CollapsibleSection
      title={title}
      subtitle={`Arquivos de referencia ${fileType} enviados na aba Referencias, agrupados por rotulo.`}
      badgeCount={totalCount}
      defaultOpen={false}
      forceOpen={hasSelectedReference}
    >
      <FileListViewHeader
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        trailing={<FileListSortToggle mode={sortMode} onChange={setSortMode} />}
      />
      {groups.map((group) => {
        const groupHasSelection = group.files.some((file) => file.id === selectedId);
        return (
          <CollapsibleSection
            key={`${group.reference_type}-${group.group_label}`}
            title={group.display_label}
            badgeCount={group.files.length}
            defaultOpen={false}
            forceOpen={groupHasSelection}
          >
            <SelectableEvidenceList
              sectionId={`global-refs-${fileType}-${caseId}-${group.group_label}`}
              items={group.files}
              selectedId={selectedId}
              selectionSource="original"
              source="original"
              onSelect={onSelect}
              radioName={radioName}
              badge="referencia"
              showToggle={false}
              emptyMessage={`Nenhum arquivo no grupo ${group.group_label}.`}
            />
          </CollapsibleSection>
        );
      })}
    </CollapsibleSection>
  );
}
