import type { MetadataTabId } from "@/components/metadata/metadataTabConfig";
import { tabDefById } from "@/components/metadata/metadataTabConfig";

export default function MetadataSectionHeader({
  tabId,
  title,
  description,
  meta,
}: {
  tabId: MetadataTabId;
  title?: string;
  description?: string;
  meta?: string;
}) {
  const def = tabDefById(tabId);
  return (
    <header className="metadata-section-header" style={{ "--metadata-tab-accent": def.accentColor } as React.CSSProperties}>
      <div className="metadata-section-header__title-row">
        <span className="metadata-section-header__icon" aria-hidden>
          {def.icon}
        </span>
        <h3 className="metadata-section-header__title">{title ?? def.label}</h3>
      </div>
      {description && <p className="metadata-section-header__description">{description}</p>}
      {meta && <p className="metadata-section-header__meta">{meta}</p>}
    </header>
  );
}
