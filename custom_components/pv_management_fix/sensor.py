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

from .const import DOMAIN, DATA_CTRL, CONF_NAME

_LOGGER = logging.getLogger(__name__)

# Geräte-Typen
DEVICE_MAIN = "main"
DEVICE_PRICES = "prices"


def get_device_info(name: str, device_type: str = DEVICE_MAIN) -> DeviceInfo:
    """Erstellt DeviceInfo für verschiedene Geräte-Typen."""
    if device_type == DEVICE_PRICES:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_prices")},
            name=f"{name} Strompreise",
            manufacturer="Custom",
            model="PV Management Fixpreis - Strompreise",
            via_device=(DOMAIN, name),
        )
    else:  # DEVICE_MAIN
        return DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Management Fixpreis",
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup der Sensoren."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Fixpreis")

    entities = [
        # === AMORTISATION (Hauptzweck) ===
        AmortisationPercentSensor(ctrl, name),
        TotalSavingsSensor(ctrl, name),
        RemainingCostSensor(ctrl, name),
        StatusSensor(ctrl, name),
        EstimatedPaybackDateSensor(ctrl, name),
        EstimatedRemainingDaysSensor(ctrl, name),

        # === ENERGIE ===
        SelfConsumptionSensor(ctrl, name),
        FeedInSensor(ctrl, name),
        SelfConsumptionRatioSensor(ctrl, name),
        AutarkyRateSensor(ctrl, name),

        # === FINANZEN ===
        SavingsSelfConsumptionSensor(ctrl, name),
        EarningsFeedInSensor(ctrl, name),

        # === STATISTIK ===
        AverageDailySavingsSensor(ctrl, name),
        AverageMonthlySavingsSensor(ctrl, name),
        AverageYearlySavingsSensor(ctrl, name),
        DaysSinceInstallationSensor(ctrl, name),

        # === UMWELT ===
        CO2SavedSensor(ctrl, name),

        # === DIAGNOSE ===
        FixedPriceSensor(ctrl, name),
        CurrentFeedInTariffSensor(ctrl, name),
        PVProductionSensor(ctrl, name),
        InstallationCostSensor(ctrl, name),
        ConfigurationDiagnosticSensor(ctrl, name, entry),

        # === STROMPREIS-VERGLEICH (Spot vs Fixpreis) ===
        TotalGridImportCostSensor(ctrl, name),
        FixedVsSpotSensor(ctrl, name),
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
        device_type: str = DEVICE_MAIN,
    ):
        self.ctrl = ctrl
        self._base_name = name
        self._attr_name = f"{name} {key}"
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_{key.lower().replace(' ', '_')}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_device_info = get_device_info(name, device_type)
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
    """Gesamtersparnis in Euro - persistiert Daten."""

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
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            attrs = last_state.attributes or {}

            def safe_float(val, default=0.0):
                try:
                    return float(val) if val is not None else default
                except (ValueError, TypeError):
                    return default

            restore_data = {
                "total_self_consumption_kwh": safe_float(attrs.get("tracked_self_consumption_kwh")),
                "total_feed_in_kwh": safe_float(attrs.get("tracked_feed_in_kwh")),
                "accumulated_savings_self": safe_float(attrs.get("accumulated_savings_self")),
                "accumulated_earnings_feed": safe_float(attrs.get("accumulated_earnings_feed")),
                "first_seen_date": attrs.get("first_seen_date"),
                "tracked_grid_import_kwh": safe_float(attrs.get("tracked_grid_import_kwh")),
                "total_grid_import_cost": safe_float(attrs.get("total_grid_import_cost")),
            }

            _LOGGER.info(
                "TotalSavingsSensor: Restore data: self=%.2f kWh, feed=%.2f kWh",
                restore_data["total_self_consumption_kwh"],
                restore_data["total_feed_in_kwh"],
            )

            self.ctrl.restore_state(restore_data)
            self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self.ctrl.total_savings, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "savings_self_consumption": f"{self.ctrl.savings_self_consumption:.2f}€",
            "earnings_feed_in": f"{self.ctrl.earnings_feed_in:.2f}€",
            "tracked_self_consumption_kwh": round(self.ctrl._total_self_consumption_kwh, 4),
            "tracked_feed_in_kwh": round(self.ctrl._total_feed_in_kwh, 4),
            "accumulated_savings_self": round(self.ctrl._accumulated_savings_self, 4),
            "accumulated_earnings_feed": round(self.ctrl._accumulated_earnings_feed, 4),
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            "tracked_grid_import_kwh": round(self.ctrl._tracked_grid_import_kwh, 4),
            "total_grid_import_cost": round(self.ctrl._total_grid_import_cost, 4),
            "calculation_method": "incremental (fixed price)",
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
            state_class=None,
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
    """Eigenverbrauch in kWh."""

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


class FeedInSensor(BaseEntity):
    """Netzeinspeisung in kWh."""

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


class PVProductionSensor(BaseEntity):
    """PV-Produktion in kWh."""

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
    """Ersparnis durch Eigenverbrauch."""

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
            "fixed_price": f"{self.ctrl.fixed_price_ct:.2f} ct/kWh",
            "calculation": "Eigenverbrauch × Fixpreis",
        }


class EarningsFeedInSensor(BaseEntity):
    """Einnahmen durch Einspeisung."""

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
    def native_value(self) -> float | None:
        rate = self.ctrl.autarky_rate
        if rate is None:
            return None
        return round(rate, 1)


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


