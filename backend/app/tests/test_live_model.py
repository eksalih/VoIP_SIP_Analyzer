"""v2.3.0 data-model tests: Call.source and the IN_PROGRESS status."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.database import engine, Base, AsyncSessionLocal
from app.models.call import Call, CallStatus


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _add_call(call_id, status, source="live"):
    async with AsyncSessionLocal() as session:
        call = Call(call_id=call_id, caller="1001", called="1002", status=status, source=source)
        session.add(call)
        await session.commit()
        return call.id


class TestLiveCallModel:
    @pytest.mark.asyncio
    async def test_source_defaults_to_upload(self):
        async with AsyncSessionLocal() as session:
            session.add(Call(call_id="x", status=CallStatus.ANSWERED))
            await session.commit()
            call = (await session.execute(select(Call))).scalar_one()
        assert call.source == "upload"

    @pytest.mark.asyncio
    async def test_api_exposes_source_and_in_progress_status(self, client):
        await _add_call("live-1", CallStatus.IN_PROGRESS, source="live")
        calls = (await client.get("/calls")).json()
        assert calls[0]["source"] == "live"
        assert calls[0]["status"] == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_in_progress_calls_are_excluded_from_analytics_totals(self, client):
        await _add_call("done", CallStatus.ANSWERED, source="live")
        await _add_call("open", CallStatus.IN_PROGRESS, source="live")
        data = (await client.get("/analytics")).json()
        assert data["total_calls"] == 1
        assert data["answered"] == 1
        assert data["success_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_finalised_call_counts_in_analytics(self, client):
        cid = await _add_call("c", CallStatus.IN_PROGRESS)
        assert (await client.get("/analytics")).json()["total_calls"] == 0
        async with AsyncSessionLocal() as session:
            call = (await session.execute(select(Call).where(Call.id == cid))).scalar_one()
            call.status = CallStatus.MISSED
            await session.commit()
        data = (await client.get("/analytics")).json()
        assert data["total_calls"] == 1
        assert data["missed"] == 1
