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
DEVICE_QUOTA = "quota"
DEVICE_BATTERY = "battery"
DEVICE_BENCHMARK = "benchmark"
DEVICE_PV_STRINGS = "pv_strings"


def get_device_info(name: str, device_type: str = DEVICE_MAIN) -> DeviceInfo:
    """Erstellt DeviceInfo für verschiedene Geräte-Typen."""
    if device_type == DEVICE_PRICES or device_type == DEVICE_QUOTA:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_prices")},
            name=f"{name} Strom & Kosten",
            manufacturer="Custom",
            model="PV Management Fixpreis - Strom & Kosten",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_BATTERY:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_battery")},
            name=f"{name} Batterie",
            manufacturer="Custom",
            model="PV Management Fixpreis - Batterie",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_BENCHMARK:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_benchmark")},
            name=f"{name} Energie-Benchmark",
            manufacturer="Custom",
            model="PV Energy Management+ - Energie-Benchmark",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_PV_STRINGS:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_pv_strings")},
            name=f"{name} PV-Strings",
            manufacturer="Custom",
            model="PV Management Fixpreis - PV-Strings",
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
        GrossPriceSensor(ctrl, name),  # EUR/kWh für Energy Dashboard
        CurrentFeedInTariffSensor(ctrl, name),
        PVProductionSensor(ctrl, name),
        InstallationCostSensor(ctrl, name),
        ConfigurationDiagnosticSensor(ctrl, name, entry),

        # === TÄGLICHE STROMKOSTEN ===
        DailyFeedInSensor(ctrl, name),
        DailyGridImportSensor(ctrl, name),
        DailyNetElectricityCostSensor(ctrl, name),

        # === ROI ===
        ROISensor(ctrl, name),
        AnnualROISensor(ctrl, name),
    ]

    # === STROMKONTINGENT (nur wenn aktiviert) ===
    if ctrl.quota_enabled:
        entities.extend([
            QuotaRemainingSensor(ctrl, name),
            QuotaConsumedPercentSensor(ctrl, name),
            QuotaDailyBudgetSensor(ctrl, name),
            QuotaForecastSensor(ctrl, name),
            QuotaDaysRemainingSensor(ctrl, name),
            QuotaTodayRemainingSensor(ctrl, name),
            QuotaStatusSensor(ctrl, name),
        ])

    # === BENCHMARK (nur wenn aktiviert) ===
    if ctrl.benchmark_enabled:
        entities.extend([
            BenchmarkAvgSensor(ctrl, name),
            BenchmarkOwnSensor(ctrl, name),
            BenchmarkGridImportSensor(ctrl, name),
            BenchmarkAnnualPVSensor(ctrl, name),
            BenchmarkComparisonSensor(ctrl, name),
            BenchmarkCO2Sensor(ctrl, name),
            BenchmarkScoreSensor(ctrl, name),
            BenchmarkRatingSensor(ctrl, name),
        ])
        # Spezifischer Ertrag nur wenn PV-Strings konfiguriert (für Peak-Summe)
        if ctrl.pv_strings:
            entities.append(BenchmarkSpecificYieldSensor(ctrl, name))
        if ctrl.benchmark_heatpump:
            entities.extend([
                BenchmarkHeatpumpAvgSensor(ctrl, name),
                BenchmarkHeatpumpOwnSensor(ctrl, name),
                BenchmarkHeatpumpComparisonSensor(ctrl, name),
                BenchmarkHouseholdSensor(ctrl, name),
            ])

    # === BATTERIE (nur wenn mindestens ein Entity konfiguriert) ===
    if ctrl.battery_soc_entity or ctrl.battery_charge_entity or ctrl.battery_discharge_entity:
        entities.extend([
            BatterySOCSensor(ctrl, name),
            BatteryChargeTotalSensor(ctrl, name),
            BatteryDischargeTotalSensor(ctrl, name),
            BatteryEfficiencySensor(ctrl, name),
            BatteryCyclesSensor(ctrl, name),
        ])

    # === PV-STRINGS (optional) ===
    if ctrl.pv_strings:
        for i, (string_name, string_entity, power_entity, installed_kwp) in enumerate(ctrl.pv_strings):
            entities.extend([
                PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "production"),
                PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "daily"),
                PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "percentage"),
            ])
            if power_entity:
                entities.extend([
                    PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "peak"),
                    PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "daily_peak"),
                ])
            # Spezifischer Ertrag + Performance Ratio (braucht kWp oder Power-Entity)
            if installed_kwp > 0 or power_entity:
                entities.append(PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "specific_yield"))
            if power_entity and installed_kwp > 0:
                entities.append(PVStringSensor(ctrl, name, i, string_name, string_entity, power_entity, installed_kwp, "performance_ratio"))
        entities.append(TotalDailyProductionSensor(ctrl, name))
        if any(p for _, _, p, _ in ctrl.pv_strings):
            entities.append(TotalPeakSensor(ctrl, name))
            entities.append(TotalDailyPeakSensor(ctrl, name))

    async_add_entities(entities)


