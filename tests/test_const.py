"""Tests for custom_components.luxtronik2.const."""

from __future__ import annotations

from datetime import timedelta
import re

from luxtronik.calculations import Calculations
from luxtronik.parameters import Parameters

from custom_components.luxtronik2.const import (
    CONF_UPDATE_INTERVAL,
    CONFIG_ENTRY_VERSION,
    DEFAULT_MAX_DATA_LENGTH,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_OPTION,
    DOMAIN,
    PLATFORMS,
    UPDATE_INTERVAL_OPTIONS,
    DeviceKey,
    LuxCalculation,
    LuxMkTypes,
    LuxMode,
    LuxOperationMode,
    LuxParameter,
    LuxSmartGridStatus,
    LuxStatus1Option,
    LuxStatus3Option,
    LuxVisibility,
    SensorKey,
)
from custom_components.luxtronik2.lux_overrides import (
    isolate_instance_data,
    update_Luxtronik_Parameters,
)


class TestConstants:
    def test_domain(self):
        assert DOMAIN == "luxtronik2"

    def test_config_version(self):
        assert CONFIG_ENTRY_VERSION == 10

    def test_default_port(self):
        assert DEFAULT_PORT == 8889

    def test_default_timeout(self):
        assert isinstance(DEFAULT_TIMEOUT, float)

    def test_default_max_data_length(self):
        assert isinstance(DEFAULT_MAX_DATA_LENGTH, int)

    def test_platforms_not_empty(self):
        assert len(PLATFORMS) > 0


class TestDeviceKey:
    def test_heatpump(self):
        assert DeviceKey.heatpump == "heatpump"

    def test_heating(self):
        assert DeviceKey.heating == "heating"

    def test_domestic_water(self):
        assert DeviceKey.domestic_water == "domestic_water"

    def test_cooling(self):
        assert DeviceKey.cooling == "cooling"


class TestLuxOperationMode:
    def test_heating(self):
        assert LuxOperationMode.heating == "heating"

    def test_domestic_water(self):
        assert LuxOperationMode.domestic_water == "hot_water"

    def test_evu(self):
        assert LuxOperationMode.evu == "evu"

    def test_no_request(self):
        assert LuxOperationMode.no_request == "no_request"

    def test_cooling(self):
        assert LuxOperationMode.cooling == "cooling"

    def test_defrost(self):
        assert LuxOperationMode.defrost == "defrost"


class TestLuxMode:
    def test_off(self):
        assert LuxMode.off == "Off"

    def test_automatic(self):
        assert LuxMode.automatic == "Automatic"

    def test_party(self):
        assert LuxMode.party == "Party"

    def test_holidays(self):
        assert LuxMode.holidays == "Holidays"


class TestLuxSmartGridStatus:
    def test_locked(self):
        assert LuxSmartGridStatus.locked == "evu_locked"

    def test_normal(self):
        assert LuxSmartGridStatus.normal == "normal_operation"

    def test_increased(self):
        assert LuxSmartGridStatus.increased == "increased_operation"

    def test_reduced(self):
        assert LuxSmartGridStatus.reduced == "reduced_operation"


class TestLuxStatus1Option:
    def test_heatpump_running(self):
        assert LuxStatus1Option.heatpump_running == "heatpump_running"

    def test_heatpump_shutdown(self):
        assert LuxStatus1Option.heatpump_shutdown == "heatpump_shutdown"

    def test_compressor_heater(self):
        assert LuxStatus1Option.compressor_heater == "compressor_heater"


class TestLuxStatus3Option:
    def test_heating(self):
        assert LuxStatus3Option.heating == "heating"

    def test_cooling(self):
        assert LuxStatus3Option.cooling == "cooling"

    def test_domestic_water(self):
        assert LuxStatus3Option.domestic_water == "domestic_water"


class TestLuxMkTypes:
    def test_off(self):
        assert LuxMkTypes.off.value == 0

    def test_cooling(self):
        assert LuxMkTypes.cooling.value == 3

    def test_heating_cooling(self):
        assert LuxMkTypes.heating_cooling.value == 4


class TestLuxParameter:
    def test_unset(self):
        assert LuxParameter.UNSET is not None

    def test_mode_heating(self):
        assert "parameters" in LuxParameter.P0003_MODE_HEATING.value

    def test_mode_dhw(self):
        assert "parameters" in LuxParameter.P0004_MODE_DHW.value


