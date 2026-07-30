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
import ImdlMethodAnalysis from "@/pages/ImdlMethodAnalysis";
import ImageAnalysisGroupPage from "@/pages/ImageAnalysisGroupPage";
import MediaAnalysisGroupPage from "@/pages/MediaAnalysisGroupPage";
import AudioForensicsHub from "@/pages/AudioForensicsHub";
import TechniquePageRouter from "@/components/TechniquePageRouter";
import "./App.css";

function LegacyImdlHubRedirect() {
  const { caseId } = useParams<{ caseId: string }>();
  return <Navigate to={caseId ? `/cases/${caseId}?tab=analises&media=imagem` : "/"} replace />;
}

function UnknownRouteRedirect() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return <Navigate to={isAuthenticated ? "/" : "/login"} replace />;
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
        <Route
          path="/cases/:caseId/analysis/media-group/:media/:groupId"
          element={
            <ProtectedRoute>
              <Layout>
                <MediaAnalysisGroupPage />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:caseId/analysis/imdl/:methodId"
          element={
            <ProtectedRoute>
              <Layout>
                <ImdlMethodAnalysis />
              </Layout>
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
        <Route
          path="/cases/:caseId/analysis/sepael"
          element={
            <ProtectedRoute>
              <Navigate to="../synthetic_image_detection" replace />
            </ProtectedRoute>
          }
        />
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
          path="/cases/:caseId/analysis/:techniqueId"
          element={<TechniquePageRouter />}
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