class BaseEntity(SensorEntity):
    """Basis-Klasse für alle Sensoren."""

    _attr_should_poll = False
    _attr_has_entity_name = True

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
        self._attr_name = key
        uid_name = "".join(c if c.isalnum() else "_" for c in name).lower()
        self._attr_unique_id = f"{DOMAIN}_{uid_name}_{key.lower().replace(' ', '_')}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        self._attr_device_info = get_device_info(name, device_type)
        self._removed = False

    @property
    def available(self) -> bool:
        """Sensor ist erst verfügbar wenn gespeicherte Daten wiederhergestellt sind."""
        return getattr(self.ctrl, "_restored", True)

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


class PVStringSensor(BaseEntity):
    """Generischer Sensor für PV-String Vergleich."""

    def __init__(self, ctrl, name: str, string_index: int, string_name: str, entity_id: str, power_entity_id: str | None, installed_kwp: float, sensor_type: str):
        self._string_entity_id = entity_id
        self._power_entity_id = power_entity_id
        self._installed_kwp = installed_kwp
        self._sensor_type = sensor_type

        uid_suffix_map = {
            "production": "Produktion",
            "daily": "Tagesproduktion",
            "peak": "Peak",
            "daily_peak": "Peak Heute",
            "percentage": "Anteil",
            "specific_yield": "Spez. Ertrag",
            "performance_ratio": "Performance Ratio",
        }
        props_map = {
            "production": ("kWh", "mdi:solar-panel", SensorStateClass.TOTAL_INCREASING),
            "daily": ("kWh/Tag", "mdi:weather-sunny", SensorStateClass.MEASUREMENT),
            "peak": ("kW", "mdi:solar-power-variant", SensorStateClass.MEASUREMENT),
            "daily_peak": ("kW", "mdi:solar-power-variant-outline", SensorStateClass.MEASUREMENT),
            "percentage": ("%", "mdi:chart-pie", SensorStateClass.MEASUREMENT),
            "specific_yield": ("kWh/kWp", "mdi:solar-power-variant-outline", SensorStateClass.MEASUREMENT),
            "performance_ratio": ("%", "mdi:gauge", SensorStateClass.MEASUREMENT),
        }
        uid_suffix = uid_suffix_map[sensor_type]
        unit, icon, state_class = props_map[sensor_type]
        key = f"{string_name} {uid_suffix}"

        super().__init__(ctrl, name, key, unit=unit, icon=icon, state_class=state_class, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        if self._sensor_type == "production":
            val = self.ctrl.get_string_production_kwh(self._string_entity_id)
            return round(val, 2) if val else 0.0
        elif self._sensor_type == "daily":
            val = self.ctrl.get_string_daily_kwh(self._string_entity_id)
            return round(val, 2) if val is not None else None
        elif self._sensor_type == "peak":
            val = self.ctrl.get_string_peak_kw(self._power_entity_id)
            return val
        elif self._sensor_type == "daily_peak":
            val = self.ctrl.get_string_daily_peak_kw(self._power_entity_id)
            return val
        elif self._sensor_type == "specific_yield":
            # Fallback: installierte kWp → gemessener Peak
            kwp = self._installed_kwp
            if kwp <= 0 and self._power_entity_id:
                peak_kw = self.ctrl.get_string_peak_kw(self._power_entity_id)
                kwp = peak_kw if peak_kw else 0.0
            return self.ctrl.get_string_specific_yield(self._string_entity_id, kwp)
        elif self._sensor_type == "performance_ratio":
            return self.ctrl.get_string_performance_ratio(self._power_entity_id, self._installed_kwp)
        else:  # percentage
            val = self.ctrl.get_string_percentage(self._string_entity_id)
            return round(val, 1) if val is not None else None


class TotalDailyProductionSensor(BaseEntity):
    """Durchschnittliche Tagesproduktion aller PV-Strings."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamt Tagesproduktion", unit="kWh/Tag", icon="mdi:weather-sunny",
                         state_class=SensorStateClass.MEASUREMENT, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        return self.ctrl.get_total_daily_production_kwh()


class TotalPeakSensor(BaseEntity):
    """Gesamt-Peak aller PV-Strings."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamt Peak", unit="kW", icon="mdi:solar-power-variant",
                         state_class=SensorStateClass.MEASUREMENT, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        return self.ctrl.get_total_peak_kw()


class TotalDailyPeakSensor(BaseEntity):
    """Gesamt-Peak heute aller PV-Strings."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamt Peak Heute", unit="kW", icon="mdi:solar-power-variant-outline",
                         state_class=SensorStateClass.MEASUREMENT, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        return self.ctrl.get_total_daily_peak_kw()


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
                # WP Delta-Tracking
                "tracked_wp_kwh": safe_float(attrs.get("tracked_wp_kwh")),
                "wp_first_seen_date": attrs.get("wp_first_seen_date"),
                # PV-String Delta-Tracking
                "string_tracked_kwh": attrs.get("string_tracked_kwh", {}),
                "string_first_seen_date": attrs.get("string_first_seen_date"),
                "string_peak_w": attrs.get("string_peak_w", {}),
                # Daily tracking
                "daily_grid_import_kwh": safe_float(attrs.get("daily_grid_import_kwh")),
                "daily_grid_import_cost": safe_float(attrs.get("daily_grid_import_cost")),
                "daily_feed_in_earnings": safe_float(attrs.get("daily_feed_in_earnings")),
                "daily_feed_in_kwh": safe_float(attrs.get("daily_feed_in_kwh")),
                "daily_reset_date": attrs.get("daily_reset_date"),
                "quota_day_start_meter": safe_float(attrs.get("quota_day_start_meter")),
                # Monthly tracking
                "monthly_grid_import_kwh": safe_float(attrs.get("monthly_grid_import_kwh")),
                "monthly_grid_import_cost": safe_float(attrs.get("monthly_grid_import_cost")),
                "monthly_reset_month": attrs.get("monthly_reset_month"),
                "monthly_reset_year": attrs.get("monthly_reset_year"),
                # Benchmark Snapshot
                "benchmark_start_date": attrs.get("benchmark_start_date"),
                "benchmark_start_self_consumption": safe_float(attrs.get("benchmark_start_self_consumption")),
                "benchmark_start_grid_import": safe_float(attrs.get("benchmark_start_grid_import")),
                "benchmark_start_feed_in": safe_float(attrs.get("benchmark_start_feed_in")),
                "monthly_buckets": attrs.get("monthly_buckets", {}),
                "monthly_bucket_month": attrs.get("monthly_bucket_month"),
            }

            _LOGGER.info(
                "TotalSavingsSensor: Restore data: self=%.2f kWh, feed=%.2f kWh, wp=%.2f kWh",
                restore_data["total_self_consumption_kwh"],
                restore_data["total_feed_in_kwh"],
                restore_data["tracked_wp_kwh"],
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
            # WP Delta-Tracking (persistent)
            "tracked_wp_kwh": round(self.ctrl._tracked_wp_kwh, 4),
            "wp_first_seen_date": self.ctrl._wp_first_seen_date.isoformat() if self.ctrl._wp_first_seen_date else None,
            # PV-String Delta-Tracking (persistent)
            "string_tracked_kwh": self.ctrl._string_tracked_kwh,
            "string_first_seen_date": self.ctrl._string_first_seen_date.isoformat() if self.ctrl._string_first_seen_date else None,
            "string_peak_w": self.ctrl._string_peak_w,
            "string_daily_peak_w": self.ctrl._string_daily_peak_w,
            "string_daily_peak_date": self.ctrl._string_daily_peak_date.isoformat() if self.ctrl._string_daily_peak_date else None,
            # Daily tracking
            "daily_grid_import_kwh": round(self.ctrl._daily_grid_import_kwh, 4),
            "daily_grid_import_cost": round(self.ctrl._daily_grid_import_cost, 4),
            "daily_feed_in_earnings": round(self.ctrl._daily_feed_in_earnings, 4),
            "daily_feed_in_kwh": round(self.ctrl._daily_feed_in_kwh, 4),
            "daily_reset_date": date.today().isoformat(),
            "quota_day_start_meter": self.ctrl._quota_day_start_meter,
            # Monthly tracking
            "monthly_grid_import_kwh": round(self.ctrl._monthly_grid_import_kwh, 4),
            "monthly_grid_import_cost": round(self.ctrl._monthly_grid_import_cost, 4),
            "monthly_reset_month": date.today().month,
            "monthly_reset_year": date.today().year,
            # Benchmark Snapshot
            "benchmark_start_date": self.ctrl._benchmark_start_date.isoformat() if self.ctrl._benchmark_start_date else None,
            "benchmark_start_self_consumption": round(self.ctrl._benchmark_start_self_consumption, 4),
            "benchmark_start_grid_import": round(self.ctrl._benchmark_start_grid_import, 4),
            "benchmark_start_feed_in": round(self.ctrl._benchmark_start_feed_in, 4),
            "monthly_buckets": {str(k): v for k, v in self.ctrl._monthly_buckets.items()},
            "monthly_bucket_month": self.ctrl._monthly_bucket_month,
            "calculation_method": "incremental (fixed price)",
        }


class RemainingCostSensor(BaseEntity):
    """Verbleibender Betrag bis Amortisation."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Amort Restbetrag",
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
            "Amort Status",
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
            "Amort Ersparnis/Tag",
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
            "Amort Ersparnis/Monat",
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
            "Amort Ersparnis/Jahr",
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
            "Amort Tage",
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
            "Amort Restlaufzeit",
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
            "Amort Datum",
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
            "Preis Fix",
            unit="ct/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.fixed_price_ct, 2)


class GrossPriceSensor(BaseEntity):
    """Brutto-Strompreis für Energy Dashboard (EUR/kWh)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Preis Brutto",
            unit="EUR/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.gross_price, 4)


class CurrentFeedInTariffSensor(BaseEntity):
    """Aktuelle Einspeisevergütung."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Preis Einspeisung",
            unit="€/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_type=DEVICE_PRICES,
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
            "Amort Kosten",
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

        return {
            "pv_production_entity": pv_status["entity_id"],
            "pv_production_status": pv_status["status"],
            "grid_export_entity": export_status["entity_id"],
            "grid_export_status": export_status["status"],
            "grid_import_entity": import_status["entity_id"],
            "grid_import_status": import_status["status"],
            "consumption_entity": consumption_status["entity_id"],
            "consumption_status": consumption_status["status"],
            "fixed_price_ct": f"{self.ctrl.fixed_price_ct:.2f}",
            "feed_in_tariff_eur": f"{self.ctrl.current_feed_in_tariff:.4f}",
            "tracked_self_consumption_kwh": round(self.ctrl._total_self_consumption_kwh, 4),
            "tracked_feed_in_kwh": round(self.ctrl._total_feed_in_kwh, 4),
            "first_seen_date": self.ctrl._first_seen_date.isoformat() if self.ctrl._first_seen_date else None,
            "days_tracked": self.ctrl.days_since_installation,
        }

    @property
    def icon(self) -> str:
        if self.native_value == "OK":
            return "mdi:check-circle"
        else:
            return "mdi:alert-circle"


# =============================================================================
# TÄGLICHE STROMKOSTEN
# =============================================================================


class DailyFeedInSensor(BaseEntity):
    """Einspeisung heute: Vergütung und Menge."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Tages Einspeisung",
            unit="€",
            icon="mdi:transmission-tower-export",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.daily_feed_in_earnings, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "menge_kwh": round(self.ctrl.daily_feed_in_kwh, 2),
            "vergütung_ct": f"{self.ctrl.current_feed_in_tariff * 100:.2f}",
        }


class DailyGridImportSensor(BaseEntity):
    """Netzbezug heute: Kosten und Verbrauch."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Tages Netzbezug",
            unit="€",
            icon="mdi:transmission-tower-import",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.daily_grid_import_cost, 2)

    @property
    def extra_state_attributes(self) -> dict:
        avg = self.ctrl.daily_average_price_ct
        return {
            "verbrauch_kwh": round(self.ctrl.daily_grid_import_kwh, 2),
            "durchschnitt_ct": round(avg, 2) if avg else None,
        }


