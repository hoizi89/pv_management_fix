"""Reine Rechenlogik ohne Home-Assistant-Abhängigkeit.

Alles hier ist bewusst frei von hass/Entity-Zugriffen, damit es ohne
laufendes Home Assistant getestet werden kann (tests/).
"""
from __future__ import annotations

from datetime import date, datetime, time, tzinfo

PRICE_UNIT_EUR = "eur"
PRICE_UNIT_CENT = "cent"

# Grenze für Auto-Detect: > 1 €/kWh ist kein realer Arbeitspreis → ct/kWh.
AUTO_DETECT_CENT_THRESHOLD = 1.0

# Sanity-Grenze pro Energie-Update (kWh) im laufenden Betrieb
MAX_DELTA_KWH = 50.0
# Zuschlag pro Stunde Ausfallzeit beim ersten Update nach Restore (kWh/h).
# 30 kWh/h deckt PV + Wallbox + Wärmepumpe großzügig ab.
MAX_DELTA_KWH_PER_HOUR = 30.0
# Deckel für die Ausfallzeit, damit ein wochenalter Stand nicht beliebig
# große Sprünge durchlässt (7 Tage).
MAX_DOWNTIME_HOURS = 24.0 * 7


# =============================================================================
# PREIS-EINHEITEN (#10)
# =============================================================================


def unit_from_uom(uom: str | None) -> str | None:
    """Leitet die Preis-Einheit aus der unit_of_measurement eines Sensors ab.

    Erkennt u. a. "ct/kWh", "Cent/kWh", "c/kWh", "EUR/kWh", "€/kWh".
    Gibt None zurück, wenn die Einheit fehlt oder nicht eindeutig ist.
    """
    if not uom:
        return None
    u = str(uom).strip().lower().replace(" ", "")
    if not u:
        return None
    # Nur den Zähler betrachten ("ct/kWh" → "ct")
    numerator = u.split("/", 1)[0]
    if numerator in ("ct", "cent", "cents", "c", "eurocent", "¢", "gr", "rp"):
        return PRICE_UNIT_CENT
    if numerator in ("eur", "€", "euro", "chf", "pln", "zł", "zl", "$", "usd"):
        return PRICE_UNIT_EUR
    return None


def convert_price_to_eur(
    price: float,
    configured_unit: str | None = None,
    sensor_uom: str | None = None,
) -> float:
    """Rechnet einen Preis in €/kWh um.

    Reihenfolge (#10):
    1. unit_of_measurement des Sensors, falls eindeutig (ct/kWh, €/kWh …)
    2. explizit konfigurierte Einheit (eur/cent)
    3. Auto-Detect nur, wenn gar keine Einheit bekannt ist: |Preis| > 1 → ct/kWh
       (Betrag, damit auch negative Spotpreise in ct erkannt werden)

    Damit werden ct-Werte ≤ 1 und negative Spotpreise nicht mehr fälschlich
    als €/kWh gewertet, sobald eine Einheit bekannt ist.
    """
    unit = unit_from_uom(sensor_uom) or configured_unit
    if unit == PRICE_UNIT_CENT:
        return price / 100.0
    if unit == PRICE_UNIT_EUR:
        return price
    # Auto-Detect (keine Einheit bekannt)
    if abs(price) > AUTO_DETECT_CENT_THRESHOLD:
        return price / 100.0
    return price


# =============================================================================
# ENERGIE-KORREKTUREN: €-WERT FESTSCHREIBEN (#6 / Issue #19)
# =============================================================================


def offset_value_eur(
    offset_kwh: float,
    applied_kwh: float | None,
    applied_eur: float | None,
    price: float,
) -> float:
    """€-Wert einer Energie-Korrektur (kWh-Offset).

    Der Betrag wird beim Setzen mit dem dann gültigen Preis festgeschrieben
    (applied_kwh/applied_eur). Wird der kWh-Offset später geändert, wird nur
    das Delta zum dann aktuellen Preis bewertet. Ohne festgeschriebenen Wert
    (noch nicht initialisiert) wird einmalig zum aktuellen Preis bewertet.
    """
    if applied_kwh is None or applied_eur is None:
        return offset_kwh * price
    return applied_eur + (offset_kwh - applied_kwh) * price


def revalue_energy_offset(
    offset_kwh: float,
    applied_kwh: float | None,
    applied_eur: float | None,
    price: float,
) -> tuple[float, float]:
    """Schreibt den €-Wert eines kWh-Offsets fest.

    Gibt (applied_kwh, applied_eur) zurück, die persistiert werden.
    Unverändert, solange sich der kWh-Offset nicht ändert — Preisschwankungen
    wirken sich damit nicht mehr rückwirkend auf historische kWh aus.
    """
    if applied_kwh is not None and applied_eur is not None and applied_kwh == offset_kwh:
        return applied_kwh, applied_eur
    return offset_kwh, offset_value_eur(offset_kwh, applied_kwh, applied_eur, price)


# =============================================================================
# HELPER-RESTORE (#1 / #2)
# =============================================================================


def helper_savings_offset(
    helper_value: float,
    savings_self: float,
    earnings_feed: float,
    yearly_costs: float,
) -> float:
    """Offset, mit dem total_savings exakt dem Helper-Wert entspricht.

    total_savings = savings_self + earnings_feed + offset - yearly_costs
    → offset = helper - (savings_self + earnings_feed - yearly_costs)

    Bewusst ohne max(0, …): der Helper ist die Wahrheit, ein negativer
    Offset ist legitim (z. B. wenn die gezählten Werte höher sind als der
    gesicherte Stand oder negative Energie-Korrekturen aktiv sind).
    """
    return helper_value - (savings_self + earnings_feed - yearly_costs)


def clamp(value: float, min_value: float | None, max_value: float | None) -> float:
    """Begrenzt value auf [min_value, max_value] (None = offen)."""
    if min_value is not None and value < min_value:
        return min_value
    if max_value is not None and value > max_value:
        return max_value
    return value


# =============================================================================
# PERIODEN (#5 / #8)
# =============================================================================


def start_of_day(day: date, tz: tzinfo) -> datetime:
    """Beginn des lokalen Tages (00:00) als aware datetime — für last_reset."""
    return datetime.combine(day, time(), tzinfo=tz)


def start_of_month(day: date, tz: tzinfo) -> datetime:
    """Beginn des lokalen Monats (1., 00:00) als aware datetime."""
    return datetime.combine(day.replace(day=1), time(), tzinfo=tz)


def previous_month(year: int, month: int) -> tuple[int, int]:
    """(Jahr, Monat) des Vormonats."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


# =============================================================================
# DOWNTIME (#7)
# =============================================================================


def max_delta_kwh(downtime_seconds: float | None) -> float:
    """Erlaubter Energie-Sprung für ein Update.

    Im laufenden Betrieb MAX_DELTA_KWH. Beim ersten Update nach einem
    Restore wächst die Grenze mit der Ausfallzeit, damit die während der
    HA-Downtime aufgelaufene Energie nicht als "unrealistisch" verworfen
    wird (gedeckelt auf MAX_DOWNTIME_HOURS).
    """
    if not downtime_seconds or downtime_seconds <= 0:
        return MAX_DELTA_KWH
    hours = min(downtime_seconds / 3600.0, MAX_DOWNTIME_HOURS)
    return MAX_DELTA_KWH + hours * MAX_DELTA_KWH_PER_HOUR
