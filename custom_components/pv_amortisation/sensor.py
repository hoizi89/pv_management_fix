from __future__ import annotations

import logging
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, DATA_CTRL, CONF_NAME,
    CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_ELECTRICITY_PRICE_ENTITY, CONF_FEED_IN_TARIFF_ENTITY,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Sensoren."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Amortisation")

    entities = [
        # === Haupt-Sensoren (Übersicht) ===
        AmortisationPercentSensor(ctrl, name),
        TotalSavingsSensor(ctrl, name),  # Dieser speichert persistent!
        RemainingCostSensor(ctrl, name),
        StatusSensor(ctrl, name),

        # === Energie-Sensoren ===
        SelfConsumptionSensor(ctrl, name),
        FeedInSensor(ctrl, name),
        PVProductionSensor(ctrl, name),

        # === Finanz-Sensoren ===
        SavingsSelfConsumptionSensor(ctrl, name),
        EarningsFeedInSensor(ctrl, name),

        # === Effizienz-Sensoren ===
        SelfConsumptionRatioSensor(ctrl, name),
        AutarkyRateSensor(ctrl, name),

        # === Statistik-Sensoren ===
        AverageDailySavingsSensor(ctrl, name),
        AverageMonthlySavingsSensor(ctrl, name),
        AverageYearlySavingsSensor(ctrl, name),
        DaysSinceInstallationSensor(ctrl, name),

        # === Prognose-Sensoren ===
        EstimatedRemainingDaysSensor(ctrl, name),
        EstimatedPaybackDateSensor(ctrl, name),

        # === Umwelt-Sensoren ===
        CO2SavedSensor(ctrl, name),

        # === Konfigurations-Sensoren (Diagnose) ===
        CurrentElectricityPriceSensor(ctrl, name),
        CurrentFeedInTariffSensor(ctrl, name),
        InstallationCostSensor(ctrl, name),
        ConfigurationDiagnosticSensor(ctrl, name, entry),
    ]

    async_add_entities(entities)


class BaseEntity(SensorEntity):
    """Basis-Klasse für alle Sensoren."""

    _attr_should_poll = False

    def __init__(
        self,
        ctrl,
        name: str,
        key: str,
        unit=None,
        icon=None,
        state_class=None,
        device_class=None,
        entity_category=None,
    ):
        self.ctrl = ctrl
        self._attr_name = f"{name} {key}"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_{key.lower().replace(' ', '_')}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Amortisation Tracker",
        )

    async def async_added_to_hass(self):
        self.ctrl.register_entity_listener(self._on_ctrl_update)

    @callback
    def _on_ctrl_update(self):
        self.async_write_ha_state()


# =============================================================================
# HAUPT-SENSOREN
# =============================================================================


