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
from homeassistant.helpers.event import async_call_later

from .const import (
    DOMAIN, DATA_CTRL, CONF_NAME,
    SURPLUS_RATIOS, SURPLUS_HYSTERESIS_RATIO,
    SURPLUS_ON_DELAY, SURPLUS_OFF_DELAY,
)

_LOGGER = logging.getLogger(__name__)


def get_pv_surplus_device_info(name: str) -> DeviceInfo:
    """DeviceInfo fuer das PV-Ueberschuss-Geraet."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{name}_pv_surplus")},
        name=f"{name} PV-Ueberschuss",
        manufacturer="Custom",
        model="PV Management - PV-Ueberschuss",
        via_device=(DOMAIN, name),
    )


LEVEL_LABELS = {"low": "Low", "medium": "Medium", "high": "High"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Binary Sensoren."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Fixpreis")

    entities = [
        PVSurplusBinarySensor(ctrl, name, "low"),
        PVSurplusBinarySensor(ctrl, name, "medium"),
        PVSurplusBinarySensor(ctrl, name, "high"),
    ]

    async_add_entities(entities)


class PVSurplusBinarySensor(BinarySensorEntity):
    """Binary Sensor fuer PV-Ueberschuss-Stufen (low/medium/high).

    Auto-derived Schwelle = SURPLUS_RATIOS[level] * pv_peak_power.
    Hysterese: ON bei surplus >= threshold, OFF bei surplus < threshold * (1 - HYSTERESIS_RATIO).
    Anti-Flacker: ON erst nach SURPLUS_ON_DELAY s stabilem Ueberschuss, OFF erst nach SURPLUS_OFF_DELAY s.

    Fuer PV-aware Verbraucher (WP-Kuehlung, Waschmaschine, Geschirrspueler, EV).
    """

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, ctrl, name: str, level: str):
        self.ctrl = ctrl
        self._level = level
        self._ratio = SURPLUS_RATIOS[level]
        label = LEVEL_LABELS[level]
        self._attr_name = f"{name} PV-Ueberschuss {label}"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_pv_surplus_{level}"
        self._attr_device_info = get_pv_surplus_device_info(name)
        self._removed = False
        # State machine
        self._committed_state: bool = False
        self._pending_target: bool | None = None
        self._pending_cancel = None

    async def async_added_to_hass(self):
        self._removed = False
        self.ctrl.register_entity_listener(self._on_ctrl_update)
        # Initial state ohne Delay (beim Start direkt commit)
        self._committed_state = self._compute_desired_state()

    async def async_will_remove_from_hass(self):
        self._removed = True
        self.ctrl.unregister_entity_listener(self._on_ctrl_update)
        self._cancel_pending()

    @callback
    def _on_ctrl_update(self):
        if self._removed or not self.hass:
            return
        self._evaluate()

    def _cancel_pending(self):
        if self._pending_cancel:
            self._pending_cancel()
        self._pending_cancel = None
        self._pending_target = None

    def _compute_desired_state(self) -> bool:
        """Raw desired state mit Hysterese."""
        if not (self.ctrl.pv_power_entity and self.ctrl.house_power_entity):
            return False  # Ohne beide Sensoren keine Ueberschussberechnung
        if self.ctrl.pv_peak_power <= 0:
            return False
        surplus = self.ctrl.current_pv_surplus_w
        threshold_on = self.ctrl.pv_peak_power * self._ratio
        threshold_off = threshold_on * (1.0 - SURPLUS_HYSTERESIS_RATIO)
        if self._committed_state:
            return surplus >= threshold_off
        return surplus >= threshold_on

    def _evaluate(self):
        desired = self._compute_desired_state()
        if desired == self._committed_state:
            # Stabilisiert — etwaige Transition abbrechen
            self._cancel_pending()
            return
        if self._pending_target == desired:
            # Schon geplant, weiter laufen lassen
            return
        # Richtung gewechselt oder neu: alte Transition abbrechen, neue starten
        self._cancel_pending()
        delay = SURPLUS_ON_DELAY if desired else SURPLUS_OFF_DELAY
        self._pending_target = desired
        self._pending_cancel = async_call_later(self.hass, delay, self._commit_pending)

    @callback
    def _commit_pending(self, _now=None):
        self._pending_cancel = None
        if self._removed or self._pending_target is None:
            return
        # Re-check beim Commit: nur uebernehmen wenn noch immer gewuenscht
        if self._compute_desired_state() == self._pending_target:
            self._committed_state = self._pending_target
            if self.hass:
                self.async_write_ha_state()
        self._pending_target = None

    @property
    def is_on(self) -> bool:
        return self._committed_state

    @property
    def icon(self) -> str:
        if self.is_on:
            return "mdi:solar-power-variant"
        return "mdi:solar-power-variant-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        threshold_on = self.ctrl.pv_peak_power * self._ratio
        threshold_off = threshold_on * (1.0 - SURPLUS_HYSTERESIS_RATIO)
        pending = (
            "ein" if self._pending_target is True
            else "aus" if self._pending_target is False
            else None
        )
        return {
            "stufe": self._level,
            "aktueller_ueberschuss_w": round(self.ctrl.current_pv_surplus_w, 0),
            "pv_leistung_w": round(self.ctrl.pv_power, 0),
            "hausverbrauch_w": round(self.ctrl.house_power, 0),
            "schwelle_ein_w": round(threshold_on, 0),
            "schwelle_aus_w": round(threshold_off, 0),
            "anteil_peak": SURPLUS_RATIOS[self._level],
            "pv_peak_w": round(self.ctrl.pv_peak_power, 0),
            "pv_peak_quelle": self.ctrl.pv_peak_power_source,
            "on_delay_s": SURPLUS_ON_DELAY,
            "off_delay_s": SURPLUS_OFF_DELAY,
            "pv_power_sensor_konfiguriert": bool(self.ctrl.pv_power_entity),
            "haus_power_sensor_konfiguriert": bool(self.ctrl.house_power_entity),
            "uebergang_ausstehend": pending,
        }