class DailyNetElectricityCostSensor(BaseEntity):
    """Netto-Stromkosten heute: Netzbezug minus Einspeisung."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Tages Stromkosten",
            unit="€",
            icon="mdi:cash-register",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.MONETARY,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.daily_net_electricity_cost, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "netzbezug_eur": round(self.ctrl.daily_grid_import_cost, 2),
            "einspeisung_eur": round(self.ctrl.daily_feed_in_earnings, 2),
        }


# =============================================================================
# STROMKONTINGENT SENSOREN
# =============================================================================


class QuotaRemainingSensor(BaseEntity):
    """Kontingent Verbleibend - Hauptsensor: wieviel kWh noch übrig."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Kontingent Verbleibend",
            unit="kWh",
            icon="mdi:lightning-bolt",
            device_type=DEVICE_QUOTA,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.quota_remaining_kwh, 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "jahres_kontingent_kwh": self.ctrl.quota_yearly_kwh,
            "verbraucht_kwh": round(self.ctrl.quota_consumed_kwh, 1),
            "abschlag_eur": self.ctrl.quota_monthly_rate if self.ctrl.quota_monthly_rate > 0 else None,
        }


class QuotaConsumedPercentSensor(BaseEntity):
    """Kontingent Verbrauch - Prozent des Jahres-Kontingents verbraucht."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Kontingent Verbrauch",
            unit="%",
            icon="mdi:gauge",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_QUOTA,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.quota_consumed_percent, 1)


class QuotaReserveSensor(BaseEntity):
    """Kontingent Reserve - positiv = unter Budget, negativ = drüber."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Kontingent Reserve",
            unit="kWh",
            icon="mdi:shield-check",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_QUOTA,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.quota_reserve_kwh, 1)

    @property
    def icon(self) -> str:
        reserve = self.ctrl.quota_reserve_kwh
        if reserve >= 0:
            return "mdi:shield-check"
        return "mdi:shield-alert"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "soll_verbrauch_kwh": round(self.ctrl.quota_expected_kwh, 1),
            "ist_verbrauch_kwh": round(self.ctrl.quota_consumed_kwh, 1),
        }