class AmortisationPercentSensor(BaseEntity):
    """Amortisation in Prozent - Hauptindikator."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amortisation",
            unit="%",
            icon="mdi:percent-circle",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.amortisation_percent, 2)

    @property
    def extra_state_attributes(self):
        return {
            "total_savings": f"{self.ctrl.total_savings:.2f}€",
            "installation_cost": f"{self.ctrl.installation_cost:.2f}€",
            "remaining": f"{self.ctrl.remaining_cost:.2f}€",
            "is_amortised": self.ctrl.is_amortised,
        }


class TotalSavingsSensor(BaseEntity, RestoreEntity):
    """
    Gesamtersparnis in Euro.

    WICHTIG: Dieser Sensor speichert die inkrementell berechneten Werte
    persistent, damit sie über Neustarts erhalten bleiben!
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Gesamtersparnis",
            unit="€",
            icon="mdi:cash-plus",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
        )

    async def async_added_to_hass(self):
        """Wiederherstellen des gespeicherten Zustands."""
        await super().async_added_to_hass()

        # Versuche letzten Zustand zu laden
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            # Lade die extra_state_attributes für die vollständigen Daten
            attrs = last_state.attributes or {}

            restore_data = {
                "total_self_consumption_kwh": attrs.get("tracked_self_consumption_kwh", 0.0),
                "total_feed_in_kwh": attrs.get("tracked_feed_in_kwh", 0.0),
                "accumulated_savings_self": attrs.get("accumulated_savings_self", 0.0),
                "accumulated_earnings_feed": attrs.get("accumulated_earnings_feed", 0.0),
                "first_seen_date": attrs.get("first_seen_date"),
            }

            self.ctrl.restore_state(restore_data)
            _LOGGER.info("TotalSavingsSensor: Zustand wiederhergestellt")

    @property
    def native_value(self) -> float:
        return round(self.ctrl.total_savings, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """
        Speichert alle wichtigen Werte als Attribute.
        Diese werden von RestoreEntity wiederhergestellt.
        """
        return {
            "savings_self_consumption": f"{self.ctrl.savings_self_consumption:.2f}€",
            "earnings_feed_in": f"{self.ctrl.earnings_feed_in:.2f}€",
            "offset": f"{self.ctrl.savings_offset:.2f}€",
            # Inkrementell berechnete Werte (werden restored)
            "tracked_self_consumption_kwh": round(self.ctrl._total_self_consumption_kwh, 4),
            "tracked_feed_in_kwh": round(self.ctrl._total_feed_in_kwh, 4),
            "accumulated_savings_self": round(self.ctrl._accumulated_savings_self, 4),
            "accumulated_earnings_feed": round(self.ctrl._accumulated_earnings_feed, 4),
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            # Info
            "calculation_method": "incremental (dynamic prices supported)",
        }


class RemainingCostSensor(BaseEntity):
    """Verbleibender Betrag bis Amortisation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Restbetrag",
            unit="€",
            icon="mdi:cash-minus",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.MONETARY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.remaining_cost, 2)

    @property
    def icon(self) -> str:
        if self.ctrl.is_amortised:
            return "mdi:cash-check"
        return "mdi:cash-minus"


class StatusSensor(BaseEntity):
    """Status-Text (z.B. '45.2% amortisiert' oder 'Amortisiert!')."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Status",
            icon="mdi:solar-power-variant",
        )

    @property
    def native_value(self) -> str:
        return self.ctrl.status_text

    @property
    def icon(self) -> str:
        if self.ctrl.is_amortised:
            return "mdi:party-popper"
        elif self.ctrl.amortisation_percent >= 75:
            return "mdi:trending-up"
        elif self.ctrl.amortisation_percent >= 50:
            return "mdi:solar-power-variant"
        else:
            return "mdi:solar-panel"

    @property
    def extra_state_attributes(self):
        attrs = {
            "percent": f"{self.ctrl.amortisation_percent:.1f}%",
            "total_savings": f"{self.ctrl.total_savings:.2f}€",
            "remaining": f"{self.ctrl.remaining_cost:.2f}€",
        }
        if self.ctrl.is_amortised:
            profit = self.ctrl.total_savings - self.ctrl.installation_cost
            attrs["profit"] = f"{profit:.2f}€"
        return attrs


# =============================================================================
# ENERGIE-SENSOREN
# =============================================================================


class SelfConsumptionSensor(BaseEntity):
    """Eigenverbrauch in kWh (inkrementell berechnet)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Eigenverbrauch",
            unit="kWh",
            icon="mdi:home-lightning-bolt",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.ENERGY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.self_consumption_kwh, 2)

    @property
    def extra_state_attributes(self):
        return {
            "tracked_kwh": round(self.ctrl._total_self_consumption_kwh, 2),
            "offset_kwh": round(self.ctrl.energy_offset_self, 2),
        }


class FeedInSensor(BaseEntity):
    """Netzeinspeisung in kWh (inkrementell berechnet)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Einspeisung",
            unit="kWh",
            icon="mdi:transmission-tower-export",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.ENERGY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.feed_in_kwh, 2)

    @property
    def extra_state_attributes(self):
        return {
            "tracked_kwh": round(self.ctrl._total_feed_in_kwh, 2),
            "offset_kwh": round(self.ctrl.energy_offset_export, 2),
        }


class PVProductionSensor(BaseEntity):
    """PV-Produktion in kWh (gespiegelt vom Input-Sensor)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV Produktion",
            unit="kWh",
            icon="mdi:solar-power",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.ENERGY,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.pv_production_kwh, 2)


# =============================================================================
# FINANZ-SENSOREN
# =============================================================================


class SavingsSelfConsumptionSensor(BaseEntity):
    """Ersparnis durch Eigenverbrauch (inkrementell berechnet)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ersparnis Eigenverbrauch",
            unit="€",
            icon="mdi:piggy-bank",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.savings_self_consumption, 2)

    @property
    def extra_state_attributes(self):
        return {
            "self_consumption_kwh": f"{self.ctrl.self_consumption_kwh:.2f} kWh",
            "current_price": f"{self.ctrl.current_electricity_price:.4f} €/kWh",
            "accumulated_savings": f"{self.ctrl._accumulated_savings_self:.2f}€",
            "calculation": "incremental (each kWh × price at that time)",
        }


