import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { MessageBox } from "@/components/AnalysisPageShell";

export type GeneratorCatalog = {
  id: string;
  label: string;
  deploy_year?: number | null;
  /** EER % per detector in API order (DF Arena, SLS, WeDefense). */
  detector_eer_percent?: (number | null)[] | null;
};
export type BaseCatalog = {
  id: string;
  label: string;
  description?: string;
  paper_title?: string | null;
  paper_url?: string | null;
  generators: GeneratorCatalog[];
};
export type MacroCategory = {
  id: string;
  label: string;
  year_range?: string;
  description: string;
  bases: BaseCatalog[];
};

export type ReferencePopulationItem = { base_group: string; subgroup: string };
export type ReferencePopulationRole = "off" | "fit" | "test" | "both";
export type ReferencePopulationEntry = ReferencePopulationItem & { role: ReferencePopulationRole };

export function referenceItemKey(item: ReferencePopulationItem): string {
  return `${item.base_group}/${item.subgroup}`;
}

export function itemsToEntries(
  items: ReferencePopulationItem[],
  role: ReferencePopulationRole = "both"
): ReferencePopulationEntry[] {
  return items.map((item) => ({ ...item, role }));
}

export function entriesToItems(entries: ReferencePopulationEntry[]): ReferencePopulationItem[] {
  return entries
    .filter((entry) => entry.role !== "off")
    .map(({ base_group, subgroup }) => ({ base_group, subgroup }));
}

export function referencePopulationPayload(
  entries: ReferencePopulationEntry[],
  enableSplitRoles: boolean
): { items?: ReferencePopulationItem[]; fit_items?: ReferencePopulationItem[]; test_items?: ReferencePopulationItem[] } {
  const active = entries.filter((entry) => entry.role !== "off");
  const mapItem = ({ base_group, subgroup }: ReferencePopulationItem) => ({ base_group, subgroup });
  if (!enableSplitRoles) {
    return { items: active.map(mapItem) };
  }
  return {
    fit_items: active.filter((entry) => entry.role === "fit" || entry.role === "both").map(mapItem),
    test_items: active.filter((entry) => entry.role === "test" || entry.role === "both").map(mapItem),
  };
}

export function referenceSelectionCounts(
  entries: ReferencePopulationEntry[],
  enableSplitRoles: boolean
): { total: number; fit: number; test: number } {
  const active = entries.filter((entry) => entry.role !== "off");
  if (!enableSplitRoles) {
    return { total: active.length, fit: active.length, test: active.length };
  }
  return {
    total: active.length,
    fit: active.filter((entry) => entry.role === "fit" || entry.role === "both").length,
    test: active.filter((entry) => entry.role === "test" || entry.role === "both").length,
  };
}

const ROLE_LABELS: Record<ReferencePopulationRole, string> = {
  off: "—",
  fit: "Treino+calib",
  test: "Teste",
  both: "Treino+teste",
};

/** Visual accent per macro block in the drawer (left border + soft tint). */
const MACRO_ACCENTS: Record<string, string> = {
  asv_classic: "#2563eb",
  codec_conditions: "#7c3aed",
  deepfake_challenges: "#059669",
  in_the_wild: "#d97706",
};

function macroAccent(macroId: string): string {
  return MACRO_ACCENTS[macroId] ?? "#64748b";
}

function countCategorySelection(
  category: MacroCategory,
  getRole: (item: ReferencePopulationItem) => ReferencePopulationRole
): { active: number; total: number } {
  let active = 0;
  let total = 0;
  for (const base of category.bases) {
    for (const generator of base.generators) {
      total += 1;
      if (getRole({ base_group: base.id, subgroup: generator.id }) !== "off") {
        active += 1;
      }
    }
  }
  return { active, total };
}

const macroPanelStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 10,
  overflow: "hidden",
  marginBottom: "0.85rem",
  background: "#fff",
};

const macroHeaderButtonStyle: React.CSSProperties = {
  width: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "0.65rem",
  padding: "0.65rem 0.75rem",
  border: "none",
  background: "transparent",
  cursor: "pointer",
  textAlign: "left",
};