class QuotaDailyBudgetSensor(BaseEntity):
    """Kontingent Tagesbudget - wieviel pro Tag noch verbrauchen darf."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Kontingent Tagesbudget",
            unit="kWh/Tag",
            icon="mdi:calendar-today",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_QUOTA,
        )

    @property
    def native_value(self) -> float | None:
        budget = self.ctrl.quota_daily_budget_kwh
        if budget is None:
            return None
        return round(budget, 1)


class QuotaForecastSensor(BaseEntity):
    """Kontingent Prognose - Hochrechnung Verbrauch am Periodenende."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Kontingent Prognose",
            unit="kWh",
            icon="mdi:crystal-ball",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_QUOTA,
        )

    @property
    def native_value(self) -> float | None:
        forecast = self.ctrl.quota_forecast_kwh
        if forecast is None:
            return None
        return round(forecast, 0)

    @property
    def icon(self) -> str:
        forecast = self.ctrl.quota_forecast_kwh
        if forecast is None:
            return "mdi:crystal-ball"
        if forecast <= self.ctrl.quota_yearly_kwh:
            return "mdi:trending-down"
        return "mdi:trending-up"

    @property
    def extra_state_attributes(self) -> dict:
        forecast = self.ctrl.quota_forecast_kwh
        attrs = {
            "kontingent_kwh": self.ctrl.quota_yearly_kwh,
        }
        if forecast is not None:
            diff = forecast - self.ctrl.quota_yearly_kwh
            attrs["prognose_differenz_kwh"] = round(diff, 0)
            if diff > 0:
                attrs["bewertung"] = f"Voraussichtlich {diff:.0f} kWh über Kontingent"
            else:
                attrs["bewertung"] = f"Voraussichtlich {abs(diff):.0f} kWh unter Kontingent"
        return attrs


