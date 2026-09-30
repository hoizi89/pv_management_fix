"""Controller-Tests mit HA-Stubs (siehe ha_stubs.py).

Prüfen das Zusammenspiel im Controller, das die reinen calc-Tests nicht
abdecken: Helper-Offset vs. Options-Update, Persistenz-Roundtrip, Monatswechsel.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import datetime, timedelta

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import ha_stubs  # noqa: E402

if not ha_stubs.install():
    pytest.skip("Echtes Home Assistant installiert — Stub-Tests übersprungen",
                allow_module_level=True)

from custom_components.pv_management_fix import (  # noqa: E402
    PVManagementFixController,
    _structure_signature,
)
from custom_components.pv_management_fix.const import (  # noqa: E402
    CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY, CONF_GRID_IMPORT_ENTITY,
    CONF_CONSUMPTION_ENTITY, CONF_ELECTRICITY_PRICE_ENTITY, CONF_FIXED_PRICE,
    CONF_AMORTISATION_HELPER, CONF_RESTORE_FROM_HELPER, CONF_YEARLY_COST,
    CONF_INSTALLATION_DATE, CONF_SAVINGS_OFFSET, CONF_ENERGY_OFFSET_SELF,
    CONF_INSTALLATION_COST, CONF_MARKUP_FACTOR, CONF_PV_POWER_ENTITY,
)
from ha_stubs import Clock, FakeEntry, FakeHass, TZ  # noqa: E402

HELPER = "input_number.pv_ersparnis"
PRICE = "sensor.epex"


@pytest.fixture(autouse=True)
def _reset_clock():
    Clock.now = datetime(2026, 9, 30, 12, 0, tzinfo=TZ)
    yield


def _base_data(**extra):
    data = {
        CONF_PV_PRODUCTION_ENTITY: "sensor.pv",
        CONF_GRID_EXPORT_ENTITY: "sensor.export",
        CONF_GRID_IMPORT_ENTITY: "sensor.import",
        CONF_FIXED_PRICE: 30.0,  # ct/kWh
        CONF_MARKUP_FACTOR: 1.0,
        CONF_INSTALLATION_COST: 20000.0,
    }
    data.update(extra)
    return data


def _ctrl(data=None, options=None, hass=None):
    hass = hass or FakeHass()
    entry = FakeEntry(data or _base_data(), options)
    return PVManagementFixController(hass, entry), hass, entry


# =============================================================================
# #1 / #2 Helper-Offset
# =============================================================================


def _helper_ctrl():
    data = _base_data(**{
        CONF_AMORTISATION_HELPER: HELPER,
        CONF_RESTORE_FROM_HELPER: True,
        CONF_YEARLY_COST: 365.0,  # 1 €/Tag
        CONF_INSTALLATION_DATE: "2025-09-30",  # 365 Tage → 365 € Jahreskosten
    })
    ctrl, hass, entry = _ctrl(data)
    hass.states.set(HELPER, "5000.0", {"min": 0, "max": 100000})
    ctrl._accumulated_savings_self = 3000.0
    ctrl._accumulated_earnings_feed = 1000.0
    ctrl._restored = True
    return ctrl, hass, entry


def test_restore_from_helper_matches_helper_incl_yearly_costs():
    ctrl, hass, _ = _helper_ctrl()
    assert ctrl.total_yearly_costs == pytest.approx(365.0)
    assert asyncio.run(ctrl._restore_from_helper()) is True
    assert ctrl.total_savings == pytest.approx(5000.0)
    # Sync darf den Helper nicht verändern (kein Schrumpfen, Befund #2)
    assert not any(c[2]["value"] != 5000.0 for c in hass.services.calls)


def test_options_save_keeps_helper_offset():
    """Speichern einer beliebigen Menüseite überschreibt den Helper-Stand nicht (#1)."""
    ctrl, hass, entry = _helper_ctrl()
    asyncio.run(ctrl._restore_from_helper())
    entry.options = {**entry.options, CONF_PV_POWER_ENTITY: "sensor.pv_w"}
    ctrl._load_options()
    ctrl._notify_entities()
    assert ctrl.total_savings == pytest.approx(5000.0)
    assert all(c[2]["value"] == pytest.approx(5000.0) for c in hass.services.calls)


def test_options_offset_change_applies_delta_on_top_of_helper():
    ctrl, _, entry = _helper_ctrl()
    asyncio.run(ctrl._restore_from_helper())
    entry.options = {**entry.options, CONF_SAVINGS_OFFSET: 250.0}
    ctrl._load_options()
    assert ctrl.total_savings == pytest.approx(5250.0)
    # Nochmal speichern mit gleichem Wert → keine erneute Anwendung
    ctrl._load_options()
    assert ctrl.total_savings == pytest.approx(5250.0)


def test_disabling_restore_from_helper_drops_helper_offset():
    ctrl, _, entry = _helper_ctrl()
    asyncio.run(ctrl._restore_from_helper())
    entry.options = {**entry.options, CONF_RESTORE_FROM_HELPER: False}
    ctrl._load_options()
    assert ctrl._helper_offset is None
    assert ctrl.total_savings == pytest.approx(3000.0 + 1000.0 - 365.0)


def test_helper_sync_clamped_to_max():
    ctrl, hass, _ = _helper_ctrl()
    hass.states.set(HELPER, "100.0", {"min": 0, "max": 1000})
    ctrl._sync_to_helper()
    assert hass.services.calls[-1][2]["value"] == 1000.0


def test_stopped_controller_does_not_sync():
    ctrl, hass, _ = _helper_ctrl()
    asyncio.run(ctrl.async_stop())
    ctrl._notify_entities()
    ctrl._sync_to_helper()
    assert hass.services.calls == []


# =============================================================================
# #6 / Issue #19 Korrektur-Offset mit dynamischem Preis
# =============================================================================


def test_energy_offset_not_revalued_with_epex_price():
    data = _base_data(**{
        CONF_ELECTRICITY_PRICE_ENTITY: PRICE,
        CONF_ENERGY_OFFSET_SELF: 20000.0,
    })
    ctrl, hass, entry = _ctrl(data)
    hass.states.set(PRICE, "10.0", {"unit_of_measurement": "ct/kWh"})
    ctrl._fix_offset_valuation()
    fixed = ctrl.savings_self_consumption
    assert fixed == pytest.approx(20000.0 * 0.10)

    for price in ("45.0", "-5.0", "0.8", "30.0"):
        hass.states.set(PRICE, price, {"unit_of_measurement": "ct/kWh"})
        assert ctrl.savings_self_consumption == pytest.approx(fixed)

    # Offset um 1000 kWh erhöht bei 30 ct → nur das Delta zu 30 ct
    entry.options = {CONF_ENERGY_OFFSET_SELF: 21000.0}
    ctrl._load_options()
    ctrl._fix_offset_valuation()
    assert ctrl.savings_self_consumption == pytest.approx(fixed + 1000.0 * 0.30)


def test_offset_valuation_waits_for_price_sensor():
    data = _base_data(**{
        CONF_ELECTRICITY_PRICE_ENTITY: PRICE,
        CONF_ENERGY_OFFSET_SELF: 1000.0,
    })
    ctrl, hass, _ = _ctrl(data)
    hass.states.set(PRICE, "unavailable")
    ctrl._fix_offset_valuation()
    assert ctrl._offset_self_eur is None
    hass.states.set(PRICE, "20.0", {"unit_of_measurement": "ct/kWh"})
    ctrl._fix_offset_valuation()
    assert ctrl._offset_self_eur == pytest.approx(200.0)


# =============================================================================
# #10 Preis-Einheit
# =============================================================================


@pytest.mark.parametrize("raw,uom,expected", [
    ("0.8", "ct/kWh", 0.008),
    ("-3.0", "ct/kWh", -0.03),
    ("0.25", "EUR/kWh", 0.25),
    ("25.0", None, 0.25),
    ("0.25", None, 0.25),
])
def test_price_unit_from_sensor(raw, uom, expected):
    ctrl, hass, _ = _ctrl(_base_data(**{CONF_ELECTRICITY_PRICE_ENTITY: PRICE}))
    hass.states.set(PRICE, raw, {"unit_of_measurement": uom} if uom else {})
    assert ctrl.current_electricity_price == pytest.approx(expected)


# =============================================================================
# #7 / #8 Persistenz-Roundtrip
# =============================================================================


def _storage_roundtrip(ctrl, **extra):
    """Simuliert extra_restore_state_data → restore_data in sensor.py."""
    data = {
        "total_self_consumption_kwh": ctrl._total_self_consumption_kwh,
        "total_feed_in_kwh": ctrl._total_feed_in_kwh,
        "accumulated_savings_self": ctrl._accumulated_savings_self,
        "accumulated_earnings_feed": ctrl._accumulated_earnings_feed,
        "daily_reset_date": (ctrl._daily_tracking_date or Clock.now.date()).isoformat(),
        "monthly_grid_import_kwh": ctrl._monthly_grid_import_kwh,
        "monthly_grid_import_cost": ctrl._monthly_grid_import_cost,
        "monthly_reset_month": ctrl._monthly_tracking_month or Clock.now.month,
        "monthly_reset_year": ctrl._monthly_tracking_year or Clock.now.year,
    }
    data.update(ctrl.get_state_for_storage())
    data.update(extra)
    return data


def _running_ctrl():
    ctrl, hass, entry = _ctrl()
    ctrl._restored = True
    for eid, attr, val in (("sensor.pv", "_pv_production_kwh", 1000.0),
                           ("sensor.export", "_grid_export_kwh", 400.0),
                           ("sensor.import", "_grid_import_kwh", 2000.0)):
        setattr(ctrl, attr, val)
        ctrl._energy_seen.add(attr)
    ctrl._process_energy_update()  # Init-Guard (_last_*)
    ctrl._process_energy_update()  # Baselines snappen
    ctrl._pv_production_kwh = 1010.0
    ctrl._grid_export_kwh = 404.0
    ctrl._grid_import_kwh = 2005.0
    ctrl._process_energy_update()
    return ctrl, hass, entry


def test_baselines_survive_restart_and_downtime_energy_is_counted():
    ctrl, _, _ = _running_ctrl()
    assert ctrl._total_self_consumption_kwh == pytest.approx(6.0)
    stored = _storage_roundtrip(ctrl)

    # 10 h Downtime, in der 80 kWh PV produziert wurden (> 50 kWh alte Grenze)
    Clock.now = Clock.now + timedelta(hours=10)
    new, _, _ = _ctrl()
    new.restore_state(stored)
    assert new._last_pv_production_kwh == pytest.approx(1010.0)
    assert new._baseline_pv_production_kwh == pytest.approx(1000.0)
    assert new._pending_downtime_s == pytest.approx(10 * 3600)

    new._pv_production_kwh = 1090.0
    new._grid_export_kwh = 430.0
    new._grid_import_kwh = 2010.0
    # Solange nicht alle Sensoren einen Wert geliefert haben: nichts rechnen
    new._process_energy_update()
    assert new._total_self_consumption_kwh == pytest.approx(6.0)
    new._energy_seen.update({"_pv_production_kwh", "_grid_export_kwh", "_grid_import_kwh"})
    new._process_energy_update()
    # Eigenverbrauch = (1090-1000) - (430-400) = 60 kWh
    assert new._total_self_consumption_kwh == pytest.approx(60.0)
    assert new._total_feed_in_kwh == pytest.approx(30.0)
    assert new._pending_downtime_s is None


def test_monthly_values_survive_restart_and_summary_reports_previous_month():
    ctrl, hass, _ = _running_ctrl()
    assert ctrl._monthly_grid_import_kwh == pytest.approx(5.0)
    stored = _storage_roundtrip(ctrl)

    # Neustart im selben Monat: Monatswerte bleiben erhalten
    new, hass, _ = _ctrl()
    new.restore_state(stored)
    assert new._monthly_grid_import_kwh == pytest.approx(5.0)
    assert new._monthly_tracking_month == 9

    # Monatswechsel: Bericht am 1. meldet den Vormonat, nicht ~0
    Clock.now = datetime(2026, 10, 1, 0, 0, 10, tzinfo=TZ)
    new._check_monthly_summary()
    summary = [e for e in hass.bus.events if e[1]["type"] == "monthly_summary"]
    assert len(summary) == 1
    assert summary[0][1]["grid_import_kwh"] == pytest.approx(5.0)
    assert new._monthly_grid_import_kwh == 0.0

    # Nach Neustart am 1. kein zweiter Bericht
    stored2 = _storage_roundtrip(new)
    again, hass2, _ = _ctrl()
    again.restore_state(stored2)
    again._check_monthly_summary()
    assert not [e for e in hass2.bus.events if e[1]["type"] == "monthly_summary"]


def test_legacy_restore_without_new_keys():
    """Daten aus v2.5.0 (ohne Baselines/Offsets) laden weiterhin."""
    legacy = {
        "total_self_consumption_kwh": 100.0,
        "total_feed_in_kwh": 50.0,
        "accumulated_savings_self": 30.0,
        "accumulated_earnings_feed": 4.0,
        "monthly_reset_month": 9,
        "monthly_reset_year": 2026,
        "monthly_grid_import_kwh": 12.0,
    }
    ctrl, _, _ = _ctrl()
    ctrl.restore_state(legacy)
    assert ctrl._total_self_consumption_kwh == 100.0
    assert ctrl._baseline_pv_production_kwh is None
    assert ctrl._offset_self_eur is None
    assert ctrl._pending_downtime_s is None
    assert ctrl._monthly_grid_import_kwh == 12.0


# =============================================================================
# #5 last_reset
# =============================================================================


def test_daily_last_reset_is_local_midnight_of_tracking_day():
    ctrl, _, _ = _ctrl()
    ctrl._daily_tracking_date = Clock.now.date()
    assert ctrl.daily_last_reset == datetime(2026, 9, 30, 0, 0, tzinfo=TZ)


# =============================================================================
# Reload-Signatur
# =============================================================================


def test_structure_signature_detects_export_and_power_changes():
    base = _base_data()
    assert _structure_signature(base) == _structure_signature(dict(base))
    assert _structure_signature(base) != _structure_signature({**base, CONF_GRID_EXPORT_ENTITY: None})
    assert _structure_signature(base) != _structure_signature({**base, CONF_PV_POWER_ENTITY: "sensor.w"})
    assert _structure_signature(base) != _structure_signature({**base, CONF_CONSUMPTION_ENTITY: "sensor.c"})
    # Reine Preis-/Offset-Änderung → kein Reload
    assert _structure_signature(base) == _structure_signature({**base, CONF_SAVINGS_OFFSET: 5.0})