export type ReferenceLrResult = {
  success?: boolean;
  error?: string;
  hypothesis_positive?: string;
  hypothesis_negative?: string;
  selected_count?: number;
  fit_count?: number;
  test_count?: number;
  split_roles_separated?: boolean;
  fit_sample_rows?: number;
  test_sample_rows?: number;
  sample_rows?: number;
  test_metrics?: {
    rows?: number;
    real_rows?: number;
    fake_rows?: number;
    cllr?: number;
    min_cllr?: number;
    auc?: number;
    eer?: number;
    wrong_extreme_lr_count?: number;
  };
  identity_mse?: number;
  bigauss?: {
    eer?: number;
    sigma?: number;
    mu_fake?: number;
    mu_real?: number;
  };
  questioned?: {
    log10_lr?: number;
    lr?: number;
    logreg_z?: number;
    cdf_p?: number;
  };
  note?: string;
  meta_classifier?: string;
  meta_classifier_label?: string;
  augmented_reference?: boolean;
  sample_multiplier?: number;
  latent_typicality?: boolean;
  used_cache?: boolean;
  typicality_config?: {
    system?: string;
    distance?: string;
    k?: number;
  };
};

export function flattenCatalog(categories: MacroCategory[]): ReferencePopulationItem[] {
  return categories.flatMap((category) =>
    category.bases.flatMap((base) =>
      base.generators.map((generator) => ({ base_group: base.id, subgroup: generator.id }))
    )
  );
}

export function formatMetric(value: unknown, digits = 4): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

export function formatGeneratorDetectorEers(eers?: (number | null)[] | null): string {
  if (!eers?.length) return "";
  const parts = eers.map((value) =>
    typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "—"
  );
  return ` (${parts.join(", ")})`;
}

export const smallButtonStyle: React.CSSProperties = {
  padding: "0.35rem 0.6rem",
  fontSize: "0.75rem",
  borderRadius: 6,
  border: "1px solid #d1d5db",
  background: "#fff",
  color: "#374151",
  cursor: "pointer",
};

export const referenceGroupStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 6,
  background: "#fff",
  padding: "0.45rem 0.6rem",
};

export const referenceSummaryStyle: React.CSSProperties = {
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "0.75rem",
  fontSize: "0.84rem",
  color: "#374151",
};

export const referenceGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "0.35rem",
  marginTop: "0.55rem",
  paddingTop: "0.5rem",
  borderTop: "1px solid #f3f4f6",
};

export const referenceItemStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.4rem",
  fontSize: "0.78rem",
  color: "#374151",
  padding: "0.25rem 0.35rem",
  borderRadius: 4,
  background: "#f9fafb",
};

export const imgStyle: React.CSSProperties = {
  width: "100%",
  borderRadius: 6,
  border: "1px solid #e5e7eb",
  display: "block",
};

export const capStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "#6b7280",
  marginTop: 4,
  textAlign: "center",
};

export const placeholderStyle: React.CSSProperties = {
  aspectRatio: "1",
  minHeight: 180,
  background: "#f3f4f6",
  borderRadius: 6,
  border: "1px solid #e5e7eb",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#9ca3af",
  fontSize: "0.8rem",
};

export function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "0.6rem", background: "#f9fafb" }}>
      <div style={{ fontSize: "0.72rem", color: "#6b7280", marginBottom: "0.2rem" }}>{label}</div>
      <div style={{ fontSize: "1rem", color: "#111827", fontWeight: 700 }}>{value}</div>
    </div>
  );
}

export function ForensicImage({
  src,
  label,
  imageStyle,
  placeholderStyle: placeholderOverride,
  captionStyle,
}: {
  src: string | null;
  label: string;
  imageStyle?: React.CSSProperties;
  placeholderStyle?: React.CSSProperties;
  captionStyle?: React.CSSProperties;
}) {
  const cap = captionStyle ?? capStyle;
  if (!src) {
    return (
      <figure style={{ margin: 0, width: "100%" }}>
        <div style={{ ...placeholderStyle, ...placeholderOverride }}>—</div>
        <figcaption style={cap}>{label}</figcaption>
      </figure>
    );
  }
  return (
    <figure style={{ margin: 0, width: "100%" }}>
      <img src={src} alt={label} style={{ ...imgStyle, ...imageStyle }} />
      <figcaption style={cap}>{label}</figcaption>
    </figure>
  );
}

function roleFlags(role: ReferencePopulationRole): { inFit: boolean; inTest: boolean } {
  return {
    inFit: role === "fit" || role === "both",
    inTest: role === "test" || role === "both",
  };
}

