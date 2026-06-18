import { Fragment } from "react";
import type { MetadataTabId } from "@/components/metadata/metadataTabConfig";
import { METADATA_TAB_GROUPS, METADATA_TABS } from "@/components/metadata/metadataTabConfig";

const GROUP_LABEL: Record<string, string> = Object.fromEntries(
  METADATA_TAB_GROUPS.map((g) => [g.id, g.label])
);

export default function MetadataTabBar({
  visibleTabs,
  activeId,
  onChange,
  sticky = true,
}: {
  visibleTabs: { id: MetadataTabId; count?: number }[];
  activeId: MetadataTabId;
  onChange: (id: MetadataTabId) => void;
  sticky?: boolean;
}) {
  const countMap = Object.fromEntries(visibleTabs.map((t) => [t.id, t.count]));
  const visibleTabIds = new Set(visibleTabs.map((t) => t.id));

  const groups = METADATA_TAB_GROUPS.map((group) => ({
    ...group,
    tabs: METADATA_TABS.filter((t) => t.group === group.id && visibleTabIds.has(t.id)),
  })).filter((g) => g.tabs.length > 0);

  return (
    <nav
      className={`metadata-tab-bar metadata-tab-bar--inline${sticky ? " metadata-tab-bar--sticky" : ""}`}
      aria-label="Seções de metadados"
    >
      <div className="metadata-tab-bar__scroll" role="tablist" aria-label="Abas de metadados">
        {groups.map((group, groupIndex) => (
          <Fragment key={group.id}>
            {groupIndex > 0 && (
              <span className="metadata-tab-bar__sep" aria-hidden>
                |
              </span>
            )}
            {group.tabs.map((tab) => {
              const isActive = activeId === tab.id;
              const count = countMap[tab.id];
              const isOverview = tab.id === "overview";
              const groupName = GROUP_LABEL[tab.group] ?? "";
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  id={`metadata-tab-${tab.id}`}
                  title={groupName ? `${groupName} · ${tab.label}` : tab.label}
                  className={[
                    "metadata-tab",
                    isActive ? "metadata-tab--active" : "",
                    isOverview ? "metadata-tab--overview" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  style={
                    isActive
                      ? ({ "--metadata-tab-accent": tab.accentColor } as React.CSSProperties)
                      : undefined
                  }
                  onClick={() => onChange(tab.id)}
                >
                  <span className="metadata-tab__icon" aria-hidden>
                    {tab.icon}
                  </span>
                  <span className="metadata-tab__label">{tab.label}</span>
                  {count != null && count > 0 && (
                    <span
                      className={[
                        "metadata-tab__badge",
                        isOverview ? "metadata-tab__badge--overview" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </Fragment>
        ))}
      </div>
    </nav>
  );
}
