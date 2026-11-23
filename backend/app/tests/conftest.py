import pytest

from app.api.auth import get_current_user
from app.main import app
from app.models.user import User


def pytest_configure(config):
    config.addinivalue_line("markers", "real_auth: run with real authentication instead of the default admin")


@pytest.fixture(autouse=True)
def _default_admin(request):
    """Most tests exercise features, not login: run them as an admin unless marked real_auth."""
    if request.node.get_closest_marker("real_auth"):
        yield
        return
    app.dependency_overrides[get_current_user] = lambda: User(
        id=0, username="test-admin", role="admin", is_active=True)
    yield
    app.dependency_overrides.pop(get_current_user, None)
