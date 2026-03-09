from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    DOMAIN, DATA_CTRL, PLATFORMS,
    CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_ELECTRICITY_PRICE, CONF_ELECTRICITY_PRICE_ENTITY, CONF_ELECTRICITY_PRICE_UNIT,
    CONF_FEED_IN_TARIFF, CONF_FEED_IN_TARIFF_ENTITY, CONF_FEED_IN_TARIFF_UNIT,
    CONF_INSTALLATION_COST, CONF_INSTALLATION_DATE, CONF_SAVINGS_OFFSET,
    CONF_ENERGY_OFFSET_SELF, CONF_ENERGY_OFFSET_EXPORT,
    CONF_FIXED_PRICE, CONF_MARKUP_FACTOR,
    CONF_AMORTISATION_HELPER, CONF_RESTORE_FROM_HELPER,
    CONF_QUOTA_ENABLED, CONF_QUOTA_YEARLY_KWH, CONF_QUOTA_START_DATE,
    CONF_QUOTA_START_METER, CONF_QUOTA_MONTHLY_RATE,
    CONF_BATTERY_SOC_ENTITY, CONF_BATTERY_CHARGE_ENTITY,
    CONF_BATTERY_DISCHARGE_ENTITY, CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY,
    CONF_BENCHMARK_ENABLED, CONF_BENCHMARK_HOUSEHOLD_SIZE, CONF_BENCHMARK_COUNTRY,
    CONF_BENCHMARK_HEATPUMP, CONF_BENCHMARK_HEATPUMP_ENTITY,
    DEFAULT_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_HOUSEHOLD_SIZE, DEFAULT_BENCHMARK_COUNTRY,
    DEFAULT_BENCHMARK_HEATPUMP,
    BENCHMARK_CONSUMPTION, BENCHMARK_HEATPUMP_CONSUMPTION, BENCHMARK_CO2_FACTORS,
    DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_FIXED_PRICE, DEFAULT_MARKUP_FACTOR, DEFAULT_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_EXPORT,
    DEFAULT_QUOTA_ENABLED, DEFAULT_QUOTA_YEARLY_KWH,
    DEFAULT_QUOTA_START_METER, DEFAULT_QUOTA_MONTHLY_RATE,
    PRICE_UNIT_CENT,
    PV_STRING_CONFIGS,
)

_LOGGER = logging.getLogger(__name__)

# CO2 Faktor für deutschen Strommix (kg CO2 pro kWh)
CO2_FACTOR_GRID = 0.4


