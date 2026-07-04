"""Phase 5 frontend integration tests.

Lightweight file-level checks because Node.js tooling is not available in this
Linux environment.
"""

from pathlib import Path


class TestDashboardIntegration:
    def test_dashboard_imported_in_app(self):
        app_tsx = Path(__file__).resolve().parents[2] / "src" / "frontend" / "src" / "App.tsx"
        content = app_tsx.read_text(encoding="utf-8")
        assert 'import Dashboard from "@/pages/Dashboard"' in content
        assert 'path="/dashboard"' in content
        assert "<Dashboard />" in content

    def test_dashboard_link_in_layout(self):
        layout_tsx = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "frontend"
            / "src"
            / "components"
            / "Layout.tsx"
        )
        content = layout_tsx.read_text(encoding="utf-8")
        assert 'to="/dashboard"' in content
        assert "Dashboard" in content

    def test_dashboard_page_exists(self):
        dashboard_tsx = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "frontend"
            / "src"
            / "pages"
            / "Dashboard.tsx"
        )
        assert dashboard_tsx.is_file()
