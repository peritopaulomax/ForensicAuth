"""Tests for authentication module — TDD Red phase.

Expected: ALL tests fail because AuthService does not exist yet.
"""

import pytest

# Import inside tests to allow collection even when module doesn't exist yet


class TestAuthService:
    """TU-AUTH-001 to TU-AUTH-007"""

    def test_login_valid_credentials(self, db_session, test_user):
        """TU-AUTH-001: Login with valid credentials returns user + token."""
        from services.auth_service import AuthService
        auth_service = AuthService(db_session)
        result = auth_service.authenticate("perito01", "Senha1234")

        assert result.user is not None
        assert result.user.username == "perito01"
        assert result.user.role == "perito"
        assert result.token is not None
        # Verify token contains sub claim
        from jose import jwt
        from app.config import get_settings
        payload = jwt.decode(result.token, get_settings().SECRET_KEY, algorithms=["HS256"])
        assert payload["sub"] == str(test_user.id)
        assert payload["role"] == "perito"

    def test_login_invalid_password(self, db_session, test_user):
        """TU-AUTH-002: Login with wrong password raises AuthenticationError."""
        from services.auth_service import AuthService
        auth_service = AuthService(db_session)
        with pytest.raises(Exception) as exc_info:
            auth_service.authenticate("perito01", "Errada9999")
        assert "Usuario ou senha incorretos" in str(exc_info.value)

    def test_login_inactive_user(self, db_session, inactive_user):
        """TU-AUTH-003: Login with inactive user raises AuthenticationError."""
        from services.auth_service import AuthService
        auth_service = AuthService(db_session)
        with pytest.raises(Exception) as exc_info:
            auth_service.authenticate("inativo01", "Senha1234")
        assert "inativo" in str(exc_info.value).lower()

    def test_hash_password(self):
        """TU-AUTH-004: Password hashing with bcrypt."""
        from services.auth_service import AuthService
        auth_service = AuthService(None)
        hashed = auth_service.hash_password("Senha1234")

        assert hashed != "Senha1234"
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

        import bcrypt
        assert bcrypt.checkpw("Senha1234".encode(), hashed.encode("utf-8")) is True
        assert bcrypt.checkpw("Errada".encode(), hashed.encode("utf-8")) is False

    @pytest.mark.parametrize(
        "password,expected_valid,expected_msg",
        [
            ("abc", False, "menor"),
            ("abcdefgh", False, "maiuscula"),
            ("Abcdefgh", False, "numero"),
            ("Abcdefg1", True, ""),
        ],
    )
    def test_password_strength(self, password, expected_valid, expected_msg):
        """TU-AUTH-005: Password strength validation."""
        from services.auth_service import AuthService
        auth_service = AuthService(None)
        valid, msg = auth_service.validate_password_strength(password)
        assert valid == expected_valid
        if not expected_valid:
            assert expected_msg in msg.lower()

    def test_register_by_admin(self, db_session, test_admin):
        """TU-AUTH-006: Admin can register new users."""
        from services.auth_service import AuthService
        auth_service = AuthService(db_session)
        data = {
            "username": "novoperito",
            "email": "novo@pf.gov.br",
            "password": "NovaSenha1",
            "role": "perito",
        }
        user = auth_service.register(data, test_admin)

        assert user.username == "novoperito"
        assert user.role == "perito"
        assert user.hashed_password != "NovaSenha1"

    def test_register_denied_for_non_admin(self, db_session, test_user):
        """TU-AUTH-007: Non-admin cannot register users."""
        from services.auth_service import AuthService
        auth_service = AuthService(db_session)
        data = {
            "username": "novoperito",
            "email": "novo@pf.gov.br",
            "password": "NovaSenha1",
            "role": "perito",
        }
        with pytest.raises(Exception) as exc_info:
            auth_service.register(data, test_user)
        assert "negado" in str(exc_info.value).lower() or "403" in str(exc_info.value)

    def test_login_without_password_set(self, db_session, provisioned_user):
        """TU-AUTH-008: User with no password must use first access."""
        from services.auth_service import AuthService
        auth_service = AuthService(db_session)
        with pytest.raises(Exception) as exc_info:
            auth_service.authenticate("novo.perito", "Qualquer1")
        assert "primeiro acesso" in str(exc_info.value).lower()

    def test_first_access_sets_password(self, db_session, provisioned_user):
        """TU-AUTH-009: First access sets password and enables login."""
        from services.auth_service import AuthService
        auth_service = AuthService(db_session)
        user = auth_service.first_access("novo.perito", "NovaSenha1", "NovaSenha1")
        assert user.password_set is True

        result = auth_service.authenticate("novo.perito", "NovaSenha1")
        assert result.user.username == "novo.perito"

    def test_first_access_password_mismatch(self, db_session, provisioned_user):
        """TU-AUTH-010: First access rejects mismatched passwords."""
        from services.auth_service import AuthService
        auth_service = AuthService(db_session)
        with pytest.raises(Exception) as exc_info:
            auth_service.first_access("novo.perito", "NovaSenha1", "OutraSenha1")
        assert "coincidem" in str(exc_info.value).lower()


class TestUserService:
    """Admin user provisioning and reset."""

    def test_admin_provisions_user(self, db_session, test_admin):
        from services.user_service import UserService
        service = UserService(db_session)
        user = service.provision_user(
            {
                "username": "silva.pf",
                "email": "silva@pf.gov.br",
                "role": "perito",
            },
            test_admin,
        )
        assert user.password_set is False
        assert user.username == "silva.pf"
        assert user.role == "perito"

    def test_admin_cannot_provision_analista(self, db_session, test_admin):
        from services.user_service import UserService
        from fastapi import HTTPException

        service = UserService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            service.provision_user(
                {
                    "username": "legado.analista",
                    "email": "legado@pf.gov.br",
                    "role": "analista",
                },
                test_admin,
            )
        assert exc_info.value.status_code == 422

    def test_admin_reset_password(self, db_session, test_admin, test_user):
        from services.user_service import UserService
        service = UserService(db_session)
        user = service.reset_password(test_user.id, test_admin)
        assert user.password_set is False


class TestAuthIntegration:
    """TI-AUTH-001/002: HTTP endpoints."""

    def test_first_access_endpoint(self, client, provisioned_user):
        response = client.post(
            "/api/v1/auth/first-access",
            json={
                "username": "novo.perito",
                "password": "NovaSenha1",
                "password_confirm": "NovaSenha1",
            },
        )
        assert response.status_code == 200
        assert response.json()["password_set"] is True

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "novo.perito", "password": "NovaSenha1"},
        )
        assert login.status_code == 200

    def test_admin_list_and_provision_users(self, client, admin_auth_headers):
        create = client.post(
            "/api/v1/users",
            json={
                "username": "costa.pf",
                "email": "costa@pf.gov.br",
                "role": "perito",
            },
            headers=admin_auth_headers,
        )
        assert create.status_code == 201
        assert create.json()["password_set"] is False

        listing = client.get("/api/v1/users", headers=admin_auth_headers)
        assert listing.status_code == 200
        usernames = [u["username"] for u in listing.json()]
        assert "costa.pf" in usernames
