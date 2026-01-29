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
    CONF_FIXED_PRICE, CONF_EPEX_PRICE_ENTITY,
    CONF_QUOTA_ENABLED, CONF_QUOTA_YEARLY_KWH, CONF_QUOTA_START_DATE,
    CONF_QUOTA_START_METER, CONF_QUOTA_MONTHLY_RATE, CONF_QUOTA_SEASONAL,
    DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_FIXED_PRICE, DEFAULT_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_EXPORT,
    DEFAULT_QUOTA_ENABLED, DEFAULT_QUOTA_YEARLY_KWH,
    DEFAULT_QUOTA_START_METER, DEFAULT_QUOTA_MONTHLY_RATE,
    DEFAULT_QUOTA_SEASONAL, SEASONAL_FACTORS,
    PRICE_UNIT_CENT,
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

        # EPEX Spot Preis (nur für Vergleich)
        self._epex_price = 0.0

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
        self._daily_tracking_date: date | None = None

        # Monatliches Strompreis-Tracking
        self._monthly_grid_import_cost = 0.0
        self._monthly_grid_import_kwh = 0.0
        self._monthly_tracking_month: int | None = None

        # Flag ob Werte aus Restore geladen wurden
        self._restored = False
        self._first_seen_date: date | None = None

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

        # EPEX Spot (nur für Vergleich)
        self.epex_price_entity = opts.get(CONF_EPEX_PRICE_ENTITY)

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

        # Fixpreis (ct/kWh → €/kWh)
        self.fixed_price = opts.get(CONF_FIXED_PRICE, DEFAULT_FIXED_PRICE) / 100.0

        # Stromkontingent
        self.quota_enabled = opts.get(CONF_QUOTA_ENABLED, DEFAULT_QUOTA_ENABLED)
        self.quota_yearly_kwh = opts.get(CONF_QUOTA_YEARLY_KWH, DEFAULT_QUOTA_YEARLY_KWH)
        self.quota_start_date_str = opts.get(CONF_QUOTA_START_DATE)
        self.quota_start_meter = opts.get(CONF_QUOTA_START_METER, DEFAULT_QUOTA_START_METER)
        self.quota_monthly_rate = opts.get(CONF_QUOTA_MONTHLY_RATE, DEFAULT_QUOTA_MONTHLY_RATE)
        self.quota_seasonal = opts.get(CONF_QUOTA_SEASONAL, DEFAULT_QUOTA_SEASONAL)

    @property
    def fixed_price_ct(self) -> float:
        """Fixpreis in ct/kWh."""
        return self.fixed_price * 100

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
        """Aktueller Strompreis in €/kWh (Fixpreis)."""
        # Bei Fixpreis: Verwende den konfigurierten Fixpreis
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

    @property
    def epex_price(self) -> float:
        """Aktueller EPEX Spot Preis in €/kWh (für Vergleich)."""
        return self._epex_price

    @property
    def epex_price_ct(self) -> float:
        """Aktueller EPEX Spot Preis in ct/kWh."""
        return self._epex_price * 100

    @property
    def has_epex_integration(self) -> bool:
        """Prüft ob EPEX Spot konfiguriert ist."""
        return bool(self.epex_price_entity)

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
    def monthly_grid_import_kwh(self) -> float:
        """Monatlicher Netzbezug in kWh."""
        return self._monthly_grid_import_kwh

    @property
    def monthly_grid_import_cost(self) -> float:
        """Monatliche Netzbezugskosten in €."""
        return self._monthly_grid_import_cost

    # =========================================================================
    # SPOT VS FIXPREIS VERGLEICH
    # =========================================================================

    @property
    def spot_vs_fixed_savings(self) -> float | None:
        """
        Ersparnis Fixpreis gegenüber Spot-Tarif.
        Positiv = Fixpreis günstiger als Spot, Negativ = Spot wäre günstiger.
        """
        if not self.has_epex_integration:
            return None
        avg_spot = self.average_electricity_price
        if avg_spot is None:
            return None
        # Differenz pro kWh: was hätte Spot gekostet - was hat Fixpreis gekostet
        diff_per_kwh = avg_spot - self.fixed_price
        return diff_per_kwh * self._tracked_grid_import_kwh

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
        """Vergangene Tage seit Periodenbeginn."""
        start = self.quota_start_date
        if start is None:
            return 0
        elapsed = (date.today() - start).days
        return max(0, min(elapsed, self.quota_days_total))

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

    def _quota_seasonal_expected(self, from_date: date, to_date: date) -> float:
        """Berechnet den saisonalen Soll-Verbrauch zwischen zwei Daten."""
        import calendar
        total = 0.0
        current = from_date
        while current < to_date:
            month = current.month
            days_in_month = calendar.monthrange(current.year, month)[1]
            factor = SEASONAL_FACTORS.get(month, 1.0)
            daily_value = (factor / 12.0) * self.quota_yearly_kwh / days_in_month
            total += daily_value
            current += timedelta(days=1)
        return total

    def _quota_seasonal_fraction(self, from_date: date, to_date: date) -> float:
        """Berechnet den saisonalen Anteil der Periode (0.0 - 1.0)."""
        if self.quota_yearly_kwh <= 0:
            return 0.0
        return self._quota_seasonal_expected(from_date, to_date) / self.quota_yearly_kwh

    @property
    def quota_expected_kwh(self) -> float:
        """Soll-Verbrauch (saisonal gewichtet oder linear)."""
        if self.quota_days_total <= 0:
            return 0.0
        start = self.quota_start_date
        if self.quota_seasonal and start is not None:
            return self._quota_seasonal_expected(start, date.today())
        return (self.quota_days_elapsed / self.quota_days_total) * self.quota_yearly_kwh

    @property
    def quota_reserve_kwh(self) -> float:
        """Reserve: Soll minus Ist. Positiv = unter Budget, negativ = drüber."""
        return self.quota_expected_kwh - self.quota_consumed_kwh

    @property
    def quota_daily_budget_kwh(self) -> float | None:
        """Tagesbudget für Rest der Periode (kWh/Tag)."""
        remaining_days = self.quota_days_remaining
        if remaining_days <= 0:
            return None
        return self.quota_remaining_kwh / remaining_days

    @property
    def quota_forecast_kwh(self) -> float | None:
        """Hochrechnung: Verbrauch am Periodenende bei aktuellem Tempo."""
        days_elapsed = self.quota_days_elapsed
        if days_elapsed <= 0:
            return None
        start = self.quota_start_date
        if self.quota_seasonal and start is not None:
            fraction = self._quota_seasonal_fraction(start, date.today())
            if fraction <= 0:
                return None
            return self.quota_consumed_kwh / fraction
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
    def self_consumption_ratio(self) -> float:
        """Eigenverbrauchsquote (%)."""
        if self._pv_production_kwh <= 0:
            return 0.0
        current_self = max(0.0, self._pv_production_kwh - self._grid_export_kwh)
        return min(100.0, (current_self / self._pv_production_kwh) * 100)

    @property
    def autarky_rate(self) -> float | None:
        """Autarkiegrad (%) - Anteil des Verbrauchs der durch PV gedeckt wird."""
        self_consumption = max(0.0, self._pv_production_kwh - self._grid_export_kwh)
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

        # Bei Fixpreis: Berechne mit dem festen Preis
        savings_self = self_consumption * self.fixed_price
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
            "daily_reset_date": today.isoformat(),
            "monthly_grid_import_kwh": self._monthly_grid_import_kwh,
            "monthly_grid_import_cost": self._monthly_grid_import_cost,
            "monthly_reset_month": today.month,
            "monthly_reset_year": today.year,
        }

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

        if delta_self_consumption > 0 or delta_export > 0:
            # Bei Fixpreis: immer der feste Preis
            price_electricity = self.fixed_price
            price_feed_in = self.current_feed_in_tariff

            savings_delta = delta_self_consumption * price_electricity
            earnings_delta = delta_export * price_feed_in

            self._total_self_consumption_kwh += delta_self_consumption
            self._total_feed_in_kwh += delta_export
            self._accumulated_savings_self += savings_delta
            self._accumulated_earnings_feed += earnings_delta

        # Strompreis-Tracking (für Spot-Vergleich, falls EPEX konfiguriert)
        if delta_import > 0:
            # Hier tracken wir den EPEX Preis für Vergleich
            if self.has_epex_integration and self._epex_price > 0:
                import_cost = delta_import * self._epex_price
            else:
                import_cost = delta_import * self.fixed_price

            self._tracked_grid_import_kwh += delta_import
            self._total_grid_import_cost += import_cost

            today = date.today()
            if self._daily_tracking_date != today:
                self._daily_grid_import_cost = 0.0
                self._daily_grid_import_kwh = 0.0
                self._daily_tracking_date = today
            self._daily_grid_import_kwh += delta_import
            self._daily_grid_import_cost += import_cost

            current_month = today.month
            if self._monthly_tracking_month != current_month:
                self._monthly_grid_import_cost = 0.0
                self._monthly_grid_import_kwh = 0.0
                self._monthly_tracking_month = current_month
            self._monthly_grid_import_kwh += delta_import
            self._monthly_grid_import_cost += import_cost

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
        elif entity_id == self.epex_price_entity:
            # EPEX Preis auto-detect: > 1 = wahrscheinlich ct/kWh
            if value > 1.0:
                self._epex_price = value / 100.0
            else:
                self._epex_price = value
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

        # EPEX Preis laden
        if self.epex_price_entity:
            state = self.hass.states.get(self.epex_price_entity)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    value = float(state.state)
                    if value > 1.0:
                        self._epex_price = value / 100.0
                    else:
                        self._epex_price = value
                except (ValueError, TypeError):
                    pass

        self._last_pv_production_kwh = self._pv_production_kwh
        self._last_grid_export_kwh = self._grid_export_kwh
        self._last_grid_import_kwh = self._grid_import_kwh

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
    """Handler für Options-Updates."""
    try:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            ctrl = hass.data[DOMAIN][entry.entry_id].get(DATA_CTRL)
            if ctrl:
                ctrl._load_options()
                ctrl._notify_entities()
                _LOGGER.info("PV Management Fixpreis Optionen aktualisiert")
    except Exception as e:
        _LOGGER.error("Fehler beim Aktualisieren der Optionen: %s", e)
