import { Link, useLocation, useNavigate } from "react-router-dom";
import BrandIdentity from "@/components/brand/BrandIdentity";
import { useAuthStore } from "@/store/authStore";
import { resolveContentWidth, useContentWidthMode, type ContentWidthMode } from "@/lib/contentWidth";

export default function Disposição({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, user } = useAuthStore();
  const { mode, setMode } = useContentWidthMode();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const isActive = (path: string) => location.pathname.startsWith(path);
  const resolvedWidth = resolveContentWidth(mode, location.pathname);
  const mainClass = resolvedWidth === "wide" ? "main-content main-content--wide" : "main-content";

  const widthOptions: { id: ContentWidthMode; label: string }[] = [
    { id: "auto", label: "Automático" },
    { id: "compact", label: "Compacto" },
    { id: "wide", label: "Expandido" },
  ];

  return (
    <div className="layout">
      <nav className="navbar">
        <BrandIdentity variant="navbar" showModuleDescription={false} />
        <ul className="nav-links">
          <li>
            <Link to="/" className={isActive("/") && !location.pathname.startsWith("/users") && !location.pathname.startsWith("/dashboard") ? "active" : ""}>
              Casos
            </Link>
          </li>
          <li>
            <Link to="/dashboard" className={isActive("/dashboard") ? "active" : ""}>
              Dashboard
            </Link>
          </li>
          {user?.role === "admin" && (
            <li>
              <Link to="/users" className={isActive("/users") ? "active" : ""}>
                Usuários
              </Link>
            </li>
          )}
        </ul>
        <div className="nav-user">
          <div
            className="content-width-toggle"
            title="Largura do conteúdo — Expandido usa quase toda a largura da janela do navegador. Automático aplica expandido em páginas de análise."
          >
            <span className="content-width-toggle__label">Disposição</span>
            {widthOptions.map((opt) => (
              <button
                key={opt.id}
                type="button"
                className={mode === opt.id ? "is-active" : undefined}
                onClick={() => setMode(opt.id)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {user && (
            <span>
              {user.username} ({user.role})
            </span>
          )}
          <button type="button" className="logout-btn" onClick={handleLogout}>
            Sair
          </button>
        </div>
      </nav>
      <main className={mainClass}>{children}</main>
    </div>
  );
}
