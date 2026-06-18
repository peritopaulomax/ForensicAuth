import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import type { User } from "@/types/api";

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: User["role"];
}

export default function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { isAuthenticated, user } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && user?.role !== requiredRole) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
