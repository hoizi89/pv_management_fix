from __future__ import annotations

import logging
from datetime import datetime, date
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
    CONF_INSTALLATION_COST, CONF_SAVINGS_OFFSET,
    CONF_ENERGY_OFFSET_SELF, CONF_ENERGY_OFFSET_EXPORT,
    CONF_INSTALLATION_DATE,
    DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET,
    DEFAULT_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_EXPORT,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    PRICE_UNIT_CENT,
)

_LOGGER = logging.getLogger(__name__)

# CO2 Faktor für deutschen Strommix (kg CO2 pro kWh)
CO2_FACTOR_GRID = 0.4


class PVAmortisationController:
    """
    Controller für PV-Amortisationsberechnung.

    WICHTIG: Berechnet Ersparnisse INKREMENTELL!
    Bei jeder Änderung der Energie-Sensoren wird die Differenz mit dem
    AKTUELLEN Preis multipliziert und aufaddiert. So sind dynamische
    Strompreise korrekt berücksichtigt.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry

        # Konfigurierbare Werte (aus Options, fallback zu data)
        # Inkl. Sensor-Entities (können nachträglich geändert werden)
        self._load_options()

        # Aktuelle Sensor-Werte (für Delta-Berechnung)
        self._last_pv_production_kwh: float | None = None
        self._last_grid_export_kwh: float | None = None
        self._last_grid_import_kwh: float | None = None
        self._last_consumption_kwh: float | None = None

        # Aktuelle Totals (werden live aktualisiert)
        self._pv_production_kwh = 0.0
        self._grid_export_kwh = 0.0
        self._grid_import_kwh = 0.0
        self._consumption_kwh = 0.0

        # INKREMENTELL berechnete Werte (werden persistent gespeichert)
        # Diese werden bei jedem Delta mit dem aktuellen Preis berechnet
        self._total_self_consumption_kwh = 0.0  # Aufaddierter Eigenverbrauch
        self._total_feed_in_kwh = 0.0  # Aufaddierte Einspeisung
        self._accumulated_savings_self = 0.0  # Aufaddierte € Ersparnis Eigenverbrauch
        self._accumulated_earnings_feed = 0.0  # Aufaddierte € Einnahmen Einspeisung

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

        # Preis-Konfiguration
        self.electricity_price = opts.get(CONF_ELECTRICITY_PRICE, DEFAULT_ELECTRICITY_PRICE)
        self.electricity_price_entity = opts.get(CONF_ELECTRICITY_PRICE_ENTITY)
        self.electricity_price_unit = opts.get(CONF_ELECTRICITY_PRICE_UNIT, DEFAULT_ELECTRICITY_PRICE_UNIT)
        self.feed_in_tariff = opts.get(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)
        self.feed_in_tariff_entity = opts.get(CONF_FEED_IN_TARIFF_ENTITY)
        self.feed_in_tariff_unit = opts.get(CONF_FEED_IN_TARIFF_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT)

        # Kosten und Offsets
        self.installation_cost = opts.get(CONF_INSTALLATION_COST, DEFAULT_INSTALLATION_COST)
        self.savings_offset = opts.get(CONF_SAVINGS_OFFSET, DEFAULT_SAVINGS_OFFSET)
        self.energy_offset_self = opts.get(CONF_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_SELF)
        self.energy_offset_export = opts.get(CONF_ENERGY_OFFSET_EXPORT, DEFAULT_ENERGY_OFFSET_EXPORT)
        self.installation_date = opts.get(CONF_INSTALLATION_DATE)

    def _convert_price_to_eur(self, price: float, unit: str) -> float:
        """Konvertiert Preis zu Euro/kWh (von Cent falls nötig)."""
        if unit == PRICE_UNIT_CENT:
            return price / 100.0
        return price

    def _get_dynamic_price(self, entity_id: str | None, fallback: float) -> float:
        """Holt dynamischen Preis von Sensor oder verwendet Fallback."""
        if not entity_id:
            return fallback

        state = self.hass.states.get(entity_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                return float(state.state)
            except (ValueError, TypeError):
                pass
        return fallback

    @property
    def current_electricity_price(self) -> float:
        """Aktueller Strompreis in €/kWh (dynamisch oder statisch, konvertiert von Cent falls nötig)."""
        raw_price = self._get_dynamic_price(self.electricity_price_entity, self.electricity_price)
        return self._convert_price_to_eur(raw_price, self.electricity_price_unit)

    @property
    def current_feed_in_tariff(self) -> float:
        """Aktuelle Einspeisevergütung in €/kWh (dynamisch oder statisch, konvertiert von Cent falls nötig)."""
        raw_tariff = self._get_dynamic_price(self.feed_in_tariff_entity, self.feed_in_tariff)
        return self._convert_price_to_eur(raw_tariff, self.feed_in_tariff_unit)

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
        """Gesamter Eigenverbrauch (inkrementell berechnet + Offset)."""
        return self._total_self_consumption_kwh + self.energy_offset_self

    @property
    def feed_in_kwh(self) -> float:
        """Gesamte Einspeisung (inkrementell berechnet + Offset)."""
        return self._total_feed_in_kwh + self.energy_offset_export

    @property
    def savings_self_consumption(self) -> float:
        """Ersparnis durch Eigenverbrauch (inkrementell berechnet + Offset-Anteil)."""
        # Offset-Energie mit aktuellem Preis (Annäherung)
        offset_savings = self.energy_offset_self * self.current_electricity_price
        return self._accumulated_savings_self + offset_savings

    @property
    def earnings_feed_in(self) -> float:
        """Einnahmen durch Einspeisung (inkrementell berechnet + Offset-Anteil)."""
        # Offset-Energie mit aktuellem Tarif (Annäherung)
        offset_earnings = self.energy_offset_export * self.current_feed_in_tariff
        return self._accumulated_earnings_feed + offset_earnings

    @property
    def total_savings(self) -> float:
        """Gesamtersparnis inkl. Offset."""
        return self.savings_self_consumption + self.earnings_feed_in + self.savings_offset

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
        # Aktuelle Eigenverbrauchsquote basierend auf Sensor-Totals
        current_self = max(0.0, self._pv_production_kwh - self._grid_export_kwh)
        return min(100.0, (current_self / self._pv_production_kwh) * 100)

    @property
    def autarky_rate(self) -> float:
        """Autarkiegrad (%)."""
        if self._consumption_kwh <= 0:
            return 0.0
        current_self = max(0.0, self._pv_production_kwh - self._grid_export_kwh)
        return min(100.0, (current_self / self._consumption_kwh) * 100)

    @property
    def co2_saved_kg(self) -> float:
        """Eingesparte CO2-Emissionen in kg."""
        return self.self_consumption_kwh * CO2_FACTOR_GRID

    @property
    def days_since_installation(self) -> int:
        """Tage seit Installation."""
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

    def register_entity_listener(self, cb) -> None:
        """Sensoren registrieren sich hier für Updates."""
        self._entity_listeners.append(cb)

    def _notify_entities(self) -> None:
        """Informiert alle Entities über Zustandsänderungen."""
        for cb in self._entity_listeners:
            try:
                cb()
            except Exception as e:
                _LOGGER.exception("Entity-Listener Fehler: %s", e)

    def restore_state(self, data: dict[str, Any]) -> None:
        """Stellt den gespeicherten Zustand wieder her."""
        self._total_self_consumption_kwh = data.get("total_self_consumption_kwh", 0.0)
        self._total_feed_in_kwh = data.get("total_feed_in_kwh", 0.0)
        self._accumulated_savings_self = data.get("accumulated_savings_self", 0.0)
        self._accumulated_earnings_feed = data.get("accumulated_earnings_feed", 0.0)

        first_seen = data.get("first_seen_date")
        if first_seen:
            try:
                self._first_seen_date = date.fromisoformat(first_seen)
            except (ValueError, TypeError):
                pass

        self._restored = True
        _LOGGER.info(
            "PV Amortisation restored: %.2f kWh self, %.2f kWh feed, %.2f€ savings, %.2f€ earnings",
            self._total_self_consumption_kwh,
            self._total_feed_in_kwh,
            self._accumulated_savings_self,
            self._accumulated_earnings_feed,
        )

    def get_state_for_storage(self) -> dict[str, Any]:
        """Gibt den zu speichernden Zustand zurück."""
        return {
            "total_self_consumption_kwh": self._total_self_consumption_kwh,
            "total_feed_in_kwh": self._total_feed_in_kwh,
            "accumulated_savings_self": self._accumulated_savings_self,
            "accumulated_earnings_feed": self._accumulated_earnings_feed,
            "first_seen_date": self._first_seen_date.isoformat() if self._first_seen_date else None,
        }

    def _process_energy_update(self) -> None:
        """
        Verarbeitet Energie-Updates INKREMENTELL.

        Bei jeder Änderung der Sensor-Werte wird:
        1. Das Delta seit dem letzten Update berechnet
        2. Das Delta mit dem AKTUELLEN Preis multipliziert
        3. Auf die Gesamtsumme addiert

        So sind dynamische Preise korrekt berücksichtigt!
        """
        # Hole aktuelle Sensor-Werte
        current_pv = self._pv_production_kwh
        current_export = self._grid_export_kwh

        # Prüfe ob wir gültige Last-Werte haben
        if self._last_pv_production_kwh is None:
            self._last_pv_production_kwh = current_pv
            self._last_grid_export_kwh = current_export
            return

        # Berechne Deltas
        delta_pv = current_pv - self._last_pv_production_kwh
        delta_export = current_export - self._last_grid_export_kwh

        # Ignoriere negative Deltas (Sensor-Reset oder Fehler)
        if delta_pv < 0:
            _LOGGER.debug("PV Delta negativ (%.3f), überspringe", delta_pv)
            self._last_pv_production_kwh = current_pv
            delta_pv = 0

        if delta_export < 0:
            _LOGGER.debug("Export Delta negativ (%.3f), überspringe", delta_export)
            self._last_grid_export_kwh = current_export
            delta_export = 0

        # Berechne Delta Eigenverbrauch
        # Eigenverbrauch = PV Produktion - Netzeinspeisung
        delta_self_consumption = max(0.0, delta_pv - delta_export)

        # Nur verarbeiten wenn es tatsächlich Änderungen gibt
        if delta_self_consumption > 0 or delta_export > 0:
            # Hole aktuelle Preise
            price_electricity = self.current_electricity_price
            price_feed_in = self.current_feed_in_tariff

            # Berechne Ersparnis/Einnahmen für dieses Delta
            savings_delta = delta_self_consumption * price_electricity
            earnings_delta = delta_export * price_feed_in

            # Addiere zu Gesamtsummen
            self._total_self_consumption_kwh += delta_self_consumption
            self._total_feed_in_kwh += delta_export
            self._accumulated_savings_self += savings_delta
            self._accumulated_earnings_feed += earnings_delta

            _LOGGER.debug(
                "Delta: +%.3f kWh self (%.4f€), +%.3f kWh export (%.4f€) @ %.4f€/kWh, %.4f€/kWh",
                delta_self_consumption, savings_delta,
                delta_export, earnings_delta,
                price_electricity, price_feed_in,
            )

        # Update Last-Werte
        self._last_pv_production_kwh = current_pv
        self._last_grid_export_kwh = current_export

        # Benachrichtige Entities
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

        # Initialisiere first_seen_date
        if self._first_seen_date is None:
            self._first_seen_date = date.today()

        # Update entsprechenden Wert
        changed = False
        if entity_id == self.pv_production_entity:
            self._pv_production_kwh = value
            changed = True
        elif entity_id == self.grid_export_entity:
            self._grid_export_kwh = value
            changed = True
        elif entity_id == self.grid_import_entity:
            self._grid_import_kwh = value
        elif entity_id == self.consumption_entity:
            self._consumption_kwh = value

        # Nur bei PV oder Export Änderungen die inkrementelle Berechnung triggern
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

        # Initialisiere Last-Werte für Delta-Berechnung
        self._last_pv_production_kwh = self._pv_production_kwh
        self._last_grid_export_kwh = self._grid_export_kwh
        self._last_grid_import_kwh = self._grid_import_kwh
        self._last_consumption_kwh = self._consumption_kwh

        # Event-Listener registrieren
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

    def set_options(self, **kwargs) -> None:
        """Setzt Optionen zur Laufzeit."""
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup der Integration."""
    ctrl = PVAmortisationController(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_CTRL: ctrl}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await ctrl.async_start()

    entry.add_update_listener(_async_update_listener)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entlädt die Integration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
        await ctrl.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handler für Options-Updates."""
    await hass.config_entries.async_reload(entry.entry_id)
