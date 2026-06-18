export const FORENSIC_AUTH_NAME = "ForensicAuth";
export const FORENSIC_AUTH_DESCRIPTION = "Módulo de Verificação de autenticidade";

type Variant = "hero" | "navbar" | "compact";

interface Props {
  variant?: Variant;
  showModuleDescription?: boolean;
  className?: string;
}

export default function BrandIdentity({
  variant = "navbar",
  showModuleDescription = true,
  className = "",
}: Props) {
  const isHero = variant === "hero";

  return (
    <div
      className={`brand-identity brand-identity--${variant} ${className}`.trim()}
      aria-label={FORENSIC_AUTH_NAME}
    >
      <img src="/icon.png" alt="" className="brand-identity__icon" aria-hidden />
      <div className="brand-identity__text">
        <div className="brand-identity__title">{FORENSIC_AUTH_NAME}</div>
        {showModuleDescription && (isHero || variant === "compact") && (
          <p className="brand-identity__description">{FORENSIC_AUTH_DESCRIPTION}</p>
        )}
      </div>
    </div>
  );
}