class TestLuxCalculation:
    def test_unset(self):
        assert LuxCalculation.UNSET is not None

    def test_flow_in_temperature(self):
        assert "calculations" in LuxCalculation.C0010_FLOW_IN_TEMPERATURE.value

    def test_firmware_version(self):
        assert "calculations" in LuxCalculation.C0081_FIRMWARE_VERSION.value


class TestLuxVisibility:
    def test_unset(self):
        assert LuxVisibility.UNSET is not None

    def test_cooling(self):
        assert "visibilities" in LuxVisibility.V0005_COOLING.value


class TestSensorKey:
    def test_firmware(self):
        assert SensorKey.FIRMWARE is not None


class TestUpdateIntervalConstants:
    def test_default_update_interval(self):
        assert timedelta(seconds=60) == DEFAULT_UPDATE_INTERVAL

    def test_update_interval_options_keys_and_timedeltas(self):
        assert set(UPDATE_INTERVAL_OPTIONS.keys()) == {
            "10 seconds",
            "30 seconds",
            "1 minute (default)",
            "5 minutes",
        }
        assert UPDATE_INTERVAL_OPTIONS["10 seconds"].total_seconds() == 10
        assert UPDATE_INTERVAL_OPTIONS["30 seconds"].total_seconds() == 30
        assert UPDATE_INTERVAL_OPTIONS["1 minute (default)"].total_seconds() == 60
        assert UPDATE_INTERVAL_OPTIONS["5 minutes"].total_seconds() == 300

    def test_default_update_interval_option_is_a_valid_key(self):
        """DEFAULT_UPDATE_INTERVAL_OPTION must be a string key of
        UPDATE_INTERVAL_OPTIONS, not the DEFAULT_UPDATE_INTERVAL timedelta
        itself - the options flow's SelectSelector default must match one of
        its own option values or the schema fails to serialize (see #656).
        """
        assert isinstance(DEFAULT_UPDATE_INTERVAL_OPTION, str)
        assert DEFAULT_UPDATE_INTERVAL_OPTION in UPDATE_INTERVAL_OPTIONS
        assert (
            UPDATE_INTERVAL_OPTIONS[DEFAULT_UPDATE_INTERVAL_OPTION]
            == DEFAULT_UPDATE_INTERVAL
        )

    def test_conf_update_interval_constant(self):
        assert CONF_UPDATE_INTERVAL == "update_interval"


class TestLuxParameterMatchesLibrary:
    """Guard LuxParameter against drifting from the luxtronik library + our overrides.

    Each member must follow `P<4-digit-number>_<description> = "parameters.<name>"`,
    where <number> and <name> both resolve to the *same* entry in
    Parameters.parameters once library overrides are applied. This catches two
    real classes of bug: a member's number pointing at the wrong upstream
    parameter (its name won't match), and a member referencing a number that
    was never registered anywhere (library or lux_overrides).
    """

    NAME_PATTERN = re.compile(r"^P(\d{4})(?:_\d{4})?_[A-Z0-9]+(?:_[A-Z0-9]+)*$")

    # Parameter numbers with no backing entry in the luxtronik library or in
    # lux_overrides.parameters_to_add_update. These entities currently always
    # read/write None. Known gap, tracked for a follow-up fix - do not add new
    # numbers here; register new parameters properly instead (see
    # lux_overrides.parameters_to_add_update).
    KNOWN_MISSING_PARAMETERS = frozenset()

    def test_members_match_library_and_overrides(self):
        update_Luxtronik_Parameters()

        problems = []
        for member in LuxParameter:
            if member is LuxParameter.UNSET:
                continue

            match = self.NAME_PATTERN.match(member.name)
            if match is None:
                problems.append(
                    f"{member.name}: name doesn't match P<NNNN>_<DESCRIPTION>"
                )
                continue

            if not member.value.startswith("parameters."):
                problems.append(
                    f"{member.name}: value {member.value!r} missing 'parameters.' prefix"
                )
                continue

            raw_name = member.value.removeprefix("parameters.")
            if "{ID}" in raw_name:
                continue  # templated multi-index parameter, resolved dynamically

            number = int(match.group(1))
            if number in self.KNOWN_MISSING_PARAMETERS:
                continue

            parameter = Parameters.parameters.get(number)
            if parameter is None:
                problems.append(
                    f"{member.name}: parameter {number} has no backing entry in "
                    f"Parameters.parameters (library or lux_overrides)"
                )
                continue
            if parameter.name != raw_name:
                problems.append(
                    f"{member.name}: parameter {number} is registered as "
                    f"{parameter.name!r} but LuxParameter expects {raw_name!r}"
                )

        assert not problems, "LuxParameter / library mismatches:\n" + "\n".join(
            problems
        )

    def test_known_missing_parameters_are_still_missing(self):
        """Fail loudly once a known-broken parameter gets registered, as a nudge
        to remove it from KNOWN_MISSING_PARAMETERS and let the main check cover it."""
        update_Luxtronik_Parameters()

        now_present = {
            number
            for number in self.KNOWN_MISSING_PARAMETERS
            if Parameters.parameters.get(number) is not None
        }
        assert not now_present, (
            f"Parameters {sorted(now_present)} are now registered - remove them "
            "from KNOWN_MISSING_PARAMETERS so the main consistency test verifies them"
        )


