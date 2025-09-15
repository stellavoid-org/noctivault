from unittest.mock import create_autospec

import pytest

pytestmark = pytest.mark.integration


class _Provider:
    def fetch(self, platform, project, name, version):  # pragma: no cover - protocol only
        ...


def test_resolver_with_provider_protocol_and_inheritance():
    from noctivault.app.resolver import SecretResolver
    from noctivault.schema.models import Platform, ReferenceConfig

    refs = ReferenceConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-refs": [
                {"cast": "a", "ref": "alpha", "version": 1},
                {"key": "g", "children": [{"cast": "b", "ref": "beta", "version": "latest"}]},
            ],
        }
    )

    provider = create_autospec(_Provider, instance=True, spec_set=True)
    provider.fetch.side_effect = ["v1", "v2"]

    r = SecretResolver(provider)
    node = r.resolve(refs.secret_refs)

    assert node.to_dict(reveal=True) == {"a": "v1", "g": {"b": "v2"}}
    # protocol call expectations (platform inherited to children)
    provider.fetch.assert_any_call(Platform.GOOGLE, "p", "alpha", 1)
    provider.fetch.assert_any_call(Platform.GOOGLE, "p", "beta", "latest")
