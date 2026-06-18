import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import JobArtifactImageThumb from "@/components/JobArtifactImageThumb";
import PdfExtractImageGrid from "@/components/PdfExtractImageGrid";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import FileListViewHeader from "@/components/FileListViewHeader";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import MediaEvidenceSelector from "@/components/MediaEvidenceSelector";
import { useForensicJob } from "@/hooks/useForensicJob";
import { saveDerivative } from "@/services/evidence";
import api from "@/services/api";
import { imageSelectorListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

interface ExtractedImage {
  id: string;
  filename: string;
  label: string;
  mime?: string;
  extraction?: string;
}

interface ExtractedVersion {
  id: string;
  filename: string;
  label: string;
}

type MetaTab = "metadata_report.txt" | "metadata.json";

const METADATA_SCROLL_HEIGHT = 380;
const INCREMENTAL_REPORT_HEIGHT = 220;

export default function PDFForensicExtractAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [images, setImages] = useState<ExtractedImage[]>([]);
  const [versions, setVersions] = useState<ExtractedVersion[]>([]);
  const [extractionReady, setExtractionReady] = useState(false);

  const [selectedImageIds, setSelectedImageIds] = useState<Set<string>>(new Set());
  const [previewImageId, setPreviewImageId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [metaTab, setMetaTab] = useState<MetaTab>("metadata_report.txt");

  const [imageViewMode, setImageViewMode] = useFileListViewMode();
  const [versionViewMode, setVersionViewMode] = useFileListViewMode();

  const [metaContent, setMetaContent] = useState("");
  const [metaLoading, setMetaLoading] = useState(false);
  const [incrementalReport, setIncrementalReport] = useState("");
  const [incMessage, setIncMessage] = useState("");

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [versionPreviewUrl, setVersionPreviewUrl] = useState<string | null>(null);
  const [savingDerivative, setSavingDerivative] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();

  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      if (versionPreviewUrl) URL.revokeObjectURL(versionPreviewUrl);
    },
    [previewUrl, versionPreviewUrl]
  );

  const clearAll = useCallback(() => {
    reset();
    setImages([]);
    setVersions([]);
    setExtractionReady(false);
    setSelectedImageIds(new Set());
    setPreviewImageId(null);
    setSelectedVersionId(null);
    setMetaTab("metadata_report.txt");
    setMetaContent("");
    setIncrementalReport("");
    setIncMessage("");
    setSaveMessage(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    if (versionPreviewUrl) URL.revokeObjectURL(versionPreviewUrl);
    setVersionPreviewUrl(null);
  }, [reset, previewUrl, versionPreviewUrl]);

  const loadMetaFile = useCallback(async (jobId: string, filename: MetaTab) => {
    setMetaLoading(true);
    try {
      const isJson = filename.endsWith(".json");
      const res = await api.get(`/analysis/${jobId}/result/file?filename=${filename}`, {
        responseType: isJson ? "json" : "text",
      });
      setMetaContent(isJson ? JSON.stringify(res.data, null, 2) : String(res.data));
    } catch {
      setMetaContent("(Nao foi possivel carregar este artefato.)");
    } finally {
      setMetaLoading(false);
    }
  }, []);

  async function loadManifest(jobId: string, jobResult: Record<string, unknown>) {
    const imageList: ExtractedImage[] = [];
    const rawImages = (jobResult.images_manifest as Array<Record<string, unknown>>) || [];
    for (const img of rawImages) {
      if (!img.filename) continue;
      imageList.push({
        id: String(img.filename),
        filename: String(img.filename),
        label: `Imagem xref ${img.xref} (${img.extraction || "?"})`,
        mime: String(img.mime || "image/jpeg"),
        extraction: String(img.extraction || ""),
      });
    }

    const versionList: ExtractedVersion[] = [];
    const rawVersions = (jobResult.version_files as Array<Record<string, string>>) || [];
    for (const v of rawVersions) {
      versionList.push({
        id: v.filename,
        filename: v.filename,
        label: `Versao incremental ${v.version_index}`,
      });
    }

    setImages(imageList);
    setVersions(versionList);
    setIncMessage(String(jobResult.incremental_message || ""));

    if (imageList.length > 0) {
      setSelectedImageIds(new Set(imageList.map((img) => img.id)));
      setPreviewImageId(imageList[0].id);
    }

    if (versionList.length > 0) {
      setSelectedVersionId(versionList[0].id);
    }

    try {
      const res = await api.get(`/analysis/${jobId}/result/file?filename=incremental_report.txt`, {
        responseType: "text",
      });
      setIncrementalReport(String(res.data));
    } catch {
      setIncrementalReport("");
    }

    setExtractionReady(true);
  }

  useEffect(() => {
    if (!currentJobId || !extractionReady) return;
    loadMetaFile(currentJobId, metaTab);
  }, [currentJobId, metaTab, extractionReady, loadMetaFile]);

  async function process() {
    if (!selectedId) return;
    clearAll();
    try {
      await runAnalysis(selectedId, "pdf_forensic_extract", {}, {
        onArtifactsLoaded: async (jobId, jobResult) => {
          await loadManifest(jobId, jobResult);
        },
      });
    } catch {
      /* hook */
    }
  }

  async function handleSaveSelectedImages() {
    if (!currentJobId || selectedImageIds.size === 0) return;
    const toSave = images.filter((img) => selectedImageIds.has(img.id));
    setSavingDerivative("__batch__");
    setSaveMessage(null);
    let ok = 0;
    for (const img of toSave) {
      try {
        await saveDerivative({
          job_id: currentJobId,
          artifact_filename: img.filename,
          label: `pdf_extract_image_${img.filename}`,
        });
        ok += 1;
      } catch {
        /* continue */
      }
    }
    setSavingDerivative(null);
    if (ok > 0) {
      setSaveMessage({
        type: "ok",
        text: `${ok} imagem(ns) salva(s) nos derivados do caso.`,
      });
    } else {
      setSaveMessage({ type: "err", text: "Nao foi possivel salvar as imagens selecionadas." });
    }
  }

  function toggleImage(id: string) {
    setSelectedImageIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSaveDerivative(artifactFilename: string, label: string) {
    if (!currentJobId) return;
    setSavingDerivative(artifactFilename);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: artifactFilename,
        label,
      });
      setSaveMessage({
        type: "ok",
        text: `${res.message} «${res.evidence.original_filename}». SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setSaveMessage({ type: "err", text: detail || "Erro ao salvar derivado" });
    } finally {
      setSavingDerivative(null);
    }
  }

  const previewImage = useMemo(
    () => images.find((f) => f.id === previewImageId) ?? null,
    [images, previewImageId]
  );

  useEffect(() => {
    if (!currentJobId || !previewImage) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
      return;
    }
    let cancelled = false;
    fetchImage(currentJobId, previewImage.filename).then((url) => {
      if (cancelled) {
        if (url) URL.revokeObjectURL(url);
        return;
      }
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(url);
    });
    return () => {
      cancelled = true;
    };
  }, [currentJobId, previewImage?.id, previewImage?.filename]);

  const selectedVersion = useMemo(
    () => versions.find((f) => f.id === selectedVersionId) ?? null,
    [versions, selectedVersionId]
  );

  useEffect(() => {
    if (!currentJobId || !selectedVersion) {
      if (versionPreviewUrl) URL.revokeObjectURL(versionPreviewUrl);
      setVersionPreviewUrl(null);
      return;
    }
    let cancelled = false;
    fetchImage(currentJobId, selectedVersion.filename).then((url) => {
      if (cancelled) {
        if (url) URL.revokeObjectURL(url);
        return;
      }
      if (versionPreviewUrl) URL.revokeObjectURL(versionPreviewUrl);
      setVersionPreviewUrl(url);
    });
    return () => {
      cancelled = true;
    };
  }, [currentJobId, selectedVersion?.id, selectedVersion?.filename]);

  const hasExtracted = extractionReady;

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="PDF — Extracao forense"
      subtitle="Imagens (JPEG stream bruto quando possivel), metadados completos e deteccao de versoes incrementais por %%EOF."
    >
      <AnalysisPanel title="Evidencia PDF">
        <MediaEvidenceSelector
          caseId={caseId}
          fileType="pdf"
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            clearAll();
          }}
          radioName="pdf-forensic-extract"
        />
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!selectedId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Extrair conteudo"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Resumo">
          <p style={{ margin: 0, fontSize: "0.88rem" }}>
            Imagens extraidas: {Number(result.image_count)} · Versoes incrementais:{" "}
            {Number(result.incremental_version_count)}
          </p>
          {incMessage && (
            <p style={{ margin: "0.5rem 0 0", fontSize: "0.82rem", color: "#6b7280" }}>{incMessage}</p>
          )}
        </AnalysisPanel>
      )}

      {hasExtracted && images.length > 0 && (
        <AnalysisPanel title="Imagens extraidas">
          <p style={hintStyle}>
            Marque uma ou mais imagens. Clique na miniatura ou no nome para visualizar.
          </p>
          <FileListViewHeader viewMode={imageViewMode} onViewModeChange={setImageViewMode}>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
              <button type="button" style={btnSmall} onClick={() => setSelectedImageIds(new Set(images.map((i) => i.id)))}>
                Marcar todas
              </button>
              <button type="button" style={btnSmall} onClick={() => setSelectedImageIds(new Set())}>
                Desmarcar
              </button>
              <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
                {selectedImageIds.size} de {images.length} selecionada(s)
              </span>
            </div>
          </FileListViewHeader>
          {imageViewMode === "grid" && currentJobId ? (
            <PdfExtractImageGrid
              jobId={currentJobId}
              items={images}
              fetchBlobUrl={fetchImage}
              selected={(item) => selectedImageIds.has(item.id)}
              onSelect={(item) => setPreviewImageId(item.id)}
              renderFooter={(item) => (
                <label
                  style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.75rem", cursor: "pointer" }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <input
                    type="checkbox"
                    checked={selectedImageIds.has(item.id)}
                    onChange={() => toggleImage(item.id)}
                  />
                  Selecionar
                </label>
              )}
              maxHeight={imageSelectorListMaxHeight}
            />
          ) : (
            <div style={{ ...scrollableListStyle, maxHeight: imageSelectorListMaxHeight }}>
              {images.map((f) => (
                <div
                  key={f.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "0.5rem",
                    background:
                      previewImageId === f.id ? "#dbeafe" : selectedImageIds.has(f.id) ? "#eff6ff" : "#fff",
                    borderRadius: 6,
                    marginBottom: 4,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedImageIds.has(f.id)}
                    onChange={() => toggleImage(f.id)}
                  />
                  {currentJobId && (
                    <JobArtifactImageThumb
                      jobId={currentJobId}
                      filename={f.filename}
                      fetchBlobUrl={fetchImage}
                      size={40}
                      alt={f.label}
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => setPreviewImageId(f.id)}
                    style={{
                      flex: 1,
                      textAlign: "left",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      fontSize: "0.85rem",
                      padding: 0,
                    }}
                  >
                    {f.label}
                  </button>
                </div>
              ))}
            </div>
          )}

          {previewImage && previewUrl && (
            <div style={{ marginTop: "1rem" }}>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.82rem", color: "#6b7280" }}>{previewImage.label}</p>
              <img
                src={previewUrl}
                alt={previewImage.label}
                style={{ maxWidth: "100%", maxHeight: 420, border: "1px solid #e5e7eb", borderRadius: 6 }}
              />
            </div>
          )}

          {selectedImageIds.size > 0 && (
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
              <button
                type="button"
                style={btnPrimary}
                disabled={!!savingDerivative}
                onClick={handleSaveSelectedImages}
              >
                {savingDerivative === "__batch__"
                  ? "Salvando…"
                  : `Salvar ${selectedImageIds.size} selecionada(s) em derivados`}
              </button>
              <button type="button" style={btnSecondary} onClick={() => navigate(`/cases/${caseId}?tab=derivados`)}>
                Abrir derivados
              </button>
            </div>
          )}
        </AnalysisPanel>
      )}

      {hasExtracted && (
        <AnalysisPanel title="Metadados">
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
            <MetaTabButton
              active={metaTab === "metadata_report.txt"}
              onClick={() => setMetaTab("metadata_report.txt")}
              label="Texto completo"
            />
            <MetaTabButton
              active={metaTab === "metadata.json"}
              onClick={() => setMetaTab("metadata.json")}
              label="JSON estruturado"
            />
          </div>
          <div style={metadataScrollBoxStyle}>
            <pre style={metadataPreStyle}>
              {metaLoading ? "Carregando…" : metaContent || "(sem conteudo)"}
            </pre>
          </div>
          <DerivativeActions
            artifactFilename={metaTab}
            label={`pdf_extract_${metaTab === "metadata.json" ? "metadata_json" : "metadata_txt"}`}
            saving={savingDerivative}
            onSave={handleSaveDerivative}
            onOpenDerivatives={() => navigate(`/cases/${caseId}?tab=derivados`)}
          />
        </AnalysisPanel>
      )}

      {hasExtracted && (versions.length > 0 || incrementalReport) && (
        <AnalysisPanel title="Versoes incrementais do PDF">
          {incMessage && (
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.82rem", color: "#6b7280" }}>{incMessage}</p>
          )}

          {versions.length > 0 && (
            <>
              <FileListViewHeader viewMode={versionViewMode} onViewModeChange={setVersionViewMode}>
                <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>{versions.length} versao(oes)</span>
              </FileListViewHeader>
              {versionViewMode === "grid" ? (
                <EvidenceFileGrid
                  items={versions.map((f) => ({
                    id: f.id,
                    original_filename: f.label,
                    file_type: "pdf",
                  }))}
                  selected={(item: { id: string }) => selectedVersionId === item.id}
                  onSelect={(item: { id: string }) => setSelectedVersionId(item.id)}
                  maxHeight={imageSelectorListMaxHeight}
                />
              ) : (
                <div style={{ ...scrollableListStyle, maxHeight: imageSelectorListMaxHeight }}>
                  {versions.map((f) => (
                    <label
                      key={f.id}
                      style={{
                        display: "flex",
                        gap: 8,
                        padding: "0.5rem",
                        cursor: "pointer",
                        background: selectedVersionId === f.id ? "#eff6ff" : "#fff",
                        borderRadius: 6,
                      }}
                    >
                      <input
                        type="radio"
                        name="extracted-version"
                        checked={selectedVersionId === f.id}
                        onChange={() => setSelectedVersionId(f.id)}
                      />
                      <span style={{ fontSize: "0.85rem" }}>{f.label}</span>
                    </label>
                  ))}
                </div>
              )}

              {selectedVersion && versionPreviewUrl && (
                <div style={{ marginTop: "0.75rem" }}>
                  <p style={{ fontSize: "0.85rem", margin: "0 0 0.5rem" }}>
                    {selectedVersion.label}:{" "}
                    <a href={versionPreviewUrl} target="_blank" rel="noreferrer">
                      abrir PDF da versao
                    </a>
                  </p>
                  <DerivativeActions
                    artifactFilename={selectedVersion.filename}
                    label={`pdf_extract_version_${selectedVersion.filename}`}
                    saving={savingDerivative}
                    onSave={handleSaveDerivative}
                    onOpenDerivatives={() => navigate(`/cases/${caseId}?tab=derivados`)}
                  />
                </div>
              )}
            </>
          )}

          {incrementalReport && (
            <div style={{ marginTop: versions.length > 0 ? "1rem" : 0 }}>
              <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.9rem", color: "#374151" }}>
                Relatorio de versoes incrementais
              </h4>
              <div style={{ ...metadataScrollBoxStyle, maxHeight: INCREMENTAL_REPORT_HEIGHT }}>
                <pre style={metadataPreStyle}>{incrementalReport}</pre>
              </div>
              <DerivativeActions
                artifactFilename="incremental_report.txt"
                label="pdf_extract_incremental_report"
                saving={savingDerivative}
                onSave={handleSaveDerivative}
                onOpenDerivatives={() => navigate(`/cases/${caseId}?tab=derivados`)}
              />
            </div>
          )}
        </AnalysisPanel>
      )}

      {hasExtracted && images.length === 0 && (
        <AnalysisPanel title="Imagens extraidas">
          <p style={{ margin: 0, fontSize: "0.85rem", color: "#9ca3af" }}>
            Nenhuma imagem embutida encontrada neste PDF.
          </p>
        </AnalysisPanel>
      )}

      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
    </AnalysisPageShell>
  );
}

function MetaTabButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: "0.4rem 0.85rem",
        background: active ? "#1a1a2e" : "#f3f4f6",
        color: active ? "#fff" : "#374151",
        border: active ? "none" : "1px solid #d1d5db",
        borderRadius: 6,
        cursor: "pointer",
        fontSize: "0.82rem",
        fontWeight: active ? 600 : 500,
      }}
    >
      {label}
    </button>
  );
}

function DerivativeActions({
  artifactFilename,
  label,
  saving,
  onSave,
  onOpenDerivatives,
}: {
  artifactFilename: string;
  label: string;
  saving: string | null;
  onSave: (filename: string, label: string) => void;
  onOpenDerivatives: () => void;
}) {
  return (
    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
      <button
        type="button"
        style={btnPrimary}
        disabled={!!saving}
        onClick={() => onSave(artifactFilename, label)}
      >
        {saving === artifactFilename ? "Salvando…" : "Salvar em derivados"}
      </button>
      <button type="button" style={btnSecondary} onClick={onOpenDerivatives}>
        Abrir derivados
      </button>
    </div>
  );
}

const hintStyle = { fontSize: "0.82rem", color: "#6b7280", marginTop: 0, marginBottom: "0.5rem" } as const;

const metadataScrollBoxStyle: CSSProperties = {
  ...scrollableListStyle,
  maxHeight: METADATA_SCROLL_HEIGHT,
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  background: "#f9fafb",
};

const metadataPreStyle: CSSProperties = {
  margin: 0,
  padding: "0.85rem 1rem",
  fontSize: "0.76rem",
  lineHeight: 1.45,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const btnPrimary = {
  padding: "0.45rem 0.9rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
} as const;

const btnSecondary = {
  padding: "0.45rem 0.9rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
} as const;

const btnSmall = {
  padding: "0.35rem 0.7rem",
  background: "#f3f4f6",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.8rem",
} as const;
