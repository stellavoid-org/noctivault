import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_top_level_requires_platform_and_project(models_module=None):
    from noctivault.schema.models import TopLevelConfig

    with pytest.raises(ValidationError):
        TopLevelConfig.model_validate({})

    cfg = TopLevelConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "my-proj",
            "secret-mocks": [],
        }
    )
    assert cfg.platform == "google"
    assert cfg.gcp_project_id == "my-proj"


def test_secret_mocks_inherit_top_level_platform_and_project():
    from noctivault.schema.models import TopLevelConfig

    cfg = TopLevelConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-mocks": [
                {"name": "db-pass", "value": "s3cr3t", "version": 1},
                {
                    "platform": "google",
                    "gcp_project_id": "q",
                    "name": "k",
                    "value": "v",
                    "version": 2,
                },
            ],
        }
    )
    # Effective inheritance tested via computed properties
    m0 = cfg.secret_mocks[0]
    assert m0.effective_platform == "google"
    assert m0.effective_project == "p"
    m1 = cfg.secret_mocks[1]
    assert m1.effective_platform == "google"
    assert m1.effective_project == "q"


def test_reference_config_validation_and_defaults():
    from noctivault.schema.models import ReferenceConfig

    cfg = ReferenceConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-refs": [
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "x",
                    "ref": "r",
                    "version": "latest",
                },
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "y",
                    "ref": "r2",
                    "version": 3,
                    "type": "int",
                },
            ],
        }
    )
    r0 = cfg.secret_refs[0]
    assert r0.type == "str"
    r1 = cfg.secret_refs[1]
    assert r1.type == "int"

    with pytest.raises(ValidationError):
        ReferenceConfig.model_validate(
            {
                "secret-refs": [
                    {
                        "platform": "google",
                        "gcp_project_id": "p",
                        "cast": "z",
                        "ref": "r3",
                        "type": "float",
                    }
                ]
            }
        )


def test_reference_config_inherits_top_level_platform_and_project():
    from noctivault.schema.models import ReferenceConfig

    cfg = ReferenceConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-refs": [
                {
                    # platform/gcp_project_id omitted; should inherit
                    "cast": "x",
                    "ref": "r",
                    "version": 1,
                },
                {
                    "key": "grp",
                    "children": [
                        {
                            # also omitted here
                            "cast": "y",
                            "ref": "r2",
                            "version": "latest",
                        }
                    ],
                },
            ],
        }
    )
    flat = []
    for e in cfg.secret_refs:
        if hasattr(e, "children"):
            flat.extend(e.children)
        else:
            flat.append(e)
    assert {e.platform for e in flat} == {"google"}
    assert {e.gcp_project_id for e in flat} == {"p"}


def test_secret_mocks_version_must_be_int_and_required():
    from noctivault.schema.models import TopLevelConfig

    with pytest.raises(ValidationError):
        TopLevelConfig.model_validate(
            {
                "platform": "google",
                "gcp_project_id": "p",
                "secret-mocks": [
                    {"name": "k", "value": "v"}  # missing version
                ],
            }
        )
    with pytest.raises(ValidationError):
        TopLevelConfig.model_validate(
            {
                "platform": "google",
                "gcp_project_id": "p",
                "secret-mocks": [
                    {"name": "k", "value": "v", "version": "latest"}  # not allowed
                ],
            }
        )


def test_secret_refs_version_int_or_latest():
    from noctivault.schema.models import ReferenceConfig

    cfg = ReferenceConfig.model_validate(
        {
            "platform": "google",
            "gcp_project_id": "p",
            "secret-refs": [
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "x",
                    "ref": "r",
                    "version": 1,
                },
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "y",
                    "ref": "r2",
                    "version": "latest",
                },
                {
                    "platform": "google",
                    "gcp_project_id": "p",
                    "cast": "z",
                    "ref": "r3",
                },  # default latest
            ],
        }
    )
    assert [e.version for e in cfg.secret_refs] == [1, "latest", "latest"]


def test_combined_config_is_rejected():
    from noctivault.schema.models import TopLevelConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TopLevelConfig.model_validate(
            {
                "platform": "google",
                "gcp_project_id": "p",
                "secret-mocks": [],
                "secret-refs": [],
            }
        )