function roleFromFlags(inFit: boolean, inTest: boolean): ReferencePopulationRole {
  if (inFit && inTest) return "both";
  if (inFit) return "fit";
  if (inTest) return "test";
  return "off";
}

function mergePoolRole(
  current: ReferencePopulationRole,
  pool: "fit" | "test",
  checked: boolean
): ReferencePopulationRole {
  const flags = roleFlags(current);
  if (pool === "fit") flags.inFit = checked;
  else flags.inTest = checked;
  return roleFromFlags(flags.inFit, flags.inTest);
}

function countCategoryInPool(
  category: MacroCategory,
  getRole: (item: ReferencePopulationItem) => ReferencePopulationRole,
  pool: "fit" | "test"
): { active: number; total: number } {
  let active = 0;
  let total = 0;
  for (const base of category.bases) {
    for (const generator of base.generators) {
      total += 1;
      const flags = roleFlags(getRole({ base_group: base.id, subgroup: generator.id }));
      if (pool === "fit" ? flags.inFit : flags.inTest) active += 1;
    }
  }
  return { active, total };
}

type DrawerPoolTab = "fit" | "test";

const drawerTabStyle = (active: boolean): CSSProperties => ({
  flex: 1,
  padding: "0.5rem 0.65rem",
  fontSize: "0.8rem",
  fontWeight: active ? 700 : 500,
  color: active ? "#1e3a8a" : "#6b7280",
  background: active ? "#fff" : "#f3f4f6",
  border: "1px solid",
  borderColor: active ? "#93c5fd" : "#e5e7eb",
  borderRadius: 8,
  cursor: "pointer",
});

