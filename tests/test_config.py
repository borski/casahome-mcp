import json

import pytest
from pydantic import SecretStr, ValidationError

from casahome_mcp.config import ConfigurationError, ConfiguredHome, Settings

HOME = "11111111-1111-4111-8111-111111111111"
SECRET = "synthetic-secret-config"


@pytest.mark.parametrize("env", [{}, {"CASA_REFRESH_TOKEN": ""}])
def test_diagnostic_defaults(env: dict[str, str]) -> None:
    settings = Settings.from_env(env)
    assert settings.refresh_token is None
    assert settings.homes == ()
    assert not settings.allow_unverified_reads


@pytest.mark.parametrize("token", [" ", "\t\n", "op://Fake/token", " op://Fake/token"])
def test_unusable_token_is_private(token: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        Settings.from_env({"CASA_REFRESH_TOKEN": token})
    assert str(caught.value) == "Invalid configuration: CASA_REFRESH_TOKEN."
    if token.strip():
        assert token not in str(caught.value)


def test_token_not_trimmed_and_repr_safe() -> None:
    settings = Settings.from_env({"CASA_REFRESH_TOKEN": f" {SECRET} "})
    assert settings.refresh_token is not None
    assert settings.refresh_token.get_secret_value() == f" {SECRET} "
    assert SECRET not in repr(settings)
    assert SECRET not in settings.model_dump_json()


@pytest.mark.parametrize("flag", ["true", "TRUE", "True", "false", "FALSE"])
def test_boolean(flag: str) -> None:
    assert Settings.from_env({"CASA_ALLOW_UNVERIFIED_READS": flag}).allow_unverified_reads == (
        flag.lower() == "true"
    )


@pytest.mark.parametrize("flag", ["1", "yes", " false ", "", SECRET])
def test_bad_boolean(flag: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        Settings.from_env({"CASA_ALLOW_UNVERIFIED_READS": flag})
    assert str(caught.value) == "Invalid configuration: CASA_ALLOW_UNVERIFIED_READS."


@pytest.mark.parametrize(
    "raw",
    [
        SECRET,
        "null",
        "{}",
        '[{"id": "bad", "label": "Home"}]',
        json.dumps([{"id": HOME, "label": "Home", "extra": SECRET}]),
        json.dumps([{"id": HOME, "label": ""}]),
        json.dumps([{"id": HOME, "label": "a" * 81}]),
        json.dumps(
            [{"id": HOME, "label": "Home"}, {"id": HOME.replace("-", ""), "label": "Duplicate"}]
        ),
        json.dumps([{"id": HOME, "label": "Home"}] * 17),
    ],
)
def test_bad_homes_private(raw: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        Settings.from_env({"CASA_HOMES_JSON": raw})
    assert str(caught.value) == "Invalid configuration: CASA_HOMES_JSON."
    assert SECRET not in str(caught.value)


def test_canonical_frozen_settings() -> None:
    settings = Settings.from_env(
        {"CASA_HOMES_JSON": json.dumps([{"id": HOME.replace("-", ""), "label": "Test home"}])}
    )
    assert settings.homes[0].id == HOME
    for target, attribute, value in (
        (settings, "allow_unverified_reads", True),
        (settings.homes[0], "label", "Changed"),
    ):
        with pytest.raises(ValidationError):
            setattr(target, attribute, value)
    with pytest.raises(ValidationError):
        Settings.model_validate({"refresh_token": SecretStr(SECRET), "extra": SECRET})
    with pytest.raises(ValidationError):
        ConfiguredHome(id=HOME, label=2)  # type: ignore[arg-type]
