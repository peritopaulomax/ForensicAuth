/**
 * Viewer genérico de artefatos para técnicas scaffolded (simple/medium/ensemble).
 *
 * Roles → UI (ver config/artifactRoles.ts):
 * - original/input → painel esquerdo
 * - heatmap/overlay/mask/score_map/confidence/detection/other(+imagem) → abas direita
 * - interactive/report → abas HTML
 * - json/txt/download → apenas **Salvar em derivados** (sem download direto do job)
 *
 * Carregamento de blobs só reage a jobId/result/filenames estáveis.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import SyncedImagePairViewer, { type SyncedImagePairViewerHandle } from "@/components/SyncedImagePairViewer";
import PlotlyHtmlFrame from "@/components/PlotlyHtmlFrame";
import type { ArtifactManifestItem } from "@/config/techniqueRegistry";
import {
  DOWNLOAD_ROLES,
  INTERACTIVE_ROLES,
  LEFT_IMAGE_ROLES,
  RIGHT_IMAGE_ROLES,
  isHtmlFilename,
  isImageFilename,
  normalizeArtifactRole,
  type ArtifactRole,
} from "@/config/artifactRoles";

export interface TechniqueArtifactViewerProps {
  evidenceId: string | null;
  jobId: string | null;
  result: Record<string, unknown> | null;
  manifest: ArtifactManifestItem[];
  fetchImage: (jobId: string, filename: string) => Promise<string | null>;
  fetchBlobUrl?: (jobId: string, filename: string, mime?: string) => Promise<string | null>;
  saving?: boolean;
  onSave?: (filename: string, label: string) => void;
}

const btnSecondary: React.CSSProperties = {
  padding: "0.45rem 0.9rem",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.82rem",
};

function tabStyle(active: boolean): React.CSSProperties {
  return {
    padding: "0.4rem 0.85rem",
    borderRadius: 6,
    border: `1px solid ${active ? "#0369a1" : "#d1d5db"}`,
    background: active ? "#e0f2fe" : "#fff",
    cursor: "pointer",
    fontSize: "0.82rem",
  };
}

function revokeBlobMap(map: Record<string, string | null>) {
  for (const u of Object.values(map)) {
    if (u?.startsWith("blob:")) URL.revokeObjectURL(u);
  }
}

function roleOf(item: ArtifactManifestItem): ArtifactRole {
  return normalizeArtifactRole(item.role);
}

export default function TechniqueArtifactViewer({
  evidenceId,
  jobId,
  result,
  manifest,
  fetchImage,
  fetchBlobUrl,
  saving = false,
  onSave,
}: TechniqueArtifactViewerProps) {
  const viewerRef = useRef<SyncedImagePairViewerHandle>(null);
  const urlsRef = useRef<Record<string, string | null>>({});
  const htmlUrlsRef = useRef<Record<string, string | null>>({});
  const [urls, setUrls] = useState<Record<string, string | null>>({});
  const [htmlUrls, setHtmlUrls] = useState<Record<string, string | null>>({});
  const [viewKey, setViewKey] = useState<string | null>(null);
  const [htmlKey, setHtmlKey] = useState<string | null>(null);

  const originalItem = useMemo(
    () =>
      manifest.find((m) => LEFT_IMAGE_ROLES.has(roleOf(m)) && !isHtmlFilename(m.filename)) ?? null,
    [manifest],
  );

  const rightItems = useMemo(
    () =>
      manifest.filter((m) => {
        if (isHtmlFilename(m.filename)) return false;
        const r = roleOf(m);
        if (LEFT_IMAGE_ROLES.has(r)) return false;
        if (DOWNLOAD_ROLES.has(r)) return false;
        if (INTERACTIVE_ROLES.has(r)) return false;
        if (RIGHT_IMAGE_ROLES.has(r)) return true;
        return isImageFilename(m.filename);
      }),
    [manifest],
  );

  const interactiveItems = useMemo(
    () =>
      manifest.filter(
        (m) => INTERACTIVE_ROLES.has(roleOf(m)) || isHtmlFilename(m.filename),
      ),
    [manifest],
  );

  /** Artefatos não-imagem/HTML: só entram no fluxo Salvar → derivados (custódia). */
  const savableFileItems = useMemo(
    () =>
      manifest.filter((m) => {
        const r = roleOf(m);
        if (DOWNLOAD_ROLES.has(r)) return true;
        if (r === "other" && !isImageFilename(m.filename) && !isHtmlFilename(m.filename)) {
          return true;
        }
        return false;
      }),
    [manifest],
  );

  const artifactKey = useMemo(() => {
    const names = [
      originalItem?.filename ?? "",
      ...rightItems.map((i) => i.filename),
      ...interactiveItems.map((i) => i.filename),
      ...savableFileItems.map((i) => i.filename),
    ];
    return names.join("|");
  }, [originalItem, rightItems, interactiveItems, savableFileItems]);

  useEffect(() => {
    return () => {
      revokeBlobMap(urlsRef.current);
      revokeBlobMap(htmlUrlsRef.current);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!jobId || !result) {
        revokeBlobMap(urlsRef.current);
        urlsRef.current = {};
        setUrls({});
        revokeBlobMap(htmlUrlsRef.current);
        htmlUrlsRef.current = {};
        setHtmlUrls({});
        setViewKey(null);
        setHtmlKey(null);
        return;
      }

      const next: Record<string, string | null> = {};
      if (originalItem) {
        next[originalItem.filename] = await fetchImage(jobId, originalItem.filename);
      } else if (evidenceId && rightItems.length > 0) {
        // Só usa a evidência como painel esquerdo quando há mapa/resultado à direita.
        // URL /api/.../file sem token no <img> quebra (ícone + alt "Resultado") —
        // técnicas só com txt/json (ex. ensemble) não devem renderizar imagem aqui.
        next.__evidence__ = `/api/v1/evidences/${evidenceId}/file`;
      }

      for (const item of rightItems) {
        next[item.filename] = await fetchImage(jobId, item.filename);
      }

      const nextHtml: Record<string, string | null> = {};
      if (fetchBlobUrl) {
        for (const item of interactiveItems) {
          nextHtml[item.filename] = await fetchBlobUrl(jobId, item.filename, "text/html");
        }
      }

      if (cancelled) {
        revokeBlobMap(next);
        revokeBlobMap(nextHtml);
        return;
      }

      revokeBlobMap(urlsRef.current);
      urlsRef.current = next;
      setUrls(next);

      revokeBlobMap(htmlUrlsRef.current);
      htmlUrlsRef.current = nextHtml;
      setHtmlUrls(nextHtml);

      setViewKey((prev) => {
        if (prev && rightItems.some((i) => i.filename === prev)) return prev;
        return rightItems[0]?.filename ?? null;
      });
      setHtmlKey((prev) => {
        if (prev && interactiveItems.some((i) => i.filename === prev)) return prev;
        return interactiveItems[0]?.filename ?? null;
      });
      viewerRef.current?.resetZoom();
    }

    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- artifactKey resumes filenames
  }, [jobId, result, evidenceId, artifactKey, fetchImage, fetchBlobUrl]);

  if (!result) return null;

  const leftSrc =
    (originalItem ? urls[originalItem.filename] : null) || urls.__evidence__ || null;
  const activeRight = rightItems.find((m) => m.filename === viewKey) ?? rightItems[0];
  const rightSrc = activeRight ? urls[activeRight.filename] : null;
  const activeHtml = interactiveItems.find((m) => m.filename === htmlKey) ?? interactiveItems[0];
  const activeHtmlUrl = activeHtml ? htmlUrls[activeHtml.filename] : null;

  const saveItems = manifest.filter((m) => m.filename);
  const showSave = Boolean(jobId && onSave && saveItems.length);

  return (
    <div>
      {rightItems.length > 1 && (
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
          {rightItems.map((item) => (
            <button
              key={item.filename}
              type="button"
              onClick={() => setViewKey(item.filename)}
              style={tabStyle(viewKey === item.filename)}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {leftSrc && rightSrc && (
        <SyncedImagePairViewer
          ref={viewerRef}
          leftSrc={leftSrc}
          rightSrc={rightSrc}
          leftLabel={originalItem?.label || "Original"}
          rightLabel={activeRight?.label || "Resultado"}
        />
      )}

      {/* Só imagem isolada se veio do manifesto (fetchImage/auth); não do fallback de evidência. */}
      {!rightSrc && leftSrc && originalItem && (
        <img
          src={leftSrc}
          alt={originalItem.label || "Original"}
          style={{ maxWidth: "100%", borderRadius: 8, border: "1px solid #e5e7eb" }}
        />
      )}

      {!leftSrc && rightSrc && (
        <img
          src={rightSrc}
          alt={activeRight?.label || "Mapa"}
          style={{ maxWidth: "100%", borderRadius: 8, border: "1px solid #e5e7eb" }}
        />
      )}

      {interactiveItems.length > 0 && (
        <div style={{ marginTop: leftSrc || rightSrc ? "1rem" : 0 }}>
          {interactiveItems.length > 1 && (
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
              {interactiveItems.map((item) => (
                <button
                  key={item.filename}
                  type="button"
                  onClick={() => setHtmlKey(item.filename)}
                  style={tabStyle(htmlKey === item.filename)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          )}
          {activeHtmlUrl && (
            <PlotlyHtmlFrame
              url={activeHtmlUrl}
              title={activeHtml?.label || "Relatório interativo"}
              height={560}
            />
          )}
        </div>
      )}

      {showSave && (
        <div
          style={{
            marginTop: "1rem",
            padding: "0.75rem 1rem",
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            background: "#f9fafb",
          }}
        >
          <div style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.35rem", color: "#374151" }}>
            Salvar em derivados
          </div>
          <p style={{ margin: "0 0 0.5rem", fontSize: "0.75rem", color: "#6b7280" }}>
            Artefatos do job não são baixados diretamente — salve como derivado para registrar na cadeia de
            custódia; o download fica a partir do derivado.
          </p>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {saveItems.map((m) => (
              <button
                key={m.filename}
                type="button"
                disabled={saving}
                onClick={() => onSave?.(m.filename, m.label)}
                style={btnSecondary}
              >
                Salvar {m.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