class QuotaDaysRemainingSensor(BaseEntity):
    """Kontingent Restlaufzeit - verbleibende Tage in der Periode."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Kontingent Restlaufzeit",
            unit="Tage",
            icon="mdi:calendar-clock",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_QUOTA,
        )

    @property
    def native_value(self) -> int:
        return self.ctrl.quota_days_remaining

    @property
    def extra_state_attributes(self) -> dict:
        start = self.ctrl.quota_start_date
        end = self.ctrl.quota_end_date
        return {
            "perioden_start": start.isoformat() if start else None,
            "perioden_ende": end.isoformat() if end else None,
            "tage_vergangen": self.ctrl.quota_days_elapsed,
            "tage_gesamt": self.ctrl.quota_days_total,
        }


class QuotaTodayRemainingSensor(BaseEntity):
    """Kontingent Heute Verbleibend — wieviel darf ich heute noch verbrauchen."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Kontingent Heute Verbleibend",
            unit="kWh",
            icon="mdi:clock-check",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_QUOTA,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.quota_today_remaining_kwh
        if val is None:
            return None
        return round(val, 1)

    @property
    def icon(self) -> str:
        val = self.ctrl.quota_today_remaining_kwh
        if val is None:
            return "mdi:clock-check"
        if val >= 0:
            return "mdi:clock-check"
        return "mdi:clock-alert"

    @property
    def extra_state_attributes(self) -> dict:
        budget = self.ctrl.quota_daily_budget_kwh
        return {
            "tagesbudget_kwh": round(budget, 1) if budget is not None else None,
            "heute_verbraucht_kwh": round(self.ctrl.daily_grid_import_kwh, 1),
        }


