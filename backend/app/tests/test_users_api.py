"""v2.3.0 user management, password change and audit listing."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.db.database import engine, Base, AsyncSessionLocal
from app.main import app
from app.models.user import User
from app.services.security import create_token, hash_password

pytestmark = pytest.mark.real_auth


@pytest_asyncio.fixture(autouse=True)
async def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_SECRET", "t")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        for n, r in [("root", "admin"), ("sup", "supervisor"), ("sam", "user")]:
            db.add(User(username=n, role=r, password_hash=hash_password("password1")))
        await db.commit()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _h(name):
    async with AsyncSessionLocal() as db:
        uid = (await db.execute(select(User.id).where(User.username == name))).scalar_one()
    return {"Authorization": f"Bearer {create_token(uid)}"}


async def _uid(name):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(User.id).where(User.username == name))).scalar_one()


class TestUserManagement:
    @pytest.mark.asyncio
    async def test_only_admin_can_manage_users_and_see_audit(self, client):
        for who in ("sup", "sam"):
            h = await _h(who)
            assert (await client.get("/users", headers=h)).status_code == 403
            assert (await client.post("/users", headers=h, json={"username": "x", "password": "password1"})).status_code == 403
            assert (await client.get("/audit", headers=h)).status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_and_login(self, client):
        h = await _h("root")
        r = await client.post("/users", headers=h, json={
            "username": " jo ", "password": "longenough", "role": "user", "extensions": ["1001", " 1002 ", "1001"]})
        assert r.status_code == 201 and r.json()["username"] == "jo" and r.json()["extensions"] == ["1001", "1002"]
        assert "password" not in r.text
        login = await client.post("/auth/login", json={"username": "jo", "password": "longenough"})
        assert login.status_code == 200

    @pytest.mark.asyncio
    async def test_create_validation(self, client):
        h = await _h("root")
        assert (await client.post("/users", headers=h, json={"username": "root", "password": "longenough"})).status_code == 409
        assert (await client.post("/users", headers=h, json={"username": "n", "password": "short"})).status_code == 422
        assert (await client.post("/users", headers=h, json={"username": "n", "password": "longenough", "role": "god"})).status_code == 422

    @pytest.mark.asyncio
    async def test_update_role_extensions_and_password_reset(self, client):
        h, sid = await _h("root"), await _uid("sam")
        r = await client.patch(f"/users/{sid}", headers=h, json={"role": "supervisor", "extensions": ["1001"], "password": "newpassword"})
        assert r.status_code == 200 and r.json()["role"] == "supervisor"
        assert (await client.post("/auth/login", json={"username": "sam", "password": "password1"})).status_code == 401
        assert (await client.post("/auth/login", json={"username": "sam", "password": "newpassword"})).status_code == 200

    @pytest.mark.asyncio
    async def test_disabling_user_blocks_login(self, client):
        sid = await _uid("sam")
        await client.patch(f"/users/{sid}", headers=await _h("root"), json={"is_active": False})
        assert (await client.post("/auth/login", json={"username": "sam", "password": "password1"})).status_code == 401

    @pytest.mark.asyncio
    async def test_last_admin_and_self_protection(self, client):
        h, rid = await _h("root"), await _uid("root")
        assert (await client.patch(f"/users/{rid}", headers=h, json={"role": "user"})).status_code == 409
        assert (await client.patch(f"/users/{rid}", headers=h, json={"is_active": False})).status_code == 409
        assert (await client.delete(f"/users/{rid}", headers=h)).status_code == 409
        # with a second admin, demoting the first is fine but you still cannot disable yourself
        await client.post("/users", headers=h, json={"username": "root2", "password": "longenough", "role": "admin"})
        assert (await client.patch(f"/users/{rid}", headers=h, json={"is_active": False})).status_code == 409

    @pytest.mark.asyncio
    async def test_delete_user(self, client):
        sid = await _uid("sam")
        assert (await client.delete(f"/users/{sid}", headers=await _h("root"))).status_code == 200
        assert (await client.delete(f"/users/{sid}", headers=await _h("root"))).status_code == 404


class TestPasswordAndAudit:
    @pytest.mark.asyncio
    async def test_change_own_password(self, client):
        h = await _h("sam")
        assert (await client.post("/auth/change-password", headers=h, json={
            "current_password": "wrong", "new_password": "brandnewpw"})).status_code == 400
        assert (await client.post("/auth/change-password", headers=h, json={
            "current_password": "password1", "new_password": "brandnewpw"})).status_code == 200
        assert (await client.post("/auth/login", json={"username": "sam", "password": "brandnewpw"})).status_code == 200

    @pytest.mark.asyncio
    async def test_audit_listing_filters_and_records_user_changes(self, client):
        h = await _h("root")
        await client.post("/users", headers=h, json={"username": "jo", "password": "longenough"})
        await client.post("/auth/login", json={"username": "sam", "password": "bad"})
        all_rows = (await client.get("/audit", headers=h)).json()
        assert {"user.create", "login_failed"} <= {r["action"] for r in all_rows}
        only = (await client.get("/audit?action=user.create", headers=h)).json()
        assert len(only) == 1 and only[0]["username"] == "root" and "jo" in only[0]["detail"]
        assert "password" not in str(all_rows).replace("login_failed", "")
