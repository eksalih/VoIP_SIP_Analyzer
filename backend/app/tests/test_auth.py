"""v2.3.0 login foundation: hashing, tokens, login/me, first-admin bootstrap."""
import pytest
import pytest_asyncio

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.api.auth import bootstrap_admin
from app.db.database import engine, Base, AsyncSessionLocal
from app.main import app
from app.models.user import User
from app.services.security import (
    create_token, decode_token, hash_password, verify_password,
)


pytestmark = pytest.mark.real_auth

@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _user(name="sam", pw="s3cret", role="user", active=True, ext="1001, 1002"):
    async with AsyncSessionLocal() as db:
        db.add(User(username=name, password_hash=hash_password(pw), role=role,
                    is_active=active, extensions=ext))
        await db.commit()


class TestSecurity:
    def test_password_roundtrip_and_salting(self):
        h1, h2 = hash_password("pw"), hash_password("pw")
        assert h1 != h2 and "pw" not in h1
        assert verify_password("pw", h1) and not verify_password("nope", h1)
        assert not verify_password("pw", "garbage")

    def test_token_valid_expired_and_tampered(self):
        t = create_token(7, ttl=60, now=1000)
        assert decode_token(t, now=1030) == 7
        assert decode_token(t, now=1061) is None
        payload, sig = t.split(".")
        assert decode_token(payload + "." + sig[:-2] + "xx", now=1030) is None
        assert decode_token("junk") is None

    def test_token_signed_with_other_secret_rejected(self, monkeypatch):
        t = create_token(7)
        monkeypatch.setenv("AUTH_SECRET", "different")
        assert decode_token(t) is None

    def test_secret_generated_once_and_persisted(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AUTH_SECRET")
        t = create_token(1)
        assert (tmp_path / ".auth_secret").exists()
        assert decode_token(t) == 1       # same key re-read from disk


class TestAuthApi:
    @pytest.mark.asyncio
    async def test_login_then_me(self, client):
        await _user()
        r = await client.post("/auth/login", json={"username": "sam", "password": "s3cret"})
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["permissions"] == ["calls.view_own", "recordings.play"]
        assert body["user"]["extensions"] == ["1001", "1002"] and "password" not in str(body)
        me = await client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
        assert me.status_code == 200 and me.json()["username"] == "sam"
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(User))).scalar_one().last_login is not None

    @pytest.mark.asyncio
    async def test_bad_credentials_and_disabled_user(self, client):
        await _user()
        await _user("off", active=False)
        assert (await client.post("/auth/login", json={"username": "sam", "password": "x"})).status_code == 401
        assert (await client.post("/auth/login", json={"username": "ghost", "password": "x"})).status_code == 401
        assert (await client.post("/auth/login", json={"username": "off", "password": "s3cret"})).status_code == 401

    @pytest.mark.asyncio
    async def test_me_requires_valid_token(self, client):
        assert (await client.get("/auth/me")).status_code == 401
        assert (await client.get("/auth/me", headers={"Authorization": "Bearer nope"})).status_code == 401

    @pytest.mark.asyncio
    async def test_deactivated_user_token_stops_working(self, client):
        await _user()
        token = (await client.post("/auth/login", json={"username": "sam", "password": "s3cret"})).json()["token"]
        async with AsyncSessionLocal() as db:
            (await db.execute(select(User))).scalar_one().is_active = False
            await db.commit()
        assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401


class TestBootstrap:
    @pytest.mark.asyncio
    async def test_creates_admin_from_env_once(self, monkeypatch):
        monkeypatch.setenv("ADMIN_USERNAME", "boss")
        monkeypatch.setenv("ADMIN_PASSWORD", "pw123")
        assert await bootstrap_admin(AsyncSessionLocal) is None   # password was supplied
        assert await bootstrap_admin(AsyncSessionLocal) is None   # already has a user: no second admin
        async with AsyncSessionLocal() as db:
            users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 1 and users[0].username == "boss" and users[0].role == "admin"
        assert verify_password("pw123", users[0].password_hash)

    @pytest.mark.asyncio
    async def test_generates_password_when_not_set(self, monkeypatch):
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        pw = await bootstrap_admin(AsyncSessionLocal)
        assert pw and len(pw) >= 12
        async with AsyncSessionLocal() as db:
            assert verify_password(pw, (await db.execute(select(User))).scalar_one().password_hash)
