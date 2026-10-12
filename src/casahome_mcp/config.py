"""Strict, immutable process settings. No dotenv or credential lookup."""

import json
import os
from collections.abc import Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator


class ConfigurationError(Exception):
    def __init__(self, setting: str) -> None:
        super().__init__(f"Invalid configuration: {setting}.")


class ConfiguredHome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    id: str
    label: str = Field(min_length=1, max_length=80)

    @field_validator("id")
    @classmethod
    def canonical_id(cls, value: str) -> str:
        return str(UUID(value))


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)
    refresh_token: SecretStr | None = Field(default=None, repr=False)
    homes: tuple[ConfiguredHome, ...] = ()
    allow_unverified_reads: bool = False
    allow_actions: bool = False
    allow_messages: bool = False
    allow_uploads: bool = False
    allow_unverified_actions: bool = False

    @field_validator("refresh_token")
    @classmethod
    def check_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or value.get_secret_value() == "":
            return None
        raw = value.get_secret_value()
        if not raw.strip() or raw.lstrip().startswith("op://"):
            raise ValueError("Unusable credential.")
        return value

    @field_validator("homes")
    @classmethod
    def check_homes(cls, value: tuple[ConfiguredHome, ...]) -> tuple[ConfiguredHome, ...]:
        if len(value) > 16 or len({home.id for home in value}) != len(value):
            raise ValueError("Invalid home list.")
        return value

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        setting = "CASA_HOMES_JSON"
        try:
            entries = json.loads(env.get(setting, "[]"))
            if not isinstance(entries, list):
                raise ValueError
            homes = tuple(ConfiguredHome.model_validate(entry) for entry in entries)
            # Check list constraints here so diagnostics name the right setting.
            cls.check_homes(homes)
            setting = "CASA_ALLOW_UNVERIFIED_READS"
            flag = env.get(setting, "false").lower()
            if flag not in {"true", "false"}:
                raise ValueError
            flags: dict[str, bool] = {}
            for key in (
                "CASA_ALLOW_ACTIONS",
                "CASA_ALLOW_MESSAGES",
                "CASA_ALLOW_UPLOADS",
                "CASA_ALLOW_UNVERIFIED_ACTIONS",
            ):
                setting = key
                value = env.get(key, "false").lower()
                if value not in {"true", "false"}:
                    raise ValueError
                flags[key] = value == "true"
            setting = "CASA_REFRESH_TOKEN"
            raw = env.get(setting, "")
            token = cls.check_token(SecretStr(raw))
            return cls(
                refresh_token=token,
                homes=homes,
                allow_unverified_reads=flag == "true",
                allow_actions=flags["CASA_ALLOW_ACTIONS"],
                allow_messages=flags["CASA_ALLOW_MESSAGES"],
                allow_uploads=flags["CASA_ALLOW_UPLOADS"],
                allow_unverified_actions=flags["CASA_ALLOW_UNVERIFIED_ACTIONS"],
            )
        except (ValidationError, ValueError, TypeError, RecursionError):
            raise ConfigurationError(setting) from None
