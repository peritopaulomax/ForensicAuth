import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useParams } from "react-router-dom";
import ImageEvidenceSelector from "@/components/ImageEvidenceSelector";
import AnalysisPageShell, { AnalysisPanel, MessageBox, ProcessButton } from "@/components/AnalysisPageShell";
import Matrix8x8 from "@/components/metadata/Matrix8x8";
import ForensicInsightsPanel, { type ForensicInsight } from "@/components/metadata/ForensicInsightsPanel";
import MetadataSectionHeader from "@/components/metadata/MetadataSectionHeader";
import MetadataTabBar from "@/components/metadata/MetadataTabBar";
import type { MetadataTabId } from "@/components/metadata/metadataTabConfig";
import { METADATA_TABS, tabDefById } from "@/components/metadata/metadataTabConfig";
import { metadataSectionDescription, metadataSectionMeta } from "@/components/metadata/metadataSectionCopy";
import MetadataTagTable, { type MetadataTag } from "@/components/metadata/MetadataTagTable";
import XmpViewer, { type XmpStructured } from "@/components/metadata/XmpViewer";
import { useForensicJob } from "@/hooks/useForensicJob";
import { useGroupAwareEvidence } from "@/hooks/useGroupAwareEvidence";
import { saveDerivative } from "@/services/evidence";

type TabId = MetadataTabId;

interface MetadataFamilies {
  exif?: MetadataTag[];
  iptc?: MetadataTag[];
  xmp?: MetadataTag[];
  icc?: MetadataTag[];
  makernotes?: MetadataTag[];
  adobe?: MetadataTag[];
  other?: MetadataTag[];
}

interface QuantTable {
  index: number;
  label: string;
  matrix: number[][];
  source?: string;
}

interface HuffTable {
  index: number;
  class: string;
  counts: number[];
  symbols: number[];
  total_codes?: number;
}

interface JpegMarker {
  index: number;
  offset: number;
  code_hex: string;
  name: string;
  segment_length?: number | null;
  identifier?: string;
  note?: string;
}

function familiesFromResult(result: Record<string, unknown> | null): MetadataFamilies {
  const meta = result?.metadata as { families?: MetadataFamilies } | undefined;
  return meta?.families || {};
}

