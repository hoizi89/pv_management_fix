from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, DATA_CTRL, CONF_NAME

_LOGGER = logging.getLogger(__name__)


def get_prices_device_info(name: str) -> DeviceInfo:
    """DeviceInfo für das Strompreise-Gerät."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{name}_prices")},
        name=f"{name} Strompreise",
        manufacturer="Custom",
        model="PV Management Fixpreis - Strompreise",
        via_device=(DOMAIN, name),
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Buttons."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Fixpreis")
    async_add_entities([
        ResetButton(ctrl, name),
        ResetGridImportButton(ctrl, name),
    ])


class BaseButton(ButtonEntity):
    """Basis-Klasse für Buttons."""

    _attr_should_poll = False

    def __init__(self, ctrl, name: str, key: str, icon: str | None = None):
        self.ctrl = ctrl
        self._attr_name = f"{name} {key}"
        self._attr_unique_id = f"{DOMAIN}_{name}_{key}".lower().replace(" ", "_")
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Management Fixpreis",
        )


class ResetButton(BaseButton):
    """Button zum Neu-Initialisieren aus Sensor-Daten."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Neu initialisieren", icon="mdi:restart")

    async def async_press(self) -> None:
        """Initialisiert die Werte neu aus den aktuellen Sensor-Totals."""
        _LOGGER.info("Reset-Button gedrückt: Initialisiere neu aus Sensor-Daten")
        # Erst zurücksetzen
        self.ctrl._total_self_consumption_kwh = 0.0
        self.ctrl._total_feed_in_kwh = 0.0
        self.ctrl._accumulated_savings_self = 0.0
        self.ctrl._accumulated_earnings_feed = 0.0
        self.ctrl._first_seen_date = None
        # Dann aus Sensoren initialisieren
        self.ctrl._initialize_from_sensors()
        # Last-Werte setzen für korrektes Delta-Tracking
        self.ctrl._last_pv_production_kwh = self.ctrl._pv_production_kwh
        self.ctrl._last_grid_export_kwh = self.ctrl._grid_export_kwh
        self.ctrl._notify_entities()


class ResetGridImportButton(ButtonEntity):
    """
    Button zum Zurücksetzen aller Strompreis-Tracking-Werte.

    Setzt zurück:
    - Gesamte Netzbezug-Kosten (€)
    - Getrackte kWh für Durchschnittsberechnung
    - Tägliche Werte
    - Monatliche Werte
    """

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} Strompreis-Tracking zurücksetzen"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_reset_grid_import_button"
        self._attr_icon = "mdi:cash-remove"
        self._attr_device_info = get_prices_device_info(name)

    async def async_press(self) -> None:
        """Handle button press - setzt alle Strompreis-Werte zurück."""
        _LOGGER.info(
            "Strompreis-Reset-Button gedrückt: Setze alle Werte zurück (war: %.2f kWh, %.2f €)",
            self.ctrl._tracked_grid_import_kwh,
            self.ctrl._total_grid_import_cost
        )
        self.ctrl.reset_grid_import_tracking()
