from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, DATA_CTRL, CONF_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Binary Sensoren."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Management")

    entities = [
        AutoChargeBinarySensor(ctrl, name),
    ]

    async_add_entities(entities)


class AutoChargeBinarySensor(BinarySensorEntity):
    """
    Binary Sensor der anzeigt ob jetzt geladen werden sollte.

    Kann in Automatisierungen verwendet werden um die Batterie zu steuern:

    automation:
      trigger:
        - platform: state
          entity_id: binary_sensor.pv_management_auto_charge_empfehlung
          to: "on"
      action:
        - service: your_inverter.start_charging
    """

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, ctrl, name: str):
        self.ctrl = ctrl
        self._attr_name = f"{name} Auto-Charge Empfehlung"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_auto_charge_recommendation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Management",
        )
        self._removed = False

    async def async_added_to_hass(self):
        self._removed = False
        self.ctrl.register_entity_listener(self._on_ctrl_update)

    async def async_will_remove_from_hass(self):
        self._removed = True
        self.ctrl.unregister_entity_listener(self._on_ctrl_update)

    @callback
    def _on_ctrl_update(self):
        if not self._removed and self.hass:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """True wenn jetzt geladen werden sollte."""
        return self.ctrl.should_auto_charge

    @property
    def icon(self) -> str:
        """Icon basierend auf Status."""
        if self.is_on:
            return "mdi:battery-charging-high"
        elif not self.ctrl.auto_charge_enabled:
            return "mdi:battery-off"
        else:
            return "mdi:battery-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Detaillierte Infos für Debugging und Dashboards."""
        forecast = self.ctrl.solcast_forecast_today if self.ctrl.has_solcast_integration else self.ctrl.pv_forecast
        price_diff = self.ctrl.epex_price_diff_today

        return {
            # Status
            "auto_charge_aktiviert": self.ctrl.auto_charge_enabled,
            "sollte_laden": self.ctrl.should_auto_charge,
            "grund": self.ctrl.auto_charge_reason,

            # Aktuelle Werte
            "aktuelle_pv_prognose_kwh": round(forecast, 1),
            "aktueller_preis_quantile": round(self.ctrl.epex_quantile, 2) if self.ctrl.has_epex_integration else None,
            "aktueller_preis_ct": round(self.ctrl.current_electricity_price * 100, 1),
            "aktueller_batterie_soc": round(self.ctrl.battery_soc, 0) if self.ctrl.battery_soc_entity else None,
            "preisdifferenz_heute_ct": price_diff,

            # Schwellwerte (zum Vergleich)
            "schwelle_pv_prognose_kwh": self.ctrl.auto_charge_pv_threshold,
            "schwelle_preis_quantile": self.ctrl.auto_charge_price_quantile,
            "schwelle_min_soc": self.ctrl.auto_charge_min_soc,
            "schwelle_ziel_soc": self.ctrl.auto_charge_target_soc,
            "schwelle_min_preisdifferenz_ct": self.ctrl.auto_charge_min_price_diff,

            # Bedingungen einzeln
            "bedingung_pv_erfuellt": self.ctrl._check_pv_condition(),
            "bedingung_preis_erfuellt": self.ctrl._check_price_condition(),
            "bedingung_soc_erfuellt": self.ctrl._check_soc_condition(),
            "bedingung_preisdiff_erfuellt": self.ctrl._check_price_diff_condition(),

            # Integration Status
            "epex_integration": self.ctrl.has_epex_integration,
            "solcast_integration": self.ctrl.has_solcast_integration,
            "batterie_sensor_konfiguriert": bool(self.ctrl.battery_soc_entity),

            # Statistiken
            **self.ctrl.auto_charge_stats,
        }