class QuotaStatusSensor(BaseEntity):
    """Kontingent Status - Textuelle Zusammenfassung."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Kontingent Status",
            icon="mdi:text-box-check",
            device_type=DEVICE_QUOTA,
        )

    @property
    def native_value(self) -> str:
        return self.ctrl.quota_status_text

    @property
    def icon(self) -> str:
        reserve = self.ctrl.quota_reserve_kwh
        if reserve >= 0:
            return "mdi:text-box-check"
        return "mdi:text-box-remove"

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {
            "verbraucht_kwh": round(self.ctrl.quota_consumed_kwh, 1),
            "verbleibend_kwh": round(self.ctrl.quota_remaining_kwh, 1),
            "reserve_kwh": round(self.ctrl.quota_reserve_kwh, 1),
            "verbrauch_prozent": round(self.ctrl.quota_consumed_percent, 1),
        }
        forecast = self.ctrl.quota_forecast_kwh
        if forecast is not None:
            attrs["prognose_kwh"] = round(forecast, 0)
        budget = self.ctrl.quota_daily_budget_kwh
        if budget is not None:
            attrs["tagesbudget_kwh"] = round(budget, 1)
        if self.ctrl.quota_monthly_rate > 0:
            attrs["monatlicher_abschlag_eur"] = self.ctrl.quota_monthly_rate
        return attrs


# =============================================================================
# BATTERIE-SENSOREN
# =============================================================================


class BatterySOCSensor(BaseEntity):
    """Batterie Ladestand."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ladestand",
            unit="%",
            icon="mdi:battery-50",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> float | None:
        soc = self.ctrl.battery_soc
        if soc is None:
            return None
        return round(soc, 1)

    @property
    def icon(self) -> str:
        soc = self.ctrl.battery_soc
        if soc is None:
            return "mdi:battery-unknown"
        if soc >= 95:
            return "mdi:battery"
        elif soc >= 85:
            return "mdi:battery-90"
        elif soc >= 75:
            return "mdi:battery-80"
        elif soc >= 65:
            return "mdi:battery-70"
        elif soc >= 55:
            return "mdi:battery-60"
        elif soc >= 45:
            return "mdi:battery-50"
        elif soc >= 35:
            return "mdi:battery-40"
        elif soc >= 25:
            return "mdi:battery-30"
        elif soc >= 15:
            return "mdi:battery-20"
        elif soc >= 5:
            return "mdi:battery-10"
        else:
            return "mdi:battery-outline"