class TestLuxCalculationMatchesLibrary:
    """Guard LuxCalculation against drifting from the library + our overrides.

    Every member must name a calculation that actually exists once the
    overrides are applied, because lookup is by name (Calculations._lookup,
    and key_exists() in common.py): a member naming a register nobody
    registered fails silently - the entity is simply never created.

    Matched by name, deliberately not by the C-number: a member's digits are
    a label, not always the register index (C0018-C0024, C0034 and C0204 all
    carry a prefix that differs from the index they read).
    """

    # 0.3.14 stops at index 259, but Calculations.parse() creates an
    # Unknown_Calculation_<index> entry for every further index the controller
    # actually returns - so a name past the table is legitimate, and is
    # verified against parse() below rather than exempted blindly.
    AUTO_CREATED_PATTERN = re.compile(r"^Unknown_Calculation_(\d+)$")

    def _auto_created_index(self, raw_name: str) -> int | None:
        match = self.AUTO_CREATED_PATTERN.match(raw_name)
        if match is None:
            return None
        index = int(match.group(1))
        return index if index > max(Calculations.calculations) else None

    def test_members_resolve_to_a_registered_calculation(self):
        update_Luxtronik_Parameters()
        registered = {
            calculation.name for calculation in Calculations.calculations.values()
        }

        problems = []
        for member in LuxCalculation:
            if member is LuxCalculation.UNSET:
                continue
            if not member.value.startswith("calculations."):
                problems.append(
                    f"{member.name}: value {member.value!r} missing "
                    "'calculations.' prefix"
                )
                continue

            raw_name = member.value.removeprefix("calculations.")
            if raw_name in registered:
                continue
            if self._auto_created_index(raw_name) is not None:
                continue

            problems.append(
                f"{member.name}: {raw_name!r} is not registered in "
                "Calculations.calculations (library or lux_overrides)"
            )

        assert not problems, "LuxCalculation / library mismatches:\n" + "\n".join(
            problems
        )

    def _auto_created_members(self) -> dict[LuxCalculation, int]:
        members = {}
        for member in LuxCalculation:
            if member is LuxCalculation.UNSET:
                continue
            index = self._auto_created_index(member.value.removeprefix("calculations."))
            if index is not None:
                members[member] = index
        return members

    def test_the_auto_created_names_are_really_created_by_parse(self):
        """The exemption above is only sound because parse() registers those
        indices. C0268 (current power consumption, and the denominator of both
        instantaneous COP sensors) is the one relying on it: absent from the
        static table, present on every controller that returns enough
        registers - 15 of the 28 units in the diagnostics corpus do, with real
        wattage."""
        update_Luxtronik_Parameters()
        isolate_instance_data()  # keep parse() off the class-level dict

        auto_created = self._auto_created_members()
        assert auto_created, "no auto-created members left - drop the exemption"

        calculations = Calculations()
        calculations.parse([0] * (max(auto_created.values()) + 1))
        for member in auto_created:
            raw_name = member.value.removeprefix("calculations.")
            assert calculations.get(raw_name) is not None, (
                f"{member.name}: parse() did not create {raw_name!r}"
            )

    def test_a_short_block_leaves_the_auto_created_names_absent(self):
        """The other half of the same rule: those registers exist only on the
        controllers that return them, which is what key_exists() reports on."""
        update_Luxtronik_Parameters()
        isolate_instance_data()

        calculations = Calculations()
        calculations.parse([0] * (max(Calculations.calculations) + 1))
        for member in self._auto_created_members():
            raw_name = member.value.removeprefix("calculations.")
            assert calculations.get(raw_name) is None
