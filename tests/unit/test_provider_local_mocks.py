import pytest

pytestmark = pytest.mark.unit


def test_local_mocks_fetch_and_latest_selection():
    from noctivault.provider.local_mocks import LocalMocksProvider
    from noctivault.schema.models import TopLevelConfig

    cfg = TopLevelConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-mocks": [
                {"name": "alpha", "value": "v1", "version": 1},
                {"name": "alpha", "value": "v2", "version": 2},
                {
                    "platform": "google",
                    "gcp_project_id": "q",
                    "name": "beta",
                    "value": "w3",
                    "version": 3,
                },
            ],
        }
    )

    provider = LocalMocksProvider.from_config(cfg)

    assert provider.fetch("google", "p", "alpha", 1) == "v1"
    assert provider.fetch("google", "p", "alpha", "latest") == "v2"
    assert provider.fetch("google", "q", "beta", 3) == "w3"


def test_local_mocks_missing_raises():
    from noctivault.core.errors import MissingLocalMockError
    from noctivault.provider.local_mocks import LocalMocksProvider
    from noctivault.schema.models import TopLevelConfig

    cfg = TopLevelConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-mocks": [
                {"name": "alpha", "value": "v1", "version": 1},
            ],
        }
    )
    provider = LocalMocksProvider.from_config(cfg)

    with pytest.raises(MissingLocalMockError):
        provider.fetch("google", "p", "alpha", 99)

    with pytest.raises(MissingLocalMockError):
        provider.fetch("google", "q", "alpha", 1)