export default function ImageMetadataAnalysis() {
  const { caseId } = useParams<{ caseId: string }>();
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const {
    running,
    currentJobId,
    result,
    error,
    progress,
    progressLabel,
    runAnalysis,
    reset,
  } = useForensicJob();

  const applyEvidence = useCallback(
    (_id: string, _source: "original" | "derivative") => {
      reset();
      setSaveMessage(null);
    },
    [reset],
  );

  const { embedded, showEvidencePicker, evidenceId, onSelectEvidence } = useGroupAwareEvidence(
    caseId!,
    applyEvidence,
  );

  const families = useMemo(() => familiesFromResult(result), [result]);
  const summary = (result?.summary || {}) as Record<string, unknown>;
  const highlights = (result?.highlights || []) as MetadataTag[];
  const warnings = ((result?.metadata as { warnings?: string[] })?.warnings || []) as string[];
  const iccProfile = ((result?.metadata as { icc_profile?: Record<string, unknown> })?.icc_profile ||
    {}) as Record<string, unknown>;
  const jpeg = (result?.jpeg_structure || {}) as Record<string, unknown>;
  const file = (result?.file || {}) as Record<string, unknown>;
  const xmpStructured = ((result?.xmp_structured ||
    (result?.metadata as { xmp_structured?: XmpStructured })?.xmp_structured) ??
    {}) as XmpStructured;
  const forensicInsights = (result?.forensic_insights || []) as ForensicInsight[];

  const tabCounts: Record<TabId, number> = useMemo(
    () => ({
      overview: highlights.length,
      exif: families.exif?.length || 0,
      iptc: families.iptc?.length || 0,
      xmp: families.xmp?.length || 0,
      icc: (families.icc?.length || 0) + (iccProfile.available ? 1 : 0),
      makernotes: families.makernotes?.length || 0,
      adobe: families.adobe?.length || 0,
      jpeg: jpeg.available ? 1 : 0,
      other: families.other?.length || 0,
    }),
    [families, highlights, iccProfile, jpeg]
  );

  const visibleTabs = useMemo(() => {
    const items: { id: TabId; count?: number }[] = [
      { id: "overview", count: forensicInsights.length || undefined },
    ];
    for (const tab of METADATA_TABS) {
      if (tab.id === "overview") continue;
      if (tab.id === "jpeg") {
        if (jpeg.available) items.push({ id: "jpeg", count: (jpeg.marker_count as number) || 1 });
        continue;
      }
      if (tabCounts[tab.id] > 0) {
        items.push({ id: tab.id, count: tabCounts[tab.id] });
      }
    }
    return items;
  }, [tabCounts, jpeg.available, jpeg.marker_count, forensicInsights.length]);

  const sectionMetaLine = useMemo(
    () =>
      metadataSectionMeta(activeTab, {
        families: families as Record<string, MetadataTag[] | undefined>,
        summary,
        xmpPropertyCount: xmpStructured.property_count,
        jpegMarkerCount: jpeg.marker_count as number | undefined,
      }),
    [activeTab, families, summary, xmpStructured.property_count, jpeg.marker_count]
  );

  useEffect(() => {
    if (result && !visibleTabs.some((t) => t.id === activeTab)) {
      setActiveTab("overview");
    }
  }, [result, visibleTabs, activeTab]);

  async function process() {
    if (!evidenceId) return;
    setActiveTab("overview");
    setSaveMessage(null);
    try {
      await runAnalysis(evidenceId, "metadata", {});
    } catch {
      /* hook */
    }
  }

  async function registerInCustody() {
    if (!currentJobId) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const res = await saveDerivative({
        job_id: currentJobId,
        artifact_filename: "metadata_report.json",
        label: "Relatorio de metadados",
      });
      setSaveMessage({
        type: "ok",
        text: `Registrado na cadeia de custodia como derivado «${res.evidence.original_filename}». Baixe em Derivados (aba do caso). SHA-256: ${res.evidence.sha256.slice(0, 16)}…`,
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Erro ao registrar derivado";
      setSaveMessage({ type: "err", text: msg });
    } finally {
      setSaving(false);
    }
  }

  if (!caseId) return null;

  return (
    <AnalysisPageShell
      caseId={caseId}
      title="Metadados e estrutura JPEG"
      subtitle="EXIF, IPTC, XMP, perfil ICC, MakerNotes, flags Adobe e tabelas de quantização / Huffman (jpegio + ExifTool quando disponível)."
      embedded={embedded}
    >
      <AnalysisPanel title="Evidência">
        {showEvidencePicker && (
          <>
            <p style={{ margin: "0 0 0.75rem", fontSize: "0.8rem", color: "#6b7280" }}>
              Escolha uma evidência original do caso. O relatório JSON gerado é registrado em Derivados, não
              aparece aqui para nova extração.
            </p>
            <ImageEvidenceSelector
              caseId={caseId}
              selectedId={evidenceId}
              selectionSource="original"
              excludeDerivatives
              onSelect={onSelectEvidence}
            />
          </>
        )}
        <div style={{ marginTop: "1rem" }}>
          <ProcessButton
            onClick={process}
            disabled={!evidenceId}
            running={running}
            progress={progress}
            progressLabel={progressLabel}
            label="Extrair metadados"
          />
        </div>
        {error && <MessageBox type="err" text={error} />}
      </AnalysisPanel>

      {result && (
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
              {warnings.map((w, i) => (
                <p key={i} style={{ margin: i ? "0.5rem 0 0" : 0 }}>
                  {w}
                </p>
              ))}
            </div>
          )}

          <SummaryCards
            summary={summary}
            file={file}
            tabCounts={tabCounts}
            activeTab={activeTab}
            onNavigate={setActiveTab}
            visibleTabIds={visibleTabs.map((t) => t.id)}
          />

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
              marginBottom: "1rem",
            }}
          >
            <button
              type="button"
              onClick={registerInCustody}
              disabled={!currentJobId || saving}
              style={{
                padding: "0.55rem 1.1rem",
                background: "#1a1a2e",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                cursor: saving || !currentJobId ? "wait" : "pointer",
                fontSize: "0.88rem",
                fontWeight: 600,
                opacity: !currentJobId ? 0.55 : 1,
              }}
            >
              {saving ? "Registrando…" : "Registrar relatorio na cadeia (derivado JSON)"}
            </button>
            <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
              O arquivo fica em <strong>Derivados</strong>; o download e feito la, com registro na custodia.
            </span>
          </div>
          {saveMessage && <MessageBox type={saveMessage.type} text={saveMessage.text} />}

          <div className="metadata-results-shell">
            <MetadataTabBar visibleTabs={visibleTabs} activeId={activeTab} onChange={setActiveTab} />

            <AnalysisPanel className="metadata-results-panel">
              <MetadataSectionHeader
                tabId={activeTab}
                description={metadataSectionDescription(activeTab)}
                meta={sectionMetaLine}
              />
              <div role="tabpanel" id={`metadata-panel-${activeTab}`} aria-labelledby={`metadata-tab-${activeTab}`}>
            {activeTab === "overview" && (
              <OverviewTab
                highlights={highlights}
                summary={summary}
                iccProfile={iccProfile}
                jpeg={jpeg}
                forensicInsights={forensicInsights}
              />
            )}
            {activeTab === "exif" && (
              <MetadataTagTable entries={families.exif || []} showHints hintLayout="stacked" />
            )}
            {activeTab === "iptc" && (
              <MetadataTagTable
                entries={families.iptc || []}
                emptyMessage="Nenhum campo IPTC (instale ExifTool para leitura completa)."
                hintLayout="stacked"
              />
            )}
            {activeTab === "xmp" && (
              <XmpViewer structured={xmpStructured} />
            )}
            {activeTab === "icc" && <IccTab entries={families.icc || []} profile={iccProfile} />}
            {activeTab === "makernotes" && (
              <MetadataTagTable
                entries={families.makernotes || []}
                emptyMessage="Nenhum MakerNote decodificado."
                showHints
                hintLayout="stacked"
              />
            )}
            {activeTab === "adobe" && (
              <MetadataTagTable
                entries={families.adobe || []}
                emptyMessage="Nenhuma tag Adobe / Photoshop / Flags encontrada."
                showHints
                hintLayout="stacked"
              />
            )}
            {activeTab === "jpeg" && <JpegStructureTab jpeg={jpeg} />}
            {activeTab === "other" && <MetadataTagTable entries={families.other || []} hintLayout="stacked" />}
              </div>
            </AnalysisPanel>
          </div>
        </>
      )}
    </AnalysisPageShell>
  );
}

