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
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.expires_in > 0
        # Verify token contains sub claim
        from jose import jwt
        from app.config import get_settings
        payload = jwt.decode(result.access_token, get_settings().SECRET_KEY, algorithms=["HS256"])
        assert payload["sub"] == str(test_user.id)
        assert payload["role"] == "perito"
        assert payload["type"] == "access"

        from models.refresh_token import RefreshToken
        import hashlib
        token_hash = hashlib.sha256(result.refresh_token.encode()).hexdigest()
        stored = db_session.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        assert stored is not None
        assert stored.user_id == test_user.id
        assert stored.revoked_at is None

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

    def test_refresh_rotates_token(self, db_session, test_user):
        """TU-AUTH-011: Valid refresh issues new pair and revokes old."""
        from services.auth_service import AuthService, AuthenticationError
        from jose import jwt
        from app.config import get_settings

        auth_service = AuthService(db_session)
        login = auth_service.authenticate("perito01", "Senha1234")
        old_refresh = login.refresh_token

        pair = auth_service.refresh(old_refresh)
        assert pair.access_token
        assert pair.refresh_token
        assert pair.refresh_token != old_refresh

        payload = jwt.decode(pair.access_token, get_settings().SECRET_KEY, algorithms=["HS256"])
        assert payload["type"] == "access"
        assert payload["sub"] == str(test_user.id)

        with pytest.raises(AuthenticationError):
            auth_service.refresh(old_refresh)

    def test_logout_invalidates_refresh(self, db_session, test_user):
        """TU-AUTH-012: Logout revokes refresh."""
        from services.auth_service import AuthService, AuthenticationError

        auth_service = AuthService(db_session)
        login = auth_service.authenticate("perito01", "Senha1234")
        auth_service.logout(login.refresh_token)

        with pytest.raises(AuthenticationError):
            auth_service.refresh(login.refresh_token)

    def test_inactive_user_cannot_refresh(self, db_session, test_user):
        """TU-AUTH-013: Inactive user cannot renew session."""
        from services.auth_service import AuthService, AuthenticationError

        auth_service = AuthService(db_session)
        login = auth_service.authenticate("perito01", "Senha1234")
        test_user.is_active = False
        db_session.commit()

        with pytest.raises(AuthenticationError):
            auth_service.refresh(login.refresh_token)


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

    def test_provision_strips_username_and_email(self, db_session, test_admin):
        from services.user_service import UserService

        service = UserService(db_session)
        user = service.provision_user(
            {
                "username": "  spaced.user  ",
                "email": "  spaced@pf.gov.br  ",
                "role": "perito",
            },
            test_admin,
        )
        assert user.username == "spaced.user"
        assert user.email == "spaced@pf.gov.br"

    def test_first_access_and_login_tolerate_padded_username(self, db_session, test_admin):
        from services.auth_service import AuthService
        from services.user_service import UserService

        service = UserService(db_session)
        service.provision_user(
            {
                "username": "  pad.user  ",
                "email": "pad@pf.gov.br",
                "role": "perito",
            },
            test_admin,
        )
        auth = AuthService(db_session)
        user = auth.first_access("  pad.user  ", "NovaSenha1", "NovaSenha1")
        assert user.username == "pad.user"
        assert user.password_set is True
        result = auth.authenticate(" pad.user ", "NovaSenha1")
        assert result.user.username == "pad.user"

    def test_trim_migration_fixes_legacy_whitespace(self, db_session):
        from app.db_migrations import ensure_trim_usernames_and_emails
        from models.user import User
        from services.user_service import unset_password_hash
        import uuid

        dirty = User(
            id=uuid.uuid4(),
            username="  legado.user  ",
            email="  legado@pf.gov.br  ",
            hashed_password=unset_password_hash(),
            password_set=False,
            role="perito",
            is_active=True,
        )
        db_session.add(dirty)
        db_session.commit()

        ensure_trim_usernames_and_emails(db_session.get_bind())
        db_session.expire_all()
        fixed = db_session.query(User).filter(User.id == dirty.id).one()
        assert fixed.username == "legado.user"
        assert fixed.email == "legado@pf.gov.br"

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
        body = login.json()
        assert body.get("access_token")
        assert body.get("refresh_token")
        assert body.get("expires_in", 0) > 0

    def test_login_me_refresh_logout(self, client, test_user):
        """TI-AUTH-001/003: login → me → refresh → logout."""
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "perito01", "password": "Senha1234"},
        )
        assert login.status_code == 200
        data = login.json()
        access = data["access_token"]
        refresh = data["refresh_token"]
        assert data["expires_in"] > 0

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert me.status_code == 200
        assert me.json()["username"] == "perito01"

        renewed = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert renewed.status_code == 200
        new_refresh = renewed.json()["refresh_token"]
        assert new_refresh != refresh

        # Old refresh must fail after rotation
        reuse = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert reuse.status_code == 401

        logout = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": new_refresh},
        )
        assert logout.status_code == 200
        assert logout.json()["ok"] is True

        after_logout = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_refresh},
        )
        assert after_logout.status_code == 401

        # Opaque refresh as Bearer must not authenticate
        bad_me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_refresh}"},
        )
        assert bad_me.status_code == 401

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
