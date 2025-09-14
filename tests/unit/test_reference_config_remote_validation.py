import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_reference_config_requires_platform_and_project():
    from noctivault.schema.models import ReferenceConfig

    with pytest.raises(ValidationError):
        ReferenceConfig.model_validate({"secret-refs": []})

    with pytest.raises(ValidationError):
        ReferenceConfig.model_validate({"platform": "google", "secret-refs": []})

    with pytest.raises(ValidationError):
        ReferenceConfig.model_validate({"gcp_project_id": "p", "secret-refs": []})