class BatteryChargeTotalSensor(BaseEntity):
    """Batterie Ladung Gesamt."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Ladung Gesamt",
            unit="kWh",
            icon="mdi:battery-charging",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.ENERGY,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.battery_charge_total
        if val is None:
            return None
        return round(val, 2)


class BatteryDischargeTotalSensor(BaseEntity):
    """Batterie Entladung Gesamt."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Entladung Gesamt",
            unit="kWh",
            icon="mdi:battery-arrow-down",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.ENERGY,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.battery_discharge_total
        if val is None:
            return None
        return round(val, 2)


class BatteryEfficiencySensor(BaseEntity):
    """Batterie Effizienz."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Effizienz",
            unit="%",
            icon="mdi:battery-heart-variant",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.battery_efficiency
        if val is None:
            return None
        return round(val, 1)


class BatteryCyclesSensor(BaseEntity):
    """Batterie Zyklen (geschätzt)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Zyklen",
            unit="Zyklen",
            icon="mdi:battery-sync",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_type=DEVICE_BATTERY,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.battery_cycles_estimate
        if val is None:
            return None
        return round(val, 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "kapazitaet_kwh": self.ctrl.battery_capacity,
        }


# =============================================================================
# ROI-SENSOREN
# =============================================================================


class ROISensor(BaseEntity):
    """Return on Investment."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "ROI",
            unit="%",
            icon="mdi:chart-line",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.roi_percent
        if val is None:
            return None
        return round(val, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "amortisiert": self.ctrl.is_amortised,
            "gesamtersparnis_eur": round(self.ctrl.total_savings, 2),
            "anschaffungskosten_eur": round(self.ctrl.installation_cost, 2),
        }


class AnnualROISensor(BaseEntity):
    """Jährlicher ROI."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "ROI pro Jahr",
            unit="%/Jahr",
            icon="mdi:chart-timeline-variant",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.annual_roi_percent
        if val is None:
            return None
        return round(val, 2)


# =============================================================================
# BENCHMARK-SENSOREN
# =============================================================================


MONTH_NAMES_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                  "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


class BenchmarkAvgSensor(BaseEntity):
    """Benchmark Durchschnitt — Referenzverbrauch Haushaltsstrom."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Haus Durchschnitt",
            unit="kWh/Jahr",
            icon="mdi:home-group",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> int:
        return self.ctrl.benchmark_avg_consumption_kwh


class BenchmarkOwnSensor(BaseEntity):
    """Benchmark Gesamtverbrauch — inkl. WP, hochgerechnet auf 1 Jahr."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Gesamtverbrauch",
            unit="kWh/Jahr",
            icon="mdi:home-lightning-bolt",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_own_annual_consumption_kwh
        if val is None:
            return None
        return round(val, 0)

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            "calculation": "buckets" if len(self.ctrl._monthly_buckets) >= 12 else "extrapolation",
            "buckets_filled": len(self.ctrl._monthly_buckets),
        }
        for m in range(1, 13):
            name = MONTH_NAMES_DE[m - 1].lower()
            bucket = self.ctrl._monthly_buckets.get(m)
            if bucket is not None:
                attrs[f"{name}_consumption_kwh"] = round(
                    bucket.get("self_consumption", 0.0) + bucket.get("grid_import", 0.0), 1
                )
                attrs[f"{name}_feed_in_kwh"] = round(bucket.get("feed_in", 0.0), 1)
                attrs[f"{name}_wp_kwh"] = round(bucket.get("wp", 0.0), 1)
        return attrs


class BenchmarkHouseholdSensor(BaseEntity):
    """Haushaltsverbrauch ohne WP, hochgerechnet auf 1 Jahr."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Haus Verbrauch",
            unit="kWh/Jahr",
            icon="mdi:home-lightning-bolt-outline",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_household_consumption_kwh
        if val is None:
            return None
        return round(val, 0)


class BenchmarkGridImportSensor(BaseEntity):
    """Jährlicher Netzbezug hochgerechnet."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Netz Bezug",
            unit="kWh/Jahr",
            icon="mdi:transmission-tower-import",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_annual_grid_import_kwh
        if val is None:
            return None
        return round(val, 0)


class BenchmarkAnnualPVSensor(BaseEntity):
    """Hochgerechnete PV-Jahresproduktion."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV Produktion",
            unit="kWh/Jahr",
            icon="mdi:solar-power",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_annual_pv_production_kwh
        if val is None:
            return None
        return round(val, 0)


class BenchmarkSpecificYieldSensor(BaseEntity):
    """Spezifischer Ertrag in kWh/kWp."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV Ertrag",
            unit="kWh/kWp",
            icon="mdi:solar-power-variant-outline",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_specific_yield
        if val is None:
            return None
        return round(val, 0)


