import { useEffect, useState } from "react";
import { getCase } from "@/services/cases";
import { listPeritusFiles, type PeritusFileEntry } from "@/services/peritus";
import { filterPeritusAnalyzable, type AnalysisMediaType } from "@/lib/peritusAnalysis";

export function usePeritusAnalyzableFiles(
  caseId: string | undefined,
  fileType?: AnalysisMediaType
) {
  const [files, setFiles] = useState<PeritusFileEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!caseId) {
      setFiles([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getCase(caseId)
      .then((c) => {
        if (c.storage_mode !== "peritus") {
          if (!cancelled) setFiles([]);
          return;
        }
        return listPeritusFiles(caseId).then((listing) => {
          if (!cancelled) {
            setFiles(filterPeritusAnalyzable(listing.files, fileType));
          }
        });
      })
      .catch(() => {
        if (!cancelled) setFiles([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, fileType]);

  return { files, loading, hasPeritusFiles: files.length > 0 };
}
