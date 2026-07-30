import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import TechniquePageShell from "@/components/TechniquePageShell";
import { MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import ForensicInsightsPanel, { type ForensicInsight } from "@/components/metadata/ForensicInsightsPanel";
import MetadataTagTable, { type MetadataTag } from "@/components/metadata/MetadataTagTable";
import C2paViewer, { type C2paStructured } from "@/components/metadata/C2paViewer";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { useDerivativeSave } from "@/hooks/useDerivativeSave";
import { useTechniqueRuntime } from "@/hooks/useTechniqueRuntime";

type AudioMetaTab =
  | "overview"
  | "id3"
  | "vorbis"
  | "riff"
  | "quicktime"
  | "xmp"
  | "c2pa"
  | "file"
  | "other";

interface AudioFamilies {
  id3?: MetadataTag[];
  vorbis?: MetadataTag[];
  riff?: MetadataTag[];
  quicktime?: MetadataTag[];
  xmp?: MetadataTag[];
  c2pa?: MetadataTag[];
  file?: MetadataTag[];
  other?: MetadataTag[];
}

const TABS: { id: AudioMetaTab; label: string; accent: string }[] = [
  { id: "overview", label: "Visão geral", accent: "#0369a1" },
  { id: "id3", label: "ID3", accent: "#0f766e" },
  { id: "vorbis", label: "Vorbis / Opus / FLAC", accent: "#7c3aed" },
  { id: "riff", label: "RIFF / WAV", accent: "#b45309" },
  { id: "quicktime", label: "QuickTime / M4A", accent: "#1e40af" },
  { id: "xmp", label: "XMP", accent: "#7c3aed" },
  { id: "c2pa", label: "C2PA", accent: "#be123c" },
  { id: "file", label: "Arquivo", accent: "#64748b" },
  { id: "other", label: "Outros", accent: "#6b7280" },
];

function familiesFromResult(result: Record<string, unknown> | null): AudioFamilies {
  const meta = result?.metadata as { families?: AudioFamilies } | undefined;
  return meta?.families || {};
}

export default function AudioMetadataAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [activeTab, setActiveTab] = useState<AudioMetaTab>("overview");
  const { saving, saveMessage, save, clearMessage } = useDerivativeSave();
  const { running, currentJobId, result, error, progress, progressLabel, runAnalysis, reset } =
    useForensicJob();
  const { status: runtimeStatus } = useTechniqueRuntime("audio_metadata");
  const runtimeOk = runtimeStatus?.available ?? null;
  const runtimeReason = runtimeStatus?.reason || "";

  const applyEvidence = useCallback(
    (_id: string) => {
      reset();
      clearMessage();
      setActiveTab("overview");
    },
    [reset, clearMessage],
  );

  const { embedded, showEvidencePicker, evidenceId, selectionSource, onSelectEvidence } =
    useGroupAwareEvidence(caseId || "", applyEvidence);

  const families = useMemo(() => familiesFromResult(result), [result]);
  const summary = (result?.summary || {}) as Record<string, unknown>;
  const highlights = (result?.highlights || []) as MetadataTag[];
  const insights = (result?.forensic_insights || []) as ForensicInsight[];
  const warnings = ((result?.metadata as { warnings?: string[] })?.warnings || []) as string[];
  const file = (result?.file || {}) as Record<string, unknown>;
  const c2paStructured = ((result?.c2pa_structured ||
    (result?.metadata as { c2pa_structured?: C2paStructured })?.c2pa_structured) ??
    {}) as C2paStructured;

  const tabCounts = useMemo(
    () => ({
      overview: highlights.length,
      id3: families.id3?.length || 0,
      vorbis: families.vorbis?.length || 0,
      riff: families.riff?.length || 0,
      quicktime: families.quicktime?.length || 0,
      xmp: families.xmp?.length || 0,
      c2pa: families.c2pa?.length || (c2paStructured.available ? 1 : 0),
      file: families.file?.length || 0,
      other: families.other?.length || 0,
    }),
    [families, highlights.length, c2paStructured.available],
  );

  const visibleTabs = useMemo(() => {
    const items: { id: AudioMetaTab; count?: number }[] = [
      { id: "overview", count: insights.length || highlights.length || undefined },
    ];
    for (const tab of TABS) {
      if (tab.id === "overview") continue;
      if (tab.id === "c2pa") {
        if (c2paStructured.available) {
          items.push({
            id: "c2pa",
            count: families.c2pa?.length || (c2paStructured.present ? 1 : 0),
          });
        }
        continue;
      }
      if (tabCounts[tab.id] > 0) items.push({ id: tab.id, count: tabCounts[tab.id] });
    }
    return items;
  }, [
    tabCounts,
    insights.length,
    highlights.length,
    c2paStructured.available,
    c2paStructured.present,
    families.c2pa?.length,
  ]);

  useEffect(() => {
    if (result && !visibleTabs.some((t) => t.id === activeTab)) {
      setActiveTab("overview");
    }
  }, [result, visibleTabs, activeTab]);

  async function process() {
    if (!evidenceId || runtimeOk === false) return;
    setActiveTab("overview");
    clearMessage();
    try {
      await runAnalysis(evidenceId, "audio_metadata", {});
    } catch {
      /* useForensicJob */
    }
  }

  if (!caseId) return null;

  const activeEntries: MetadataTag[] =
    activeTab === "overview"
      ? highlights
      : ((families[activeTab] as MetadataTag[] | undefined) || []);

  const parametersPanel = (
    <>
      <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#4b5563", lineHeight: 1.45 }}>
        Extrai tags comuns e particulares (ID3, Vorbis/Opus, RIFF, QuickTime/M4A, XMP) via ExifTool,
        Content Credentials (C2PA) via c2pa-python, e probe técnico (codec, taxa, duração).
      </p>
      {runtimeReason && runtimeOk !== false && (
        <p style={{ margin: "0 0 0.75rem", fontSize: "0.8rem", color: "#92400e" }}>{runtimeReason}</p>
      )}
      <ProcessButton
        onClick={process}
        disabled={!evidenceId || runtimeOk === false}
        running={running}
        progress={progress}
        progressLabel={progressLabel}
        label="Extrair metadados"
      />
      {error && <MessageBox type="err" text={error} />}
    </>
  );

  const resultPanel = result ? (
    <>
      {warnings.length > 0 && (
        <div
          style={{
            background: "#fffbeb",
            border: "1px solid #fcd34d",
            borderRadius: 8,
            padding: "0.75rem 1rem",
            marginBottom: "1rem",
            fontSize: "0.85rem",
            color: "#92400e",
          }}
        >
          {warnings.map((w) => (
            <p key={w} style={{ margin: 0 }}>
              {w}
            </p>
          ))}
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
        {[
          { label: "Arquivo", value: String(file.filename || "—") },
          { label: "Codec", value: String(summary.codec ?? "—") },
          { label: "Taxa (Hz)", value: String(summary.sample_rate_hz ?? "—") },
          { label: "Canais", value: String(summary.channels ?? "—") },
          { label: "Duração (s)", value: String(summary.duration_sec ?? "—") },
          { label: "Tags", value: String(summary.total_tags ?? 0) },
          {
            label: "C2PA",
            value: summary.has_c2pa
              ? String(summary.c2pa_validation_state || (summary.c2pa_valid ? "válido" : "presente"))
              : summary.c2pa_available
                ? "ausente"
                : "—",
          },
          { label: "Motor", value: String(summary.metadata_engine ?? "—") },
        ].map((chip) => (
          <div
            key={chip.label}
            style={{
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              padding: "0.45rem 0.7rem",
              minWidth: 110,
            }}
          >
            <div style={{ fontSize: "0.68rem", color: "#64748b", textTransform: "uppercase" }}>
              {chip.label}
            </div>
            <div style={{ fontSize: "0.86rem", color: "#0f172a", fontWeight: 600, marginTop: 2 }}>
              {chip.value}
            </div>
          </div>
        ))}
      </div>

      {insights.length > 0 && (
        <div style={{ marginBottom: "1rem" }}>
          <ForensicInsightsPanel insights={insights} />
        </div>
      )}

      <div
        role="tablist"
        aria-label="Famílias de metadados de áudio"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.35rem",
          marginBottom: "0.85rem",
          borderBottom: "2px solid #e5e7eb",
          paddingBottom: "0.5rem",
        }}
      >
        {visibleTabs.map((tab) => {
          const def = TABS.find((t) => t.id === tab.id)!;
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setActiveTab(tab.id)}
              style={{
                border: selected ? `1px solid ${def.accent}` : "1px solid #e5e7eb",
                background: selected ? "#f0f9ff" : "#fff",
                color: selected ? def.accent : "#374151",
                borderRadius: 8,
                padding: "0.35rem 0.7rem",
                cursor: "pointer",
                fontSize: "0.8rem",
                fontWeight: selected ? 600 : 500,
              }}
            >
              {def.label}
              {tab.count != null && tab.count > 0 ? ` (${tab.count})` : ""}
            </button>
          );
        })}
      </div>

      {activeTab === "c2pa" ? (
        <C2paViewer structured={c2paStructured} entries={families.c2pa || []} />
      ) : (
        <MetadataTagTable
          entries={activeEntries}
          emptyMessage={
            activeTab === "overview"
              ? "Nenhum destaque automático — veja as famílias à direita."
              : "Nenhuma tag nesta família."
          }
          showHints={false}
        />
      )}

      {currentJobId && (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.85rem" }}>
          <button
            type="button"
            disabled={!!saving}
            onClick={() => save(currentJobId, "metadata_report.json", "audio_metadata_json")}
            style={btnPrimary}
          >
            {saving ? "Salvando…" : "Salvar JSON nos derivados"}
          </button>
          <button
            type="button"
            disabled={!!saving}
            onClick={() => save(currentJobId, "metadata_report.txt", "audio_metadata_txt")}
            style={btnPrimary}
          >
            {saving ? "Salvando…" : "Salvar TXT nos derivados"}
          </button>
          {Boolean(c2paStructured.present) && (
            <button
              type="button"
              disabled={!!saving}
              onClick={() => save(currentJobId, "c2pa_manifest.json", "audio_c2pa_manifest")}
              style={btnPrimary}
            >
              {saving ? "Salvando…" : "Salvar manifesto C2PA"}
            </button>
          )}
        </div>
      )}
      {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}
    </>
  ) : undefined;

  return (
    <TechniquePageShell
      caseId={caseId}
      techniqueId="audio_metadata"
      mediaType="audio"
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
      resultPanel={resultPanel}
    />
  );
}

const btnPrimary = {
  padding: "0.45rem 0.9rem",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: "0.85rem",
  fontWeight: 500,
} as const;
