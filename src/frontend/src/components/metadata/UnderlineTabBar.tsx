export interface UnderlineTabItem {
  id: string;
  label: string;
  icon?: string;
  count?: number;
  accentColor?: string;
}

export default function UnderlineTabBar({
  items,
  activeId,
  onChange,
  groupLabel,
  sticky = false,
}: {
  items: UnderlineTabItem[];
  activeId: string;
  onChange: (id: string) => void;
  groupLabel?: string;
  sticky?: boolean;
}) {
  const activeItem = items.find((t) => t.id === activeId);
  const accent = activeItem?.accentColor ?? "#0369a1";

  return (
    <nav
      className={`metadata-tab-bar metadata-tab-bar--grouped${sticky ? " metadata-tab-bar--sticky" : ""}`}
      aria-label={groupLabel || "Subseções"}
    >
      <div className="metadata-tab-group" role="presentation">
        {groupLabel && <span className="metadata-tab-group__label">{groupLabel}</span>}
        <div className="metadata-tab-group__tabs" role="tablist">
          {items.map((tab) => {
            const isActive = activeId === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`metadata-tab${isActive ? " metadata-tab--active" : ""}`}
                style={
                  isActive ? ({ "--metadata-tab-accent": tab.accentColor ?? accent } as React.CSSProperties) : undefined
                }
                onClick={() => onChange(tab.id)}
              >
                {tab.icon && (
                  <span className="metadata-tab__icon" aria-hidden>
                    {tab.icon}
                  </span>
                )}
                <span className="metadata-tab__label">{tab.label}</span>
                {tab.count != null && tab.count > 0 && <span className="metadata-tab__badge">{tab.count}</span>}
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
