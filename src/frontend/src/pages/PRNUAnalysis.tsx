import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/services/api";
import EvidenceDropZone from "@/components/EvidenceDropZone";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import EvidenceFilePreview from "@/components/EvidenceFilePreview";
import FileListViewHeader from "@/components/FileListViewHeader";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import TechniqueReferenceIntro from "@/components/TechniqueReferenceIntro";
import { FORENSIC_TECHNIQUE_META } from "@/config/forensicTechniqueMeta";
import PlotlyHtmlFrame from "@/components/PlotlyHtmlFrame";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useBusyProgress } from "@/hooks/useBusyProgress";
import { listCaseReferences, saveDerivative, uploadPrnuReference } from "@/services/evidence";
import {
  createCaseFingerprint,
  listCaseFingerprints,
  type PrnuFingerprintMeta,
} from "@/services/prnu";
import type { Evidence } from "@/types/api";
import { prnuRefListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

type PrnuMode = "full" | "cropped" | "scaled";

const MODE_LABELS: Record<PrnuMode, string> = {
  full: "Completa",
  cropped: "Recortada",
  scaled: "Recortada e redimensionada",
};

export default function PRNUAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [refImages, setRefImages] = useState<Evidence[]>([]);
  const [rotuloOptions, setRotuloOptions] = useState<string[]>([]);
  const [selectedRotulo, setSelectedRotulo] = useState("");
  const [newRotulo, setNewRotulo] = useState("");
  const [selectedRefIds, setSelectedRefIds] = useState<Set<string>>(new Set());
  const [uploadingRefs, setUploadingRefs] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [refViewMode, setRefViewMode] = useFileListViewMode();

  const [fingerprints, setFingerprints] = useState<PrnuFingerprintMeta[]>([]);
  const [fpSigma, setFpSigma] = useState(3);
  const [generatingFp, setGeneratingFp] = useState(false);
  const [fpMessage, setFpMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const [selectedFingerprintId, setSelectedFingerprintId] = useState<string | null>(null);
  const [mode, setMode] = useState<PrnuMode>("full");
  const [analysisSigma, setAnalysisSigma] = useState(2);
  const [localizedMap, setLocalizedMap] = useState(true);
  const [blockHalf, setBlockHalf] = useState(32);
  const [overlapK, setOverlapK] = useState(50);
  const [localizedThreshold, setLocalizedThreshold] = useState(0);
  const [localizedMapUrl, setLocalizedMapUrl] = useState<string | null>(null);
  const [localizedOverlayUrl, setLocalizedOverlayUrl] = useState<string | null>(null);
  const [localizedPositiveUrl, setLocalizedPositiveUrl] = useState<string | null>(null);
  const [savingLocalized, setSavingLocalized] = useState(false);
  const [surfaceHtmlUrl, setSurfaceHtmlUrl] = useState<string | null>(null);
  const [scaleCurveUrl, setScaleCurveUrl] = useState<string | null>(null);
  const [savingPlot, setSavingPlot] = useState(false);
  const [savePlotMessage, setSavePlotMessage] = useState<{ type: "ok" | "err"; text: string } | null>(
    null
  );
  const [localizedParamsSnapshot, setLocalizedParamsSnapshot] = useState<{
    blockHalf: number;
    overlapK: number;
    localizedThreshold: number;
  } | null>(null);

  const activeRotulo = useMemo(() => {
    if (selectedRotulo === "__new__") return newRotulo.trim();
    return selectedRotulo.trim();
  }, [selectedRotulo, newRotulo]);

  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, fetchImage, reset } =
    useForensicJob();
  const {
    progress: fpProgress,
    label: fpProgressLabel,
    start: startFpProgress,
    finish: finishFpProgress,
    reset: resetFpProgress,
    stopLoop: stopFpProgressLoop,
  } = useBusyProgress();

  useEffect(() => {
    return () => {
      if (surfaceHtmlUrl) URL.revokeObjectURL(surfaceHtmlUrl);
    };
  }, [surfaceHtmlUrl]);

  const loadRefImages = useCallback(async () => {
    if (!caseId) return;
    try {
      const data = await listCaseReferences(caseId);
      const prnuGroups = data.groups.filter((g) => g.technique === "prnu");
      const labels = prnuGroups.map((g) => g.group_label);
      setRotuloOptions(labels);

      setSelectedRotulo((prev) => {
        if (prev && (prev === "__new__" || labels.includes(prev))) return prev;
        return labels[0] || "__new__";
      });

      const rotulo =
        selectedRotulo === "__new__"
          ? newRotulo.trim()
          : selectedRotulo && labels.includes(selectedRotulo)
            ? selectedRotulo
            : labels[0] || "";

      const group = prnuGroups.find((g) => g.group_label === rotulo);
      const refs = group?.files ?? [];
      setRefImages(refs);
      setSelectedRefIds((prev) => {
        if (prev.size > 0) {
          const valid = new Set(refs.map((r) => r.id));
          return new Set([...prev].filter((id) => valid.has(id)));
        }
        return new Set(refs.map((r) => r.id));
      });
    } catch {
      setRefImages([]);
      setRotuloOptions([]);
    }
  }, [caseId, selectedRotulo, newRotulo]);

  const loadFingerprints = useCallback(async () => {
    if (!caseId) return;
    try {
      const list = await listCaseFingerprints(caseId);
      const valid = list.filter((f) => f.exists !== false);
      setFingerprints(valid);
      setSelectedFingerprintId((prev) => prev ?? valid[0]?.id ?? null);
    } catch {
      setFingerprints([]);
    }
  }, [caseId]);

  useEffect(() => {
    if (!caseId) return;
    loadRefImages();
    loadFingerprints();
  }, [caseId, loadRefImages, loadFingerprints]);

  async function handleRefUpload(files: FileList) {
    if (!caseId) return;
    const rotulo = activeRotulo;
    if (!rotulo) {
      setFpMessage({ type: "err", text: "Informe ou selecione um rotulo de grupo antes do upload." });
      return;
    }
    setUploadingRefs(true);
    setFpMessage(null);
    const fileList = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (fileList.length === 0) {
      setFpMessage({ type: "err", text: "Envie apenas arquivos de imagem." });
      setUploadingRefs(false);
      return;
    }

    const uploaded: Evidence[] = [];
    for (const file of fileList) {
      try {
        const ev = await uploadPrnuReference(caseId, file, rotulo, (pct) => {
          setUploadProgress((p) => ({ ...p, [file.name]: pct }));
        });
        uploaded.push(ev);
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          `Falha ao enviar ${file.name}`;
        setFpMessage({ type: "err", text: String(msg) });
      }
    }

    if (uploaded.length > 0) {
      if (!rotuloOptions.includes(rotulo)) {
        setRotuloOptions((prev) => [...prev, rotulo].sort());
        setSelectedRotulo(rotulo);
      }
      await loadRefImages();
      setSelectedRefIds((prev) => {
        const next = new Set(prev);
        uploaded.forEach((u) => next.add(u.id));
        return next;
      });
      setFpMessage({
        type: "ok",
        text: `${uploaded.length} imagem(ns) no grupo PRNU - ${rotulo} (cadeia de custodia).`,
      });
    }

    setUploadProgress({});
    setUploadingRefs(false);
  }

  function toggleRef(id: string) {
    setSelectedRefIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAllRefs() {
    setSelectedRefIds(new Set(refImages.map((r) => r.id)));
  }

  function clearRefSelection() {
    setSelectedRefIds(new Set());
  }

  async function handleGenerateFingerprint() {
    const rotulo = activeRotulo;
    if (!caseId || selectedRefIds.size === 0 || !rotulo) {
      setFpMessage({
        type: "err",
        text: "Selecione um rotulo de grupo e ao menos uma imagem de referencia.",
      });
      return;
    }
    setGeneratingFp(true);
    setFpMessage(null);
    startFpProgress("Preparando imagens de referencia…");
    try {
      const meta = await createCaseFingerprint(caseId, {
        evidence_ids: Array.from(selectedRefIds),
        group_label: rotulo,
        sigma: fpSigma,
      });
      finishFpProgress();
      setFpMessage({
        type: "ok",
        text: `Fingerprint "${meta.label}" gerado (PRNU-${rotulo}-seq). Salvo nos derivados com custodia. ${meta.images_used} imagens.`,
      });
      setSelectedFingerprintId(meta.id);
      await loadFingerprints();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Falha ao gerar fingerprint";
      setFpMessage({ type: "err", text: String(msg) });
    } finally {
      setGeneratingFp(false);
      stopFpProgressLoop();
      setTimeout(() => resetFpProgress(), 700);
    }
  }

  const applyEvidence = useCallback(
    (_id: string, _source: "original" | "derivative") => {
      reset();
      if (surfaceHtmlUrl) URL.revokeObjectURL(surfaceHtmlUrl);
      setSurfaceHtmlUrl(null);
      setScaleCurveUrl(null);
      setLocalizedMapUrl(null);
      setLocalizedOverlayUrl(null);
      setLocalizedPositiveUrl(null);
      setLocalizedParamsSnapshot(null);
      setSavePlotMessage(null);
    },
    [reset, surfaceHtmlUrl],
  );

  const { embedded, showEvidencePicker, evidenceId, onSelectEvidence } = useGroupAwareEvidence(
    caseId!,
    applyEvidence,
  );

  const localizedParamsStale = useMemo(() => {
    if (!localizedParamsSnapshot) return false;
    return (
      blockHalf !== localizedParamsSnapshot.blockHalf ||
      overlapK !== localizedParamsSnapshot.overlapK ||
      localizedThreshold !== localizedParamsSnapshot.localizedThreshold
    );
  }, [blockHalf, overlapK, localizedThreshold, localizedParamsSnapshot]);

  async function loadLocalizedArtifacts(jobId: string) {
    const loc = await fetchImage(jobId, "localized_map.png");
    const lov = await fetchImage(jobId, "localized_overlay.png");
    const lpos = await fetchImage(jobId, "localized_positive.png");
    setLocalizedMapUrl(loc);
    setLocalizedOverlayUrl(lov);
    setLocalizedPositiveUrl(lpos);
    setLocalizedParamsSnapshot({ blockHalf, overlapK, localizedThreshold });
  }

  async function handleSaveLocalizedArtifacts() {
    if (!currentJobId) return;
    if (localizedParamsStale) {
      setSavePlotMessage({
        type: "err",
        text: "Parametros do mapa localizado mudaram. Clique em «Reprocessar somente mapa localizado» antes de salvar.",
      });
      return;
    }
    setSavingLocalized(true);
    const effective_parameters: Record<string, unknown> = {
      fingerprint_id: selectedFingerprintId,
      sigma: analysisSigma,
      mode,
      block_half: blockHalf,
      overlap_k: overlapK,
      localized_threshold: localizedThreshold,
      localized_map: localizedMap,
    };
    try {
      const files = ["localized_map.png", "localized_positive.png", "localized_overlay.png"];
      await Promise.all(
        files.map((f) =>
          saveDerivative({
            job_id: currentJobId,
            artifact_filename: f,
            label: `prnu_${f.replace(".png", "")}`,
            effective_parameters,
          })
        )
      );
      setSavePlotMessage({ type: "ok", text: "Mapas localizados salvos nos derivados." });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSavePlotMessage({ type: "err", text: String(msg) });
    } finally {
      setSavingLocalized(false);
    }
  }

  async function reprocessLocalizedOnly() {
    if (!evidenceId || !caseId || !selectedFingerprintId) return;
    try {
      await runAnalysis(
        evidenceId,
        "prnu",
        {
          case_id: caseId,
          fingerprint_id: selectedFingerprintId,
          sigma: analysisSigma,
          localized_only: true,
          block_half: blockHalf,
          overlap_k: overlapK,
          localized_threshold: localizedThreshold,
        },
        {
          onArtifactsLoaded: async (jobId) => {
            await loadLocalizedArtifacts(jobId);
          },
        }
      );
    } catch {
      /* hook */
    }
  }

  async function handleSaveSurfacePlot() {
    if (!currentJobId) return;
    setSavingPlot(true);
    setSavePlotMessage(null);
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: "correlation_surface.html",
        label: "prnu_superficie_C",
      });
      setSavePlotMessage({
        type: "ok",
        text: `Superficie 3D salva nos derivados. SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Erro ao salvar";
      setSavePlotMessage({ type: "err", text: String(msg) });
    } finally {
      setSavingPlot(false);
    }
  }

  async function process() {
    if (!evidenceId || !caseId || !selectedFingerprintId) return;
    try {
      await runAnalysis(
        evidenceId,
        "prnu",
        {
          case_id: caseId,
          fingerprint_id: selectedFingerprintId,
          mode,
          sigma: analysisSigma,
          localized_map: localizedMap,
          block_half: blockHalf,
          overlap_k: overlapK,
          localized_threshold: localizedThreshold,
        },
        {
          onArtifactsLoaded: async (jobId, jobResult) => {
            try {
              const htmlRes = await api.get(`/analysis/${jobId}/result/file?filename=correlation_surface.html`, {
                responseType: "blob",
              });
              if (surfaceHtmlUrl) URL.revokeObjectURL(surfaceHtmlUrl);
              setSurfaceHtmlUrl(URL.createObjectURL(new Blob([htmlRes.data], { type: "text/html" })));
            } catch {
              setSurfaceHtmlUrl(null);
            }
            if (jobResult?.mode === "scaled") {
              const sc = await fetchImage(jobId, "scale_curve.png");
              setScaleCurveUrl(sc);
            } else {
              setScaleCurveUrl(null);
            }
            if (!jobResult?.localized_skipped) {
              await loadLocalizedArtifacts(jobId);
            } else {
              setLocalizedMapUrl(null);
              setLocalizedOverlayUrl(null);
              setLocalizedPositiveUrl(null);
              setLocalizedParamsSnapshot(null);
            }
          },
        }
      );
    } catch {
      /* hook */
    }
  }

  const selectedFp = fingerprints.find((f) => f.id === selectedFingerprintId);
  const fingerprintsForRotulo = activeRotulo
    ? fingerprints.filter(
        (f) =>
          !f.legacy &&
          (f.reference_group_label === activeRotulo || f.label?.includes(`-${activeRotulo}-`))
      )
    : fingerprints;

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title={FORENSIC_TECHNIQUE_META.prnu.title}
      intro={<TechniqueReferenceIntro meta={FORENSIC_TECHNIQUE_META.prnu} />}
      embedded={embedded}
    >
      <AnalysisPanel title="1. Imagens de referencia (padrao do sensor)">
        <p style={hintStyle}>
          Escolha ou crie um rotulo de grupo (ex.: D70). Cada upload entra nesse grupo e na cadeia de custodia —
          nao aparece na lista de evidencias do caso.
        </p>

        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-end", marginBottom: "1rem" }}>
          <label style={fieldStyle}>
            Rotulo do grupo
            <select
              value={selectedRotulo}
              onChange={(e) => {
                setSelectedRotulo(e.target.value);
                setSelectedRefIds(new Set());
              }}
              style={{ ...inputStyle, minWidth: 200 }}
            >
              {rotuloOptions.map((r) => (
                <option key={r} value={r}>
                  PRNU - {r}
                </option>
              ))}
              <option value="__new__">+ Novo rotulo…</option>
            </select>
          </label>
          {selectedRotulo === "__new__" && (
            <label style={fieldStyle}>
              Novo rotulo
              <input
                type="text"
                value={newRotulo}
                onChange={(e) => setNewRotulo(e.target.value)}
                placeholder="Ex.: D70, Rotulo2"
                style={inputStyle}
              />
            </label>
          )}
        </div>

        <EvidenceDropZone
          inputId="prnu-ref-upload"
          accept="image/*"
          multiple
          uploading={uploadingRefs}
          hint="Clique ou arraste imagens para o grupo selecionado"
          subHint={
            activeRotulo
              ? `Grupo: PRNU - ${activeRotulo} · registro na cadeia de custodia`
              : "Defina o rotulo antes de enviar"
          }
          onFiles={handleRefUpload}
        />

        {Object.keys(uploadProgress).length > 0 && (
          <div style={{ marginTop: "0.75rem" }}>
            {Object.entries(uploadProgress).map(([name, pct]) => (
              <div key={name} style={{ fontSize: "0.8rem", color: "#374151", marginBottom: 4 }}>
                {name}: {pct}%
              </div>
            ))}
          </div>
        )}

        {refImages.length > 0 && (
          <div style={{ marginTop: "1rem" }}>
            <FileListViewHeader viewMode={refViewMode} onViewModeChange={setRefViewMode}>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                <button type="button" onClick={selectAllRefs} style={btnSmall}>
                  Marcar todas
                </button>
                <button type="button" onClick={clearRefSelection} style={btnSmall}>
                  Desmarcar
                </button>
                <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
                  {selectedRefIds.size} de {refImages.length} no grupo PRNU - {activeRotulo || "?"}
                </span>
              </div>
            </FileListViewHeader>
            {refViewMode === "grid" ? (
              <EvidenceFileGrid
                items={refImages}
                selected={(ev) => selectedRefIds.has(ev.id)}
                onSelect={(ev) => toggleRef(ev.id)}
                maxHeight={prnuRefListMaxHeight}
                thumbSize={64}
                renderFooter={(ev) => (
                  <span style={{ fontSize: "0.68rem", color: "#9ca3af" }}>
                    SHA {(ev.sha256 ?? "").slice(0, 12)}…
                  </span>
                )}
              />
            ) : (
              <div
                style={{
                  ...scrollableListStyle,
                  maxHeight: prnuRefListMaxHeight,
                  border: "1px solid #e5e7eb",
                  borderRadius: 6,
                  padding: 8,
                }}
              >
                {refImages.map((ev) => (
                  <label
                    key={ev.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      fontSize: "0.85rem",
                      marginBottom: 8,
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedRefIds.has(ev.id)}
                      onChange={() => toggleRef(ev.id)}
                    />
                    <EvidenceFilePreview evidenceId={ev.id} fileType={ev.file_type} size={40} />
                    <span>
                      {ev.original_filename}
                      <span style={{ display: "block", fontSize: "0.72rem", color: "#9ca3af" }}>
                        SHA {(ev.sha256 ?? "").slice(0, 12)}… · custodia
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
        )}

        <div
          style={{
            display: "flex",
            gap: "1rem",
            marginTop: "1rem",
            flexWrap: "wrap",
            alignItems: "flex-end",
          }}
        >
          <label style={fieldStyle}>
            Sigma (geracao)
            <input
              type="number"
              min={0.5}
              max={10}
              step={0.5}
              value={fpSigma}
              onChange={(e) => setFpSigma(Number(e.target.value))}
              style={{ ...inputStyle, width: 80 }}
            />
          </label>
          <ProcessButton
            onClick={handleGenerateFingerprint}
            disabled={selectedRefIds.size === 0 || !activeRotulo}
            running={generatingFp}
            progress={fpProgress}
            progressLabel={fpProgressLabel}
            label="Gerar fingerprint"
          />
        </div>
        <p style={{ fontSize: "0.78rem", color: "#6b7280", margin: "0.5rem 0 0" }}>
          Nome automatico: PRNU-&#123;rotulo&#125;-&#123;seq&#125; (ex.: PRNU-D70-001).
        </p>
        {fpMessage && <MessageBox type={fpMessage.type} text={fpMessage.text} />}
      </AnalysisPanel>

      <AnalysisPanel title="2. Fingerprints do caso (derivados)">
        <p style={hintStyle}>
          Fingerprints salvos em Derivados com custodia. Filtro pelo rotulo do grupo selecionado acima.
        </p>
        {(fingerprintsForRotulo.length > 0 ? fingerprintsForRotulo : fingerprints).length === 0 ? (
          <p style={{ fontSize: "0.88rem", color: "#6b7280", margin: 0 }}>
            Nenhum fingerprint ainda. Gere um na secao acima.
          </p>
        ) : (
          <select
            value={selectedFingerprintId || ""}
            onChange={(e) => setSelectedFingerprintId(e.target.value || null)}
            style={{ ...inputStyle, maxWidth: 560 }}
          >
            {(fingerprintsForRotulo.length > 0 ? fingerprintsForRotulo : fingerprints).map((fp) => (
              <option key={fp.id} value={fp.id}>
                {fp.label}
                {fp.legacy ? " (importado)" : ""} — {fp.images_used ?? "?"} img · σ={fp.sigma} ·{" "}
                {fp.created_at ? new Date(fp.created_at).toLocaleString() : ""}
              </option>
            ))}
          </select>
        )}
        {selectedFp && (
          <p style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 8, marginBottom: 0 }}>
            Derivado: {selectedFp.sha256?.slice(0, 16) ?? "—"}… · shape{" "}
            {selectedFp.shape?.join("×") ?? "—"}
          </p>
        )}
      </AnalysisPanel>

      <AnalysisPanel title="3. Imagem questionada (confronto)">
        <p style={{ ...hintStyle, marginBottom: "0.75rem" }}>
          Apenas evidencias originais do caso — sem referencias PRNU nem derivados.
        </p>
        {showEvidencePicker && (
          <ImageEvidenceSelector
            caseId={caseId}
            selectedId={evidenceId}
            selectionSource="original"
            onSelect={onSelectEvidence}
            excludeReferences
            excludeDerivatives
            excludePrnuFingerprints
          />
        )}

        <fieldset style={{ border: "none", padding: 0, margin: "1rem 0 0" }}>
          <legend style={{ fontSize: "0.88rem", fontWeight: 600, marginBottom: 8 }}>Modo de correlacao</legend>
          {(Object.keys(MODE_LABELS) as PrnuMode[]).map((m) => (
            <label key={m} style={{ display: "block", fontSize: "0.85rem", marginBottom: 4 }}>
              <input type="radio" name="prnu-mode" checked={mode === m} onChange={() => setMode(m)} />{" "}
              {MODE_LABELS[m]}
            </label>
          ))}
        </fieldset>

        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem", marginTop: "0.75rem" }}>
          <input
            type="checkbox"
            checked={localizedMap}
            onChange={(e) => setLocalizedMap(e.target.checked)}
          />
          Gerar mapa PRNU localizado (correlacao por blocos)
        </label>

        <label style={{ ...fieldStyle, marginTop: "0.75rem" }}>
          Sigma (analise)
          <input
            type="number"
            min={0.5}
            max={10}
            step={0.5}
            value={analysisSigma}
            onChange={(e) => setAnalysisSigma(Number(e.target.value))}
            style={{ ...inputStyle, width: 80 }}
          />
        </label>

        {localizedMap && (
          <div
            style={{
              marginTop: "0.75rem",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
              gap: "0.75rem",
            }}
          >
            <label style={fieldStyle}>
              Meio-bloco (px)
              <input
                type="number"
                min={8}
                max={64}
                value={blockHalf}
                onChange={(e) => setBlockHalf(Number(e.target.value))}
                style={inputStyle}
              />
            </label>
            <label style={fieldStyle}>
              Sobreposicao k
              <input
                type="number"
                min={10}
                max={80}
                value={overlapK}
                onChange={(e) => setOverlapK(Number(e.target.value))}
                style={inputStyle}
              />
            </label>
            <label style={fieldStyle}>
              Limiar correlacao
              <input
                type="number"
                step={0.01}
                min={-1}
                max={1}
                value={localizedThreshold}
                onChange={(e) => setLocalizedThreshold(Number(e.target.value))}
                style={inputStyle}
              />
            </label>
          </div>
        )}

        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!evidenceId || !selectedFingerprintId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Correlacionar PRNU"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
        <AnalysisPanel title="Metricas (interpretacao pelo perito)">
          <table style={metricsTableStyle}>
            <tbody>
              <tr>
                <th style={thStyle}>PCE</th>
                <td style={tdStyle}>{formatNum(result.pce)}</td>
              </tr>
              {result.pce_no_crop != null && (
                <tr>
                  <th style={thStyle}>PCE (sem recorte)</th>
                  <td style={tdStyle}>{formatNum(result.pce_no_crop)}</td>
                </tr>
              )}
              <tr>
                <th style={thStyle}>p-value</th>
                <td style={tdStyle}>{formatSci(result.p_value)}</td>
              </tr>
              <tr>
                <th style={thStyle}>P_FA</th>
                <td style={tdStyle}>{formatSci(result.p_fa)}</td>
              </tr>
              <tr>
                <th style={thStyle}>log10(P_FA)</th>
                <td style={tdStyle}>{formatNum(result.log10_p_fa)}</td>
              </tr>
              <tr>
                <th style={thStyle}>Altura do pico</th>
                <td style={tdStyle}>{formatNum(result.peak_height)}</td>
              </tr>
              <tr>
                <th style={thStyle}>Local do pico</th>
                <td style={tdStyle}>
                  {Array.isArray(result.peak_location)
                    ? (result.peak_location as number[]).join(", ")
                    : "—"}
                </td>
              </tr>
              {result.mode === "scaled" && result.best_scale != null && (
                <tr>
                  <th style={thStyle}>Melhor escala</th>
                  <td style={tdStyle}>{formatNum(result.best_scale)}</td>
                </tr>
              )}
              <tr>
                <th style={thStyle}>Modo</th>
                <td style={tdStyle}>{String(result.mode)}</td>
              </tr>
              <tr>
                <th style={thStyle}>Sigma</th>
                <td style={tdStyle}>{formatNum(result.sigma)}</td>
              </tr>
            </tbody>
          </table>

          {surfaceHtmlUrl && (
            <div style={{ marginTop: "1.25rem" }}>
              <p style={capStyle}>
                Superficie <code>C</code> apos <code>fftshift</code>, recortada em torno do
                pico PCE.
              </p>
              <PlotlyHtmlFrame
                url={surfaceHtmlUrl}
                title="PRNU — superficie de correlacao 3D"
                height={760}
              />
              {currentJobId && (
                <div style={{ marginTop: "0.75rem" }}>
                  <button type="button" disabled={savingPlot} onClick={handleSaveSurfacePlot} style={btnPrimary}>
                    {savingPlot ? "Salvando…" : "Salvar superficie 3D nos derivados"}
                  </button>
                </div>
              )}
              {savePlotMessage && <MessageBox type={savePlotMessage.type} text={savePlotMessage.text} />}
            </div>
          )}

          {scaleCurveUrl && (
            <figure style={{ marginTop: "1rem" }}>
              <img src={scaleCurveUrl} alt="Curva PCE vs escala" style={imgStyle} />
              <figcaption style={capStyle}>PCE em funcao do fator de escala (modo redimensionado).</figcaption>
            </figure>
          )}

          {(localizedMapUrl || localizedOverlayUrl) && (
            <div style={{ marginTop: "1.25rem" }}>
              <h4 style={{ fontSize: "0.9rem", margin: "0 0 0.5rem" }}>PRNU localizado (espacial)</h4>
              {localizedParamsStale && currentJobId && (
                <div style={{ marginBottom: "0.75rem" }}>
                  <button type="button" onClick={reprocessLocalizedOnly} disabled={running} style={btnPrimary}>
                    Reprocessar somente mapa localizado
                  </button>
                </div>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem" }}>
                {localizedMapUrl && (
                  <figure>
                    <img src={localizedMapUrl} alt="Mapa localizado" style={imgStyle} />
                    <figcaption style={capStyle}>Mapa de correlacao por blocos (jet)</figcaption>
                  </figure>
                )}
                {localizedPositiveUrl && (
                  <figure>
                    <img src={localizedPositiveUrl} alt="Mapa positivo" style={imgStyle} />
                    <figcaption style={capStyle}>Mascara positiva (limiar)</figcaption>
                  </figure>
                )}
                {localizedOverlayUrl && (
                  <figure>
                    <img src={localizedOverlayUrl} alt="Overlay localizado" style={imgStyle} />
                    <figcaption style={capStyle}>Sobreposicao na imagem</figcaption>
                  </figure>
                )}
              </div>
              {currentJobId && (
                <div style={{ marginTop: "0.75rem" }}>
                  <button
                    type="button"
                    disabled={savingLocalized}
                    onClick={handleSaveLocalizedArtifacts}
                    style={btnPrimary}
                  >
                    {savingLocalized ? "Salvando…" : "Salvar mapas localizados nos derivados"}
                  </button>
                </div>
              )}
            </div>
          )}
        </AnalysisPanel>
      )}
    </AnalysisPageShell>
  );
}

function formatNum(v: unknown): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 4 }) : String(v);
}

function formatSci(v: unknown): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toExponential(3) : String(v);
}

const hintStyle: React.CSSProperties = { fontSize: "0.85rem", color: "#4b5563", marginTop: 0 };
const fieldStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4, fontSize: "0.82rem" };
const inputStyle: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  fontSize: "0.88rem",
};
const btnPrimary: React.CSSProperties = {
  padding: "0.5rem 1rem",
  background: "#0369a1",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.88rem",
};
const btnSmall: React.CSSProperties = {
  padding: "0.3rem 0.65rem",
  background: "#fff",
  border: "1px solid #d1d5db",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.78rem",
};
const imgStyle: React.CSSProperties = { width: "100%", maxWidth: 900, borderRadius: 6, border: "1px solid #e5e7eb" };
const capStyle: React.CSSProperties = { fontSize: "0.8rem", color: "#6b7280", marginTop: 4 };
const metricsTableStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: 520,
  borderCollapse: "collapse",
  fontSize: "0.88rem",
};
const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.35rem 0.75rem 0.35rem 0",
  color: "#374151",
  fontWeight: 600,
  verticalAlign: "top",
};
const tdStyle: React.CSSProperties = { padding: "0.35rem 0", color: "#111827" };