class PVManagementFixController:
    """
    Controller für PV-Management Fixpreis.

    Vereinfachte Version für Fixpreis-Tarife ohne Batterie-Management.

    Features:
    - Amortisationsberechnung (inkrementell)
    - Spot vs. Fixpreis Vergleich
    - Energie-Tracking
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry

        # Konfigurierbare Werte (aus Options, fallback zu data)
        self._load_options()

        # Aktuelle Sensor-Werte (für Delta-Berechnung)
        self._last_pv_production_kwh: float | None = None
        self._last_grid_export_kwh: float | None = None
        self._last_grid_import_kwh: float | None = None

        # Aktuelle Totals (werden live aktualisiert)
        self._pv_production_kwh = 0.0
        self._grid_export_kwh = 0.0
        self._grid_import_kwh = 0.0
        self._consumption_kwh = 0.0

        # Letzte bekannte Preise (für Fallback wenn Sensor temporär nicht verfügbar)
        self._last_known_electricity_price: float | None = None
        self._last_known_feed_in_tariff: float | None = None
        self._price_sensor_available = True
        self._tariff_sensor_available = True

        # INKREMENTELL berechnete Werte (werden persistent gespeichert)
        self._total_self_consumption_kwh = 0.0
        self._total_feed_in_kwh = 0.0
        self._accumulated_savings_self = 0.0
        self._accumulated_earnings_feed = 0.0

        # Strompreis-Tracking für Durchschnittsberechnung (gewichtet nach Verbrauch)
        self._total_grid_import_cost = 0.0  # Gesamtkosten Netzbezug in €
        self._tracked_grid_import_kwh = 0.0  # Netzbezug für Durchschnittsberechnung

        # Tägliches Strompreis-Tracking
        self._daily_grid_import_cost = 0.0
        self._daily_grid_import_kwh = 0.0
        self._daily_feed_in_earnings = 0.0
        self._daily_feed_in_kwh = 0.0
        self._daily_tracking_date: date | None = None

        # Monatliches Strompreis-Tracking
        self._monthly_grid_import_cost = 0.0
        self._monthly_grid_import_kwh = 0.0
        self._monthly_tracking_month: int | None = None

        # Flag ob Werte aus Restore geladen wurden
        self._restored = False
        self._first_seen_date: date | None = None

        # Notification Tracking (verhindert Spam)
        self._milestones_fired: set[int] = set()
        self._quota_warning_80_sent = False
        self._quota_warning_100_sent = False
        self._quota_over_budget_sent = False
        self._monthly_summary_month: int | None = None

        # Benchmark-Startpunkte (Snapshot bei Reset/Erststart)
        self._benchmark_start_date: date | None = None
        self._benchmark_start_self_consumption: float = 0.0
        self._benchmark_start_grid_import: float = 0.0
        self._benchmark_start_feed_in: float = 0.0

        # Wärmepumpe Delta-Tracking (persistent über Neustarts)
        self._last_wp_kwh: float | None = None
        self._tracked_wp_kwh = 0.0
        self._wp_first_seen_date: date | None = None

        # Quota: Zählerstand bei Tagesbeginn (für robustes "Heute Verbleibend")
        self._quota_day_start_meter: float = 0.0
        self._quota_day_start_date: date | None = None

        # PV-String Delta-Tracking
        self._string_last_kwh: dict[str, float | None] = {}
        self._string_tracked_kwh: dict[str, float] = {}
        self._string_first_seen_date: date | None = None
        self._string_peak_w: dict[str, float] = {}
        self._string_daily_peak_w: dict[str, float] = {}
        self._string_daily_peak_date: date | None = None

        # Monatliche Buckets für Rolling-12-Month (Ring-Buffer)
        # Key: Monat (1-12), Value: dict mit Energiewerten
        self._monthly_buckets: dict[int, dict[str, float]] = {}
        self._monthly_bucket_month: int | None = None

        # Listener
        self._remove_listeners = []
        self._entity_listeners = []

    def _load_options(self):
        """Lädt Optionen aus Entry (Options überschreiben Data)."""
        opts = {**self.entry.data, **self.entry.options}

        # Sensor-Entities (können nachträglich geändert werden)
        self.pv_production_entity = opts.get(CONF_PV_PRODUCTION_ENTITY)
        self.grid_export_entity = opts.get(CONF_GRID_EXPORT_ENTITY)
        self.grid_import_entity = opts.get(CONF_GRID_IMPORT_ENTITY)
        self.consumption_entity = opts.get(CONF_CONSUMPTION_ENTITY)

        # Preis-Konfiguration
        self.electricity_price = opts.get(CONF_ELECTRICITY_PRICE, DEFAULT_ELECTRICITY_PRICE)
        self.electricity_price_entity = opts.get(CONF_ELECTRICITY_PRICE_ENTITY)
        self.electricity_price_unit = opts.get(CONF_ELECTRICITY_PRICE_UNIT, DEFAULT_ELECTRICITY_PRICE_UNIT)
        self.feed_in_tariff = opts.get(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)
        self.feed_in_tariff_entity = opts.get(CONF_FEED_IN_TARIFF_ENTITY)
        self.feed_in_tariff_unit = opts.get(CONF_FEED_IN_TARIFF_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT)

        # Kosten und Datum
        self.installation_cost = opts.get(CONF_INSTALLATION_COST, DEFAULT_INSTALLATION_COST)
        self.installation_date = opts.get(CONF_INSTALLATION_DATE)
        self.savings_offset = opts.get(CONF_SAVINGS_OFFSET, DEFAULT_SAVINGS_OFFSET)

        # Energie-Offsets (für historische Daten vor Tracking)
        self.energy_offset_self = opts.get(CONF_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_SELF)
        self.energy_offset_export = opts.get(CONF_ENERGY_OFFSET_EXPORT, DEFAULT_ENERGY_OFFSET_EXPORT)

        # Fixpreis (ct/kWh → €/kWh) und Aufschlagfaktor
        self.fixed_price = opts.get(CONF_FIXED_PRICE, DEFAULT_FIXED_PRICE) / 100.0
        self.markup_factor = opts.get(CONF_MARKUP_FACTOR, DEFAULT_MARKUP_FACTOR)

        # Stromkontingent
        self.quota_enabled = opts.get(CONF_QUOTA_ENABLED, DEFAULT_QUOTA_ENABLED)
        self.quota_yearly_kwh = opts.get(CONF_QUOTA_YEARLY_KWH, DEFAULT_QUOTA_YEARLY_KWH)
        self.quota_start_date_str = opts.get(CONF_QUOTA_START_DATE)
        self.quota_start_meter = opts.get(CONF_QUOTA_START_METER, DEFAULT_QUOTA_START_METER)
        self.quota_monthly_rate = opts.get(CONF_QUOTA_MONTHLY_RATE, DEFAULT_QUOTA_MONTHLY_RATE)
        # quota_seasonal entfernt — linearer Ansatz ist transparenter

        # Batterie
        self.battery_soc_entity = opts.get(CONF_BATTERY_SOC_ENTITY)
        self.battery_charge_entity = opts.get(CONF_BATTERY_CHARGE_ENTITY)
        self.battery_discharge_entity = opts.get(CONF_BATTERY_DISCHARGE_ENTITY)
        self.battery_capacity = opts.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)

        # Amortisation Helper (Pflicht für Persistenz)
        self.amortisation_helper = opts.get(CONF_AMORTISATION_HELPER)
        self.restore_from_helper = opts.get(CONF_RESTORE_FROM_HELPER, False)

        # Benchmark
        self.benchmark_enabled = opts.get(CONF_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_ENABLED)
        self.benchmark_household_size = opts.get(CONF_BENCHMARK_HOUSEHOLD_SIZE, DEFAULT_BENCHMARK_HOUSEHOLD_SIZE)
        self.benchmark_country = opts.get(CONF_BENCHMARK_COUNTRY, DEFAULT_BENCHMARK_COUNTRY)
        self.benchmark_heatpump = opts.get(CONF_BENCHMARK_HEATPUMP, DEFAULT_BENCHMARK_HEATPUMP)
        self.benchmark_heatpump_entity = opts.get(CONF_BENCHMARK_HEATPUMP_ENTITY)

        # PV-Strings
        self.pv_strings = []  # list of (name, energy_entity_id, power_entity_id_or_None)
        for name_key, entity_key, power_key, kwp_key in PV_STRING_CONFIGS:
            s_name = opts.get(name_key, "").strip()
            s_entity = opts.get(entity_key)
            s_power = opts.get(power_key)
            s_kwp = opts.get(kwp_key, 0.0)
            try:
                s_kwp = float(s_kwp) if s_kwp else 0.0
            except (ValueError, TypeError):
                s_kwp = 0.0
            if s_name and s_entity:
                self.pv_strings.append((s_name, s_entity, s_power, s_kwp))
        self._string_entity_ids = {e for _, e, _, _ in self.pv_strings}
        self._string_power_entity_ids = {p for _, _, p, _ in self.pv_strings if p}

    @property
    def fixed_price_ct(self) -> float:
        """Fixpreis netto in ct/kWh."""
        return self.fixed_price * 100

    @property
    def gross_price(self) -> float:
        """Brutto-Strompreis in €/kWh (netto × Aufschlagfaktor)."""
        return self.current_electricity_price * self.markup_factor

    @property
    def gross_price_ct(self) -> float:
        """Brutto-Strompreis in ct/kWh."""
        return self.gross_price * 100

    def _convert_price_to_eur(self, price: float, unit: str, auto_detect: bool = False) -> float:
        """Konvertiert Preis zu Euro/kWh (von Cent falls nötig)."""
        if auto_detect:
            if price > 1.0:
                return price / 100.0
            else:
                return price
        if unit == PRICE_UNIT_CENT:
            return price / 100.0
        return price

    def _get_entity_value(self, entity_id: str | None, fallback: float = 0.0) -> tuple[float, bool]:
        """Holt Wert von Entity oder verwendet Fallback."""
        if not entity_id:
            return fallback, True
        state = self.hass.states.get(entity_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                return float(state.state), True
            except (ValueError, TypeError):
                pass
        return fallback, False

    @property
    def current_electricity_price(self) -> float:
        """Aktueller Netto-Strompreis in €/kWh (aus Sensor oder statischem Fixpreis)."""
        if self.electricity_price_entity:
            raw_price, is_available = self._get_entity_value(
                self.electricity_price_entity, self.fixed_price
            )
            self._price_sensor_available = is_available
            if is_available:
                # Auto-detect: > 1 = wahrscheinlich ct/kWh
                price_eur = self._convert_price_to_eur(raw_price, self.electricity_price_unit, auto_detect=True)
                self._last_known_electricity_price = price_eur
                return price_eur
            elif self._last_known_electricity_price is not None:
                return self._last_known_electricity_price
        self._price_sensor_available = True
        return self.fixed_price

    @property
    def current_feed_in_tariff(self) -> float:
        """Aktuelle Einspeisevergütung in €/kWh."""
        if self.feed_in_tariff_entity:
            raw_tariff, is_available = self._get_entity_value(
                self.feed_in_tariff_entity, self.feed_in_tariff
            )
            self._tariff_sensor_available = is_available
            if is_available:
                self._last_known_feed_in_tariff = raw_tariff
                return self._convert_price_to_eur(raw_tariff, self.feed_in_tariff_unit, auto_detect=True)
            elif self._last_known_feed_in_tariff is not None:
                return self._convert_price_to_eur(self._last_known_feed_in_tariff, self.feed_in_tariff_unit, auto_detect=True)
        self._tariff_sensor_available = True
        return self._convert_price_to_eur(self.feed_in_tariff, self.feed_in_tariff_unit, auto_detect=False)

    # =========================================================================
    # ENERGIE PROPERTIES
    # =========================================================================

    @property
    def pv_production_kwh(self) -> float:
        """Aktuelle PV-Produktion vom Sensor."""
        return self._pv_production_kwh

    @property
    def grid_export_kwh(self) -> float:
        """Aktuelle Netzeinspeisung vom Sensor."""
        return self._grid_export_kwh

    @property
    def grid_import_kwh(self) -> float:
        """Aktueller Netzbezug vom Sensor."""
        return self._grid_import_kwh

    @property
    def consumption_kwh(self) -> float:
        """Aktueller Verbrauch vom Sensor."""
        return self._consumption_kwh

    @property
    def self_consumption_kwh(self) -> float:
        """Gesamter Eigenverbrauch (inkrementell + Offset)."""
        return self._total_self_consumption_kwh + self.energy_offset_self

    @property
    def feed_in_kwh(self) -> float:
        """Gesamte Einspeisung (inkrementell + Offset)."""
        return self._total_feed_in_kwh + self.energy_offset_export

    @property
    def tracked_grid_import_kwh(self) -> float:
        """Getrackte Netzbezug-kWh für Durchschnittsberechnung."""
        return self._tracked_grid_import_kwh

    @property
    def total_grid_import_cost(self) -> float:
        """Gesamtkosten Netzbezug in €."""
        return self._total_grid_import_cost

    # =========================================================================
    # STROMPREIS-DURCHSCHNITT
    # =========================================================================

    @property
    def average_electricity_price(self) -> float | None:
        """Gewichteter durchschnittlicher Strompreis in €/kWh."""
        if self._tracked_grid_import_kwh <= 0:
            return None
        return self._total_grid_import_cost / self._tracked_grid_import_kwh

    @property
    def average_electricity_price_ct(self) -> float | None:
        """Gewichteter durchschnittlicher Strompreis in ct/kWh."""
        avg = self.average_electricity_price
        if avg is None:
            return None
        return avg * 100

    @property
    def daily_average_price_ct(self) -> float | None:
        """Täglicher gewichteter Durchschnittspreis in ct/kWh."""
        if self._daily_grid_import_kwh <= 0:
            return None
        return (self._daily_grid_import_cost / self._daily_grid_import_kwh) * 100

    @property
    def monthly_average_price_ct(self) -> float | None:
        """Monatlicher gewichteter Durchschnittspreis in ct/kWh."""
        if self._monthly_grid_import_kwh <= 0:
            return None
        return (self._monthly_grid_import_cost / self._monthly_grid_import_kwh) * 100

    @property
    def daily_grid_import_kwh(self) -> float:
        """Täglicher Netzbezug in kWh."""
        return self._daily_grid_import_kwh

    @property
    def daily_grid_import_cost(self) -> float:
        """Tägliche Netzbezugskosten in €."""
        return self._daily_grid_import_cost

    @property
    def daily_feed_in_earnings(self) -> float:
        """Tägliche Einspeisevergütung in €."""
        return self._daily_feed_in_earnings

    @property
    def daily_feed_in_kwh(self) -> float:
        """Tägliche Einspeisung in kWh."""
        return self._daily_feed_in_kwh

    @property
    def daily_net_electricity_cost(self) -> float:
        """Tägliche Netto-Stromkosten (Einkauf minus Verkauf) in €."""
        return self._daily_grid_import_cost - self._daily_feed_in_earnings

    @property
    def monthly_grid_import_kwh(self) -> float:
        """Monatlicher Netzbezug in kWh."""
        return self._monthly_grid_import_kwh

    @property
    def monthly_grid_import_cost(self) -> float:
        """Monatliche Netzbezugskosten in €."""
        return self._monthly_grid_import_cost

    # =========================================================================
    # STROMKONTINGENT
    # =========================================================================

    @property
    def quota_start_date(self) -> date | None:
        """Startdatum der Kontingent-Periode."""
        if not self.quota_start_date_str:
            return None
        try:
            if isinstance(self.quota_start_date_str, str):
                return datetime.fromisoformat(self.quota_start_date_str).date()
            return self.quota_start_date_str
        except (ValueError, TypeError):
            return None

    @property
    def quota_end_date(self) -> date | None:
        """Enddatum der Kontingent-Periode (Start + 1 Jahr)."""
        start = self.quota_start_date
        if start is None:
            return None
        from datetime import timedelta
        return start + timedelta(days=365)

    @property
    def quota_days_total(self) -> int:
        """Gesamttage der Periode (365)."""
        return 365

    @property
    def quota_days_elapsed(self) -> int:
        """Vergangene Tage seit Periodenbeginn (Starttag = Tag 1)."""
        start = self.quota_start_date
        if start is None:
            return 0
        elapsed = (date.today() - start).days
        if elapsed < 0:
            return 0
        return min(elapsed + 1, self.quota_days_total)

    @property
    def quota_days_remaining(self) -> int:
        """Verbleibende Tage in der Periode."""
        return max(0, self.quota_days_total - self.quota_days_elapsed)

    @property
    def quota_consumed_kwh(self) -> float:
        """Verbrauchte kWh seit Periodenbeginn (Zählerstand - Startwert)."""
        if not self.quota_enabled or self.quota_start_date is None:
            return 0.0
        current_meter = self._grid_import_kwh
        consumed = current_meter - self.quota_start_meter
        return max(0.0, consumed)

    @property
    def quota_remaining_kwh(self) -> float:
        """Verbleibendes Kontingent in kWh."""
        return self.quota_yearly_kwh - self.quota_consumed_kwh

    @property
    def quota_consumed_percent(self) -> float:
        """Verbrauchter Anteil des Kontingents in Prozent."""
        if self.quota_yearly_kwh <= 0:
            return 0.0
        return min(100.0, (self.quota_consumed_kwh / self.quota_yearly_kwh) * 100)

    @property
    def quota_expected_kwh(self) -> float:
        """Soll-Verbrauch (linear, Starttag = Tag 1)."""
        if self.quota_days_total <= 0:
            return 0.0
        start = self.quota_start_date
        if start is None or date.today() < start:
            return 0.0
        return (self.quota_days_elapsed / self.quota_days_total) * self.quota_yearly_kwh

    @property
    def quota_reserve_kwh(self) -> float:
        """Reserve: Soll minus Ist. Positiv = unter Budget, negativ = drüber."""
        return self.quota_expected_kwh - self.quota_consumed_kwh

    @property
    def quota_daily_budget_kwh(self) -> float | None:
        """Tagesbudget: Restmenge / Resttage (steigt wenn du sparst, sinkt wenn du mehr verbrauchst)."""
        remaining_days = self.quota_days_remaining
        if remaining_days <= 0:
            return None
        return self.quota_remaining_kwh / remaining_days

    @property
    def quota_today_consumed_kwh(self) -> float:
        """Heutiger Verbrauch aus Zählerstand (robust gegen Restarts)."""
        if self._grid_import_kwh <= 0:
            return 0.0
        # Am Starttag: Start-Meter verwenden (unabhängig von Persistierung)
        day_start = self._quota_day_start_meter
        qs = self.quota_start_date
        if (self.quota_enabled and qs is not None
                and date.today() == qs and self.quota_start_meter > 0):
            day_start = self.quota_start_meter
        if day_start <= 0:
            return 0.0
        return max(0.0, self._grid_import_kwh - day_start)

    @property
    def quota_today_remaining_kwh(self) -> float | None:
        """Verbleibendes Tagesbudget: Budget minus heutiger Verbrauch (zählerstandbasiert)."""
        budget = self.quota_daily_budget_kwh
        if budget is None:
            return None
        return budget - self.quota_today_consumed_kwh

    @property
    def quota_forecast_kwh(self) -> float | None:
        """Hochrechnung: Verbrauch am Periodenende bei aktuellem Tempo."""
        days_elapsed = self.quota_days_elapsed
        if days_elapsed <= 0:
            return None
        return (self.quota_consumed_kwh / days_elapsed) * self.quota_days_total

    @property
    def quota_status_text(self) -> str:
        """Status-Text für Kontingent."""
        if not self.quota_enabled or self.quota_start_date is None:
            return "Nicht konfiguriert"
        reserve = self.quota_reserve_kwh
        if reserve >= 0:
            return f"Im Budget (+{reserve:.0f} kWh Reserve)"
        else:
            return f"Über Budget ({reserve:.0f} kWh)"

    # =========================================================================
    # AMORTISATION
    # =========================================================================

    @property
    def savings_self_consumption(self) -> float:
        """Ersparnis durch Eigenverbrauch."""
        return self._accumulated_savings_self

    @property
    def earnings_feed_in(self) -> float:
        """Einnahmen durch Einspeisung."""
        return self._accumulated_earnings_feed

    @property
    def total_savings(self) -> float:
        """Gesamtersparnis inkl. manuellem Offset."""
        base = self.savings_self_consumption + self.earnings_feed_in
        return base + self.savings_offset

    @property
    def amortisation_percent(self) -> float:
        """Amortisation in Prozent."""
        if self.installation_cost <= 0:
            return 100.0
        return min(100.0, (self.total_savings / self.installation_cost) * 100)

    @property
    def remaining_cost(self) -> float:
        """Restbetrag bis zur Amortisation."""
        return max(0.0, self.installation_cost - self.total_savings)

    @property
    def is_amortised(self) -> bool:
        """True wenn vollständig amortisiert."""
        return self.total_savings >= self.installation_cost

    @property
    def _current_self_consumption_kwh(self) -> float:
        """Aktueller Eigenverbrauch in kWh (Batterie-kompatibel).

        Bevorzugt: Verbrauch - Netzbezug (korrekt bei Batterie-Systemen).
        Fallback: PV - Export (nur korrekt ohne Batterie).
        """
        if self.consumption_entity and self._consumption_kwh > 0 and self.grid_import_entity:
            return max(0.0, self._consumption_kwh - self._grid_import_kwh)
        return max(0.0, self._pv_production_kwh - self._grid_export_kwh)

    @property
    def self_consumption_ratio(self) -> float:
        """Eigenverbrauchsquote (%) - Anteil der PV-Produktion der selbst verbraucht wird."""
        if self._pv_production_kwh <= 0:
            return 0.0
        return min(100.0, (self._current_self_consumption_kwh / self._pv_production_kwh) * 100)

    @property
    def autarky_rate(self) -> float | None:
        """Autarkiegrad (%) - Anteil des Verbrauchs der durch PV gedeckt wird."""
        self_consumption = self._current_self_consumption_kwh
        if self_consumption <= 0:
            return None
        if self.consumption_entity and self._consumption_kwh > 0:
            return min(100.0, (self_consumption / self._consumption_kwh) * 100)
        if self.grid_import_entity and self._grid_import_kwh > 0:
            total_consumption = self_consumption + self._grid_import_kwh
            if total_consumption > 0:
                return min(100.0, (self_consumption / total_consumption) * 100)
        return None

    @property
    def co2_saved_kg(self) -> float:
        """Eingesparte CO2-Emissionen in kg."""
        return self.self_consumption_kwh * CO2_FACTOR_GRID

    # =========================================================================
    # BATTERIE
    # =========================================================================

    @property
    def battery_soc(self) -> float | None:
        """Batterie-Ladestand in %."""
        if not self.battery_soc_entity:
            return None
        val, ok = self._get_entity_value(self.battery_soc_entity)
        return val if ok else None

    @property
    def battery_charge_total(self) -> float | None:
        """Gesamt-Ladung in kWh."""
        if not self.battery_charge_entity:
            return None
        val, ok = self._get_entity_value(self.battery_charge_entity)
        return val if ok else None

    @property
    def battery_discharge_total(self) -> float | None:
        """Gesamt-Entladung in kWh."""
        if not self.battery_discharge_entity:
            return None
        val, ok = self._get_entity_value(self.battery_discharge_entity)
        return val if ok else None

    @property
    def battery_efficiency(self) -> float | None:
        """Batterie-Effizienz in % (Entladung / Ladung × 100)."""
        charge = self.battery_charge_total
        discharge = self.battery_discharge_total
        if charge is None or discharge is None or charge <= 0:
            return None
        return (discharge / charge) * 100

    @property
    def battery_cycles_estimate(self) -> float | None:
        """Geschätzte Zyklen (Gesamt-Ladung / Kapazität)."""
        charge = self.battery_charge_total
        if charge is None or self.battery_capacity <= 0:
            return None
        return charge / self.battery_capacity

    # =========================================================================
    # ROI
    # =========================================================================

    @property
    def roi_percent(self) -> float | None:
        """Return on Investment in % (negativ vor, positiv nach Amortisation)."""
        if self.installation_cost <= 0:
            return None
        return ((self.total_savings - self.installation_cost) / self.installation_cost) * 100

    @property
    def annual_roi_percent(self) -> float | None:
        """Jährlicher ROI in %."""
        if self.installation_cost <= 0:
            return None
        days = self.days_since_installation
        if days <= 0:
            return None
        years = days / 365.0
        annual_savings = self.total_savings / years
        return ((annual_savings - (self.installation_cost / years)) / self.installation_cost) * 100

    @property
    def days_since_installation(self) -> int:
        """Tage seit Installation (oder erstem Tracking)."""
        if self.installation_date:
            try:
                if isinstance(self.installation_date, str):
                    install_date = datetime.fromisoformat(self.installation_date).date()
                else:
                    install_date = self.installation_date
                return (date.today() - install_date).days
            except (ValueError, TypeError):
                pass
        return self.days_tracking

    @property
    def days_tracking(self) -> int:
        """Tage seit erstem Tracking (unabhängig von Installationsdatum)."""
        if self._first_seen_date:
            return (date.today() - self._first_seen_date).days
        return 0

    @property
    def average_daily_savings(self) -> float:
        """Durchschnittliche tägliche Ersparnis."""
        days = self.days_since_installation
        if days <= 0:
            return 0.0
        return self.total_savings / days

    @property
    def average_monthly_savings(self) -> float:
        """Durchschnittliche monatliche Ersparnis."""
        return self.average_daily_savings * 30.44

    @property
    def average_yearly_savings(self) -> float:
        """Durchschnittliche jährliche Ersparnis."""
        return self.average_daily_savings * 365

    @property
    def estimated_remaining_days(self) -> int | None:
        """Geschätzte verbleibende Tage bis Amortisation."""
        if self.is_amortised:
            return 0
        daily_avg = self.average_daily_savings
        if daily_avg <= 0:
            return None
        return int(self.remaining_cost / daily_avg)

    @property
    def estimated_payback_date(self) -> date | None:
        """Geschätztes Amortisationsdatum."""
        remaining = self.estimated_remaining_days
        if remaining is None:
            return None
        if remaining == 0:
            return date.today()
        from datetime import timedelta
        return date.today() + timedelta(days=remaining)

    @property
    def status_text(self) -> str:
        """Status-Text für Anzeige."""
        if self.is_amortised:
            profit = self.total_savings - self.installation_cost
            return f"Amortisiert! +{profit:.2f}€ Gewinn"
        else:
            return f"{self.amortisation_percent:.1f}% amortisiert"

    # =========================================================================
    # BENCHMARK
    # =========================================================================

    @property
    def benchmark_avg_consumption_kwh(self) -> int:
        """Referenz-Haushaltsstrom (OHNE WP) aus Benchmark-Tabelle."""
        country_data = BENCHMARK_CONSUMPTION.get(self.benchmark_country, BENCHMARK_CONSUMPTION["AT"])
        size = max(1, min(6, self.benchmark_household_size))
        return country_data.get(size, country_data[3])

    @property
    def benchmark_avg_heatpump_kwh(self) -> int | None:
        """WP-Referenzverbrauch (nur wenn WP aktiv)."""
        if not self.benchmark_heatpump:
            return None
        return BENCHMARK_HEATPUMP_CONSUMPTION.get(self.benchmark_country, BENCHMARK_HEATPUMP_CONSUMPTION["AT"])

    @property
    def benchmark_own_annual_consumption_kwh(self) -> float | None:
        """Gesamtverbrauch hochgerechnet auf 1 Jahr (inkl. WP).

        Verwendet Rolling-12-Month Buckets wenn 12 Monate vorhanden,
        sonst Extrapolation seit Benchmark-Start.
        """
        # Bucket-basiert (12 Monate vorhanden)
        if len(self._monthly_buckets) >= 12:
            total = sum(
                b.get("self_consumption", 0.0) + b.get("grid_import", 0.0)
                for b in self._monthly_buckets.values()
            )
            if 0 < total < 100_000:
                return total
        # Fallback: Extrapolation
        if self._benchmark_start_date is None:
            return None
        days = max(1, (date.today() - self._benchmark_start_date).days)
        consumption = (
            (self._total_self_consumption_kwh - self._benchmark_start_self_consumption)
            + (self._tracked_grid_import_kwh - self._benchmark_start_grid_import)
        )
        if consumption <= 0:
            return None
        total_annual = consumption / days * 365
        if total_annual > 100_000:
            return None
        return total_annual

    @property
    def benchmark_annual_grid_import_kwh(self) -> float | None:
        """Jährlicher Netzbezug hochgerechnet (seit Benchmark-Start)."""
        if len(self._monthly_buckets) >= 12:
            grid = sum(b.get("grid_import", 0.0) for b in self._monthly_buckets.values())
            if 0 < grid < 100_000:
                return grid
        # Fallback: Extrapolation
        if self._benchmark_start_date is None:
            return None
        days = max(1, (date.today() - self._benchmark_start_date).days)
        grid_since_start = self._tracked_grid_import_kwh - self._benchmark_start_grid_import
        if grid_since_start <= 0:
            return None
        annual = grid_since_start / days * 365
        if annual > 100_000:
            return None
        return annual

    @property
    def benchmark_own_heatpump_kwh(self) -> float | None:
        """WP-Jahresverbrauch (Delta seit erstem Sehen, hochgerechnet auf 1 Jahr)."""
        if not self.benchmark_heatpump or not self.benchmark_heatpump_entity:
            return None
        # Bucket-basiert
        if len(self._monthly_buckets) >= 12:
            wp_total = sum(b.get("wp", 0.0) for b in self._monthly_buckets.values())
            if wp_total > 0:
                return wp_total
        # Fallback: Extrapolation
        if self._wp_first_seen_date is None or self._tracked_wp_kwh <= 0:
            return None
        wp_days = max(1, (date.today() - self._wp_first_seen_date).days)
        return self._tracked_wp_kwh / wp_days * 365

    @property
    def benchmark_household_consumption_kwh(self) -> float | None:
        """Haushaltsverbrauch ohne WP, hochgerechnet auf 1 Jahr."""
        total = self.benchmark_own_annual_consumption_kwh
        if total is None:
            return None
        wp = self.benchmark_own_heatpump_kwh or 0.0
        wp = min(wp, total)  # WP kann nicht mehr als Gesamtverbrauch sein
        return total - wp

    @property
    def benchmark_consumption_vs_avg(self) -> float | None:
        """Vergleich Haushaltsverbrauch (ohne WP) vs. Durchschnitt in %."""
        household = self.benchmark_household_consumption_kwh
        if household is None:
            return None
        avg = self.benchmark_avg_consumption_kwh
        if avg <= 0:
            return None
        return (household - avg) / avg * 100

    @property
    def benchmark_heatpump_vs_avg(self) -> float | None:
        """Vergleich WP-Verbrauch vs. WP-Durchschnitt in %."""
        own_wp = self.benchmark_own_heatpump_kwh
        if own_wp is None:
            return None
        avg_wp = self.benchmark_avg_heatpump_kwh
        if avg_wp is None or avg_wp <= 0:
            return None
        return (own_wp - avg_wp) / avg_wp * 100

    @property
    def benchmark_co2_avoided_kg(self) -> float | None:
        """CO2-Einsparung durch PV pro Jahr (kg)."""
        co2_factor = BENCHMARK_CO2_FACTORS.get(self.benchmark_country, BENCHMARK_CO2_FACTORS["AT"])
        # Bucket-basiert
        if len(self._monthly_buckets) >= 12:
            annual_pv = sum(
                b.get("self_consumption", 0.0) + b.get("feed_in", 0.0)
                for b in self._monthly_buckets.values()
            )
            if 0 < annual_pv < 100_000:
                return annual_pv * co2_factor
        # Fallback: Extrapolation
        if self._benchmark_start_date is None:
            return None
        days = max(1, (date.today() - self._benchmark_start_date).days)
        pv_since_start = (
            (self._total_self_consumption_kwh - self._benchmark_start_self_consumption)
            + (self._total_feed_in_kwh - self._benchmark_start_feed_in)
        )
        if pv_since_start <= 0:
            return None
        daily_pv = pv_since_start / days
        annual_pv = daily_pv * 365
        if annual_pv > 100_000:
            return None
        return annual_pv * co2_factor

    @property
    def benchmark_annual_pv_production_kwh(self) -> float | None:
        """Hochgerechnete PV-Jahresproduktion (snapshot-basiert)."""
        # Bucket-basiert
        if len(self._monthly_buckets) >= 12:
            pv = sum(
                b.get("self_consumption", 0.0) + b.get("feed_in", 0.0)
                for b in self._monthly_buckets.values()
            )
            if 0 < pv < 100_000:
                return pv
        # Fallback: Extrapolation
        if self._benchmark_start_date is None:
            return None
        days = max(1, (date.today() - self._benchmark_start_date).days)
        pv_since_start = (
            (self._total_self_consumption_kwh - self._benchmark_start_self_consumption)
            + (self._total_feed_in_kwh - self._benchmark_start_feed_in)
        )
        if pv_since_start <= 0:
            return None
        annual = pv_since_start / days * 365
        if annual > 100_000:
            return None
        return annual

    @property
    def total_installed_kwp(self) -> float:
        """Summe der installierten kWp aller Strings."""
        return sum(kwp for _, _, _, kwp in self.pv_strings if kwp > 0)

    @property
    def benchmark_specific_yield(self) -> float | None:
        """Spezifischer Ertrag in kWh/kWp (Jahresproduktion / installierte Leistung).

        Fallback auf gemessene Peaks wenn keine kWp konfiguriert.
        """
        annual = self.benchmark_annual_pv_production_kwh
        if annual is None:
            return None
        kwp = self.total_installed_kwp
        if kwp <= 0:
            # Fallback: gemessene Peaks
            peak_kw = self.get_total_peak_kw()
            kwp = peak_kw if peak_kw else 0.0
        if kwp <= 0:
            return None
        return round(annual / kwp, 0)

    @property
    def benchmark_efficiency_score(self) -> int | None:
        """Effizienz-Score 0-100.

        Gewichtung:
        - Autarkiegrad (35): Wie unabhängig vom Netz
        - Spezifischer Ertrag (25): Wie gut die Anlage genutzt wird (kWh/kWp vs 900 Referenz)
        - Eigenverbrauchsquote (20): Reduziert, da große Anlagen hier benachteiligt sind
        - Verbrauch vs. Durchschnitt (20): Reduziert, da WP-Nutzer sonst bestraft werden
        """
        # Mindestens Autarkie oder Verbrauchsvergleich muss vorhanden sein
        autarky = self.autarky_rate
        comparison = self.benchmark_consumption_vs_avg
        if autarky is None and comparison is None:
            return None

        # Autarkiegrad (35 Punkte) — 100% = 35, 0% = 0
        autarky_score = 0.0
        if autarky is not None:
            autarky_score = min(35, autarky * 0.35)

        # Spezifischer Ertrag (25 Punkte) — 900 kWh/kWp = 25, 0 = 0
        yield_score = 0.0
        specific = self.benchmark_specific_yield
        if specific is not None and specific > 0:
            # 900 kWh/kWp als Referenz (guter Wert für Mitteleuropa)
            yield_score = min(25, (specific / 900) * 25)

        # Eigenverbrauchsquote (20 Punkte) — 100% = 20, 0% = 0
        ratio_score = 0.0
        self_ratio = self.self_consumption_ratio
        if self_ratio is not None:
            ratio_score = min(20, self_ratio * 0.2)

        # Verbrauch vs. Durchschnitt (20 Punkte)
        # -50% = 20, 0% = 10, +50% = 0
        consumption_score = 0.0
        if comparison is not None:
            consumption_score = max(0, min(20, 10 - comparison * 0.2))

        return int(autarky_score + yield_score + ratio_score + consumption_score)

    @property
    def benchmark_rating(self) -> str | None:
        """Bewertung als Text."""
        score = self.benchmark_efficiency_score
        if score is None:
            return None
        if score >= 80:
            return "Hervorragend"
        if score >= 60:
            return "Sehr gut"
        if score >= 40:
            return "Gut"
        if score >= 20:
            return "Durchschnittlich"
        return "Verbesserungspotenzial"

    # =========================================================================
    # ENTITY MANAGEMENT
    # =========================================================================

    def register_entity_listener(self, cb) -> None:
        """Sensoren registrieren sich hier für Updates."""
        if cb not in self._entity_listeners:
            self._entity_listeners.append(cb)

    def unregister_entity_listener(self, cb) -> None:
        """Entfernt einen Entity-Listener."""
        try:
            self._entity_listeners.remove(cb)
        except ValueError:
            pass

    def _notify_entities(self) -> None:
        """Informiert alle Entities über Zustandsänderungen."""
        for cb in list(self._entity_listeners):
            try:
                cb()
            except Exception as e:
                _LOGGER.debug("Entity-Listener Fehler (ignoriert): %s", e)

        # Sync to helper after every update
        self._sync_to_helper()

        # Check for notifications
        self._check_milestones()
        self._check_quota_warnings()
        self._check_monthly_summary()

    def _sync_to_helper(self) -> None:
        """Synchronisiert die Gesamtersparnis zum Helper."""
        if not self.amortisation_helper:
            return

        try:
            current_savings = self.total_savings
            state = self.hass.states.get(self.amortisation_helper)

            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    helper_value = float(state.state)
                    # Nur updaten wenn sich der Wert signifikant geändert hat (> 0.01 EUR)
                    if abs(helper_value - current_savings) > 0.01:
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "input_number",
                                "set_value",
                                {
                                    "entity_id": self.amortisation_helper,
                                    "value": round(current_savings, 2),
                                },
                            )
                        )
                        _LOGGER.debug(
                            "Amortisation Helper synced: %.2f EUR → %s",
                            current_savings, self.amortisation_helper
                        )
                except (ValueError, TypeError) as e:
                    _LOGGER.warning("Helper sync error: %s", e)
        except Exception as e:
            _LOGGER.debug("Helper sync failed (ignoriert): %s", e)

    async def _restore_from_helper(self) -> bool:
        """Stellt die Gesamtersparnis vom Helper wieder her."""
        if not self.amortisation_helper or not self.restore_from_helper:
            return False

        try:
            state = self.hass.states.get(self.amortisation_helper)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                helper_value = float(state.state)

                if helper_value > 0:
                    # Berechne Eigenverbrauch/Einspeisung aus Gesamtersparnis
                    # Vereinfachung: Nutze nur savings_offset und accumulated values
                    _LOGGER.info(
                        "Restoring from helper %s: %.2f EUR",
                        self.amortisation_helper, helper_value
                    )

                    # Setze den Offset so, dass total_savings dem Helper entspricht
                    # total_savings = savings_offset + accumulated_savings_self + accumulated_earnings_feed
                    # Also: savings_offset = helper_value - (accumulated_savings_self + accumulated_earnings_feed)
                    current_accumulated = self._accumulated_savings_self + self._accumulated_earnings_feed
                    self.savings_offset = max(0, helper_value - current_accumulated)

                    self._restored = True
                    self._notify_entities()
                    return True
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Restore from helper failed: %s", e)

        return False

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    def _check_milestones(self) -> None:
        """Prüft und feuert Meilenstein-Events (25%, 50%, 75%, 100%)."""
        if self.installation_cost <= 0:
            return

        percent = self.amortisation_percent
        milestones = [25, 50, 75, 100]

        for milestone in milestones:
            if percent >= milestone and milestone not in self._milestones_fired:
                self._milestones_fired.add(milestone)

                if milestone == 100:
                    profit = self.total_savings - self.installation_cost
                    message = f"PV-Anlage vollständig amortisiert! +{profit:.2f}€ Gewinn!"
                    event_type = "amortisation_complete"
                else:
                    message = f"{milestone}% der PV-Anlage amortisiert! Noch {self.remaining_cost:.2f}€ bis zur Amortisation."
                    event_type = "amortisation_milestone"

                self.hass.bus.async_fire("pv_management_event", {
                    "type": event_type,
                    "milestone": milestone,
                    "total_savings": round(self.total_savings, 2),
                    "remaining": round(self.remaining_cost, 2),
                    "installation_cost": self.installation_cost,
                    "message": message,
                })
                _LOGGER.info("Meilenstein erreicht: %s", message)

    def _check_quota_warnings(self) -> None:
        """Prüft Kontingent und feuert Warnungen."""
        if not self.quota_enabled:
            return

        consumed_percent = self.quota_consumed_percent
        reserve = self.quota_reserve_kwh
        remaining = self.quota_remaining_kwh

        # 80% Warnung
        if consumed_percent >= 80 and not self._quota_warning_80_sent:
            self._quota_warning_80_sent = True
            message = f"80% des Stromkontingents verbraucht! Noch {remaining:.0f} kWh übrig."
            self.hass.bus.async_fire("pv_management_event", {
                "type": "quota_warning_80",
                "consumed_percent": round(consumed_percent, 1),
                "remaining_kwh": round(remaining, 0),
                "reserve_kwh": round(reserve, 0),
                "message": message,
            })
            _LOGGER.info("Kontingent-Warnung: %s", message)

        # 100% Warnung
        if consumed_percent >= 100 and not self._quota_warning_100_sent:
            self._quota_warning_100_sent = True
            message = f"Stromkontingent aufgebraucht! {self.quota_yearly_kwh:.0f} kWh erreicht."
            self.hass.bus.async_fire("pv_management_event", {
                "type": "quota_warning_100",
                "consumed_percent": round(consumed_percent, 1),
                "remaining_kwh": 0,
                "message": message,
            })
            _LOGGER.info("Kontingent-Warnung: %s", message)

        # Über Budget
        if reserve < -10 and not self._quota_over_budget_sent:  # 10 kWh Toleranz
            self._quota_over_budget_sent = True
            message = f"Stromkontingent überschritten! {abs(reserve):.0f} kWh über Budget."
            self.hass.bus.async_fire("pv_management_event", {
                "type": "quota_over_budget",
                "consumed_percent": round(consumed_percent, 1),
                "over_budget_kwh": round(abs(reserve), 0),
                "message": message,
            })
            _LOGGER.warning("Kontingent überschritten: %s", message)

    def _check_monthly_summary(self) -> None:
        """Sendet monatliche Zusammenfassung am 1. des Monats."""
        today = date.today()

        # Nur am 1. des Monats und nur einmal pro Monat
        if today.day != 1:
            return
        if self._monthly_summary_month == today.month:
            return

        self._monthly_summary_month = today.month

        # Berechne Vormonat
        last_month = today - timedelta(days=1)
        month_name = last_month.strftime("%B %Y")

        # Monatliche Werte (aus dem Tracking)
        monthly_savings = self._monthly_grid_import_cost  # Ungefähr
        monthly_kwh = self._monthly_grid_import_kwh

        message = f"PV-Bericht {month_name}: {monthly_kwh:.0f} kWh Netzbezug, {self.amortisation_percent:.1f}% amortisiert"

        self.hass.bus.async_fire("pv_management_event", {
            "type": "monthly_summary",
            "month": month_name,
            "grid_import_kwh": round(monthly_kwh, 1),
            "grid_import_cost": round(monthly_savings, 2),
            "amortisation_percent": round(self.amortisation_percent, 1),
            "total_savings": round(self.total_savings, 2),
            "message": message,
        })
        _LOGGER.info("Monatliche Zusammenfassung: %s", message)

    def restore_state(self, data: dict[str, Any]) -> None:
        """Stellt den gespeicherten Zustand wieder her."""
        def safe_float(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        self._total_self_consumption_kwh = safe_float(data.get("total_self_consumption_kwh"))
        self._total_feed_in_kwh = safe_float(data.get("total_feed_in_kwh"))
        self._accumulated_savings_self = safe_float(data.get("accumulated_savings_self"))
        self._accumulated_earnings_feed = safe_float(data.get("accumulated_earnings_feed"))

        self._tracked_grid_import_kwh = safe_float(data.get("tracked_grid_import_kwh"))
        self._total_grid_import_cost = safe_float(data.get("total_grid_import_cost"))

        today = date.today()

        # Daily tracking restore
        daily_reset_str = data.get("daily_reset_date")
        if daily_reset_str:
            try:
                daily_reset_date = date.fromisoformat(daily_reset_str)
                if daily_reset_date == today:
                    self._daily_grid_import_kwh = safe_float(data.get("daily_grid_import_kwh"))
                    self._daily_grid_import_cost = safe_float(data.get("daily_grid_import_cost"))
                    self._daily_feed_in_earnings = safe_float(data.get("daily_feed_in_earnings"))
                    self._daily_feed_in_kwh = safe_float(data.get("daily_feed_in_kwh"))
                    self._daily_tracking_date = today  # Prevent reset on first update
                    # Restore quota day start meter
                    qdsm = data.get("quota_day_start_meter")
                    if qdsm is not None:
                        self._quota_day_start_meter = safe_float(qdsm)
                        self._quota_day_start_date = today
            except (ValueError, TypeError):
                pass

        # Monthly tracking restore
        monthly_reset_month = data.get("monthly_reset_month")
        monthly_reset_year = data.get("monthly_reset_year")
        if monthly_reset_month is not None and monthly_reset_year is not None:
            try:
                if int(monthly_reset_month) == today.month and int(monthly_reset_year) == today.year:
                    self._monthly_grid_import_kwh = safe_float(data.get("monthly_grid_import_kwh"))
                    self._monthly_grid_import_cost = safe_float(data.get("monthly_grid_import_cost"))
            except (ValueError, TypeError):
                pass

        first_seen = data.get("first_seen_date")
        if first_seen:
            try:
                if isinstance(first_seen, str):
                    self._first_seen_date = date.fromisoformat(first_seen)
                elif isinstance(first_seen, date):
                    self._first_seen_date = first_seen
            except (ValueError, TypeError):
                pass

        # WP Delta-Tracking wiederherstellen
        restored_wp = safe_float(data.get("tracked_wp_kwh"))
        # Sanity: wenn tracked > 50.000 kWh, war vermutlich Absolutwert statt Delta
        self._tracked_wp_kwh = restored_wp if restored_wp < 50000 else 0.0
        wp_first_seen = data.get("wp_first_seen_date")
        if wp_first_seen:
            try:
                self._wp_first_seen_date = date.fromisoformat(wp_first_seen) if isinstance(wp_first_seen, str) else wp_first_seen
            except (ValueError, TypeError):
                pass

        # PV-String Delta-Tracking wiederherstellen
        raw = data.get("string_tracked_kwh", {})
        self._string_tracked_kwh = {k: safe_float(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        s_first = data.get("string_first_seen_date")
        if s_first:
            try:
                self._string_first_seen_date = date.fromisoformat(s_first) if isinstance(s_first, str) else s_first
            except (ValueError, TypeError):
                pass
        raw_peak = data.get("string_peak_w", {})
        self._string_peak_w = {k: safe_float(v) for k, v in raw_peak.items()} if isinstance(raw_peak, dict) else {}
        # Daily Peak restore (nur wenn heute)
        dp_date = data.get("string_daily_peak_date")
        if dp_date:
            try:
                dp = date.fromisoformat(dp_date) if isinstance(dp_date, str) else dp_date
                if dp == date.today():
                    raw_dp = data.get("string_daily_peak_w", {})
                    self._string_daily_peak_w = {k: safe_float(v) for k, v in raw_dp.items()} if isinstance(raw_dp, dict) else {}
                    self._string_daily_peak_date = dp
            except (ValueError, TypeError):
                pass

        # Benchmark-Snapshot wiederherstellen
        bsd = data.get("benchmark_start_date")
        if bsd:
            try:
                self._benchmark_start_date = date.fromisoformat(bsd) if isinstance(bsd, str) else bsd
            except (ValueError, TypeError):
                pass
        self._benchmark_start_self_consumption = safe_float(data.get("benchmark_start_self_consumption"))
        self._benchmark_start_grid_import = safe_float(data.get("benchmark_start_grid_import"))
        self._benchmark_start_feed_in = safe_float(data.get("benchmark_start_feed_in"))

        # Monthly Buckets wiederherstellen
        raw_buckets = data.get("monthly_buckets", {})
        if isinstance(raw_buckets, dict):
            self._monthly_buckets = {}
            for k, v in raw_buckets.items():
                try:
                    month = int(k)
                    if 1 <= month <= 12 and isinstance(v, dict):
                        self._monthly_buckets[month] = {
                            "self_consumption": safe_float(v.get("self_consumption")),
                            "grid_import": safe_float(v.get("grid_import")),
                            "feed_in": safe_float(v.get("feed_in")),
                            "wp": safe_float(v.get("wp")),
                        }
                except (ValueError, TypeError):
                    pass
        self._monthly_bucket_month = data.get("monthly_bucket_month")
        if self._monthly_bucket_month is not None:
            try:
                self._monthly_bucket_month = int(self._monthly_bucket_month)
            except (ValueError, TypeError):
                self._monthly_bucket_month = None

        self._restored = True
        _LOGGER.info(
            "PV Management Fixpreis restored: %.2f kWh self, %.2f kWh feed, %.2f€ savings",
            self._total_self_consumption_kwh,
            self._total_feed_in_kwh,
            self._accumulated_savings_self + self._accumulated_earnings_feed,
        )

        @callback
        def delayed_restore_notify(_now):
            self._notify_entities()

        from homeassistant.helpers.event import async_call_later
        async_call_later(self.hass, 5.0, delayed_restore_notify)

    def _initialize_from_sensors(self) -> None:
        """Initialisiert die Werte mit den aktuellen Sensor-Totals."""
        pv_total = 0.0
        export_total = 0.0

        if self.pv_production_entity:
            state = self.hass.states.get(self.pv_production_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    pv_total = float(state.state)
                except (ValueError, TypeError):
                    pass

        if self.grid_export_entity:
            state = self.hass.states.get(self.grid_export_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    export_total = float(state.state)
                except (ValueError, TypeError):
                    pass

        if pv_total <= 0:
            _LOGGER.info("Keine historischen PV-Daten verfügbar, starte bei 0")
            return

        self_consumption = max(0, pv_total - export_total)
        feed_in = export_total

        # Bei Fixpreis: Berechne mit dem Brutto-Preis (inkl. Netz/Steuern)
        savings_self = self_consumption * self.gross_price
        earnings_feed = feed_in * self.current_feed_in_tariff

        self._total_self_consumption_kwh = self_consumption
        self._total_feed_in_kwh = feed_in
        self._accumulated_savings_self = savings_self
        self._accumulated_earnings_feed = earnings_feed
        self._first_seen_date = date.today()

        _LOGGER.info(
            "PV Management Fixpreis initialisiert: Eigenverbrauch=%.2f kWh (%.2f€), Einspeisung=%.2f kWh (%.2f€)",
            self_consumption, savings_self, feed_in, earnings_feed,
        )
        self._notify_entities()

    def get_state_for_storage(self) -> dict[str, Any]:
        """Gibt den zu speichernden Zustand zurück."""
        today = date.today()
        return {
            "total_self_consumption_kwh": self._total_self_consumption_kwh,
            "total_feed_in_kwh": self._total_feed_in_kwh,
            "accumulated_savings_self": self._accumulated_savings_self,
            "accumulated_earnings_feed": self._accumulated_earnings_feed,
            "first_seen_date": self._first_seen_date.isoformat() if self._first_seen_date else None,
            "tracked_grid_import_kwh": self._tracked_grid_import_kwh,
            "total_grid_import_cost": self._total_grid_import_cost,
            "daily_grid_import_kwh": self._daily_grid_import_kwh,
            "daily_grid_import_cost": self._daily_grid_import_cost,
            "daily_feed_in_earnings": self._daily_feed_in_earnings,
            "daily_feed_in_kwh": self._daily_feed_in_kwh,
            "quota_day_start_meter": self._quota_day_start_meter,
            "daily_reset_date": today.isoformat(),
            "monthly_grid_import_kwh": self._monthly_grid_import_kwh,
            "monthly_grid_import_cost": self._monthly_grid_import_cost,
            "monthly_reset_month": today.month,
            "monthly_reset_year": today.year,
            "tracked_wp_kwh": self._tracked_wp_kwh,
            "wp_first_seen_date": self._wp_first_seen_date.isoformat() if self._wp_first_seen_date else None,
            "string_tracked_kwh": self._string_tracked_kwh,
            "string_first_seen_date": self._string_first_seen_date.isoformat() if self._string_first_seen_date else None,
            "string_peak_w": self._string_peak_w,
            "string_daily_peak_w": self._string_daily_peak_w,
            "string_daily_peak_date": self._string_daily_peak_date.isoformat() if self._string_daily_peak_date else None,
            "benchmark_start_date": self._benchmark_start_date.isoformat() if self._benchmark_start_date else None,
            "benchmark_start_self_consumption": self._benchmark_start_self_consumption,
            "benchmark_start_grid_import": self._benchmark_start_grid_import,
            "benchmark_start_feed_in": self._benchmark_start_feed_in,
            "monthly_buckets": {str(k): v for k, v in self._monthly_buckets.items()},
            "monthly_bucket_month": self._monthly_bucket_month,
        }

    def get_string_production_kwh(self, entity_id: str) -> float:
        """Gibt die getrackte Produktion eines PV-Strings zurück."""
        return self._string_tracked_kwh.get(entity_id, 0.0)

    def get_string_daily_kwh(self, entity_id: str) -> float | None:
        """Gibt die durchschnittliche Tagesproduktion eines PV-Strings zurück."""
        if not self._string_first_seen_date:
            return None
        days = max(1, (date.today() - self._string_first_seen_date).days)
        tracked = self._string_tracked_kwh.get(entity_id, 0.0)
        return tracked / days if tracked > 0 else None

    def get_string_percentage(self, entity_id: str) -> float | None:
        """Gibt den prozentualen Anteil eines PV-Strings an der Gesamtproduktion zurück."""
        total = sum(self._string_tracked_kwh.values())
        if total <= 0:
            return None
        return self._string_tracked_kwh.get(entity_id, 0.0) / total * 100

    def get_string_peak_kw(self, power_entity_id: str) -> float | None:
        """Peak-Leistung in kW (gerundet auf 1 Nachkommastelle)."""
        if not power_entity_id:
            return None
        peak = self._string_peak_w.get(power_entity_id, 0.0)
        return round(peak / 1000, 1) if peak > 0 else None

    def get_total_daily_production_kwh(self) -> float | None:
        """Durchschnittliche Tagesproduktion aller Strings zusammen."""
        if not self._string_first_seen_date or not self._string_tracked_kwh:
            return None
        days = max(1, (date.today() - self._string_first_seen_date).days)
        total = sum(self._string_tracked_kwh.values())
        return round(total / days, 2) if total > 0 else None

    def get_total_peak_kw(self) -> float | None:
        """Summe aller String-Peaks in kW."""
        if not self._string_peak_w:
            return None
        total = sum(self._string_peak_w.values())
        return round(total / 1000, 1) if total > 0 else None

    def get_string_specific_yield(self, energy_entity_id: str, installed_kwp: float) -> float | None:
        """Spezifischer Ertrag eines Strings in kWh/kWp."""
        if installed_kwp <= 0:
            return None
        tracked = self._string_tracked_kwh.get(energy_entity_id, 0.0)
        if tracked <= 0 or self._string_first_seen_date is None:
            return None
        days = max(1, (date.today() - self._string_first_seen_date).days)
        annual = tracked / days * 365
        return round(annual / installed_kwp, 0)

    def get_string_performance_ratio(self, power_entity_id: str, installed_kwp: float) -> float | None:
        """Performance Ratio: gemessener Peak / installierte Leistung in %."""
        if not power_entity_id or installed_kwp <= 0:
            return None
        peak_kw = self._string_peak_w.get(power_entity_id, 0.0) / 1000
        if peak_kw <= 0:
            return None
        return round(peak_kw / installed_kwp * 100, 1)

    def get_string_daily_peak_kw(self, power_entity_id: str) -> float | None:
        """Heutiger Peak eines Strings in kW."""
        if not power_entity_id:
            return None
        peak = self._string_daily_peak_w.get(power_entity_id, 0.0)
        return round(peak / 1000, 1) if peak > 0 else None

    def get_total_daily_peak_kw(self) -> float | None:
        """Summe aller String-Peaks heute in kW."""
        if not self._string_daily_peak_w:
            return None
        total = sum(self._string_daily_peak_w.values())
        return round(total / 1000, 1) if total > 0 else None

    def _process_energy_update(self) -> None:
        """Verarbeitet Energie-Updates INKREMENTELL."""
        current_pv = self._pv_production_kwh
        current_export = self._grid_export_kwh
        current_import = self._grid_import_kwh

        if self._last_pv_production_kwh is None or self._last_grid_import_kwh is None:
            self._last_pv_production_kwh = current_pv
            self._last_grid_export_kwh = current_export
            self._last_grid_import_kwh = current_import
            _LOGGER.info(
                "Energie-Tracking initialisiert: PV=%.2f, Export=%.2f, Import=%.2f kWh",
                current_pv, current_export, current_import
            )
            return

        delta_pv = current_pv - self._last_pv_production_kwh
        delta_export = current_export - self._last_grid_export_kwh
        delta_import = current_import - self._last_grid_import_kwh

        MAX_DELTA_KWH = 50.0
        if delta_pv > MAX_DELTA_KWH:
            self._last_pv_production_kwh = current_pv
            delta_pv = 0
        if delta_export > MAX_DELTA_KWH:
            self._last_grid_export_kwh = current_export
            delta_export = 0
        if delta_import > MAX_DELTA_KWH:
            self._last_grid_import_kwh = current_import
            delta_import = 0

        if delta_pv < 0:
            self._last_pv_production_kwh = current_pv
            delta_pv = 0
        if delta_export < 0:
            self._last_grid_export_kwh = current_export
            delta_export = 0
        if delta_import < 0:
            self._last_grid_import_kwh = current_import
            delta_import = 0

        delta_self_consumption = max(0.0, delta_pv - delta_export)

        # Tägliches Tracking: Reset bei Tageswechsel
        today = date.today()
        if self._daily_tracking_date != today:
            self._daily_grid_import_cost = 0.0
            self._daily_grid_import_kwh = 0.0
            self._daily_feed_in_earnings = 0.0
            self._daily_feed_in_kwh = 0.0
            self._daily_tracking_date = today
            # Quota: Zählerstand für Tagesbeginn merken
            if self._grid_import_kwh > 0:
                self._quota_day_start_meter = self._grid_import_kwh
                self._quota_day_start_date = today

        if delta_self_consumption > 0 or delta_export > 0:
            # Bei Fixpreis: Brutto-Preis für Ersparnis (netto × Aufschlagfaktor)
            price_electricity = self.gross_price
            price_feed_in = self.current_feed_in_tariff

            savings_delta = delta_self_consumption * price_electricity
            earnings_delta = delta_export * price_feed_in

            self._total_self_consumption_kwh += delta_self_consumption
            self._total_feed_in_kwh += delta_export
            self._accumulated_savings_self += savings_delta
            self._accumulated_earnings_feed += earnings_delta
            self._daily_feed_in_earnings += earnings_delta
            self._daily_feed_in_kwh += delta_export

        # Strompreis-Tracking
        if delta_import > 0:
            import_cost = delta_import * self.gross_price

            self._tracked_grid_import_kwh += delta_import
            self._total_grid_import_cost += import_cost

            self._daily_grid_import_kwh += delta_import
            self._daily_grid_import_cost += import_cost

            current_month = today.month
            if self._monthly_tracking_month != current_month:
                self._monthly_grid_import_cost = 0.0
                self._monthly_grid_import_kwh = 0.0
                self._monthly_tracking_month = current_month
            self._monthly_grid_import_kwh += delta_import
            self._monthly_grid_import_cost += import_cost

        # Monatlicher Bucket (Rolling 12-Month)
        current_month = today.month
        if self._monthly_bucket_month != current_month:
            self._monthly_buckets[current_month] = {
                "self_consumption": 0.0,
                "grid_import": 0.0,
                "feed_in": 0.0,
                "wp": 0.0,
            }
            self._monthly_bucket_month = current_month

        bucket = self._monthly_buckets[current_month]
        bucket["self_consumption"] += delta_self_consumption
        bucket["grid_import"] += delta_import
        bucket["feed_in"] += delta_export

        self._last_pv_production_kwh = current_pv
        self._last_grid_export_kwh = current_export
        self._last_grid_import_kwh = current_import
        self._notify_entities()

    @callback
    def _on_state_changed(self, event: Event) -> None:
        """Handler für Zustandsänderungen der überwachten Entities."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")

        if not new_state or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        try:
            value = float(new_state.state)
        except (ValueError, TypeError):
            return

        if self._first_seen_date is None:
            self._first_seen_date = date.today()

        changed = False

        if entity_id == self.pv_production_entity:
            self._pv_production_kwh = value
            changed = True
        elif entity_id == self.grid_export_entity:
            self._grid_export_kwh = value
            changed = True
        elif entity_id == self.grid_import_entity:
            self._grid_import_kwh = value
            changed = True
        elif entity_id == self.consumption_entity:
            self._consumption_kwh = value
        elif entity_id in (self.battery_soc_entity, self.battery_charge_entity, self.battery_discharge_entity):
            self._notify_entities()
        elif entity_id == self.benchmark_heatpump_entity:
            # Unit-Konvertierung: Wh → kWh falls nötig
            state_obj = self.hass.states.get(entity_id)
            uom = state_obj.attributes.get("unit_of_measurement", "") if state_obj else ""
            if uom in ("Wh", "wh"):
                value = value / 1000
            if self._wp_first_seen_date is None:
                self._wp_first_seen_date = date.today()
            if self._last_wp_kwh is not None and value >= self._last_wp_kwh:
                delta = value - self._last_wp_kwh
                # Sanity check: max 200 kWh pro Update (verhindert Absolutwert als Delta)
                if delta < 200:
                    self._tracked_wp_kwh += delta
                    # WP-Bucket-Update
                    if self._monthly_bucket_month is not None and self._monthly_bucket_month in self._monthly_buckets:
                        self._monthly_buckets[self._monthly_bucket_month]["wp"] += delta
            self._last_wp_kwh = value
            self._notify_entities()

        # PV-Strings (Delta-Tracking)
        elif entity_id in self._string_entity_ids:
            if self._string_first_seen_date is None:
                self._string_first_seen_date = date.today()
            last = self._string_last_kwh.get(entity_id)
            if last is not None and value >= last:
                self._string_tracked_kwh[entity_id] = (
                    self._string_tracked_kwh.get(entity_id, 0.0) + (value - last)
                )
            self._string_last_kwh[entity_id] = value
            self._notify_entities()

        # PV-String Power Peak-Tracking
        elif entity_id in self._string_power_entity_ids:
            current_peak = self._string_peak_w.get(entity_id, 0.0)
            if value > current_peak:
                self._string_peak_w[entity_id] = value
            # Daily Peak: bei neuem Tag resetten
            today = date.today()
            if self._string_daily_peak_date != today:
                self._string_daily_peak_w = {}
                self._string_daily_peak_date = today
            daily_peak = self._string_daily_peak_w.get(entity_id, 0.0)
            if value > daily_peak:
                self._string_daily_peak_w[entity_id] = value
            self._notify_entities()

        if changed:
            self._process_energy_update()

    async def async_start(self) -> None:
        """Startet das Tracking."""
        # Initiale Werte laden
        for entity_id, attr in [
            (self.pv_production_entity, "_pv_production_kwh"),
            (self.grid_export_entity, "_grid_export_kwh"),
            (self.grid_import_entity, "_grid_import_kwh"),
            (self.consumption_entity, "_consumption_kwh"),
        ]:
            if entity_id:
                state = self.hass.states.get(entity_id)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        setattr(self, attr, float(state.state))
                    except (ValueError, TypeError):
                        pass

        self._last_pv_production_kwh = self._pv_production_kwh
        self._last_grid_export_kwh = self._grid_export_kwh
        self._last_grid_import_kwh = self._grid_import_kwh

        # Quota: Auto-Capture Zählerstand nur wenn 0 eingetragen
        # Erst am/nach Startdatum erfassen, damit kein Verbrauch von vor der Periode mitgezählt wird
        # Wenn der User einen Wert > 0 manuell eingetragen hat, wird dieser NICHT überschrieben
        quota_start = self.quota_start_date
        if (self.quota_enabled and self.quota_start_meter == 0 and self._grid_import_kwh > 0
                and quota_start is not None and date.today() >= quota_start):
            self.quota_start_meter = self._grid_import_kwh
            _LOGGER.info(
                "Quota: Zählerstand automatisch erfasst: %.2f kWh",
                self.quota_start_meter,
            )
            new_opts = {**self.entry.options, CONF_QUOTA_START_METER: self._grid_import_kwh}
            self.hass.config_entries.async_update_entry(self.entry, options=new_opts)

        # Quota: Tages-Zählerstand initialisieren
        if self._grid_import_kwh > 0:
            if self._quota_day_start_date != date.today():
                self._quota_day_start_meter = self._grid_import_kwh
            self._quota_day_start_date = date.today()

        # WP-Sensor initialisieren (last-Wert + first_seen_date)
        if self.benchmark_heatpump_entity:
            state = self.hass.states.get(self.benchmark_heatpump_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    val = float(state.state)
                    uom = state.attributes.get("unit_of_measurement", "")
                    if uom in ("Wh", "wh"):
                        val = val / 1000
                    self._last_wp_kwh = val
                    if self._wp_first_seen_date is None:
                        self._wp_first_seen_date = date.today()
                except (ValueError, TypeError):
                    pass

        # PV-Strings initialisieren
        for _, entity_id, power_entity, _ in self.pv_strings:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._string_last_kwh[entity_id] = float(state.state)
                except (ValueError, TypeError):
                    pass
            if power_entity:
                p_state = self.hass.states.get(power_entity)
                if p_state and p_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        val = float(p_state.state)
                        current = self._string_peak_w.get(power_entity, 0.0)
                        if val > current:
                            self._string_peak_w[power_entity] = val
                    except (ValueError, TypeError):
                        pass
        if self.pv_strings and self._string_first_seen_date is None:
            self._string_first_seen_date = date.today()

        # Benchmark-Snapshot auto-initialisieren (frischer Start)
        if self.benchmark_enabled and self._benchmark_start_date is None:
            self._benchmark_start_date = date.today()
            self._benchmark_start_self_consumption = self._total_self_consumption_kwh
            self._benchmark_start_grid_import = self._tracked_grid_import_kwh
            self._benchmark_start_feed_in = self._total_feed_in_kwh
            _LOGGER.info(
                "Benchmark-Snapshot initialisiert: date=%s, self=%.2f, grid=%.2f, feed=%.2f",
                self._benchmark_start_date,
                self._benchmark_start_self_consumption,
                self._benchmark_start_grid_import,
                self._benchmark_start_feed_in,
            )

        # Versuche zuerst vom Helper zu restoren (falls konfiguriert)
        if self.restore_from_helper and self.amortisation_helper:
            restored = await self._restore_from_helper()
            if restored:
                _LOGGER.info("Amortisation erfolgreich von Helper wiederhergestellt")

        @callback
        def delayed_init_check(_now: datetime) -> None:
            if not self._restored and self._total_self_consumption_kwh == 0:
                _LOGGER.info("Keine restored Daten, initialisiere von Sensoren")
                self._initialize_from_sensors()

        from homeassistant.helpers.event import async_call_later
        async_call_later(self.hass, 60.0, delayed_init_check)

        @callback
        def state_listener(event: Event):
            self._on_state_changed(event)

        self._remove_listeners.append(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, state_listener)
        )

        self._notify_entities()

    async def async_stop(self) -> None:
        """Stoppt das Tracking."""
        for remove in self._remove_listeners:
            remove()
        self._remove_listeners.clear()
        self._entity_listeners.clear()

    def reset_grid_import_tracking(self) -> None:
        """Setzt das Strompreis-Tracking auf 0 zurück."""
        _LOGGER.info(
            "Strompreis-Tracking wird zurückgesetzt (war: %.2f kWh, %.2f €)",
            self._tracked_grid_import_kwh, self._total_grid_import_cost
        )
        self._tracked_grid_import_kwh = 0.0
        self._total_grid_import_cost = 0.0
        self._daily_grid_import_kwh = 0.0
        self._daily_grid_import_cost = 0.0
        self._monthly_grid_import_kwh = 0.0
        self._monthly_grid_import_cost = 0.0
        self._last_grid_import_kwh = self._grid_import_kwh
        self._notify_entities()

    def reset_benchmark_tracking(self) -> None:
        """Setzt Benchmark/WP-Tracking zurück — Snapshot der aktuellen Werte."""
        _LOGGER.info("Benchmark-Tracking wird zurückgesetzt (WP war: %.2f kWh)", self._tracked_wp_kwh)
        # WP-Tracking zurücksetzen
        self._tracked_wp_kwh = 0.0
        self._wp_first_seen_date = None
        self._last_wp_kwh = None
        # Benchmark-Startpunkt auf jetzt setzen
        self._benchmark_start_date = date.today()
        self._benchmark_start_self_consumption = self._total_self_consumption_kwh
        self._benchmark_start_grid_import = self._tracked_grid_import_kwh
        self._benchmark_start_feed_in = self._total_feed_in_kwh
        # Monthly Buckets zurücksetzen
        self._monthly_buckets = {}
        self._monthly_bucket_month = None
        self._notify_entities()

    def reset_pv_strings_tracking(self) -> None:
        """Setzt PV-String-Tracking und Peaks zurück."""
        _LOGGER.info("PV-Strings-Tracking wird zurückgesetzt")
        self._string_tracked_kwh.clear()
        self._string_last_kwh.clear()
        self._string_first_seen_date = None
        self._string_peak_w.clear()
        self._string_daily_peak_w.clear()
        self._string_daily_peak_date = None
        self._notify_entities()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup der Integration."""
    ctrl = PVManagementFixController(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_CTRL: ctrl}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await ctrl.async_start()

    async def handle_reset_grid_import(call):
        """Handle reset_grid_import service call."""
        for entry_data in hass.data.get(DOMAIN, {}).values():
            controller = entry_data.get(DATA_CTRL)
            if controller:
                controller.reset_grid_import_tracking()

    if not hass.services.has_service(DOMAIN, "reset_grid_import"):
        hass.services.async_register(DOMAIN, "reset_grid_import", handle_reset_grid_import)

    entry.add_update_listener(_async_update_listener)
    return True




async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entlädt die Integration."""
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            ctrl = hass.data[DOMAIN][entry.entry_id].get(DATA_CTRL)
            if ctrl:
                await ctrl.async_stop()
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return unload_ok
    except Exception as e:
        _LOGGER.error("Fehler beim Entladen: %s", e)
        return False


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handler für Options-Updates. Reload bei strukturellen Änderungen."""
    try:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            ctrl = hass.data[DOMAIN][entry.entry_id].get(DATA_CTRL)
            if ctrl:
                old_quota = ctrl.quota_enabled
                old_batt_soc = ctrl.battery_soc_entity
                old_batt_charge = ctrl.battery_charge_entity
                old_batt_discharge = ctrl.battery_discharge_entity
                old_benchmark = ctrl.benchmark_enabled
                old_benchmark_hp = ctrl.benchmark_heatpump

                opts = {**entry.data, **entry.options}
                new_quota = opts.get(CONF_QUOTA_ENABLED, DEFAULT_QUOTA_ENABLED)
                new_batt_soc = opts.get(CONF_BATTERY_SOC_ENTITY)
                new_batt_charge = opts.get(CONF_BATTERY_CHARGE_ENTITY)
                new_batt_discharge = opts.get(CONF_BATTERY_DISCHARGE_ENTITY)
                new_benchmark = opts.get(CONF_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_ENABLED)
                new_benchmark_hp = opts.get(CONF_BENCHMARK_HEATPUMP, DEFAULT_BENCHMARK_HEATPUMP)

                needs_reload = (
                    old_quota != new_quota
                    or old_batt_soc != new_batt_soc
                    or old_batt_charge != new_batt_charge
                    or old_batt_discharge != new_batt_discharge
                    or old_benchmark != new_benchmark
                    or old_benchmark_hp != new_benchmark_hp
                )

                if needs_reload:
                    _LOGGER.info("Strukturelle Änderung erkannt, Reload wird ausgeführt")
                    await hass.config_entries.async_reload(entry.entry_id)
                else:
                    ctrl._load_options()
                    ctrl._notify_entities()
                    _LOGGER.info("PV Management Fixpreis Optionen aktualisiert")
    except Exception as e:
        _LOGGER.error("Fehler beim Aktualisieren der Optionen: %s", e)
