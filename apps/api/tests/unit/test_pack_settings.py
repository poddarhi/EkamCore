"""Unit tests for the S14-001 pack settings registry entries."""

from __future__ import annotations

import pytest

from api.errors import ValidationError
from api.services.settings_service import (
    SETTINGS_REGISTRY,
    _IntDef,
    _StringDef,
    validate_setting,
)


class TestPackSettingsRegistry:
    def test_all_pack_keys_registered(self):
        for key in (
            "pack.pla.daily_run_time",
            "pack.pla.weekly_run_day",
            "pack.pla.weekly_run_time",
            "pack.pla.follow_up_lookback_days",
            "pack.pla.relationship_inactive_days",
            "pack.pla.max_suggestions_per_day",
        ):
            assert key in SETTINGS_REGISTRY, key

    def test_defaults_match_spec(self):
        assert SETTINGS_REGISTRY["pack.pla.daily_run_time"].default == "06:00"
        assert SETTINGS_REGISTRY["pack.pla.weekly_run_day"].default == "monday"
        assert SETTINGS_REGISTRY["pack.pla.weekly_run_time"].default == "08:00"
        assert (
            SETTINGS_REGISTRY["pack.pla.follow_up_lookback_days"].default == 7
        )
        assert (
            SETTINGS_REGISTRY["pack.pla.relationship_inactive_days"].default
            == 30
        )
        assert (
            SETTINGS_REGISTRY["pack.pla.max_suggestions_per_day"].default == 5
        )


class TestStringDef:
    def test_daily_run_time_accepts_valid_hhmm(self):
        assert validate_setting("pack.pla.daily_run_time", "06:00") == "06:00"
        assert validate_setting("pack.pla.daily_run_time", "23:59") == "23:59"
        assert validate_setting("pack.pla.daily_run_time", "00:00") == "00:00"

    def test_daily_run_time_rejects_bad_format(self):
        for bad in ("6:00", "25:00", "12:60", "noon", "12:00:00", ""):
            with pytest.raises(ValidationError) as excinfo:
                validate_setting("pack.pla.daily_run_time", bad)
            assert excinfo.value.error_code == "VALIDATION_ERROR"

    def test_daily_run_time_rejects_non_string(self):
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.daily_run_time", 600)
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.daily_run_time", None)

    def test_weekly_run_time_independent_of_daily(self):
        # Same pattern, different key.
        assert validate_setting("pack.pla.weekly_run_time", "08:00") == "08:00"
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.weekly_run_time", "8am")


class TestEnumDef:
    def test_weekly_run_day_accepts_valid_days(self):
        for day in ("monday", "tuesday", "wednesday"):
            assert validate_setting("pack.pla.weekly_run_day", day) == day

    def test_weekly_run_day_rejects_unknown(self):
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.weekly_run_day", "Monday")
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.weekly_run_day", "mon")


class TestIntDef:
    def test_follow_up_lookback_accepts_in_range(self):
        assert validate_setting("pack.pla.follow_up_lookback_days", 3) == 3
        assert validate_setting("pack.pla.follow_up_lookback_days", 7) == 7
        assert validate_setting("pack.pla.follow_up_lookback_days", 30) == 30

    def test_follow_up_lookback_rejects_below_min(self):
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.follow_up_lookback_days", 2)
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.follow_up_lookback_days", 0)

    def test_follow_up_lookback_rejects_above_max(self):
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.follow_up_lookback_days", 31)

    def test_relationship_inactive_days_bounds(self):
        assert (
            validate_setting("pack.pla.relationship_inactive_days", 14) == 14
        )
        assert (
            validate_setting("pack.pla.relationship_inactive_days", 90) == 90
        )
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.relationship_inactive_days", 13)
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.relationship_inactive_days", 91)

    def test_max_suggestions_per_day_edges(self):
        assert validate_setting("pack.pla.max_suggestions_per_day", 1) == 1
        assert validate_setting("pack.pla.max_suggestions_per_day", 20) == 20
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.max_suggestions_per_day", 0)
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.max_suggestions_per_day", 21)


class TestStringDefUnitLevel:
    """Direct tests of _StringDef validation paths that the pack
    registry doesn't exercise directly (e.g. max_length enforcement,
    unused pattern branch)."""

    def test_max_length_enforced(self):
        # Inject a tiny custom entry + validate against it without
        # touching the public registry.
        key = "__test__.string_bounds"
        SETTINGS_REGISTRY[key] = _StringDef(
            default="ok", scope="user", max_length=3
        )
        try:
            assert validate_setting(key, "abc") == "abc"
            with pytest.raises(ValidationError):
                validate_setting(key, "abcd")
        finally:
            SETTINGS_REGISTRY.pop(key, None)

    def test_int_type_not_confused_with_bool(self):
        # Regression guard for the existing ``isinstance(value, bool)``
        # check in validate_setting — booleans must not pass as ints.
        with pytest.raises(ValidationError):
            validate_setting("pack.pla.max_suggestions_per_day", True)
        # Spot-check an _IntDef entry is still an _IntDef instance so
        # the test above actually exercises the integer branch.
        assert isinstance(
            SETTINGS_REGISTRY["pack.pla.max_suggestions_per_day"], _IntDef
        )
