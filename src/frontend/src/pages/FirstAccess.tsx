import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { firstAccess } from "@/services/auth";
import BrandIdentity from "@/components/brand/BrandIdentity";

export default function FirstAccess() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (password !== passwordConfirm) {
      setError("As senhas não coincidem.");
      return;
    }

    setLoading(true);
    try {
      await firstAccess({
        username,
        password,
        password_confirm: passwordConfirm,
      });
      setSuccess("Senha criada com sucesso! Redirecionando para o login...");
      setTimeout(() => navigate("/login"), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Não foi possível criar a senha.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card login-card--branded">
        <BrandIdentity variant="compact" />
        <h2 className="login-card__heading">Primeiro Acesso</h2>
        <p className="login-card__sub">Crie sua senha para acessar o ForensicAuth</p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">Usuário</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              placeholder="Nome de usuário autorizado"
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Nova senha</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
            />
          </div>
          <div className="form-group">
            <label htmlFor="passwordConfirm">Confirmar senha</label>
            <input
              id="passwordConfirm"
              type="password"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              required
              minLength={8}
            />
          </div>
          <p className="form-hint">Mínimo 8 caracteres, 1 maiúscula e 1 número.</p>
          {error && <div className="error-message">{error}</div>}
          {success && <div className="success-message">{success}</div>}
          <button type="submit" disabled={loading}>
            {loading ? "Salvando..." : "Criar senha"}
          </button>
        </form>
        <p className="login-footer">
          <Link to="/login">Voltar ao login</Link>
        </p>
      </div>
    </div>
  );
}
