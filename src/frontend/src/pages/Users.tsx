import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listUsers,
  provisionUser,
  resetUserPassword,
  updateUser,
} from "@/services/users";
import type { User } from "@/types/api";

const ROLE_LABELS: Record<User["role"], string> = {
  admin: "Administrador",
  perito: "Perito",
};

export default function Users() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<User["role"]>("perito");
  const [formError, setFormError] = useState("");

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const provisionMutation = useMutation({
    mutationFn: provisionUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setShowForm(false);
      setUsername("");
      setEmail("");
      setRole("perito");
      setFormError("");
    },
    onError: (err: Error) => setFormError(err.message),
  });

  const resetMutation = useMutation({
    mutationFn: resetUserPassword,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updateUser(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const handleProvision = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    provisionMutation.mutate({ username, email, role });
  };

  return (
    <div className="users-page">
      <div className="page-header">
        <h2>Usuários autorizados</h2>
        <button type="button" className="btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? "Cancelar" : "+ Adicionar usuário"}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h3>Novo usuário</h3>
          <p className="form-hint">
            O usuário definirá a senha no primeiro acesso após ser cadastrado.
          </p>
          <form onSubmit={handleProvision}>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="new-username">Usuário</label>
                <input
                  id="new-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  placeholder="ex: silva.pf"
                />
              </div>
              <div className="form-group">
                <label htmlFor="new-email">E-mail</label>
                <input
                  id="new-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="new-role">Perfil</label>
                <select
                  id="new-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as User["role"])}
                >
                  <option value="perito">Perito</option>
                  <option value="admin">Administrador</option>
                </select>
              </div>
            </div>
            {formError && <div className="error-message">{formError}</div>}
            <button type="submit" className="btn-primary" disabled={provisionMutation.isPending}>
              {provisionMutation.isPending ? "Salvando..." : "Cadastrar usuário"}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        {isLoading ? (
          <p>Carregando...</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Usuário</th>
                <th>E-mail</th>
                <th>Perfil</th>
                <th>Status</th>
                <th>Senha</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>{u.email}</td>
                  <td>{ROLE_LABELS[u.role]}</td>
                  <td>
                    <span className={`tag ${u.is_active ? "tag-active" : "tag-inactive"}`}>
                      {u.is_active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td>
                    <span className={`tag ${u.password_set ? "tag-ok" : "tag-pending"}`}>
                      {u.password_set ? "Definida" : "Pendente"}
                    </span>
                  </td>
                  <td className="actions-cell">
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() => resetMutation.mutate(u.id)}
                      disabled={resetMutation.isPending}
                    >
                      Resetar senha
                    </button>
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() =>
                        toggleActiveMutation.mutate({ id: u.id, is_active: !u.is_active })
                      }
                      disabled={toggleActiveMutation.isPending}
                    >
                      {u.is_active ? "Desativar" : "Ativar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