function SummaryCards({
  summary,
  file,
  tabCounts,
  activeTab,
  onNavigate,
  visibleTabIds,
}: {
  summary: Record<string, unknown>;
  file: Record<string, unknown>;
  tabCounts: Record<TabId, number>;
  activeTab: TabId;
  onNavigate: (tab: TabId) => void;
  visibleTabIds: TabId[];
}) {
  const staticCards = [
    { label: "Formato", value: String(file.format || "—") },
    { label: "Dimensões", value: `${file.width || "?"} × ${file.height || "?"}` },
    {
      label: "Motores",
      value: Array.isArray(summary.metadata_engines) && summary.metadata_engines.length
        ? (summary.metadata_engines as string[]).join(" + ")
        : String(summary.metadata_engine || "—"),
    },
  ];

  const navigable: { tabId: TabId; label: string; value: string; hint?: string }[] = [];
  if (visibleTabIds.includes("exif"))
    navigable.push({ tabId: "exif", label: "EXIF", value: String(tabCounts.exif) });
  if (visibleTabIds.includes("xmp"))
    navigable.push({
      tabId: "xmp",
      label: "XMP",
      value: summary.has_xmp_packet ? String(tabCounts.xmp) : String(tabCounts.xmp),
      hint: summary.has_xmp_packet ? "com pacote" : undefined,
    });
  if (visibleTabIds.includes("adobe"))
    navigable.push({ tabId: "adobe", label: "Adobe", value: String(tabCounts.adobe) });
  if (visibleTabIds.includes("makernotes"))
    navigable.push({ tabId: "makernotes", label: "MakerNotes", value: String(tabCounts.makernotes) });
  if (visibleTabIds.includes("icc"))
    navigable.push({ tabId: "icc", label: "ICC", value: String(tabCounts.icc) });
  if (visibleTabIds.includes("iptc"))
    navigable.push({ tabId: "iptc", label: "IPTC", value: String(tabCounts.iptc) });
  if (visibleTabIds.includes("jpeg"))
    navigable.push({
      tabId: "jpeg",
      label: "JPEG",
      value: summary.jpeg_structure_available
        ? `Q:${summary.quantization_table_count}`
        : "N/A",
      hint: summary.jpeg_structure_available ? "estrutura" : undefined,
    });

  return (
    <div className="metadata-summary-grid">
      {staticCards.map((c) => (
        <div key={c.label} className="metadata-summary-card">
          <div className="metadata-summary-card__label">{c.label}</div>
          <div className="metadata-summary-card__value">{c.value}</div>
        </div>
      ))}
      {navigable.map((c) => {
        const def = tabDefById(c.tabId);
        const isActive = activeTab === c.tabId;
        return (
          <button
            key={c.tabId}
            type="button"
            className={[
              "metadata-summary-card",
              "metadata-summary-card--clickable",
              isActive ? "metadata-summary-card--active" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            style={{ "--metadata-card-accent": def.accentColor } as CSSProperties}
            onClick={() => onNavigate(c.tabId)}
            title={`Abrir aba ${def.label}`}
          >
            <div className="metadata-summary-card__label">
              {def.icon} {c.label}
            </div>
            <div className="metadata-summary-card__value">{c.value}</div>
            {c.hint && <div className="metadata-summary-card__hint">{c.hint}</div>}
          </button>
        );
      })}
    </div>
  );
}

function OverviewTab({
  highlights,
  summary,
  iccProfile,
  jpeg,
  forensicInsights,
}: {
  highlights: MetadataTag[];
  summary: Record<string, unknown>;
  iccProfile: Record<string, unknown>;
  jpeg: Record<string, unknown>;
  forensicInsights: ForensicInsight[];
}) {
  return (
    <div>
      <ForensicInsightsPanel insights={forensicInsights} />
      <p style={{ fontSize: "0.85rem", color: "#6b7280", marginTop: 0 }}>
        GPS: {summary.has_gps ? "detectado" : "não"} · ICC: {summary.has_icc ? "sim" : "não"} · MakerNotes:{" "}
        {summary.has_makernotes ? "sim" : "não"} · Tags Adobe: {summary.has_adobe_tags ? "sim" : "não"}
      </p>
      <h4 style={{ fontSize: "0.9rem", margin: "1rem 0 0.5rem" }}>Campos forenses frequentes</h4>
      <MetadataTagTable entries={highlights} emptyMessage="Nenhum campo em destaque." showHints hintLayout="stacked" />
      {Boolean(iccProfile.available) && (
        <>
          <h4 style={{ fontSize: "0.9rem", margin: "1.25rem 0 0.5rem" }}>Perfil ICC (cabeçalho)</h4>
          <IccProfileBlock profile={iccProfile} />
        </>
      )}
      {Boolean(jpeg.available) && (
        <p style={{ fontSize: "0.85rem", color: "#0369a1", marginTop: "1rem" }}>
          Estrutura JPEG disponível — veja a aba &quot;Estrutura JPEG&quot;.
        </p>
      )}
    </div>
  );
}

function IccTab({ entries, profile }: { entries: MetadataTag[]; profile: Record<string, unknown> }) {
  return (
    <div>
      {Boolean(profile.available) && <IccProfileBlock profile={profile} />}
      <h4 style={{ fontSize: "0.9rem", margin: "1rem 0 0.5rem" }}>Tags ICC (metadados)</h4>
      <MetadataTagTable entries={entries} showHints hintLayout="stacked" />
    </div>
  );
}

function IccProfileBlock({ profile }: { profile: Record<string, unknown> }) {
  const rows: Array<[string, unknown]> = [
    ["Tamanho", profile.size_bytes],
    ["CMM", profile.cmm_type],
    ["Classe", profile.device_class],
    ["Espaço de cor", profile.color_space],
    ["PCS", profile.profile_connection_space],
    ["Tags no perfil", profile.tag_count],
    ["Fonte", profile.source],
  ];
  return (
    <table style={{ fontSize: "0.85rem", borderCollapse: "collapse" }}>
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={String(k)}>
            <td style={{ padding: "0.35rem 0.75rem 0.35rem 0", color: "#6b7280", fontWeight: 500 }}>{k}</td>
            <td style={{ padding: "0.35rem 0" }}>{String(v ?? "—")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function JpegStructureTab({ jpeg }: { jpeg: Record<string, unknown> }) {
  if (!jpeg.available) {
    return (
      <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>
        {(jpeg.reason as string) || "Estrutura JPEG indisponível para este arquivo."}
      </p>
    );
  }

  const quant = (jpeg.quantization_tables || []) as QuantTable[];
  const dc = (jpeg.huffman_dc_tables || []) as HuffTable[];
  const ac = (jpeg.huffman_ac_tables || []) as HuffTable[];
  const components = (jpeg.components || []) as Record<string, unknown>[];
  const markers = (jpeg.marker_sequence || []) as JpegMarker[];

  return (
    <div className="jpeg-structure-layout">
      <div className="jpeg-structure-summary">
        <span className="jpeg-structure-summary__item">
          <strong>Dimensões:</strong> {String(jpeg.image_width)}×{String(jpeg.image_height)}
        </span>
        <span className="jpeg-structure-summary__item">
          <strong>Componentes:</strong> {String(jpeg.num_components)}
        </span>
        <span className="jpeg-structure-summary__item">
          <strong>Modo:</strong> {jpeg.progressive ? "progressive" : "baseline"}
        </span>
        <span className="jpeg-structure-summary__item">
          <strong>Espaço de cor:</strong> {String(jpeg.jpeg_color_space)}
        </span>
      </div>

      {markers.length > 0 && (
        <section className="jpeg-structure-card">
          <h4 className="jpeg-structure-card__title">Sequência de marcadores JPEG</h4>
          {jpeg.marker_summary != null ? (
            <p className="jpeg-structure-card__subtitle">{String(jpeg.marker_summary)}</p>
          ) : null}
          <div style={{ maxHeight: 280, overflow: "auto", border: "1px solid #e5e7eb", borderRadius: 6 }}>
            <table style={{ width: "100%", fontSize: "0.78rem", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "#f3f4f6", position: "sticky", top: 0 }}>
                  <th style={th}>#</th>
                  <th style={th}>Offset</th>
                  <th style={th}>Código</th>
                  <th style={th}>Marcador</th>
                  <th style={th}>Tamanho</th>
                  <th style={th}>Detalhe</th>
                </tr>
              </thead>
              <tbody>
                {markers.map((m) => (
                  <tr key={`${m.index}-${m.offset}`} style={{ borderTop: "1px solid #f3f4f6" }}>
                    <td style={td}>{m.index}</td>
                    <td style={{ ...td, fontFamily: "monospace" }}>0x{m.offset.toString(16).toUpperCase()}</td>
                    <td style={{ ...td, fontFamily: "monospace", color: "#1e40af" }}>{m.code_hex}</td>
                    <td style={{ ...td, fontWeight: 600 }}>{m.name}</td>
                    <td style={td}>{m.segment_length != null ? m.segment_length : "—"}</td>
                    <td style={{ ...td, color: "#6b7280", fontSize: "0.72rem" }}>
                      {[m.identifier, m.note].filter(Boolean).join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {components.length > 0 && (
        <section className="jpeg-structure-card">
          <h4 className="jpeg-structure-card__title">Componentes de cor</h4>
          <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f3f4f6" }}>
                <th style={th}>Componente</th>
                <th style={th}>Amostragem H×V</th>
                <th style={th}>Tabela Q</th>
                <th style={th}>Huffman DC</th>
                <th style={th}>Huffman AC</th>
              </tr>
            </thead>
            <tbody>
              {components.map((c, i) => (
                <tr key={i} style={{ borderTop: "1px solid #eee" }}>
                  <td style={td}>{String(c.label)}</td>
                  <td style={td}>
                    {String(c.h_samp_factor)}×{String(c.v_samp_factor)}
                  </td>
                  <td style={td}>{String(c.quant_table_index)}</td>
                  <td style={td}>{String(c.dc_huff_table_index)}</td>
                  <td style={td}>{String(c.ac_huff_table_index)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {quant.length > 0 && (
        <section className="jpeg-structure-card">
          <h4 className="jpeg-structure-card__title">Tabelas de quantização (DQT)</h4>
          <div className="jpeg-structure-grid-2">
            {quant.map((q) => (
              <Matrix8x8 key={q.index} matrix={q.matrix} title={`${q.label} (índice ${q.index})`} />
            ))}
          </div>
        </section>
      )}

      {dc.length > 0 && (
        <section className="jpeg-structure-card">
          <h4 className="jpeg-structure-card__title">Tabelas Huffman DC (DHT)</h4>
          <div className="jpeg-huffman-grid">
            {dc.map((h) => (
              <HuffmanBlock key={`dc-${h.index}`} table={h} />
            ))}
          </div>
        </section>
      )}

      {ac.length > 0 && (
        <section className="jpeg-structure-card">
          <h4 className="jpeg-structure-card__title">Tabelas Huffman AC (DHT)</h4>
          <div className="jpeg-huffman-grid">
            {ac.map((h) => (
              <HuffmanBlock key={`ac-${h.index}`} table={h} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function HuffmanBlock({ table }: { table: HuffTable }) {
  const codeCount = table.total_codes ?? table.counts?.reduce((a, b) => a + b, 0);
  return (
    <div className="jpeg-huffman-card">
      <div className="jpeg-huffman-card__title">
        {table.class} — índice {table.index} ({codeCount} códigos)
      </div>
      <div className="jpeg-huffman-card__row">
        <strong>BITS:</strong> {table.counts?.join(", ")}
      </div>
      {table.symbols?.length > 0 && (
        <div className="jpeg-huffman-card__row">
          <strong>Símbolos:</strong> {table.symbols.slice(0, 64).join(", ")}
          {table.symbols.length > 64 ? "…" : ""}
        </div>
      )}
    </div>
  );
}

const th: CSSProperties = { textAlign: "left", padding: "0.4rem 0.5rem" };
const td: CSSProperties = { padding: "0.4rem 0.5rem" };
