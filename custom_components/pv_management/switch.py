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


def get_battery_device_info(name: str) -> DeviceInfo:
    """DeviceInfo für das Batterie-Gerät."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{name}_battery")},
        name=f"{name} Batterie",
        manufacturer="Custom",
        model="PV Management - Batterie",
        via_device=(DOMAIN, name),
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Switches."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Management")

    entities = [
        AutoChargeSwitch(ctrl, name),
        DischargeSwitch(ctrl, name),
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
        self._attr_device_info = get_battery_device_info(name)
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
            "min_preisdifferenz_ct": self.ctrl.auto_charge_min_price_diff,
            "ladeleistung_w": self.ctrl.auto_charge_power,
            "aktuelle_pv_prognose_kwh": self.ctrl.solcast_forecast_today if self.ctrl.has_solcast_integration else self.ctrl.pv_forecast,
            "aktueller_preis_quantile": self.ctrl.epex_quantile if self.ctrl.has_epex_integration else None,
            "aktueller_batterie_soc": self.ctrl.battery_soc if self.ctrl.battery_soc_entity else None,
            "preisdifferenz_heute_ct": self.ctrl.epex_price_diff_today,
            "sollte_jetzt_laden": self.ctrl.should_auto_charge if self._is_on else False,
            "grund": self.ctrl.auto_charge_reason if self._is_on else "Auto-Charge deaktiviert",
        }


class DischargeSwitch(SwitchEntity, RestoreEntity):
    """
    Switch zum Aktivieren/Deaktivieren der Entlade-Steuerung.

    Wenn aktiviert, zeigt der "Entladung Empfehlung" Sensor an,
    wann die Batterie entladen werden sollte (teurer Preis).
    Im Sommer (Apr-Sep) wird automatisch normale Entladung verwendet.
    """

    _attr_should_poll = False

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} Entlade-Steuerung"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_discharge_switch"
        self._attr_icon = "mdi:battery-arrow-down"
        self._attr_device_info = get_battery_device_info(name)
        self._is_on = False
        self._removed = False

    async def async_added_to_hass(self):
        """Wiederherstellen des gespeicherten Zustands."""
        self._removed = False

        # Versuche letzten Zustand zu laden
        last_state = await self.async_get_last_state()
        if last_state:
            self._is_on = last_state.state == "on"
            self.ctrl.discharge_enabled = self._is_on
            _LOGGER.info("DischargeSwitch: Zustand wiederhergestellt: %s", self._is_on)

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
        """Aktiviert Entlade-Steuerung."""
        self._is_on = True
        self.ctrl.discharge_enabled = True
        _LOGGER.info("Entlade-Steuerung aktiviert")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deaktiviert Entlade-Steuerung."""
        self._is_on = False
        self.ctrl.discharge_enabled = False
        _LOGGER.info("Entlade-Steuerung deaktiviert")
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Zeigt die Entlade-Steuerung Einstellungen und aktuellen Status."""
        return {
            "nur_winter": self.ctrl.discharge_winter_only,
            "ist_winter": self.ctrl.is_winter,
            "sommer_modus": self.ctrl.discharge_is_summer_mode if self._is_on else False,
            "preis_quantile_schwelle": self.ctrl.discharge_price_quantile,
            "halten_soc_prozent": self.ctrl.discharge_hold_soc,
            "entladen_soc_prozent": self.ctrl.discharge_allow_soc,
            "sommer_soc_prozent": self.ctrl.discharge_summer_soc,
            "aktueller_preis_quantile": self.ctrl.epex_quantile if self.ctrl.has_epex_integration else None,
            "aktueller_batterie_soc": self.ctrl.battery_soc if self.ctrl.battery_soc_entity else None,
            "ziel_entladungstiefe": self.ctrl.discharge_target_soc if self._is_on else None,
            "sollte_jetzt_entladen": self.ctrl.should_discharge if self._is_on else False,
            "grund": self.ctrl.discharge_reason if self._is_on else "Entlade-Steuerung deaktiviert",
        }
