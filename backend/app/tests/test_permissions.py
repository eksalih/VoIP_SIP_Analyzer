"""v2.3.0 roles: scoping by extension, recording permissions, admin-only actions, audit trail."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.db.database import engine, Base, AsyncSessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.call import Call, CallStatus
from app.models.user import User
from app.services.security import create_token, hash_password

pytestmark = pytest.mark.real_auth


@pytest_asyncio.fixture(autouse=True)
async def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_SECRET", "t")
    monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path / "rec"))
    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "c.wav").write_bytes(b"RIFF" + b"\0" * 2000)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        for name, role, ext in [("root", "admin", None), ("sup", "supervisor", None),
                                ("sam", "user", "1001"), ("noext", "user", None)]:
            db.add(User(username=name, role=role, extensions=ext, password_hash=hash_password("x")))
        # 1001 involved in two calls (as caller / as callee), 2001<->2002 in one
        db.add(Call(call_id="a", caller="1001", called="2001", status=CallStatus.ANSWERED, audio_path="c.wav"))
        db.add(Call(call_id="b", caller="2002", called="1001", status=CallStatus.MISSED))
        db.add(Call(call_id="c", caller="2001", called="2002", status=CallStatus.ANSWERED, audio_path="c.wav"))
        await db.commit()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _h(username):
    async with AsyncSessionLocal() as db:
        uid = (await db.execute(select(User.id).where(User.username == username))).scalar_one()
    return {"Authorization": f"Bearer {create_token(uid)}"}


async def _id(call_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Call.id).where(Call.call_id == call_id))).scalar_one()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _audit():
    async with AsyncSessionLocal() as db:
        return [(r.username, r.action, r.call_id) for r in (await db.execute(select(AuditLog))).scalars()]


class TestScoping:
    @pytest.mark.asyncio
    async def test_everything_requires_login(self, client):
        for path in ("/calls", "/analytics", "/capture-files", "/export/csv"):
            assert (await client.get(path)).status_code == 401, path
        assert (await client.get("/health")).status_code == 200

    @pytest.mark.asyncio
    async def test_admin_and_supervisor_see_all_calls(self, client):
        for who in ("root", "sup"):
            assert len((await client.get("/calls", headers=await _h(who))).json()) == 3

    @pytest.mark.asyncio
    async def test_user_sees_only_own_extension_calls(self, client):
        calls = (await client.get("/calls", headers=await _h("sam"))).json()
        assert sorted(c["call_id"] for c in calls) == ["a", "b"]

    @pytest.mark.asyncio
    async def test_user_without_extensions_sees_nothing(self, client):
        assert (await client.get("/calls", headers=await _h("noext"))).json() == []

    @pytest.mark.asyncio
    async def test_other_peoples_call_looks_nonexistent(self, client):
        h = await _h("sam")
        cid = await _id("c")
        for suffix in ("", "/events", "/audio"):
            r = await client.get(f"/calls/{cid}{suffix}", headers=h)
            assert r.status_code == 404, suffix
        assert (await client.get(f"/calls/{cid}/media", headers=h)).json() == []
        assert (await client.get(f"/calls/{await _id('a')}", headers=h)).status_code == 200

    @pytest.mark.asyncio
    async def test_user_cannot_use_all_calls_features(self, client):
        h = await _h("sam")
        for path in ("/analytics", "/capture-files", "/export/csv"):
            assert (await client.get(path, headers=h)).status_code == 403, path


class TestRecordings:
    @pytest.mark.asyncio
    async def test_user_can_play_but_not_download_own_recording(self, client):
        h, cid = await _h("sam"), await _id("a")
        assert (await client.get(f"/calls/{cid}/audio", headers=h)).status_code == 200
        assert (await client.get(f"/calls/{cid}/audio?download=1", headers=h)).status_code == 403

    @pytest.mark.asyncio
    async def test_supervisor_can_download(self, client):
        r = await client.get(f"/calls/{await _id('c')}/audio?download=1", headers=await _h("sup"))
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_playback_and_download_are_audited(self, client):
        h, cid = await _h("sup"), await _id("a")
        await client.get(f"/calls/{cid}/audio", headers=h)
        await client.get(f"/calls/{cid}/audio", headers={**h, "Range": "bytes=100-"})  # seek: not a new play
        await client.get(f"/calls/{cid}/audio?download=1", headers=h)
        log = [e for e in await _audit() if e[1].startswith("recording")]
        assert log == [("sup", "recording.play", cid), ("sup", "recording.download", cid)]

    @pytest.mark.asyncio
    async def test_denied_access_is_not_audited_as_playback(self, client):
        await client.get(f"/calls/{await _id('c')}/audio", headers=await _h("sam"))
        assert not [e for e in await _audit() if e[1].startswith("recording")]


class TestAdminOnly:
    @pytest.mark.asyncio
    async def test_only_admin_can_delete(self, client):
        cid = await _id("b")
        assert (await client.delete(f"/calls/{cid}", headers=await _h("sup"))).status_code == 403
        assert (await client.delete(f"/calls/{cid}", headers=await _h("sam"))).status_code == 403
        assert (await client.delete("/calls/clear-all?confirm=true", headers=await _h("sup"))).status_code == 403
        assert (await client.delete(f"/calls/{cid}", headers=await _h("root"))).status_code == 200
        assert ("root", "call.delete", cid) in await _audit()

    @pytest.mark.asyncio
    async def test_supervisor_cannot_delete_capture_files(self, client):
        assert (await client.delete("/capture-files/1", headers=await _h("sup"))).status_code == 403

    @pytest.mark.asyncio
    async def test_login_attempts_are_audited(self, client):
        await client.post("/auth/login", json={"username": "root", "password": "wrong"})
        assert ("root", "login_failed", None) in await _audit()