class EarningsFeedInSensor(BaseEntity):
    """Einnahmen durch Einspeisung (inkrementell berechnet)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Einnahmen Einspeisung",
            unit="€",
            icon="mdi:cash-plus",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.earnings_feed_in, 2)

    @property
    def extra_state_attributes(self):
        return {
            "feed_in_kwh": f"{self.ctrl.feed_in_kwh:.2f} kWh",
            "current_tariff": f"{self.ctrl.current_feed_in_tariff:.4f} €/kWh",
            "accumulated_earnings": f"{self.ctrl._accumulated_earnings_feed:.2f}€",
            "calculation": "incremental (each kWh × tariff at that time)",
        }


# =============================================================================
# EFFIZIENZ-SENSOREN
# =============================================================================


class SelfConsumptionRatioSensor(BaseEntity):
    """Eigenverbrauchsquote in Prozent."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Eigenverbrauchsquote",
            unit="%",
            icon="mdi:home-percent",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.self_consumption_ratio, 1)

    @property
    def extra_state_attributes(self):
        return {
            "description": "Anteil der PV-Produktion der selbst verbraucht wird",
        }


class AutarkyRateSensor(BaseEntity):
    """Autarkiegrad in Prozent."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Autarkiegrad",
            unit="%",
            icon="mdi:home-battery",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.autarky_rate, 1)

    @property
    def extra_state_attributes(self):
        return {
            "description": "Anteil des Verbrauchs der durch PV gedeckt wird",
        }


# =============================================================================
# STATISTIK-SENSOREN
# =============================================================================


class AverageDailySavingsSensor(BaseEntity):
    """Durchschnittliche tägliche Ersparnis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ersparnis pro Tag",
            unit="€/Tag",
            icon="mdi:calendar-today",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_daily_savings, 2)


class AverageMonthlySavingsSensor(BaseEntity):
    """Durchschnittliche monatliche Ersparnis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ersparnis pro Monat",
            unit="€/Monat",
            icon="mdi:calendar-month",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_monthly_savings, 2)


class AverageYearlySavingsSensor(BaseEntity):
    """Durchschnittliche jährliche Ersparnis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ersparnis pro Jahr",
            unit="€/Jahr",
            icon="mdi:calendar",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.average_yearly_savings, 2)


class DaysSinceInstallationSensor(BaseEntity):
    """Tage seit Installation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Tage seit Installation",
            unit="Tage",
            icon="mdi:calendar-clock",
            state_class=SensorStateClass.TOTAL_INCREASING,
        )

    @property
    def native_value(self) -> int:
        return self.ctrl.days_since_installation


# =============================================================================
# PROGNOSE-SENSOREN
# =============================================================================


class EstimatedRemainingDaysSensor(BaseEntity):
    """Geschätzte verbleibende Tage bis Amortisation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Restlaufzeit",
            unit="Tage",
            icon="mdi:timer-sand",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> int | None:
        return self.ctrl.estimated_remaining_days

    @property
    def extra_state_attributes(self):
        remaining = self.ctrl.estimated_remaining_days
        if remaining is None:
            return {"status": "Berechnung nicht möglich"}

        years = remaining // 365
        months = (remaining % 365) // 30
        days = remaining % 30

        parts = []
        if years > 0:
            parts.append(f"{years} Jahr{'e' if years > 1 else ''}")
        if months > 0:
            parts.append(f"{months} Monat{'e' if months > 1 else ''}")
        if days > 0 or not parts:
            parts.append(f"{days} Tag{'e' if days != 1 else ''}")

        return {
            "formatted": ", ".join(parts),
            "years": years,
            "months": months,
            "days": days,
        }


class EstimatedPaybackDateSensor(BaseEntity):
    """Geschätztes Amortisationsdatum."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amortisationsdatum",
            icon="mdi:calendar-check",
            device_class=SensorDeviceClass.DATE,
        )

    @property
    def native_value(self) -> date | None:
        return self.ctrl.estimated_payback_date

    @property
    def icon(self) -> str:
        if self.ctrl.is_amortised:
            return "mdi:calendar-check"
        return "mdi:calendar-question"


# =============================================================================
# UMWELT-SENSOREN
# =============================================================================


class CO2SavedSensor(BaseEntity):
    """Eingesparte CO2-Emissionen."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "CO2 Ersparnis",
            unit="kg",
            icon="mdi:molecule-co2",
            state_class=SensorStateClass.TOTAL_INCREASING,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.co2_saved_kg, 1)

    @property
    def extra_state_attributes(self):
        kg = self.ctrl.co2_saved_kg
        return {
            "tonnes": f"{kg / 1000:.2f} t",
            "trees_equivalent": int(kg / 21),
            "car_km_equivalent": int(kg / 0.12),
        }


# =============================================================================
# KONFIGURATIONS-SENSOREN (DIAGNOSE)
# =============================================================================


