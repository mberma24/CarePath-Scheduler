import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from app.config import Settings


class SettingsWithoutEnvFile(Settings):
    model_config = SettingsConfigDict(env_file=None)  # ignore any local .env


def make(**overrides):
    return SettingsWithoutEnvFile(**overrides)


def test_defaults_are_valid():
    settings = make()
    assert (settings.clinic_open_hour, settings.clinic_close_hour) == (7, 19)


def test_close_hour_24_is_allowed():
    assert make(clinic_open_hour=0, clinic_close_hour=24).clinic_close_hour == 24


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param({"slot_minutes": 25}, "SLOT_MINUTES must divide an hour", id="slot-25"),
        pytest.param({"slot_minutes": 0}, "greater than or equal to 1", id="slot-0"),
        pytest.param(
            {"clinic_open_hour": 9, "clinic_close_hour": 9},
            "must be before",
            id="open-equals-close",
        ),
        pytest.param(
            {"clinic_open_hour": 19, "clinic_close_hour": 7},
            "must be before",
            id="open-after-close",
        ),
        pytest.param({"clinic_close_hour": 25}, "less than or equal to 24", id="close-25"),
        pytest.param({"schedule_horizon_days": 0}, "greater than or equal to 1", id="horizon-0"),
        pytest.param({"clinic_timezone": "Mars/Base"}, "Unknown CLINIC_TIMEZONE", id="bad-tz"),
    ],
)
def test_invalid_settings_fail_with_a_clear_message(overrides, message):
    with pytest.raises(ValidationError, match=message):
        make(**overrides)
