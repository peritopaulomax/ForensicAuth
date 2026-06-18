import type { ForensicTechniqueMeta } from "@/config/forensicTechniqueMeta";
import { hasTechniquePaper } from "@/config/techniquePapers";
import TechniquePaperDownload from "@/components/TechniquePaperDownload";

interface Props {
  meta: ForensicTechniqueMeta;
  /** ID da técnica para download do PDF (ex.: trufor, safire). */
  techniqueId?: string;
}

/** Bloco bibliográfico abaixo do título (citação ABNT, detalhamento, licença). */
export default function TechniqueReferenceIntro({ meta, techniqueId }: Props) {
  const citations = meta.citation.split(/\n\n+/).filter(Boolean);

  return (
    <section
      className="technique-reference-intro"
      style={{
        margin: "0 0 1.25rem",
        padding: "0.85rem 1rem",
        background: "#f8fafc",
        border: "1px solid #e2e8f0",
        borderRadius: 8,
        fontSize: "0.84rem",
        color: "#374151",
        lineHeight: 1.55,
      }}
    >
      {citations.map((cite, index) => (
        <p
          key={index}
          style={{
            margin: index < citations.length - 1 ? "0 0 0.65rem" : "0 0 0.65rem",
            fontStyle: "italic",
            color: "#4b5563",
          }}
        >
          {cite}
        </p>
      ))}
      <p style={{ margin: "0 0 0.65rem" }}>{meta.detail}</p>
      {meta.summary ? <p style={{ margin: "0 0 0.65rem", color: "#4b5563" }}>{meta.summary}</p> : null}
      {(meta.license || meta.repoUrl) && (
        <p style={{ margin: 0, fontSize: "0.8rem", color: "#6b7280" }}>
          {meta.license ? (
            <>
              Licença: <strong style={{ fontWeight: 600, color: "#374151" }}>{meta.license}</strong>
            </>
          ) : null}
          {meta.license && meta.repoUrl ? " · " : null}
          {meta.repoUrl ? (
            <a href={meta.repoUrl} target="_blank" rel="noreferrer" style={{ color: "#0369a1" }}>
              Repositório oficial
            </a>
          ) : null}
        </p>
      )}
      {techniqueId && hasTechniquePaper(techniqueId) ? (
        <TechniquePaperDownload techniqueId={techniqueId} />
      ) : null}
    </section>
  );
}