class CurrentElectricityPriceSensor(BaseEntity):
    """Aktueller Strompreis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Strompreis",
            unit="€/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.current_electricity_price, 4)

    @property
    def extra_state_attributes(self):
        return {
            "source": "sensor" if self.ctrl.electricity_price_entity else "config",
            "config_value": f"{self.ctrl.electricity_price:.4f}",
            "unit_config": self.ctrl.electricity_price_unit,
        }


class CurrentFeedInTariffSensor(BaseEntity):
    """Aktuelle Einspeisevergütung."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Einspeisevergütung",
            unit="€/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.current_feed_in_tariff, 4)

    @property
    def extra_state_attributes(self):
        return {
            "source": "sensor" if self.ctrl.feed_in_tariff_entity else "config",
            "config_value": f"{self.ctrl.feed_in_tariff:.4f}",
            "unit_config": self.ctrl.feed_in_tariff_unit,
        }


class InstallationCostSensor(BaseEntity):
    """Anschaffungskosten der PV-Anlage."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Anschaffungskosten",
            unit="€",
            icon="mdi:cash",
            device_class=SensorDeviceClass.MONETARY,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.installation_cost, 2)


class ConfigurationDiagnosticSensor(BaseEntity):
    """Diagnose-Sensor zeigt alle konfigurierten Sensoren und deren Status."""

    def __init__(self, ctrl, name: str, entry: ConfigEntry):
        super().__init__(
            ctrl,
            name,
            "Konfiguration",
            icon="mdi:cog",
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._entry = entry

    def _get_entity_status(self, entity_id: str | None) -> dict[str, Any]:
        """Holt Status einer Entity."""
        if not entity_id:
            return {"configured": False, "entity_id": None, "state": None, "status": "nicht konfiguriert"}

        state = self.hass.states.get(entity_id)
        if state is None:
            return {
                "configured": True,
                "entity_id": entity_id,
                "state": None,
                "status": "nicht gefunden",
            }
        elif state.state in ("unavailable", "unknown"):
            return {
                "configured": True,
                "entity_id": entity_id,
                "state": state.state,
                "status": "nicht verfügbar",
            }
        else:
            return {
                "configured": True,
                "entity_id": entity_id,
                "state": state.state,
                "status": "OK",
            }

    @property
    def native_value(self) -> str:
        """Zeigt Gesamtstatus der Konfiguration."""
        issues = 0

        # Prüfe alle konfigurierten Sensoren
        entities_to_check = [
            self.ctrl.pv_production_entity,
            self.ctrl.grid_export_entity,
        ]

        for entity_id in entities_to_check:
            if entity_id:
                status = self._get_entity_status(entity_id)
                if status["status"] != "OK":
                    issues += 1

        if issues == 0:
            return "OK"
        else:
            return f"{issues} Problem{'e' if issues > 1 else ''}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Zeigt alle konfigurierten Sensoren und deren Status."""
        pv_status = self._get_entity_status(self.ctrl.pv_production_entity)
        export_status = self._get_entity_status(self.ctrl.grid_export_entity)
        import_status = self._get_entity_status(self.ctrl.grid_import_entity)
        consumption_status = self._get_entity_status(self.ctrl.consumption_entity)
        price_status = self._get_entity_status(self.ctrl.electricity_price_entity)
        tariff_status = self._get_entity_status(self.ctrl.feed_in_tariff_entity)

        return {
            # Hauptsensoren
            "pv_production_entity": pv_status["entity_id"],
            "pv_production_status": pv_status["status"],
            "pv_production_value": pv_status["state"],

            "grid_export_entity": export_status["entity_id"],
            "grid_export_status": export_status["status"],
            "grid_export_value": export_status["state"],

            "grid_import_entity": import_status["entity_id"],
            "grid_import_status": import_status["status"],
            "grid_import_value": import_status["state"],

            "consumption_entity": consumption_status["entity_id"],
            "consumption_status": consumption_status["status"],
            "consumption_value": consumption_status["state"],

            # Preissensoren (optional)
            "electricity_price_entity": price_status["entity_id"],
            "electricity_price_status": price_status["status"],
            "electricity_price_value": price_status["state"],
            "electricity_price_source": "sensor" if self.ctrl.electricity_price_entity else "config",

            "feed_in_tariff_entity": tariff_status["entity_id"],
            "feed_in_tariff_status": tariff_status["status"],
            "feed_in_tariff_value": tariff_status["state"],
            "feed_in_tariff_source": "sensor" if self.ctrl.feed_in_tariff_entity else "config",

            # Berechnungsmethode
            "calculation_method": "incremental",
            "supports_dynamic_prices": True,
            "supports_battery": True,

            # Tracking-Status
            "tracking_active": self.ctrl._first_seen_date is not None,
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            "data_restored": self.ctrl._restored,
        }

    @property
    def icon(self) -> str:
        """Icon basierend auf Status."""
        if self.native_value == "OK":
            return "mdi:check-circle"
        else:
            return "mdi:alert-circle"
