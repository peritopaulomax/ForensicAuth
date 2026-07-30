import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useNavigate, useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import { AnalysisPanel, ProcessButton } from "@/components/AnalysisPageShell";
import JobArtifactImageThumb from "@/components/JobArtifactImageThumb";
import PdfExtractImageGrid from "@/components/PdfExtractImageGrid";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import FileListViewHeader from "@/components/FileListViewHeader";
import MarkdownReportView from "@/components/MarkdownReportView";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";
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
/** UI view for signatures panel (maps to on-disk artifacts). */
type SigView = "relatorio" | "fonte" | "json";

const METADATA_SCROLL_HEIGHT = 380;
const INCREMENTAL_REPORT_HEIGHT = 220;
const SIGNATURES_SCROLL_HEIGHT = 520;

function sigArtifactFilename(view: SigView): "signatures_report.txt" | "signatures.json" {
  return view === "json" ? "signatures.json" : "signatures_report.txt";
}

export default function PDFForensicExtractAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();

  const [images, setImages] = useState<ExtractedImage[]>([]);
  const [versions, setVersions] = useState<ExtractedVersion[]>([]);
  const [extractionReady, setExtractionReady] = useState(false);

  const [selectedImageIds, setSelectedImageIds] = useState<Set<string>>(new Set());
  const [previewImageId, setPreviewImageId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [metaTab, setMetaTab] = useState<MetaTab>("metadata_report.txt");
  const [sigView, setSigView] = useState<SigView>("relatorio");

  const [imageViewMode, setImageViewMode] = useFileListViewMode();
  const [versionViewMode, setVersionViewMode] = useFileListViewMode();

  const [metaContent, setMetaContent] = useState("");
  const [metaLoading, setMetaLoading] = useState(false);
  const [sigContent, setSigContent] = useState("");
  const [sigLoading, setSigLoading] = useState(false);
  const [incrementalReport, setIncrementalReport] = useState("");
  const [incMessage, setIncMessage] = useState("");
  const [sigMessage, setSigMessage] = useState("");
  const [signatureCount, setSignatureCount] = useState(0);
  const [pdfSigned, setPdfSigned] = useState(false);
  const [sigHeadline, setSigHeadline] = useState("");
  const [sigPadesLevel, setSigPadesLevel] = useState("");
  const [sigDssPresent, setSigDssPresent] = useState(false);
  const [sigVerdict, setSigVerdict] = useState<Record<string, string> | null>(null);
  const [sigFindingsSummary, setSigFindingsSummary] = useState<Record<string, number> | null>(null);

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [versionPreviewUrl, setVersionPreviewUrl] = useState<string | null>(null);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { status: runtimeStatus } = useTechniqueRuntime("pdf_forensic_extract");

  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

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
    setSigView("relatorio");
    setMetaContent("");
    setSigContent("");
    setIncrementalReport("");
    setIncMessage("");
    setSigMessage("");
    setSignatureCount(0);
    setPdfSigned(false);
    setSigHeadline("");
    setSigPadesLevel("");
    setSigDssPresent(false);
    setSigVerdict(null);
    setSigFindingsSummary(null);
    clearMessage();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    if (versionPreviewUrl) URL.revokeObjectURL(versionPreviewUrl);
    setVersionPreviewUrl(null);
  }, [reset, clearMessage, previewUrl, versionPreviewUrl]);

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

  const loadSigFile = useCallback(async (jobId: string, view: SigView) => {
    setSigLoading(true);
    try {
      const filename = sigArtifactFilename(view);
      const isJson = filename.endsWith(".json");
      const res = await api.get(`/analysis/${jobId}/result/file?filename=${filename}`, {
        responseType: isJson ? "json" : "text",
      });
      setSigContent(isJson ? JSON.stringify(res.data, null, 2) : String(res.data));
    } catch {
      setSigContent("(Nao foi possivel carregar este artefato.)");
    } finally {
      setSigLoading(false);
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
    setSigMessage(String(jobResult.signatures_message || ""));
    setSignatureCount(Number(jobResult.signature_count || 0));
    setPdfSigned(Boolean(jobResult.pdf_signed));
    setSigHeadline(String(jobResult.signatures_headline || ""));
    setSigPadesLevel(String(jobResult.signatures_pades_level || ""));
    setSigDssPresent(Boolean(jobResult.signatures_dss_present));
    setSigVerdict(
      jobResult.signatures_verdict && typeof jobResult.signatures_verdict === "object"
        ? (jobResult.signatures_verdict as Record<string, string>)
        : null
    );
    setSigFindingsSummary(
      jobResult.signatures_findings_summary &&
        typeof jobResult.signatures_findings_summary === "object"
        ? (jobResult.signatures_findings_summary as Record<string, number>)
        : null
    );

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

  useEffect(() => {
    if (!currentJobId || !extractionReady) return;
    loadSigFile(currentJobId, sigView);
  }, [currentJobId, sigView, extractionReady, loadSigFile]);

  const applyEvidence = useCallback(
    (_id: string) => {
      clearAll();
    },
    [clearAll]
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId!, applyEvidence);

  async function process() {
    if (!evidenceId || !runtimeOk) return;
    clearAll();
    try {
      await runAnalysis(evidenceId, "pdf_forensic_extract", {}, {
        onArtifactsLoaded: async (jobId, jobResult) => {
          await loadManifest(jobId, jobResult);
        },
      });
    } catch {
    }
  }

  async function handleSaveSelectedImages() {
    if (!currentJobId || selectedImageIds.size === 0) return;
    const toSave = images.filter((img) => selectedImageIds.has(img.id));
    let ok = 0;
    for (const img of toSave) {
      const stem = img.filename.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") || img.id;
      const done = await save(currentJobId, img.filename, `pdf_extract_${stem}`);
      if (done) ok += 1;
    }
    if (ok > 0) {
      
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

  const parametersPanel = (
    <>
      <div style={{ marginTop: "1rem" }}>
        <ProcessButton
          onClick={process}
          disabled={!evidenceId || runtimeOk === false}
          running={running}
          progress={progress}
          progressLabel={progressLabel}
          label="Extrair conteudo"
        />
      </div>
    </>
  );

  const resultPanel = (
    <>
      {result && (
        <>
          <p style={{ margin: 0, fontSize: "0.88rem" }}>
            Imagens extraidas: {Number(result.image_count)} · Versoes incrementais:{" "}
            {Number(result.incremental_version_count)} · Assinaturas:{" "}
            {Number(result.signature_count)}
            {result.pdf_signed ? " (PDF assinado)" : ""}
          </p>
          {incMessage && (
            <p style={{ margin: "0.5rem 0 0", fontSize: "0.82rem", color: "#6b7280" }}>{incMessage}</p>
          )}
          {sigMessage && (
            <p style={{ margin: "0.35rem 0 0", fontSize: "0.82rem", color: "#6b7280" }}>{sigMessage}</p>
          )}
        </>
      )}
    </>
  );

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="pdf_forensic_extract"
      mediaType="pdf"
      embedded={embedded}
      evidenceId={evidenceId}
      selectionSource={selectionSource}
      onSelectEvidence={onSelectEvidence}
      showEvidencePicker={showEvidencePicker}
      running={running}
      error={error}
      progress={progress}
      progressLabel={progressLabel}
      saveMessage={saveMessage}
      runtimeOk={runtimeOk}
      runtimeReason={runtimeReason}
      parametersPanel={parametersPanel}
      resultPanel={resultPanel || undefined}
    >
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
                disabled={!!saving}
                onClick={handleSaveSelectedImages}
              >
                {saving ? "Salvando…" : `Salvar ${selectedImageIds.size} selecionada(s) em derivados`}
              </button>
              <button type="button" style={btnSecondary} onClick={() => navigate(`/cases/${caseId}?tab=derivados`)}>
                Abrir derivados
              </button>
            </div>
          )}
        </AnalysisPanel>
      )}

      {hasExtracted && (
        <AnalysisPanel title="Assinaturas digitais">
          <p style={hintStyle}>
            {pdfSigned
              ? `${signatureCount} assinatura(s) analisada(s) com pdfsig_forense (PAdES/ICP). Relatório abaixo, não substitui validar.iti.gov.br.`
              : "Nenhuma assinatura digital embutida neste PDF."}
          </p>
          {sigMessage && (
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.82rem", color: "#6b7280" }}>{sigMessage}</p>
          )}
          {pdfSigned && sigHeadline && (
            <div
              style={{
                marginBottom: "0.85rem",
                padding: "0.75rem 0.9rem",
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 6,
                fontSize: "0.88rem",
                lineHeight: 1.45,
                color: "#1e293b",
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: "0.35rem" }}>Leitura rapida</div>
              <div>{sigHeadline}</div>
              <div style={{ marginTop: "0.55rem", display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                {sigPadesLevel && (
                  <span style={sigChipStyle}>PAdES: {sigPadesLevel}</span>
                )}
                <span style={sigChipStyle}>DSS: {sigDssPresent ? "presente" : "ausente"}</span>
                {sigFindingsSummary && (
                  <span style={sigChipStyle}>
                    Achados: {sigFindingsSummary.CRITICO || sigFindingsSummary.error || 0} crítico(s),{" "}
                    {sigFindingsSummary.ALERTA || sigFindingsSummary.warning || 0} alerta(s),{" "}
                    {sigFindingsSummary.ATENCAO || 0} atencao
                  </span>
                )}
              </div>
              {sigVerdict && (
                <ul style={{ margin: "0.65rem 0 0", paddingLeft: "1.1rem", color: "#334155" }}>
                  {sigVerdict.integrity_label && (
                    <li>Integridade: {sigVerdict.integrity_label}</li>
                  )}
                  {sigVerdict.crypto_label && (
                    <li>Assinatura matematica: {sigVerdict.crypto_label}</li>
                  )}
                  {sigVerdict.timestamp_label && (
                    <li>Carimbo de tempo: {sigVerdict.timestamp_label}</li>
                  )}
                  {sigVerdict.revocation_label && (
                    <li>Revogacao: {sigVerdict.revocation_label}</li>
                  )}
                </ul>
              )}
            </div>
          )}
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
            <MetaTabButton
              active={sigView === "relatorio"}
              onClick={() => setSigView("relatorio")}
              label="Relatório (renderizado)"
            />
            <MetaTabButton
              active={sigView === "fonte"}
              onClick={() => setSigView("fonte")}
              label="Fonte Markdown"
            />
            <MetaTabButton
              active={sigView === "json"}
              onClick={() => setSigView("json")}
              label="JSON estruturado"
            />
          </div>
          {sigView === "relatorio" ? (
            <MarkdownReportView
              content={sigContent}
              loading={sigLoading}
              maxHeight={SIGNATURES_SCROLL_HEIGHT}
            />
          ) : (
            <div style={{ ...metadataScrollBoxStyle, maxHeight: SIGNATURES_SCROLL_HEIGHT }}>
              <pre style={metadataPreStyle}>
                {sigLoading ? "Carregando…" : sigContent || "(sem conteudo)"}
              </pre>
            </div>
          )}
          <DerivativeActions
            artifactFilename={sigArtifactFilename(sigView)}
            label={`pdf_extract_${sigView === "json" ? "signatures_json" : "signatures_txt"}`}
            saving={saving}
            onSave={(filename, label) => currentJobId && save(currentJobId, filename, label)}
            onOpenDerivatives={() => navigate(`/cases/${caseId}?tab=derivados`)}
          />
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
            saving={saving}
            onSave={(filename, label) => currentJobId && save(currentJobId, filename, label)}
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
                    label={`pdf_extract_${selectedVersion.filename.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") || "version"}`}
                    saving={saving}
                    onSave={(filename, label) => currentJobId && save(currentJobId, filename, label)}
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
                saving={saving}
                onSave={(filename, label) => currentJobId && save(currentJobId, filename, label)}
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
    </TechniquePageShell>
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
  saving: boolean;
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
        {saving ? "Salvando…" : "Salvar em derivados"}
      </button>
      <button type="button" style={btnSecondary} onClick={onOpenDerivatives}>
        Abrir derivados
      </button>
    </div>
  );
}

const hintStyle = { fontSize: "0.82rem", color: "#6b7280", marginTop: 0, marginBottom: "0.5rem" } as const;

const sigChipStyle: CSSProperties = {
  display: "inline-block",
  padding: "0.15rem 0.5rem",
  background: "#e2e8f0",
  borderRadius: 4,
  fontSize: "0.75rem",
  color: "#334155",
};

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
