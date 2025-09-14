import pytest

pytestmark = pytest.mark.integration


def test_resolver_resolves_refs_and_builds_tree_with_casts():
    from noctivault.app.resolver import SecretResolver
    from noctivault.provider.local_mocks import LocalMocksProvider
    from noctivault.schema.models import ReferenceConfig, TopLevelConfig

    mocks = TopLevelConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-mocks": [
                {"name": "db-pass", "value": "00123", "version": 1},
                {"name": "port", "value": "5432", "version": 1},
            ],
        }
    )
    refs = ReferenceConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-refs": [
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "password",
                    "ref": "db-pass",
                    "version": 1,
                    "type": "str",
                },
                {
                    "key": "database",
                    "children": [
                        {
                            "platform": "google",
                            "gcp_project_id": "p",
                            "cast": "port",
                            "ref": "port",
                            "version": 1,
                            "type": "int",
                        }
                    ],
                },
            ],
        }
    )

    provider = LocalMocksProvider.from_config(mocks)
    resolver = SecretResolver(provider)
    node = resolver.resolve(refs.secret_refs)

    # attribute access
    assert str(node.password) == "***"  # masked repr
    assert node.to_dict(reveal=False)["password"] == "***"
    assert node.to_dict(reveal=True)["password"] == "00123"
    assert node.database.port.get() == "5432"  # leaf .get() returns raw string
    # typed via to_dict reveal
    assert node.to_dict(reveal=True)["database"]["port"] == 5432


def test_resolver_duplicate_path_raises():
    from noctivault.app.resolver import SecretResolver
    from noctivault.core.errors import DuplicatePathError
    from noctivault.provider.local_mocks import LocalMocksProvider
    from noctivault.schema.models import ReferenceConfig, TopLevelConfig

    mocks = TopLevelConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-mocks": [
                {"name": "x", "value": "1", "version": 1},
                {"name": "y", "value": "2", "version": 1},
            ],
        }
    )
    refs = ReferenceConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-refs": [
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "same",
                    "ref": "x",
                    "version": 1,
                },
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "same",
                    "ref": "y",
                    "version": 1,
                },
            ],
        }
    )
    provider = LocalMocksProvider.from_config(mocks)
    resolver = SecretResolver(provider)
    with pytest.raises(DuplicatePathError):
        resolver.resolve(refs.secret_refs)


def test_resolver_type_cast_error():
    from noctivault.app.resolver import SecretResolver
    from noctivault.core.errors import TypeCastError
    from noctivault.provider.local_mocks import LocalMocksProvider
    from noctivault.schema.models import ReferenceConfig, TopLevelConfig

    mocks = TopLevelConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-mocks": [
                {"name": "n", "value": "not-int", "version": 1},
            ],
        }
    )
    refs = ReferenceConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-refs": [
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "n",
                    "ref": "n",
                    "version": 1,
                    "type": "int",
                },
            ],
        }
    )
    provider = LocalMocksProvider.from_config(mocks)
    resolver = SecretResolver(provider)
    with pytest.raises(TypeCastError):
        resolver.resolve(refs.secret_refs)
