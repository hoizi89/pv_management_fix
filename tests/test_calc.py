"""Tests für die HA-freie Rechenlogik (calc.py)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest


# =============================================================================
# #6 / Issue #19: €-Wert der Energie-Korrektur festschreiben
# =============================================================================


def test_offset_fixed_despite_price_swings(calc):
    """Ein einmal bewerteter Offset ändert sich nicht mehr mit dem Börsenpreis."""
    kwh = 20000.0
    applied_kwh, applied_eur = calc.revalue_energy_offset(kwh, None, None, 0.30)
    assert applied_kwh == kwh
    assert applied_eur == pytest.approx(6000.0)

    # EPEX schwankt über den Tag stark, auch negativ
    for price in (0.05, 0.45, -0.10, 0.30, 1.20):
        value = calc.offset_value_eur(kwh, applied_kwh, applied_eur, price)
        assert value == pytest.approx(6000.0)
        assert calc.revalue_energy_offset(kwh, applied_kwh, applied_eur, price) == (
            applied_kwh, applied_eur,
        )


def test_offset_change_values_only_delta(calc):
    """Bei Änderung des kWh-Offsets wird nur das Delta zum aktuellen Preis bewertet."""
    applied_kwh, applied_eur = calc.revalue_energy_offset(1000.0, None, None, 0.20)
    assert applied_eur == pytest.approx(200.0)

    # Offset um 500 kWh erhöht, Preis inzwischen 0,40
    applied_kwh, applied_eur = calc.revalue_energy_offset(1500.0, applied_kwh, applied_eur, 0.40)
    assert applied_kwh == 1500.0
    assert applied_eur == pytest.approx(200.0 + 500.0 * 0.40)

    # Offset reduziert (negatives Delta) bei Preis 0,10
    applied_kwh, applied_eur = calc.revalue_energy_offset(1200.0, applied_kwh, applied_eur, 0.10)
    assert applied_eur == pytest.approx(400.0 - 300.0 * 0.10)


def test_offset_value_pending_change_is_previewed(calc):
    """Noch nicht festgeschriebene Änderung: bestehender Betrag + Delta × Preis."""
    assert calc.offset_value_eur(1500.0, 1000.0, 200.0, 0.40) == pytest.approx(400.0)


def test_offset_uninitialised_uses_current_price(calc):
    """Bestandsinstallation ohne festgeschriebenen Wert: einmalig aktueller Preis."""
    assert calc.offset_value_eur(100.0, None, None, 0.25) == pytest.approx(25.0)
    assert calc.offset_value_eur(-50.0, None, None, 0.08) == pytest.approx(-4.0)


def test_zero_offset_stays_zero(calc):
    applied = calc.revalue_energy_offset(0.0, None, None, 0.33)
    assert applied == (0.0, 0.0)
    assert calc.offset_value_eur(0.0, *applied, price=0.99) == 0.0


# =============================================================================
# #1 / #2: Helper-Restore inkl. Jahreskosten
# =============================================================================


def _total(savings_self, earnings_feed, offset, yearly_costs):
    """Spiegelt PVManagementFixController.total_savings."""
    return savings_self + earnings_feed + offset - yearly_costs


def test_helper_restore_includes_yearly_costs(calc):
    helper = 5000.0
    savings_self, earnings_feed, yearly_costs = 3000.0, 1200.0, 450.0
    offset = calc.helper_savings_offset(helper, savings_self, earnings_feed, yearly_costs)
    assert _total(savings_self, earnings_feed, offset, yearly_costs) == pytest.approx(helper)


def test_helper_does_not_shrink_over_restarts(calc):
    """Mehrere Neustarts hintereinander: der Helper-Wert bleibt stabil (#2)."""
    helper = 5000.0
    savings_self, earnings_feed, yearly_costs = 3000.0, 1200.0, 450.0
    for _ in range(10):
        offset = calc.helper_savings_offset(helper, savings_self, earnings_feed, yearly_costs)
        helper = _total(savings_self, earnings_feed, offset, yearly_costs)
    assert helper == pytest.approx(5000.0)


def test_helper_offset_may_be_negative(calc):
    """Kein max(0, …): gezählte Werte über dem Helper → negativer Offset."""
    offset = calc.helper_savings_offset(1000.0, 1100.0, 100.0, 0.0)
    assert offset == pytest.approx(-200.0)
    assert _total(1100.0, 100.0, offset, 0.0) == pytest.approx(1000.0)


def test_clamp(calc):
    assert calc.clamp(5.0, 0.0, 10.0) == 5.0
    assert calc.clamp(-1.0, 0.0, 10.0) == 0.0
    assert calc.clamp(99999.0, 0.0, 10000.0) == 10000.0
    assert calc.clamp(3.0, None, None) == 3.0


# =============================================================================
# #5: last_reset
# =============================================================================


def test_start_of_day_local(calc):
    tz = timezone(timedelta(hours=2))  # Sommerzeit Wien
    result = calc.start_of_day(date(2026, 9, 30), tz)
    assert result == datetime(2026, 9, 30, 0, 0, tzinfo=tz)
    assert result.utcoffset() == timedelta(hours=2)
    # In UTC ist das der Vorabend 22:00
    assert result.astimezone(timezone.utc) == datetime(2026, 9, 29, 22, 0, tzinfo=timezone.utc)


def test_start_of_month(calc):
    tz = timezone(timedelta(hours=1))
    assert calc.start_of_month(date(2026, 2, 17), tz) == datetime(2026, 2, 1, tzinfo=tz)


def test_previous_month(calc):
    assert calc.previous_month(2026, 1) == (2025, 12)
    assert calc.previous_month(2026, 10) == (2026, 9)


# =============================================================================
# #10: Preis-Einheiten
# =============================================================================


@pytest.mark.parametrize("uom,expected", [
    ("ct/kWh", "cent"),
    ("Cent/kWh", "cent"),
    ("c/kWh", "cent"),
    ("EUR/kWh", "eur"),
    ("€/kWh", "eur"),
    (" € / kWh ", "eur"),
    ("", None),
    (None, None),
    ("kWh", None),
])
def test_unit_from_uom(calc, uom, expected):
    assert calc.unit_from_uom(uom) == expected


def test_cent_sensor_small_and_negative_values(calc):
    """ct-Werte ≤ 1 und negative Spotpreise werden als ct erkannt (Bug #10)."""
    assert calc.convert_price_to_eur(0.8, sensor_uom="ct/kWh") == pytest.approx(0.008)
    assert calc.convert_price_to_eur(-3.5, sensor_uom="ct/kWh") == pytest.approx(-0.035)
    assert calc.convert_price_to_eur(0.8, configured_unit="cent") == pytest.approx(0.008)
    assert calc.convert_price_to_eur(-3.5, configured_unit="cent") == pytest.approx(-0.035)


def test_eur_sensor_is_not_divided(calc):
    assert calc.convert_price_to_eur(0.25, sensor_uom="EUR/kWh") == pytest.approx(0.25)
    assert calc.convert_price_to_eur(-0.02, sensor_uom="€/kWh") == pytest.approx(-0.02)


def test_sensor_uom_beats_configured_unit(calc):
    assert calc.convert_price_to_eur(25.0, configured_unit="eur", sensor_uom="ct/kWh") == pytest.approx(0.25)


def test_auto_detect_only_without_unit(calc):
    assert calc.convert_price_to_eur(25.0) == pytest.approx(0.25)
    assert calc.convert_price_to_eur(0.25) == pytest.approx(0.25)
    # Mit konfigurierter Einheit kein Auto-Detect
    assert calc.convert_price_to_eur(25.0, configured_unit="eur") == pytest.approx(25.0)


# =============================================================================
# #7: Downtime-Toleranz
# =============================================================================


def test_max_delta_default(calc):
    assert calc.max_delta_kwh(None) == calc.MAX_DELTA_KWH
    assert calc.max_delta_kwh(0) == calc.MAX_DELTA_KWH


def test_max_delta_scales_with_downtime(calc):
    assert calc.max_delta_kwh(3600 * 4) == pytest.approx(calc.MAX_DELTA_KWH + 4 * calc.MAX_DELTA_KWH_PER_HOUR)
    # Gedeckelt
    capped = calc.max_delta_kwh(3600 * 24 * 365)
    assert capped == pytest.approx(calc.MAX_DELTA_KWH + calc.MAX_DOWNTIME_HOURS * calc.MAX_DELTA_KWH_PER_HOUR)
