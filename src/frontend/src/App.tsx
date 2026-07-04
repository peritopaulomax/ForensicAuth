import { Routes, Route, Navigate, useParams } from "react-router-dom";
import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuthStore } from "@/store/authStore";
import Login from "@/pages/Login";
import FirstAccess from "@/pages/FirstAccess";
import Users from "@/pages/Users";
import AuthBootstrap from "@/components/AuthBootstrap";
import Cases from "@/pages/Cases";
import Dashboard from "@/pages/Dashboard";
import CaseForm from "@/pages/CaseForm";
import CaseDetail from "@/pages/CaseDetail";
import MediaPanels from "@/pages/MediaPanels";
import Analysis from "@/pages/Analysis";
import AudioForensicsHub from "@/pages/AudioForensicsHub";
import AudioSpoofingAnalysis from "@/pages/AudioSpoofingAnalysis";
import PDFFontColorAnalysis from "@/pages/PDFFontColorAnalysis";
import PDFStructureMetricsAnalysis from "@/pages/PDFStructureMetricsAnalysis";
import PDFStructureSimilarityAnalysis from "@/pages/PDFStructureSimilarityAnalysis";
import PDFForensicExtractAnalysis from "@/pages/PDFForensicExtractAnalysis";
import VideoFactAnalysis from "@/pages/VideoFactAnalysis";
import StilVideoAnalysis from "@/pages/StilVideoAnalysis";
import LowResFakeVideoAnalysis from "@/pages/LowResFakeVideoAnalysis";
import IsoMediaStructureAnalysis from "@/pages/IsoMediaStructureAnalysis";
import IsoMediaSimilarityAnalysis from "@/pages/IsoMediaSimilarityAnalysis";
import ImageAnalysisGroupPage from "@/pages/ImageAnalysisGroupPage";
import ImageLegacyAnalysisRedirect from "@/components/ImageLegacyAnalysisRedirect";
import "./App.css";

function LegacyImdlHubRedirect() {
  const { caseId } = useParams<{ caseId: string }>();
  return <Navigate to={caseId ? `/cases/${caseId}?tab=analises&media=imagem` : "/"} replace />;
}

function UnknownRouteRedirect() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return <Navigate to={isAuthenticated ? "/" : "/login"} replace />;
}

function legacyImageRedirect(slug: string) {
  return (
    <ProtectedRoute>
      <ImageLegacyAnalysisRedirect slug={slug} />
    </ProtectedRoute>
  );
}

function App() {
  return (
    <AuthBootstrap>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/primeiro-acesso" element={<FirstAccess />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout>
                <Cases />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Layout>
                <Dashboard />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/new"
          element={
            <ProtectedRoute>
              <Layout>
                <CaseForm />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId"
          element={
            <ProtectedRoute>
              <Layout>
                <CaseDetail />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/edit"
          element={
            <ProtectedRoute>
              <Layout>
                <CaseForm />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/analysis"
          element={
            <ProtectedRoute>
              <Layout>
                <MediaPanels />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/analysis/run"
          element={
            <ProtectedRoute>
              <Layout>
                <Analysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/image-group/:groupId"
          element={
            <ProtectedRoute>
              <Layout>
                <ImageAnalysisGroupPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route path="/cases/:caseId/analysis/ela" element={legacyImageRedirect("ela")} />
        <Route path="/cases/:caseId/analysis/image_metadata" element={legacyImageRedirect("image_metadata")} />
        <Route path="/cases/:caseId/analysis/dct_quantization" element={legacyImageRedirect("dct_quantization")} />
        <Route path="/cases/:caseId/analysis/resampling" element={legacyImageRedirect("resampling")} />
        <Route path="/cases/:caseId/analysis/patchmatch" element={legacyImageRedirect("patchmatch")} />
        <Route path="/cases/:caseId/analysis/copy_move_pca" element={legacyImageRedirect("copy_move_pca")} />
        <Route
          path="/cases/:caseId/analysis/wavelet_noise_residue"
          element={legacyImageRedirect("wavelet_noise_residue")}
        />
        <Route path="/cases/:caseId/analysis/double_compression" element={legacyImageRedirect("double_compression")} />
        <Route path="/cases/:caseId/analysis/bag_extraction" element={legacyImageRedirect("bag_extraction")} />
        <Route path="/cases/:caseId/analysis/jpeg_ghosts" element={legacyImageRedirect("jpeg_ghosts")} />
        <Route path="/cases/:caseId/analysis/zero_grid" element={legacyImageRedirect("zero_grid")} />
        <Route
          path="/cases/:caseId/analysis/synthetic_image_detection"
          element={legacyImageRedirect("synthetic_image_detection")}
        />
        <Route
          path="/cases/:caseId/analysis/sepael"
          element={<Navigate to="../synthetic_image_detection" replace />}
        />
        <Route path="/cases/:caseId/analysis/safire" element={legacyImageRedirect("safire")} />
        <Route path="/cases/:caseId/analysis/noiseprint" element={legacyImageRedirect("noiseprint")} />
        <Route
          path="/cases/:caseId/analysis/presentation_attack_detection"
          element={legacyImageRedirect("presentation_attack_detection")}
        />
        <Route
          path="/cases/:caseId/analysis/imdl/:methodId"
          element={
            <ProtectedRoute>
              <ImageLegacyAnalysisRedirect />
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/imdlbenco"
          element={
            <ProtectedRoute>
              <LegacyImdlHubRedirect />
            </ProtectedRoute>
          }
        />
        <Route path="/cases/:caseId/analysis/prnu" element={legacyImageRedirect("prnu")} />
        <Route path="/cases/:caseId/analysis/jpeg_structure_compare" element={legacyImageRedirect("jpeg_structure_compare")} />
        <Route
          path="/cases/:caseId/analysis/audio"
          element={
            <ProtectedRoute>
              <Layout>
                <AudioForensicsHub />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/audio_spoofing"
          element={
            <ProtectedRoute>
              <Layout>
                <AudioSpoofingAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/pdf_font_overlay"
          element={
            <ProtectedRoute>
              <Layout>
                <PDFFontColorAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/pdf_structure_metrics"
          element={
            <ProtectedRoute>
              <Layout>
                <PDFStructureMetricsAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/pdf_forensic_extract"
          element={
            <ProtectedRoute>
              <Layout>
                <PDFForensicExtractAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/pdf_structure_similarity"
          element={
            <ProtectedRoute>
              <Layout>
                <PDFStructureSimilarityAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/videofact"
          element={
            <ProtectedRoute>
              <Layout>
                <VideoFactAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/stil_video_detection"
          element={
            <ProtectedRoute>
              <Layout>
                <StilVideoAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/lowres_fake_video"
          element={
            <ProtectedRoute>
              <Layout>
                <LowResFakeVideoAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/isomedia_parser"
          element={
            <ProtectedRoute>
              <Layout>
                <IsoMediaStructureAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/isomedia_compare"
          element={
            <ProtectedRoute>
              <Layout>
                <IsoMediaSimilarityAnalysis />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/users"
          element={
            <ProtectedRoute requiredRole="admin">
              <Layout>
                <Users />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<UnknownRouteRedirect />} />
      </Routes>
    </AuthBootstrap>
  );
}

export default App;
