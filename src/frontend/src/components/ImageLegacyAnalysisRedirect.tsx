import { Navigate, useParams } from "react-router-dom";
import { findImageGroupForTechnique } from "@/config/imageAnalysisGroups";
import { ANALYSIS_ROUTE_META, buildImageGroupUrl } from "@/utils/caseAnalysisNav";

interface Props {
  /** Slug da rota legada (ex.: `ela`, `image_metadata`). */
  slug?: string;
  /** ID do método IMDL (rota `/analysis/imdl/:methodId`). */
  methodId?: string;
}

/** Redireciona rotas legadas de análise de imagem para o grupo correspondente. */
export default function ImageLegacyAnalysisRedirect({ slug, methodId: methodIdProp }: Props) {
  const { caseId, methodId: methodIdParam } = useParams<{ caseId: string; methodId?: string }>();
  const technique =
    methodIdProp ??
    methodIdParam ??
    (slug ? (ANALYSIS_ROUTE_META[slug]?.technique ?? slug) : undefined);

  if (!caseId || !technique) {
    return <Navigate to="/" replace />;
  }

  const match = findImageGroupForTechnique(technique);
  if (!match) {
    return <Navigate to={`/cases/${caseId}?tab=analises&media=imagem`} replace />;
  }

  return (
    <Navigate to={buildImageGroupUrl(caseId, match.group.id, match.tabId)} replace />
  );
}
