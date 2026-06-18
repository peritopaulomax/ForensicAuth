import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/authStore";

export default function AuthBootstrap({ children }: { children: React.ReactNode }) {
  const restoreSession = useAuthStore((s) => s.restoreSession);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    restoreSession().finally(() => setReady(true));
  }, [restoreSession]);

  if (!ready) {
    return (
      <div className="login-page">
        <p style={{ color: "#fff" }}>Carregando...</p>
      </div>
    );
  }

  return <>{children}</>;
}
