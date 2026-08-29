"""Tests for custom_components.luxtronik2.const."""

from __future__ import annotations

from datetime import timedelta
import re
from unittest.mock import MagicMock

from luxtronik.calculations import Calculations
from luxtronik.parameters import Parameters
from luxtronik.visibilities import Visibilities

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
from custom_components.luxtronik2.coordinator import LuxtronikCoordinator
from custom_components.luxtronik2.lux_overrides import (
    isolate_instance_data,
    name_unknown_visibilities_correctly,
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


# The highest index each library table *declares*. Snapshotted at import,
# because parse() adds an entry for every index a controller returns beyond
# it: one un-isolated long parse anywhere in the process would raise these
# and silently reclassify a generated register as a declared one.
_LIBRARY_CALCULATION_MAX = max(Calculations.calculations)
_LIBRARY_VISIBILITY_MAX = max(Visibilities.visibilities)


class TestLuxCalculationMatchesLibrary:
    """Guard LuxCalculation against drifting from the library + our overrides.

    Each member must follow `C<4-digit-index>_<description> =
    "calculations.<name>"`, where <index> and <name> resolve to the *same*
    entry in Calculations.calculations once the overrides are applied.

    Both halves catch a real bug. The name is what lookup actually matches on
    (Calculations._lookup, and key_exists() in common.py), so a name nobody
    registered fails silently - the entity is simply never created. The index
    is what base.py slices into the Luxtronik_Key state attribute, so a wrong
    one advertises a register the entity does not read.
    """

    NAME_PATTERN = re.compile(r"^C(\d{4})_[A-Z0-9]+(?:_[A-Z0-9]+)*$")

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
        return index if index > _LIBRARY_CALCULATION_MAX else None

    def test_members_match_library_and_overrides(self):
        update_Luxtronik_Parameters()
        registered = {
            calculation.name: index
            for index, calculation in Calculations.calculations.items()
        }

        problems = []
        for member in LuxCalculation:
            if member is LuxCalculation.UNSET:
                continue

            match = self.NAME_PATTERN.match(member.name)
            if match is None:
                problems.append(
                    f"{member.name}: name doesn't match C<NNNN>_<DESCRIPTION>"
                )
                continue

            if not member.value.startswith("calculations."):
                problems.append(
                    f"{member.name}: value {member.value!r} missing "
                    "'calculations.' prefix"
                )
                continue

            raw_name = member.value.removeprefix("calculations.")
            auto_created = self._auto_created_index(raw_name)
            index = registered.get(raw_name, auto_created)
            if index is None:
                problems.append(
                    f"{member.name}: {raw_name!r} is not registered in "
                    "Calculations.calculations (library or lux_overrides)"
                )
                continue

            label = int(match.group(1))
            if label != index:
                problems.append(
                    f"{member.name}: {raw_name!r} is calculation {index}, but the "
                    f"member is labelled {label} - base.py reports that label as "
                    "the register number"
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


class TestLuxVisibilityMatchesLibrary:
    """Guard LuxVisibility the way LuxParameter and LuxCalculation are guarded.

    Each member must follow `V<4-digit-index>_<description> =
    "visibilities.<name>"`, with <index> and <name> resolving to the same
    entry in Visibilities.visibilities. The name is what get_value() matches
    on, so a stale one makes entity_visible() log "Could not load visibility"
    and fall open - every gated entity turns up enabled.

    Two members are legitimately not register keys and are checked separately
    below rather than exempted on trust.
    """

    NAME_PATTERN = re.compile(r"^V(\d{4})[A-Z]?_[A-Z0-9]+(?:_[A-Z0-9]+)*$")

    # Visibilities.parse() creates an entry for every index past its table.
    # 0.3.14 names those Unknown_Parameter_<index> - a copy-paste from
    # parameters.py - which lux_overrides rewrites to the prefix the library
    # already uses inside its own table.
    AUTO_CREATED_PATTERN = re.compile(r"^Unknown_Visibility_(\d+)$")

    # Synthetic gates that name no register at all: _special_visibility()
    # answers them before get_value() is ever reached.
    SYNTHETIC = frozenset({LuxVisibility.V0059A_DHW_CHARGING_PUMP})

    def _auto_created_index(self, raw_name: str) -> int | None:
        match = self.AUTO_CREATED_PATTERN.match(raw_name)
        if match is None:
            return None
        index = int(match.group(1))
        return index if index > _LIBRARY_VISIBILITY_MAX else None

    def test_members_match_library_and_overrides(self):
        update_Luxtronik_Parameters()
        registered = {
            visibility.name: index
            for index, visibility in Visibilities.visibilities.items()
        }

        problems = []
        for member in LuxVisibility:
            if member is LuxVisibility.UNSET or member in self.SYNTHETIC:
                continue

            match = self.NAME_PATTERN.match(member.name)
            if match is None:
                problems.append(
                    f"{member.name}: name doesn't match V<NNNN>_<DESCRIPTION>"
                )
                continue

            if not member.value.startswith("visibilities."):
                problems.append(
                    f"{member.name}: value {member.value!r} missing "
                    "'visibilities.' prefix"
                )
                continue

            raw_name = member.value.removeprefix("visibilities.")
            # A generated name is accepted on its shape alone here; that it is
            # the name parse() really produces is what the next test proves.
            index = registered.get(raw_name, self._auto_created_index(raw_name))
            if index is None:
                problems.append(
                    f"{member.name}: {raw_name!r} is not registered in "
                    "Visibilities.visibilities"
                )
                continue

            label = int(match.group(1))
            if label != index:
                problems.append(
                    f"{member.name}: {raw_name!r} is visibility {index}, but the "
                    f"member is labelled {label}"
                )

        assert not problems, "LuxVisibility / library mismatches:\n" + "\n".join(
            problems
        )

    def test_the_auto_created_names_are_really_created_by_parse(self):
        """V0357 (electrical power limitation) sits past the table: 64 of the
        80 diagnostics dumps carry that index, generated rather than declared.
        The name asserted here is the one lux_overrides installs."""
        update_Luxtronik_Parameters()
        isolate_instance_data()  # keep parse() off the class-level dict
        name_unknown_visibilities_correctly()

        auto_created = {
            member: index
            for member in LuxVisibility
            if member is not LuxVisibility.UNSET
            and member not in self.SYNTHETIC
            and (
                index := self._auto_created_index(
                    member.value.removeprefix("visibilities.")
                )
            )
            is not None
        }
        assert auto_created, "no auto-created members left - drop the exemption"

        visibilities = Visibilities()
        visibilities.parse([0] * (max(auto_created.values()) + 1))
        for member in auto_created:
            raw_name = member.value.removeprefix("visibilities.")
            assert visibilities.get(raw_name) is not None, (
                f"{member.name}: parse() did not create {raw_name!r}"
            )

    def test_the_synthetic_members_are_answered_without_a_register(self):
        """V0059A is not a register: the DHW charging pump is present exactly
        when the recirculation pump is not, so _special_visibility() answers
        it and get_value() is never reached. If that special case ever goes
        away, the member becomes an unresolvable key instead of a gate."""
        coordinator = MagicMock(spec=LuxtronikCoordinator)
        for member in self.SYNTHETIC:
            answer = LuxtronikCoordinator._special_visibility(coordinator, member)
            assert answer is not None, (
                f"{member.name} names no register and has no special case"
            )


class TestLuxEnumsHaveNoAliases:
    """Two members sharing a value make the second one a Python enum *alias*:
    `LuxVisibility(...)` and iteration both yield only the first, so the
    second name silently resolves to the first member and never shows up in
    any check that walks the enum. V0009_MK3 and V0211_MK3 were exactly that
    - the same visibility defined twice, the correct label shadowed by the
    wrong one, and every consistency test blind to it.
    """

    def test_no_member_is_an_alias_of_another(self):
        problems = []
        for enum in (LuxParameter, LuxCalculation, LuxVisibility):
            for name, member in enum.__members__.items():
                if name != member.name:
                    problems.append(
                        f"{enum.__name__}.{name} is an alias of {member.name} "
                        f"- both are {member.value!r}"
                    )
        assert not problems, "duplicate enum values:\n" + "\n".join(problems)
