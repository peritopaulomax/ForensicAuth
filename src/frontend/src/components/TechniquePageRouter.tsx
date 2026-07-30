import { useParams, Navigate } from "react-router-dom";
import { Suspense } from "react";
import { getTechniqueConfig } from "@/config/techniqueRegistry";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import ImageAnalysisRedirect from "@/components/ImageAnalysisRedirect";

function TechniquePageRouterInner() {
  const { caseId, techniqueId } = useParams<{ caseId: string; techniqueId: string }>();

  if (!caseId || !techniqueId) {
    return <Navigate to="/" replace />;
  }

  // Resolve aliases (audio_spoofing → audio_spoofing_detection, pdf_font_overlay → …).
  const config = getTechniqueConfig(techniqueId);

  if (!config) {
    return <ImageAnalysisRedirect slug={techniqueId} />;
  }

  const Component = config.component;

  return (
    <Suspense fallback={<p style={{ padding: "2rem", color: "#6b7280" }}>Carregando técnica…</p>}>
      <Component />
    </Suspense>
  );
}

/**
 * Roteador genérico de páginas de técnica forense.
 * Resolve techniqueId via TechniqueRegistry e renderiza o componente lazy apropriado.
 */
export default function TechniquePageRouter() {
  return (
    <ProtectedRoute>
      <Layout>
        <TechniquePageRouterInner />
      </Layout>
    </ProtectedRoute>
  );
}