export function ReferencePopulationSelector({
  catalog,
  loading,
  error,
  entries,
  onChange,
  disabled,
  enableSplitRoles = false,
  defaultPresetItems,
  subgroupUnitLabel = "geradores",
  detectorEerLabels,
  hypothesisHint = "LR positiva favorece H1 = real/autêntica. Defina quais subgrupos entram no treino/calibração e quais no teste.",
}: {
  catalog: MacroCategory[];
  loading: boolean;
  error: string | null;
  entries: ReferencePopulationEntry[];
  onChange: (entries: ReferencePopulationEntry[]) => void;
  disabled: boolean;
  enableSplitRoles?: boolean;
  defaultPresetItems?: ReferencePopulationItem[];
  subgroupUnitLabel?: string;
  detectorEerLabels?: string[];
  hypothesisHint?: string;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [openMacros, setOpenMacros] = useState<Set<string>>(new Set());
  const [drawerTab, setDrawerTab] = useState<DrawerPoolTab>("fit");
  const drawerWasOpen = useRef(false);

  const entryMap = new Map(entries.map((entry) => [referenceItemKey(entry), entry]));
  const getRole = (item: ReferencePopulationItem): ReferencePopulationRole =>
    entryMap.get(referenceItemKey(item))?.role ?? "off";

  const counts = referenceSelectionCounts(entries, enableSplitRoles);
  const activePool: DrawerPoolTab | null = enableSplitRoles ? drawerTab : null;
  const totalGenerators = catalog.reduce(
    (sum, category) =>
      sum + category.bases.reduce((baseSum, base) => baseSum + base.generators.length, 0),
    0
  );

  const isInActivePool = (item: ReferencePopulationItem): boolean => {
    const flags = roleFlags(getRole(item));
    if (!activePool) return flags.inFit || flags.inTest;
    return activePool === "fit" ? flags.inFit : flags.inTest;
  };

  const macrosWithSelection = useMemo(() => {
    const hasSelection = (category: MacroCategory) => {
      if (activePool) {
        return countCategoryInPool(category, getRole, activePool).active > 0;
      }
      return countCategorySelection(category, getRole).active > 0;
    };
    return catalog.filter(hasSelection).map((category) => category.id);
  }, [catalog, entries, activePool]);

  useEffect(() => {
    const justOpened = drawerOpen && !drawerWasOpen.current;
    drawerWasOpen.current = drawerOpen;
    if (!justOpened) return;

    const initial = new Set(macrosWithSelection);
    if (initial.size === 0 && catalog[0]) {
      initial.add(catalog[0].id);
    }
    setOpenMacros(initial);
  }, [drawerOpen, catalog, macrosWithSelection]);

  const upsertRole = (item: ReferencePopulationItem, role: ReferencePopulationRole) => {
    const key = referenceItemKey(item);
    const next = entries.filter((entry) => referenceItemKey(entry) !== key);
    if (role !== "off") {
      next.push({ ...item, role });
    }
    onChange(next);
  };

  const togglePool = (item: ReferencePopulationItem, pool: DrawerPoolTab, checked: boolean) => {
    upsertRole(item, mergePoolRole(getRole(item), pool, checked));
  };

  const setManyInPool = (items: ReferencePopulationItem[], pool: DrawerPoolTab, checked: boolean) => {
    const keys = new Set(items.map(referenceItemKey));
    const rest = entries.filter((entry) => !keys.has(referenceItemKey(entry)));
    const updated: ReferencePopulationEntry[] = [];
    for (const item of items) {
      const existing = entryMap.get(referenceItemKey(item));
      const role = mergePoolRole(existing?.role ?? "off", pool, checked);
      if (role !== "off") {
        updated.push({ ...item, role });
      }
    }
    onChange([...rest, ...updated]);
  };

  const setRole = (item: ReferencePopulationItem, role: ReferencePopulationRole) => {
    upsertRole(item, role);
  };

  const setMany = (items: ReferencePopulationItem[], role: ReferencePopulationRole) => {
    const keys = new Set(items.map(referenceItemKey));
    const rest = entries.filter((entry) => !keys.has(referenceItemKey(entry)));
    if (role === "off") {
      onChange(rest);
      return;
    }
    onChange([...rest, ...items.map((item) => ({ ...item, role }))]);
  };

  const toggleMacroOpen = (macroId: string) => {
    setOpenMacros((current) => {
      const next = new Set(current);
      if (next.has(macroId)) next.delete(macroId);
      else next.add(macroId);
      return next;
    });
  };

  const expandAllMacros = () => setOpenMacros(new Set(catalog.map((category) => category.id)));
  const collapseAllMacros = () => setOpenMacros(new Set());

  const applyPreset = (items: ReferencePopulationItem[]) => {
    onChange(itemsToEntries(items, enableSplitRoles ? "both" : "both"));
  };

  const selectAllInDrawer = () => {
    const all = flattenCatalog(catalog);
    if (activePool) {
      setManyInPool(all, activePool, true);
      return;
    }
    onChange(itemsToEntries(all, "both"));
  };

  const clearActivePool = () => {
    if (activePool) {
      setManyInPool(flattenCatalog(catalog), activePool, false);
      return;
    }
    onChange([]);
  };

  const searchLower = search.trim().toLowerCase();
  const matchesSearch = (text: string) => !searchLower || text.toLowerCase().includes(searchLower);

  if (loading) {
    return (
      <p style={{ marginTop: "1rem", fontSize: "0.85rem", color: "#6b7280" }}>
        Carregando catálogo de população de referência…
      </p>
    );
  }

  if (error) {
    return (
      <p style={{ marginTop: "1rem", fontSize: "0.85rem", color: "#b91c1c" }}>
        Erro ao carregar catálogo: {error}
      </p>
    );
  }

  const drawer = drawerOpen ? (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Seleção da população de referência LR"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "flex",
        justifyContent: "flex-end",
        background: "rgba(15, 23, 42, 0.45)",
      }}
      onClick={() => setDrawerOpen(false)}
    >
      <div
        style={{
          width: "min(520px, 100vw)",
          height: "100%",
          background: "#fff",
          boxShadow: "-8px 0 24px rgba(0,0,0,0.12)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          style={{
            padding: "1rem 1rem 0.75rem",
            borderBottom: "1px solid #e5e7eb",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "0.75rem",
          }}
        >
          <div>
            <h3 style={{ margin: 0, fontSize: "1rem", color: "#1a1a2e" }}>População de referência LR</h3>
            <p style={{ margin: "0.35rem 0 0", fontSize: "0.76rem", color: "#6b7280", lineHeight: 1.45 }}>
              {hypothesisHint}
            </p>
          </div>
          <button type="button" onClick={() => setDrawerOpen(false)} style={smallButtonStyle}>
            Fechar
          </button>
        </div>

        <div style={{ padding: "0.75rem 1rem", borderBottom: "1px solid #f3f4f6" }}>
          <input
            type="search"
            placeholder="Buscar base ou gerador…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{
              width: "100%",
              padding: "0.45rem 0.6rem",
              borderRadius: 6,
              border: "1px solid #d1d5db",
              fontSize: "0.85rem",
            }}
          />
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.55rem" }}>
            {defaultPresetItems && defaultPresetItems.length > 0 && (
              <button
                type="button"
                disabled={disabled}
                onClick={() => applyPreset(defaultPresetItems)}
                style={smallButtonStyle}
              >
                Default
              </button>
            )}
            <button type="button" disabled={disabled} onClick={selectAllInDrawer} style={smallButtonStyle}>
              {activePool ? `Todas (${activePool === "fit" ? "treino+calib" : "teste"})` : "Todas"}
            </button>
            <button type="button" disabled={disabled} onClick={clearActivePool} style={smallButtonStyle}>
              {activePool ? `Limpar aba` : "Limpar"}
            </button>
            <button type="button" disabled={disabled} onClick={expandAllMacros} style={smallButtonStyle}>
              Expandir macros
            </button>
            <button type="button" disabled={disabled} onClick={collapseAllMacros} style={smallButtonStyle}>
              Recolher macros
            </button>
          </div>
          {enableSplitRoles && (
            <p style={{ margin: "0.55rem 0 0", fontSize: "0.72rem", color: "#6b7280" }}>
              Use as abas para marcar subgrupos em <strong>treino+calibração</strong> (splits 1–2) e em{" "}
              <strong>teste</strong> (split 3). O mesmo subgrupo pode aparecer nas duas abas.
            </p>
          )}
        </div>

        {enableSplitRoles ? (
          <div
            style={{
              display: "flex",
              gap: "0.45rem",
              padding: "0.65rem 1rem 0",
              borderBottom: "1px solid #e5e7eb",
              background: "#fff",
            }}
          >
            <button
              type="button"
              style={drawerTabStyle(drawerTab === "fit")}
              onClick={() => setDrawerTab("fit")}
            >
              Treino + calibração
              <span style={{ display: "block", fontSize: "0.68rem", fontWeight: 600, marginTop: 2 }}>
                {counts.fit} selecionado{counts.fit === 1 ? "" : "s"}
              </span>
            </button>
            <button
              type="button"
              style={drawerTabStyle(drawerTab === "test")}
              onClick={() => setDrawerTab("test")}
            >
              Teste
              <span style={{ display: "block", fontSize: "0.68rem", fontWeight: 600, marginTop: 2 }}>
                {counts.test} selecionado{counts.test === 1 ? "" : "s"}
              </span>
            </button>
          </div>
        ) : null}

        <div style={{ flex: 1, overflow: "auto", padding: "0.75rem 1rem 1rem", background: "#f8fafc" }}>
          {catalog.map((category) => {
            const visibleBases = category.bases
              .map((base) => ({
                base,
                generators: base.generators.filter(
                  (generator) =>
                    matchesSearch(category.label) ||
                    matchesSearch(base.label) ||
                    matchesSearch(base.id) ||
                    matchesSearch(generator.label) ||
                    matchesSearch(generator.id)
                ),
              }))
              .filter((row) => row.generators.length > 0);
            if (visibleBases.length === 0) return null;

            const { active: categoryActive, total: categoryTotal } = activePool
              ? countCategoryInPool(category, getRole, activePool)
              : countCategorySelection(category, getRole);
            const accent = macroAccent(category.id);
            const isSearchHit = Boolean(searchLower);
            const macroExpanded = isSearchHit || openMacros.has(category.id);

            return (
              <section
                key={category.id}
                style={{
                  ...macroPanelStyle,
                  borderLeft: `4px solid ${accent}`,
                  boxShadow: macroExpanded ? "0 1px 3px rgba(15,23,42,0.06)" : "none",
                }}
              >
                <button
                  type="button"
                  onClick={() => toggleMacroOpen(category.id)}
                  style={{
                    ...macroHeaderButtonStyle,
                    background: macroExpanded ? `${accent}10` : "#f9fafb",
                  }}
                  aria-expanded={macroExpanded}
                >
                  <span style={{ display: "flex", flexDirection: "column", gap: "0.15rem", minWidth: 0 }}>
                    <span style={{ fontSize: "0.86rem", fontWeight: 700, color: "#111827" }}>
                      {macroExpanded ? "▾" : "▸"} {category.label}
                      {category.year_range ? (
                        <span style={{ color: "#6b7280", fontWeight: 500, fontSize: "0.76rem" }}>
                          {" "}
                          ({category.year_range})
                        </span>
                      ) : null}
                    </span>
                    {!macroExpanded && category.description ? (
                      <span
                        style={{
                          fontSize: "0.72rem",
                          color: "#6b7280",
                          lineHeight: 1.35,
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {category.description}
                      </span>
                    ) : null}
                  </span>
                  <span
                    style={{
                      flexShrink: 0,
                      fontSize: "0.72rem",
                      fontWeight: 600,
                      color: categoryActive > 0 ? accent : "#6b7280",
                      background: "#fff",
                      border: `1px solid ${categoryActive > 0 ? accent : "#e5e7eb"}`,
                      borderRadius: 999,
                      padding: "0.15rem 0.5rem",
                    }}
                  >
                    {categoryActive}/{categoryTotal}
                  </span>
                </button>

                {macroExpanded ? (
                  <div style={{ padding: "0.55rem 0.65rem 0.75rem", borderTop: "1px solid #eef2f7" }}>
                    <p
                      style={{
                        margin: "0 0 0.55rem",
                        fontSize: "0.72rem",
                        color: "#6b7280",
                        lineHeight: 1.45,
                      }}
                    >
                      {category.description}
                    </p>
                    {visibleBases.map(({ base, generators }) => {
                      const baseItems = generators.map((g) => ({
                        base_group: base.id,
                        subgroup: g.id,
                      }));
                      const baseActive = baseItems.filter((item) => isInActivePool(item)).length;

                      return (
                        <div
                          key={base.id}
                          style={{
                            border: "1px solid #e5e7eb",
                            borderRadius: 8,
                            marginBottom: "0.5rem",
                            background: "#fff",
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              padding: "0.5rem 0.6rem",
                              background: "#fafafa",
                              borderBottom: "1px solid #f3f4f6",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              gap: "0.5rem",
                            }}
                          >
                            <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "#374151" }}>
                              {base.label}
                              <span style={{ color: "#9ca3af", fontWeight: 500, marginLeft: 6 }}>
                                {baseActive}/{generators.length}
                              </span>
                            </span>
                            <span style={{ display: "flex", gap: "0.25rem" }}>
                              <button
                                type="button"
                                disabled={disabled}
                                style={smallButtonStyle}
                                title="Selecionar todos desta base na aba ativa"
                                onClick={() => {
                                  if (activePool) setManyInPool(baseItems, activePool, true);
                                  else setMany(baseItems, "both");
                                }}
                              >
                                +
                              </button>
                              <button
                                type="button"
                                disabled={disabled}
                                style={smallButtonStyle}
                                title="Limpar esta base na aba ativa"
                                onClick={() => {
                                  if (activePool) setManyInPool(baseItems, activePool, false);
                                  else setMany(baseItems, "off");
                                }}
                              >
                                −
                              </button>
                            </span>
                          </div>
                          <div
                            style={{
                              padding: "0.35rem 0.55rem 0.5rem",
                              maxHeight: generators.length > 6 ? 200 : undefined,
                              overflowY: generators.length > 6 ? "auto" : undefined,
                            }}
                          >
                            {generators.map((generator) => {
                              const item = { base_group: base.id, subgroup: generator.id };
                              const role = getRole(item);
                              const flags = roleFlags(role);
                              const checked = activePool
                                ? activePool === "fit"
                                  ? flags.inFit
                                  : flags.inTest
                                : role !== "off";
                              const alsoInOtherPool =
                                activePool === "fit"
                                  ? flags.inTest
                                  : activePool === "test"
                                    ? flags.inFit
                                    : false;
                              return (
                                <div
                                  key={referenceItemKey(item)}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.45rem",
                                    padding: "0.32rem 0.2rem",
                                    fontSize: "0.78rem",
                                    borderRadius: 4,
                                    background: checked ? `${accent}08` : "transparent",
                                  }}
                                >
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    disabled={disabled}
                                    onChange={(event) => {
                                      if (activePool) {
                                        togglePool(item, activePool, event.target.checked);
                                        return;
                                      }
                                      setRole(item, event.target.checked ? "both" : "off");
                                    }}
                                  />
                                  <span style={{ flex: 1, minWidth: 0, color: "#374151" }}>
                                    {generator.label}
                                    {generator.deploy_year ? (
                                      <span style={{ color: "#9ca3af", marginLeft: 6 }}>
                                        {generator.deploy_year}
                                      </span>
                                    ) : null}
                                    {alsoInOtherPool ? (
                                      <span
                                        style={{
                                          display: "inline-block",
                                          marginLeft: 6,
                                          fontSize: "0.66rem",
                                          color: "#6b7280",
                                          background: "#f3f4f6",
                                          borderRadius: 4,
                                          padding: "0.05rem 0.3rem",
                                        }}
                                      >
                                        também em {activePool === "fit" ? "teste" : "treino+calib"}
                                      </span>
                                    ) : null}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
      </div>
    </div>
  ) : null;

  const previewEntries = entries.filter((entry) => entry.role !== "off").slice(0, 8);

  return (
    <div style={{ marginTop: "1rem", borderTop: "1px solid #e5e7eb", paddingTop: "1rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "0.75rem",
          flexWrap: "wrap",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "#1a1a2e" }}>
            População de referência LR
          </div>
          <p style={{ margin: "0.25rem 0 0", fontSize: "0.76rem", color: "#6b7280" }}>
            {enableSplitRoles ? (
              <>
                Fit: <strong>{counts.fit}</strong> · Teste: <strong>{counts.test}</strong>
                {counts.total > Math.max(counts.fit, counts.test) ? (
                  <> · <strong>{counts.total}</strong> subgrupos ativos</>
                ) : null}
              </>
            ) : (
              <>
                <strong>{counts.total}</strong>/{totalGenerators} {subgroupUnitLabel} selecionados
              </>
            )}
          </p>
          {previewEntries.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginTop: "0.45rem" }}>
              {previewEntries.map((entry) => (
                <span
                  key={referenceItemKey(entry)}
                  style={{
                    fontSize: "0.72rem",
                    padding: "0.15rem 0.45rem",
                    borderRadius: 999,
                    background: "#f3f4f6",
                    color: "#374151",
                    border: "1px solid #e5e7eb",
                  }}
                >
                  {entry.base_group}/{entry.subgroup}
                  {enableSplitRoles && entry.role !== "both" ? ` · ${ROLE_LABELS[entry.role]}` : ""}
                </span>
              ))}
              {counts.total > previewEntries.length ? (
                <span style={{ fontSize: "0.72rem", color: "#9ca3af" }}>
                  +{counts.total - previewEntries.length} mais
                </span>
              ) : null}
            </div>
          )}
        </div>
        <button
          type="button"
          disabled={disabled}
          onClick={() => setDrawerOpen(true)}
          style={{ ...smallButtonStyle, fontWeight: 600 }}
        >
          Editar seleção…
        </button>
      </div>
      {detectorEerLabels && detectorEerLabels.length > 0 && (
        <p style={{ margin: "0.55rem 0 0", fontSize: "0.72rem", color: "#9ca3af" }}>
          EER% por gerador (ordem): {detectorEerLabels.join(" · ")}
        </p>
      )}
      {drawer}
    </div>
  );
}

export function ReferenceLrPanel({
  lr,
  tippettUrl,
  distributionUrl,
  identityUrl,
  populationUnitLabel = "imagens",
  lrPositiveLabel = "real",
  augmentedDescription,
}: {
  lr: ReferenceLrResult | null;
  tippettUrl: string | null;
  distributionUrl: string | null;
  identityUrl: string | null;
  populationUnitLabel?: string;
  lrPositiveLabel?: string;
  augmentedDescription?: string;
}) {
  if (!lr) return null;
  if (lr.success === false) {
    return (
      <MessageBox
        type="err"
        text={`LR por população de referência não calculada: ${lr.error || "erro desconhecido"}`}
      />
    );
  }
  const q = lr.questioned || {};
  const metrics = lr.test_metrics || {};
  const defaultNote =
    lrPositiveLabel === "bonafide"
      ? "LR > 1 favorece bonafide/autêntico."
      : "LR > 1 favorece real/autêntica.";

  return (
    <div style={{ marginTop: "1.5rem", borderTop: "1px solid #e5e7eb", paddingTop: "1rem" }}>
      <h4 style={{ margin: "0 0 0.25rem", fontSize: "0.95rem", color: "#1a1a2e" }}>
        LR calibrada por população de referência
      </h4>
      {lr.augmented_reference && (
        <p
          style={{
            margin: "0 0 0.75rem",
            fontSize: "0.78rem",
            color: "#1d4ed8",
            fontWeight: 500,
          }}
        >
          {augmentedDescription ||
            `População aumentada ativa (multiplicador ${lr.sample_multiplier ?? "—"}×) — inclui variações JPEG 85, WebP 80, crop+upscale e resize 50%.`}
        </p>
      )}
      {lr.latent_typicality && (
        <p
          style={{
            margin: "0 0 0.75rem",
            fontSize: "0.78rem",
            color: "#047857",
            fontWeight: 500,
          }}
        >
          Tipicidade latente (k-NN): sistema {lr.typicality_config?.system ?? "D"},{" "}
          {lr.typicality_config?.distance ?? "cosine"}, k={lr.typicality_config?.k ?? 5}.
          {lr.used_cache ? " Cache de calibração reutilizado." : ""}
        </p>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "0.6rem" }}>
        <MetricCard label={`log10(LR ${lrPositiveLabel})`} value={formatMetric(q.log10_lr)} />
        <MetricCard label={`LR ${lrPositiveLabel}`} value={formatMetric(q.lr, 3)} />
        <MetricCard label="CLLR teste" value={formatMetric(metrics.cllr)} />
        <MetricCard label="minCLLR teste" value={formatMetric(metrics.min_cllr)} />
        <MetricCard label="EER teste" value={formatMetric(metrics.eer)} />
      </div>
      <p style={{ margin: "0 0 0.75rem", fontSize: "0.78rem", color: "#6b7280" }}>
        {lr.split_roles_separated ? (
          <>
            Treino/calib: {lr.fit_count ?? "—"} subgrupos ({lr.fit_sample_rows ?? "—"} amostras) · Teste:{" "}
            {lr.test_count ?? "—"} subgrupos ({lr.test_sample_rows ?? "—"} amostras).{" "}
          </>
        ) : (
          <>
            População usada: {lr.selected_count ?? "—"} subgrupos, {lr.sample_rows ?? "—"} {populationUnitLabel}.{" "}
          </>
        )}
        Meta-classificador: {lr.meta_classifier_label || lr.meta_classifier || "—"}.{" "}
        {lr.note || defaultNote}
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "0.75rem" }}>
        <ForensicImage src={tippettUrl} label="Tippett plot" />
        <ForensicImage src={distributionUrl} label="Distribuição das LRs" />
        <ForensicImage src={identityUrl} label="Função identidade por KDE" />
      </div>
    </div>
  );
}

export const META_CLASSIFIER_OPTIONS = [
  { value: "logistic", label: "Regressao Logistica" },
  { value: "logistic_poly2", label: "Regressao Logistica (grau 2)" },
  { value: "xgboost", label: "XGBoost" },
  { value: "gradient_boosting", label: "Gradient Boosting" },
  { value: "random_forest", label: "Random Forest" },
  { value: "extra_trees", label: "Extra Trees" },
  { value: "svm_rbf", label: "SVM (RBF)" },
  { value: "mlp", label: "MLP (rede neural)" },
  { value: "kde_naive_bayes", label: "KDE Naive Bayes" },
] as const;

export function MetaClassifierSelect({
  value,
  disabled,
  onChange,
  id = "meta-classifier",
}: {
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  id?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.88rem" }}>
      <label htmlFor={id} style={{ color: "#374151" }}>
        Meta-classificador LR:
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: "0.35rem 0.6rem",
          borderRadius: 6,
          border: "1px solid #d1d5db",
          background: "#fff",
          fontSize: "0.85rem",
          color: "#1f2937",
        }}
      >
        {META_CLASSIFIER_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function SaveButton({
  label,
  filename,
  saving,
  onSave,
  primary,
}: {
  label: string;
  filename: string;
  saving: string | null;
  onSave: (filename: string, label: string) => void;
  primary?: boolean;
}) {
  const busy = saving === filename;
  return (
    <button
      type="button"
      disabled={!!saving}
      onClick={() => onSave(filename, label)}
      style={{
        padding: "0.45rem 0.85rem",
        fontSize: "0.8rem",
        borderRadius: 6,
        border: primary ? "none" : "1px solid #d1d5db",
        background: primary ? "#1a1a2e" : "#fff",
        color: primary ? "#fff" : "#374151",
        cursor: saving ? "not-allowed" : "pointer",
        opacity: saving && !busy ? 0.6 : 1,
      }}
    >
      {busy ? "Salvando…" : label}
    </button>
  );
}
