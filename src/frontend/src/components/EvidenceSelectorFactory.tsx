import ImageEvidenceSelector, {
  type ImageEvidenceSelectorProps,
} from "@/components/ImageEvidenceSelector";
import AudioEvidenceSelector, {
  type AudioEvidenceSelectorProps,
} from "@/components/AudioEvidenceSelector";
import MediaEvidenceSelector, {
  type MediaEvidenceSelectorProps,
} from "@/components/MediaEvidenceSelector";
import type { AnalysisMediaType } from "@/lib/peritusAnalysis";

export type MediaType = "imagem" | "audio" | "video" | "pdf";

interface BaseFactoryProps {
  caseId: string;
  selectedId: string | null;
}

export type EvidenceSelectorFactoryProps =
  | ({ mediaType: "imagem" } & BaseFactoryProps & Omit<ImageEvidenceSelectorProps, "caseId" | "selectedId" | "onSelect"> & {
        onSelect: (id: string, source: "original" | "derivative") => void;
      })
  | ({ mediaType: "audio" } & BaseFactoryProps & Omit<AudioEvidenceSelectorProps, "caseId" | "selectedId" | "onSelect"> & {
        onSelect: (id: string, source: "original" | "derivative", filename?: string) => void;
      })
  | ({ mediaType: "video" | "pdf" } & BaseFactoryProps & Omit<MediaEvidenceSelectorProps, "caseId" | "selectedId" | "onSelect" | "fileType"> & {
        onSelect: (id: string, source: "original" | "derivative") => void;
      });

export function getMediaFileType(mediaType: MediaType): AnalysisMediaType {
  switch (mediaType) {
    case "video":
      return "video";
    case "pdf":
      return "pdf";
    default:
      return "imagem";
  }
}

/**
 * Factory que instancia o seletor de evidência correto por tipo de mídia.
 * Preserva tipagem forte das props específicas de cada seletor.
 */
export default function EvidenceSelectorFactory(props: EvidenceSelectorFactoryProps) {
  const { mediaType, onSelect, caseId, selectedId, ...rest } = props;

  if (mediaType === "imagem") {
    const imageProps = rest as Omit<ImageEvidenceSelectorProps, "caseId" | "selectedId" | "onSelect">;
    return (
      <ImageEvidenceSelector
        {...imageProps}
        caseId={caseId}
        selectedId={selectedId}
        onSelect={onSelect as ImageEvidenceSelectorProps["onSelect"]}
      />
    );
  }

  if (mediaType === "audio") {
    const audioProps = rest as Omit<AudioEvidenceSelectorProps, "caseId" | "selectedId" | "onSelect">;
    return (
      <AudioEvidenceSelector
        {...audioProps}
        caseId={caseId}
        selectedId={selectedId}
        onSelect={onSelect as AudioEvidenceSelectorProps["onSelect"]}
      />
    );
  }

  const mediaProps = rest as Omit<MediaEvidenceSelectorProps, "caseId" | "selectedId" | "onSelect" | "fileType">;
  return (
    <MediaEvidenceSelector
      {...mediaProps}
      caseId={caseId}
      selectedId={selectedId}
      fileType={getMediaFileType(mediaType)}
      onSelect={onSelect as MediaEvidenceSelectorProps["onSelect"]}
    />
  );
}