class FixedPriceSensor(BaseEntity):
    """Konfigurierter Fixpreis."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Fixpreis",
            unit="ct/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.fixed_price_ct, 2)


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
    """Diagnose-Sensor zeigt alle konfigurierten Sensoren."""

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
            return {"configured": True, "entity_id": entity_id, "state": None, "status": "nicht gefunden"}
        elif state.state in ("unavailable", "unknown"):
            return {"configured": True, "entity_id": entity_id, "state": state.state, "status": "nicht verfügbar"}
        else:
            return {"configured": True, "entity_id": entity_id, "state": state.state, "status": "OK"}

    @property
    def native_value(self) -> str:
        """Zeigt Gesamtstatus der Konfiguration."""
        issues = 0
        for entity_id in [self.ctrl.pv_production_entity, self.ctrl.grid_export_entity]:
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
        pv_status = self._get_entity_status(self.ctrl.pv_production_entity)
        export_status = self._get_entity_status(self.ctrl.grid_export_entity)
        import_status = self._get_entity_status(self.ctrl.grid_import_entity)
        consumption_status = self._get_entity_status(self.ctrl.consumption_entity)
        epex_status = self._get_entity_status(self.ctrl.epex_price_entity)

        return {
            "pv_production_entity": pv_status["entity_id"],
            "pv_production_status": pv_status["status"],
            "grid_export_entity": export_status["entity_id"],
            "grid_export_status": export_status["status"],
            "grid_import_entity": import_status["entity_id"],
            "grid_import_status": import_status["status"],
            "consumption_entity": consumption_status["entity_id"],
            "consumption_status": consumption_status["status"],
            "epex_price_entity": epex_status["entity_id"],
            "epex_price_status": epex_status["status"],
            "fixed_price_ct": f"{self.ctrl.fixed_price_ct:.2f}",
            "feed_in_tariff_eur": f"{self.ctrl.current_feed_in_tariff:.4f}",
            "tracked_self_consumption_kwh": round(self.ctrl._total_self_consumption_kwh, 4),
            "tracked_feed_in_kwh": round(self.ctrl._total_feed_in_kwh, 4),
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            "days_tracked": self.ctrl.days_since_installation,
            "has_epex_integration": self.ctrl.has_epex_integration,
        }

    @property
    def icon(self) -> str:
        if self.native_value == "OK":
            return "mdi:check-circle"
        else:
            return "mdi:alert-circle"


# =============================================================================
# SPOT VS FIXPREIS VERGLEICH
# =============================================================================


class TotalGridImportCostSensor(BaseEntity):
    """Gesamtkosten für Netzbezug (Spot-Preis Tracking)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Netzbezug Kosten (Spot)",
            unit="€",
            icon="mdi:cash-minus",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.total_grid_import_cost, 2)

    @property
    def extra_state_attributes(self) -> dict:
        avg = self.ctrl.average_electricity_price_ct
        return {
            "verbrauch_kwh": round(self.ctrl.tracked_grid_import_kwh, 2),
            "durchschnittspreis_ct": f"{avg:.2f}" if avg else None,
            "hinweis": "Kosten wenn Spot-Tarif" if self.ctrl.has_epex_integration else "Gleich wie Fixpreis",
        }


class FixedVsSpotSensor(BaseEntity):
    """
    Vergleich Fixpreis vs. Spot-Tarif.

    Positiv = Fixpreis günstiger, Negativ = Spot wäre günstiger.
    """

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Fixpreis vs Spot",
            unit="€",
            icon="mdi:scale-balance",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float | None:
        savings = self.ctrl.spot_vs_fixed_savings
        if savings is None:
            return None
        return round(savings, 2)

    @property
    def icon(self) -> str:
        savings = self.ctrl.spot_vs_fixed_savings
        if savings is None:
            return "mdi:scale-balance"
        elif savings > 0:
            return "mdi:thumb-up"  # Fixpreis günstiger
        elif savings < 0:
            return "mdi:thumb-down"  # Spot wäre günstiger
        return "mdi:scale-balance"

    @property
    def extra_state_attributes(self) -> dict:
        fixed_ct = self.ctrl.fixed_price_ct
        avg_spot_ct = self.ctrl.average_electricity_price_ct
        savings = self.ctrl.spot_vs_fixed_savings
        kwh = self.ctrl.tracked_grid_import_kwh

        attrs = {
            "fixpreis_ct": round(fixed_ct, 2),
            "spot_durchschnitt_ct": round(avg_spot_ct, 2) if avg_spot_ct else None,
            "verbrauch_kwh": round(kwh, 2),
        }

        if avg_spot_ct and kwh > 0:
            fixed_cost = kwh * (fixed_ct / 100)
            spot_cost = self.ctrl.total_grid_import_cost
            attrs["fixpreis_kosten_eur"] = round(fixed_cost, 2)
            attrs["spot_kosten_eur"] = round(spot_cost, 2)
            attrs["differenz_pro_kwh_ct"] = round(avg_spot_ct - fixed_ct, 2) if avg_spot_ct else None

            if savings and savings > 0:
                attrs["fazit"] = f"Fixpreis {abs(savings):.2f}€ günstiger"
            elif savings and savings < 0:
                attrs["fazit"] = f"Spot wäre {abs(savings):.2f}€ günstiger"
            else:
                attrs["fazit"] = "Etwa gleich"

        if not self.ctrl.has_epex_integration:
            attrs["hinweis"] = "Kein EPEX Sensor konfiguriert - Vergleich nicht möglich"

        return attrs
