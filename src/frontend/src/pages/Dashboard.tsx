import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { listTechniques } from "@/services/analysis";
import { useAuthStore } from "@/store/authStore";

export default function Dashboard() {
  const { restoreSession, user } = useAuthStore();

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  const { data: techniques, isLoading } = useQuery({
    queryKey: ["techniques"],
    queryFn: listTechniques,
  });

  return (
    <div className="dashboard">
      <h2>Dashboard</h2>
      {user && (
        <p>
          Bem-vindo, <strong>{user.username}</strong> ({user.role})
        </p>
      )}

      <section className="card">
        <h3>Técnicas Disponíveis</h3>
        {isLoading ? (
          <p>Carregando...</p>
        ) : (
          <ul className="technique-list">
            {techniques?.map((t) => (
              <li key={t.name}>
                <strong>{t.name}</strong>
                <span className="tag">{t.supported_types.join(", ")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
