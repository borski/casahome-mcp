import json

import pytest
from pydantic import SecretStr, ValidationError

from casahome_mcp.config import ConfigurationError, ConfiguredHome, Settings

HOME = "11111111-1111-4111-8111-111111111111"
SECRET = "synthetic-secret-config"
FLAGS = {
    "CASA_ALLOW_UNVERIFIED_READS": "allow_unverified_reads",
    "CASA_ALLOW_ACTIONS": "allow_actions",
    "CASA_ALLOW_UNVERIFIED_ACTIONS": "allow_unverified_actions",
    "CASA_ALLOW_MESSAGES": "allow_messages",
    "CASA_ALLOW_UPLOADS": "allow_uploads",
}


@pytest.mark.parametrize("env", [{}, {"CASA_REFRESH_TOKEN": ""}])
def test_diagnostic_defaults(env: dict[str, str]) -> None:
    settings = Settings.from_env(env)
    assert settings.refresh_token is None
    assert settings.homes == ()
    assert settings.mode == "read_only"
    assert not settings.allow_unverified_reads
    assert not any(getattr(settings, field) for field in FLAGS.values())


@pytest.mark.parametrize(
    ("raw", "expected", "enabled"),
    [
        ("read_only", "read_only", set()),
        ("READ_ONLY", "read_only", set()),
        ("verified_actions", "verified_actions", {"allow_actions"}),
        ("Verified_Actions", "verified_actions", {"allow_actions"}),
        ("full", "full", set(FLAGS.values())),
        ("FULL", "full", set(FLAGS.values())),
    ],
)
def test_mode_profiles(raw: str, expected: str, enabled: set[str]) -> None:
    settings = Settings.from_env({"CASA_MODE": raw})
    assert settings.mode == expected
    assert {field for field in FLAGS.values() if getattr(settings, field)} == enabled


@pytest.mark.parametrize("raw", ["", " ", " full", "full ", "read-only", SECRET])
def test_bad_mode_is_private(raw: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        Settings.from_env({"CASA_MODE": raw})
    assert str(caught.value) == "Invalid configuration: CASA_MODE."
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize(("key", "field"), FLAGS.items())
@pytest.mark.parametrize("raw", ["true", "FALSE", "TrUe", "false"])
@pytest.mark.parametrize("mode", ["read_only", "verified_actions", "full"])
def test_present_flags_override_each_profile(mode: str, key: str, field: str, raw: str) -> None:
    baseline = Settings.from_env({"CASA_MODE": mode})
    settings = Settings.from_env({"CASA_MODE": mode, key: raw})
    assert getattr(settings, field) is (raw.lower() == "true")
    assert all(
        getattr(settings, other) == getattr(baseline, other)
        for other in FLAGS.values()
        if other != field
    )


@pytest.mark.parametrize("key", list(FLAGS))
@pytest.mark.parametrize("raw", ["", " ", "TRUE ", "1", "yes", SECRET])
def test_invalid_granular_flag_names_setting(key: str, raw: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        Settings.from_env({"CASA_MODE": "full", key: raw})
    assert str(caught.value) == f"Invalid configuration: {key}."
    assert SECRET not in str(caught.value)


def test_direct_construction_retains_old_flag_defaults() -> None:
    settings = Settings(allow_actions=True)
    assert settings.mode == "read_only"
    assert settings.allow_actions
    assert not settings.allow_unverified_actions
    assert not settings.allow_messages
    assert not settings.allow_uploads
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
        (settings, "mode", "full"),
        (settings.homes[0], "label", "Changed"),
    ):
        with pytest.raises(ValidationError):
            setattr(target, attribute, value)
    with pytest.raises(ValidationError):
        Settings.model_validate({"refresh_token": SecretStr(SECRET), "extra": SECRET})
    with pytest.raises(ValidationError):
        ConfiguredHome(id=HOME, label=2)  # type: ignore[arg-type]
