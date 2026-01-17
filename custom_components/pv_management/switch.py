from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, DATA_CTRL, CONF_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Switches."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Management")

    entities = [
        AutoChargeSwitch(ctrl, name),
    ]

    async_add_entities(entities)


class AutoChargeSwitch(SwitchEntity, RestoreEntity):
    """
    Switch zum Aktivieren/Deaktivieren der automatischen Batterie-Ladefunktion.

    Wenn aktiviert, zeigt der "Auto-Charge Empfehlung" Sensor an,
    wann die Batterie geladen werden sollte (günstiger Preis + schlechte PV-Prognose).
    """

    _attr_should_poll = False

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} Auto-Charge"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_auto_charge_switch"
        self._attr_icon = "mdi:battery-charging"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Management",
        )
        self._is_on = False
        self._removed = False

    async def async_added_to_hass(self):
        """Wiederherstellen des gespeicherten Zustands."""
        self._removed = False

        # Versuche letzten Zustand zu laden
        last_state = await self.async_get_last_state()
        if last_state:
            self._is_on = last_state.state == "on"
            self.ctrl.auto_charge_enabled = self._is_on
            _LOGGER.info("AutoChargeSwitch: Zustand wiederhergestellt: %s", self._is_on)

        self.ctrl.register_entity_listener(self._on_ctrl_update)

    async def async_will_remove_from_hass(self):
        """Entfernt den Listener wenn die Entity entladen wird."""
        self._removed = True
        self.ctrl.unregister_entity_listener(self._on_ctrl_update)

    @callback
    def _on_ctrl_update(self):
        if not self._removed and self.hass:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Gibt den aktuellen Zustand zurück."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Aktiviert Auto-Charge."""
        self._is_on = True
        self.ctrl.auto_charge_enabled = True
        _LOGGER.info("Auto-Charge aktiviert")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deaktiviert Auto-Charge."""
        self._is_on = False
        self.ctrl.auto_charge_enabled = False
        _LOGGER.info("Auto-Charge deaktiviert")
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Zeigt die Auto-Charge Einstellungen und aktuellen Status."""
        return {
            "pv_prognose_schwelle_kwh": self.ctrl.auto_charge_pv_threshold,
            "preis_quantile_schwelle": self.ctrl.auto_charge_price_quantile,
            "min_soc_prozent": self.ctrl.auto_charge_min_soc,
            "ziel_soc_prozent": self.ctrl.auto_charge_target_soc,
            "aktuelle_pv_prognose_kwh": self.ctrl.solcast_forecast_today if self.ctrl.has_solcast_integration else self.ctrl.pv_forecast,
            "aktueller_preis_quantile": self.ctrl.epex_quantile if self.ctrl.has_epex_integration else None,
            "aktueller_batterie_soc": self.ctrl.battery_soc if self.ctrl.battery_soc_entity else None,
            "sollte_jetzt_laden": self.ctrl.should_auto_charge if self._is_on else False,
            "grund": self.ctrl.auto_charge_reason if self._is_on else "Auto-Charge deaktiviert",
        }