class BenchmarkComparisonSensor(BaseEntity):
    """Benchmark Vergleich — Eigener vs. Durchschnitt in %."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Haus Vergleich",
            unit="%",
            icon="mdi:check-circle",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_consumption_vs_avg
        if val is None:
            return None
        return round(val, 1)

    @property
    def icon(self) -> str:
        val = self.ctrl.benchmark_consumption_vs_avg
        if val is None:
            return "mdi:check-circle"
        if val <= 0:
            return "mdi:check-circle"
        return "mdi:alert"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "country": self.ctrl.benchmark_country,
            "household_size": self.ctrl.benchmark_household_size,
            "reference_kwh": self.ctrl.benchmark_avg_consumption_kwh,
            "own_kwh": self.ctrl.benchmark_own_annual_consumption_kwh,
            "heatpump_excluded": bool(self.ctrl.benchmark_heatpump and self.ctrl.benchmark_heatpump_entity),
        }


class BenchmarkCO2Sensor(BaseEntity):
    """Benchmark CO2 Vermieden — CO2-Einsparung durch PV pro Jahr."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV CO2 Vermieden",
            unit="kg/Jahr",
            icon="mdi:molecule-co2",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_co2_avoided_kg
        if val is None:
            return None
        return round(val, 1)


class BenchmarkScoreSensor(BaseEntity):
    """Benchmark Effizienz Score — 0-100 Punkte."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Effizienz Score",
            unit="Punkte",
            icon="mdi:star-circle",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> int | None:
        return self.ctrl.benchmark_efficiency_score

    @property
    def extra_state_attributes(self) -> dict:
        autarky = self.ctrl.autarky_rate
        specific = self.ctrl.benchmark_specific_yield
        sc_ratio = self.ctrl.self_consumption_ratio
        comparison = self.ctrl.benchmark_consumption_vs_avg
        return {
            "autarkie_punkte": f"{min(35, autarky * 0.35):.1f}/35" if autarky is not None else "n/a",
            "spez_ertrag_punkte": f"{min(25, (specific / 900) * 25):.1f}/25" if specific and specific > 0 else "n/a",
            "eigenverbrauch_punkte": f"{min(20, sc_ratio * 0.2):.1f}/20" if sc_ratio is not None else "n/a",
            "verbrauch_punkte": f"{max(0, min(20, 10 - comparison * 0.2)):.1f}/20" if comparison is not None else "n/a",
        }

    @property
    def icon(self) -> str:
        score = self.ctrl.benchmark_efficiency_score
        if score is None:
            return "mdi:star-outline"
        if score >= 60:
            return "mdi:star-circle"
        if score >= 30:
            return "mdi:star-half-full"
        return "mdi:star-outline"


class BenchmarkRatingSensor(BaseEntity):
    """Benchmark Bewertung — Textuelle Bewertung."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Bewertung",
            icon="mdi:trophy",
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> str | None:
        return self.ctrl.benchmark_rating


class BenchmarkHeatpumpAvgSensor(BaseEntity):
    """Benchmark WP Durchschnitt — Referenz-WP-Verbrauch."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "WP Durchschnitt",
            unit="kWh/Jahr",
            icon="mdi:heat-pump",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> int | None:
        return self.ctrl.benchmark_avg_heatpump_kwh


class BenchmarkHeatpumpOwnSensor(BaseEntity):
    """Benchmark WP Verbrauch — Eigener WP-Verbrauch hochgerechnet."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "WP Verbrauch",
            unit="kWh/Jahr",
            icon="mdi:heat-pump-outline",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_own_heatpump_kwh
        if val is None:
            return None
        return round(val, 0)


class BenchmarkHeatpumpComparisonSensor(BaseEntity):
    """Benchmark WP Vergleich — WP-Verbrauch vs. WP-Durchschnitt in %."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "WP Vergleich",
            unit="%",
            icon="mdi:heat-pump",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_BENCHMARK,
        )

    @property
    def native_value(self) -> float | None:
        val = self.ctrl.benchmark_heatpump_vs_avg
        if val is None:
            return None
        return round(val, 1)
