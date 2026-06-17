"""
Integration tests for REST API endpoints.
Uses httpx + in-memory SQLite database.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.database import engine, Base


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


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"


class TestCallsEndpoint:
    @pytest.mark.asyncio
    async def test_list_calls_empty(self, client):
        response = await client.get("/calls")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_call_not_found(self, client):
        response = await client.get("/calls/9999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_calls_filter_status(self, client):
        response = await client.get("/calls?status=ANSWERED")
        assert response.status_code == 200


class TestAnalyticsEndpoint:
    @pytest.mark.asyncio
    async def test_analytics_empty(self, client):
        response = await client.get("/analytics")
        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 0
        assert data["success_rate"] == 0.0
        assert data["answered"] == 0
