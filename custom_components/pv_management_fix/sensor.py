from __future__ import annotations

import logging
from dataclasses import dataclass
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
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import DOMAIN, DATA_CTRL, CONF_NAME

_LOGGER = logging.getLogger(__name__)

# Device types
DEVICE_MAIN = "main"
DEVICE_PRICES = "prices"
DEVICE_QUOTA = "quota"
DEVICE_BATTERY = "battery"
DEVICE_BENCHMARK = "benchmark"
DEVICE_PV_STRINGS = "pv_strings"
DEVICE_FORECAST = "forecast"


def get_device_info(name: str, device_type: str = DEVICE_MAIN) -> DeviceInfo:
    """Create DeviceInfo for different device types."""
    if device_type == DEVICE_PRICES or device_type == DEVICE_QUOTA:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_prices")},
            name=f"{name} Electricity & Costs",
            manufacturer="Custom",
            model="PV Management Fixed Price - Electricity & Costs",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_BATTERY:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_battery")},
            name=f"{name} Battery",
            manufacturer="Custom",
            model="PV Management Fixed Price - Battery",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_BENCHMARK:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_benchmark")},
            name=f"{name} Energy Benchmark",
            manufacturer="Custom",
            model="PV Energy Management+ - Energy Benchmark",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_PV_STRINGS:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_pv_strings")},
            name=f"{name} PV Strings",
            manufacturer="Custom",
            model="PV Management Fixed Price - PV Strings",
            via_device=(DOMAIN, name),
        )
    elif device_type == DEVICE_FORECAST:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{name}_forecast")},
            name=f"{name} Load Forecast",
            manufacturer="Custom",
            model="PV Energy Management+ - Load Forecast",
            via_device=(DOMAIN, name),
        )
    else:  # DEVICE_MAIN
        return DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            manufacturer="Custom",
            model="PV Management Fixed Price",
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Setup sensors."""
    ctrl = hass.data[DOMAIN][entry.entry_id][DATA_CTRL]
    name = entry.data.get(CONF_NAME, "PV Fixpreis")

    entities = [
        # === AMORTISATION (Main purpose) ===
        AmortisationPercentSensor(ctrl, name),
        TotalSavingsSensor(ctrl, name),
        RemainingCostSensor(ctrl, name),
        StatusSensor(ctrl, name),
        EstimatedPaybackDateSensor(ctrl, name),
        EstimatedRemainingDaysSensor(ctrl, name),

        # === ENERGY (requires export sensor for meaningful values) ===
        SelfConsumptionRatioSensor(ctrl, name),
        AutarkyRateSensor(ctrl, name),

        # === STATISTICS ===
        AverageDailySavingsSensor(ctrl, name),
        AverageMonthlySavingsSensor(ctrl, name),
        AverageYearlySavingsSensor(ctrl, name),
        DaysSinceInstallationSensor(ctrl, name),

        # === ENVIRONMENT ===
        CO2SavedSensor(ctrl, name),

        # === DIAGNOSTICS ===
        FixedPriceSensor(ctrl, name),
        GrossPriceSensor(ctrl, name),  # EUR/kWh for Energy Dashboard
        CurrentFeedInTariffSensor(ctrl, name),
        PVProductionSensor(ctrl, name),
        InstallationCostSensor(ctrl, name),
        ConfigurationDiagnosticSensor(ctrl, name, entry),

        # === DAILY ELECTRICITY COSTS ===
        DailyNetElectricityCostSensor(ctrl, name),

        # === ROI ===
        ROISensor(ctrl, name),
        AnnualROISensor(ctrl, name),
    ]

    # === EXPORT-DEPENDENT SENSORS (only if grid export sensor configured) ===
    if ctrl.grid_export_entity:
        entities.extend([
            SelfConsumptionSensor(ctrl, name),
            FeedInSensor(ctrl, name),
            SavingsSelfConsumptionSensor(ctrl, name),
            EarningsFeedInSensor(ctrl, name),
            DailyFeedInSensor(ctrl, name),
        ])

    # === GRID-IMPORT-DEPENDENT SENSORS ===
    if ctrl.grid_import_entity:
        entities.append(DailyGridImportSensor(ctrl, name))

    # === ELECTRICITY QUOTA (only if enabled) ===
    if ctrl.quota_enabled:
        entities.extend([
            QuotaRemainingSensor(ctrl, name),
            QuotaConsumedPercentSensor(ctrl, name),
            QuotaDailyBudgetSensor(ctrl, name),
            QuotaForecastSensor(ctrl, name),
            QuotaDaysRemainingSensor(ctrl, name),
            QuotaTodayRemainingSensor(ctrl, name),
            QuotaReserveSensor(ctrl, name),
            QuotaStatusSensor(ctrl, name),
        ])

    # === BENCHMARK (only if enabled) ===
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
        # Specific yield only if PV strings configured (for peak sum)
        if ctrl.pv_strings:
            entities.append(BenchmarkSpecificYieldSensor(ctrl, name))
        if ctrl.benchmark_heatpump:
            entities.extend([
                BenchmarkHeatpumpAvgSensor(ctrl, name),
                BenchmarkHeatpumpOwnSensor(ctrl, name),
                BenchmarkHeatpumpComparisonSensor(ctrl, name),
                BenchmarkHouseholdSensor(ctrl, name),
            ])

    # === BATTERY (only if at least one entity is configured) ===
    if ctrl.battery_soc_entity or ctrl.battery_charge_entity or ctrl.battery_discharge_entity:
        entities.extend([
            BatterySOCSensor(ctrl, name),
            BatteryChargeTotalSensor(ctrl, name),
            BatteryDischargeTotalSensor(ctrl, name),
            BatteryEfficiencySensor(ctrl, name),
            BatteryCyclesSensor(ctrl, name),
        ])

    # === LOAD FORECAST (optional, 24x7 profile) ===
    if ctrl.forecast_enabled and ctrl.consumption_entity:
        entities.extend([
            LoadForecast1hSensor(ctrl, name),
            LoadForecast6hSensor(ctrl, name),
            LoadForecastTodayRestSensor(ctrl, name),
            LoadForecastTomorrowSensor(ctrl, name),
            LoadForecast24hSensor(ctrl, name),
        ])

    # === PV STRINGS (optional) ===
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
            # Specific yield + Performance Ratio (requires kWp or power entity)
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
    """Base class for all sensors."""

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
        self._attr_translation_key = key.lower().replace(' ', '_').replace('/', '_')
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
        """Sensor is only available once saved data has been restored."""
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
    """Generic sensor for PV string comparison."""

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
        self._attr_translation_key = None
        self._attr_name = key

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
            # Fallback: installed kWp -> measured peak
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
    """Average daily production of all PV strings."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamt Tagesproduktion", unit="kWh/Tag", icon="mdi:weather-sunny",
                         state_class=SensorStateClass.MEASUREMENT, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        return self.ctrl.get_total_daily_production_kwh()


class TotalPeakSensor(BaseEntity):
    """Total peak of all PV strings."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamt Peak", unit="kW", icon="mdi:solar-power-variant",
                         state_class=SensorStateClass.MEASUREMENT, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        return self.ctrl.get_total_peak_kw()


class TotalDailyPeakSensor(BaseEntity):
    """Total peak today of all PV strings."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Gesamt Peak Heute", unit="kW", icon="mdi:solar-power-variant-outline",
                         state_class=SensorStateClass.MEASUREMENT, device_type=DEVICE_PV_STRINGS)

    @property
    def native_value(self):
        return self.ctrl.get_total_daily_peak_kw()


# =============================================================================
# MAIN SENSORS
# =============================================================================


class AmortisationPercentSensor(BaseEntity):
    """Amortisation in percent - main indicator."""

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


@dataclass
class _PersistedTrackingData(ExtraStoredData):
    """Kumulative Tracking-Daten, die unabhängig vom Entity-State
    (auch bei "unavailable") von Home Assistant persistiert werden."""

    data: dict

    def as_dict(self) -> dict:
        return self.data


class TotalSavingsSensor(BaseEntity, RestoreEntity):
    """Total savings in Euro - persists data."""

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

        # Issue #9: Kumulative Werte aus extra_restore_state_data laden.
        # extra_state_attributes eines "unavailable" Sensors werden von HA
        # NICHT persistiert — extra_restore_state_data dagegen schon. Damit
        # überleben die Werte den Reboot auch wenn der Sensor durch die
        # _restored-Race kurzzeitig unavailable war.
        attrs: dict | None = None
        last_extra = await self.async_get_last_extra_data()
        if last_extra is not None:
            stored = last_extra.as_dict()
            if isinstance(stored, dict) and stored.get("tracked_self_consumption_kwh") is not None:
                attrs = stored

        # Fallback: attributbasierter Restore (Migration von Versionen < v2.0.9)
        if attrs is None:
            last_state = await self.async_get_last_state()
            if last_state and (last_state.attributes or {}).get("tracked_self_consumption_kwh") is not None:
                attrs = dict(last_state.attributes or {})

        if attrs is not None:

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
                # Heat pump delta tracking
                "tracked_wp_kwh": safe_float(attrs.get("tracked_wp_kwh")),
                "wp_first_seen_date": attrs.get("wp_first_seen_date"),
                # PV string delta tracking
                "string_tracked_kwh": attrs.get("string_tracked_kwh", {}),
                "string_first_seen_date": attrs.get("string_first_seen_date"),
                "string_peak_w": attrs.get("string_peak_w", {}),
                # Daily tracking (restore)
                "daily_grid_import_kwh": safe_float(attrs.get("daily_grid_import_kwh")),
                "daily_grid_import_cost": safe_float(attrs.get("daily_grid_import_cost")),
                "daily_feed_in_earnings": safe_float(attrs.get("daily_feed_in_earnings")),
                "daily_feed_in_kwh": safe_float(attrs.get("daily_feed_in_kwh")),
                "daily_reset_date": attrs.get("daily_reset_date"),
                "quota_day_start_meter": safe_float(attrs.get("quota_day_start_meter")),
                # Monthly tracking (persistent)
                "monthly_grid_import_kwh": safe_float(attrs.get("monthly_grid_import_kwh")),
                "monthly_grid_import_cost": safe_float(attrs.get("monthly_grid_import_cost")),
                "monthly_reset_month": attrs.get("monthly_reset_month"),
                "monthly_reset_year": attrs.get("monthly_reset_year"),
                # Benchmark snapshot
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
            # Heat pump delta tracking (persistent)
            "tracked_wp_kwh": round(self.ctrl._tracked_wp_kwh, 4),
            "wp_first_seen_date": self.ctrl._wp_first_seen_date.isoformat() if self.ctrl._wp_first_seen_date else None,
            # PV string delta tracking (persistent)
            "string_tracked_kwh": self.ctrl._string_tracked_kwh,
            "string_first_seen_date": self.ctrl._string_first_seen_date.isoformat() if self.ctrl._string_first_seen_date else None,
            "string_peak_w": self.ctrl._string_peak_w,
            "string_daily_peak_w": self.ctrl._string_daily_peak_w,
            "string_daily_peak_date": self.ctrl._string_daily_peak_date.isoformat() if self.ctrl._string_daily_peak_date else None,
            # Daily tracking (persistent)
            "daily_grid_import_kwh": round(self.ctrl._daily_grid_import_kwh, 4),
            "daily_grid_import_cost": round(self.ctrl._daily_grid_import_cost, 4),
            "daily_feed_in_earnings": round(self.ctrl._daily_feed_in_earnings, 4),
            "daily_feed_in_kwh": round(self.ctrl._daily_feed_in_kwh, 4),
            "daily_reset_date": date.today().isoformat(),
            "quota_day_start_meter": self.ctrl._quota_day_start_meter,
            # Monthly tracking (persistent)
            "monthly_grid_import_kwh": round(self.ctrl._monthly_grid_import_kwh, 4),
            "monthly_grid_import_cost": round(self.ctrl._monthly_grid_import_cost, 4),
            "monthly_reset_month": date.today().month,
            "monthly_reset_year": date.today().year,
            # Benchmark snapshot
            "benchmark_start_date": self.ctrl._benchmark_start_date.isoformat() if self.ctrl._benchmark_start_date else None,
            "benchmark_start_self_consumption": round(self.ctrl._benchmark_start_self_consumption, 4),
            "benchmark_start_grid_import": round(self.ctrl._benchmark_start_grid_import, 4),
            "benchmark_start_feed_in": round(self.ctrl._benchmark_start_feed_in, 4),
            "monthly_buckets": {str(k): v for k, v in self.ctrl._monthly_buckets.items()},
            "monthly_bucket_month": self.ctrl._monthly_bucket_month,
            "calculation_method": "incremental (fixed price)",
        }

    @property
    def extra_restore_state_data(self) -> _PersistedTrackingData:
        """Persistiert alle kumulativen Werte über Reboots hinweg (Issue #9).

        Anders als extra_state_attributes wird extra_restore_state_data von
        HA auch dann gespeichert, wenn die Entity gerade "unavailable" ist.
        """
        return _PersistedTrackingData(dict(self.extra_state_attributes))


class RemainingCostSensor(BaseEntity):
    """Remaining amount until amortisation."""

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
    """Status text (e.g. '45.2% amortised' or 'Amortised!')."""

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
# ENERGY SENSORS
# =============================================================================


class SelfConsumptionSensor(BaseEntity):
    """Self consumption in kWh."""

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
    """Grid feed-in in kWh."""

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
    """PV production in kWh."""

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
# FINANCIAL SENSORS
# =============================================================================


class SavingsSelfConsumptionSensor(BaseEntity):
    """Savings from self consumption."""

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
            "calculation": "Self Consumption × Fixed Price",
        }


class EarningsFeedInSensor(BaseEntity):
    """Earnings from feed-in."""

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
# EFFICIENCY SENSORS
# =============================================================================


class SelfConsumptionRatioSensor(BaseEntity):
    """Self consumption ratio in percent."""

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
    """Autarky rate in percent."""

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
# STATISTICS SENSORS
# =============================================================================


class AverageDailySavingsSensor(BaseEntity):
    """Average daily savings."""

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
    """Average monthly savings."""

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
    """Average yearly savings."""

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
    """Days since installation."""

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
# FORECAST SENSORS
# =============================================================================


class EstimatedRemainingDaysSensor(BaseEntity):
    """Estimated remaining days until amortisation."""

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
            return {"status": "Calculation not possible"}

        years = remaining // 365
        months = (remaining % 365) // 30
        days = remaining % 30

        parts = []
        if years > 0:
            parts.append(f"{years} year{'s' if years > 1 else ''}")
        if months > 0:
            parts.append(f"{months} month{'s' if months > 1 else ''}")
        if days > 0 or not parts:
            parts.append(f"{days} day{'s' if days != 1 else ''}")

        return {
            "formatted": ", ".join(parts),
            "years": years,
            "months": months,
            "days": days,
        }


class EstimatedPaybackDateSensor(BaseEntity):
    """Estimated amortisation date."""

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
# ENVIRONMENT SENSORS
# =============================================================================


class CO2SavedSensor(BaseEntity):
    """Saved CO2 emissions."""

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
# CONFIGURATION SENSORS (DIAGNOSTICS)
# =============================================================================


class FixedPriceSensor(BaseEntity):
    """Configured fixed price."""

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
        return round(self.ctrl.current_electricity_price * 100, 2)

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {
            "gross_price_ct": round(self.ctrl.gross_price_ct, 2),
        }
        if self.ctrl.has_itemized_costs:
            attrs["grid_fee_ct"] = round(self.ctrl.grid_fee * 100, 2)
            attrs["taxes_levies_ct"] = round(self.ctrl.taxes_levies * 100, 2)
            attrs["vat_percent"] = self.ctrl.vat_percent
        else:
            attrs["markup_factor"] = self.ctrl.markup_factor
        attrs["source"] = "sensor" if self.ctrl.electricity_price_entity else "config"
        return attrs


class GrossPriceSensor(BaseEntity):
    """Gross electricity price for Energy Dashboard (EUR/kWh)."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Preis Brutto",
            unit="€/kWh",
            icon="mdi:currency-eur",
            state_class=SensorStateClass.MEASUREMENT,
            device_type=DEVICE_PRICES,
        )

    @property
    def native_value(self) -> float:
        return round(self.ctrl.gross_price, 4)

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {
            "net_price_ct": round(self.ctrl.current_electricity_price * 100, 2),
            "gross_price_ct": round(self.ctrl.gross_price_ct, 2),
        }
        if self.ctrl.has_itemized_costs:
            attrs["grid_fee_ct"] = round(self.ctrl.grid_fee * 100, 2)
            attrs["taxes_levies_ct"] = round(self.ctrl.taxes_levies * 100, 2)
            attrs["vat_percent"] = self.ctrl.vat_percent
            net_total = self.ctrl.current_electricity_price + self.ctrl.grid_fee + self.ctrl.taxes_levies
            attrs["net_total_ct"] = round(net_total * 100, 2)
        else:
            attrs["markup_factor"] = self.ctrl.markup_factor
        return attrs


class CurrentFeedInTariffSensor(BaseEntity):
    """Current feed-in tariff."""

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
    """Installation cost of the PV system."""

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
    """Diagnostic sensor showing all configured sensors."""

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
        """Get status of an entity."""
        if not entity_id:
            return {"configured": False, "entity_id": None, "state": None, "status": "not configured"}

        state = self.hass.states.get(entity_id)
        if state is None:
            return {"configured": True, "entity_id": entity_id, "state": None, "status": "not found"}
        elif state.state in ("unavailable", "unknown"):
            return {"configured": True, "entity_id": entity_id, "state": state.state, "status": "unavailable"}
        else:
            return {"configured": True, "entity_id": entity_id, "state": state.state, "status": "OK"}

    @property
    def native_value(self) -> str:
        """Show overall configuration status."""
        issues = 0
        for entity_id in [self.ctrl.pv_production_entity, self.ctrl.grid_export_entity]:
            if entity_id:
                status = self._get_entity_status(entity_id)
                if status["status"] != "OK":
                    issues += 1
        if issues == 0:
            return "OK"
        else:
            return f"{issues} problem{'s' if issues > 1 else ''}"

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
# DAILY ELECTRICITY COSTS
# =============================================================================


class DailyFeedInSensor(BaseEntity):
    """Feed-in today: remuneration and amount."""

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
            "amount_kwh": round(self.ctrl.daily_feed_in_kwh, 2),
            "tariff_ct": f"{self.ctrl.current_feed_in_tariff * 100:.2f}",
        }


class DailyGridImportSensor(BaseEntity):
    """Grid import today: costs and consumption."""

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
            "consumption_kwh": round(self.ctrl.daily_grid_import_kwh, 2),
            "average_ct": round(avg, 2) if avg else None,
        }


class DailyNetElectricityCostSensor(BaseEntity):
    """Net electricity costs today: grid import minus feed-in."""

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
            "import_eur": round(self.ctrl.daily_grid_import_cost, 2),
            "export_eur": round(self.ctrl.daily_feed_in_earnings, 2),
        }


# =============================================================================
# ELECTRICITY QUOTA SENSORS
# =============================================================================


class QuotaRemainingSensor(BaseEntity):
    """Quota remaining - main sensor: how many kWh are left."""

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
            "yearly_quota_kwh": self.ctrl.quota_yearly_kwh,
            "consumed_kwh": round(self.ctrl.quota_consumed_kwh, 1),
            "monthly_rate_eur": self.ctrl.quota_monthly_rate if self.ctrl.quota_monthly_rate > 0 else None,
        }


class QuotaConsumedPercentSensor(BaseEntity):
    """Quota consumption - percent of yearly quota consumed."""

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
    """Quota reserve - positive = under budget, negative = over."""

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
            "expected_kwh": round(self.ctrl.quota_expected_kwh, 1),
            "consumed_kwh": round(self.ctrl.quota_consumed_kwh, 1),
        }


class QuotaDailyBudgetSensor(BaseEntity):
    """Quota daily budget - how much can still be consumed per day."""

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
    """Quota forecast - projected consumption at end of period."""

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
            "quota_kwh": self.ctrl.quota_yearly_kwh,
        }
        if forecast is not None:
            diff = forecast - self.ctrl.quota_yearly_kwh
            attrs["forecast_diff_kwh"] = round(diff, 0)
            if diff > 0:
                attrs["evaluation"] = f"Expected {diff:.0f} kWh over quota"
            else:
                attrs["evaluation"] = f"Expected {abs(diff):.0f} kWh under quota"
        return attrs


class QuotaDaysRemainingSensor(BaseEntity):
    """Quota remaining time - remaining days in the period."""

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
            "period_start": start.isoformat() if start else None,
            "period_end": end.isoformat() if end else None,
            "days_elapsed": self.ctrl.quota_days_elapsed,
            "days_total": self.ctrl.quota_days_total,
        }


class QuotaTodayRemainingSensor(BaseEntity):
    """Quota today remaining - how much can still be consumed today."""

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
            "daily_budget_kwh": round(budget, 1) if budget is not None else None,
            "consumed_today_kwh": round(self.ctrl.daily_grid_import_kwh, 1),
        }


class QuotaStatusSensor(BaseEntity):
    """Quota status - textual summary."""

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
            "consumed_kwh": round(self.ctrl.quota_consumed_kwh, 1),
            "remaining_kwh": round(self.ctrl.quota_remaining_kwh, 1),
            "reserve_kwh": round(self.ctrl.quota_reserve_kwh, 1),
            "consumed_percent": round(self.ctrl.quota_consumed_percent, 1),
        }
        forecast = self.ctrl.quota_forecast_kwh
        if forecast is not None:
            attrs["forecast_kwh"] = round(forecast, 0)
        budget = self.ctrl.quota_daily_budget_kwh
        if budget is not None:
            attrs["daily_budget_kwh"] = round(budget, 1)
        if self.ctrl.quota_monthly_rate > 0:
            attrs["monthly_payment_eur"] = self.ctrl.quota_monthly_rate
        return attrs


# =============================================================================
# BATTERY SENSORS
# =============================================================================


class BatterySOCSensor(BaseEntity):
    """Battery state of charge."""

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
    """Battery charge total."""

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
    """Battery discharge total."""

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
    """Battery efficiency."""

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
    """Battery cycles (estimated)."""

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


# =============================================================================
# ROI SENSORS
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


class AnnualROISensor(BaseEntity):
    """Annual ROI."""

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
# BENCHMARK SENSORS
# =============================================================================


MONTH_NAMES_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                  "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


class BenchmarkAvgSensor(BaseEntity):
    """Benchmark average - reference household electricity consumption."""

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
    """Benchmark total consumption - incl. heat pump, extrapolated to 1 year."""

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
    """Household consumption without heat pump, extrapolated to 1 year."""

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
    """Annual grid import extrapolated."""

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
    """Extrapolated annual PV production."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "PV Produktion Benchmark",
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
    """Specific yield in kWh/kWp."""

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
    """Benchmark comparison - own vs. average in %."""

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
    """Benchmark CO2 avoided - CO2 savings from PV per year."""

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
    """Benchmark efficiency score - 0-100 points."""

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
        self._last_score: int | None = None

    @property
    def native_value(self) -> int | None:
        score = self.ctrl.benchmark_efficiency_score
        if score is not None:
            self._last_score = score
        return self._last_score

    @property
    def extra_state_attributes(self) -> dict:
        autarky = self.ctrl.autarky_rate
        specific = self.ctrl.benchmark_specific_yield
        sc_ratio = self.ctrl.self_consumption_ratio
        comparison = self.ctrl.benchmark_consumption_vs_avg
        return {
            "autarky_points": f"{min(35, autarky * 0.35):.1f}/35" if autarky is not None else "n/a",
            "specific_yield_points": f"{min(25, (specific / 900) * 25):.1f}/25" if specific and specific > 0 else "n/a",
            "self_consumption_points": f"{min(20, sc_ratio * 0.2):.1f}/20" if sc_ratio is not None else "n/a",
            "consumption_points": f"{max(0, min(20, 10 - comparison * 0.2)):.1f}/20" if comparison is not None else "n/a",
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
    """Benchmark rating - textual rating."""

    def __init__(self, ctrl, name: str):
        super().__init__(
            ctrl,
            name,
            "Bewertung",
            icon="mdi:trophy",
            device_type=DEVICE_BENCHMARK,
        )
        self._last_rating: str | None = None

    @property
    def native_value(self) -> str | None:
        rating = self.ctrl.benchmark_rating
        if rating is not None:
            self._last_rating = rating
        return self._last_rating


class BenchmarkHeatpumpAvgSensor(BaseEntity):
    """Benchmark heat pump average - reference heat pump consumption."""

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
    """Benchmark heat pump consumption - own heat pump consumption extrapolated."""

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
    """Benchmark heat pump comparison - heat pump consumption vs. average in %."""

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


# ---------------------------------------------------------------------------
# LOAD FORECAST SENSORS (24x7 profile)
# ---------------------------------------------------------------------------

class _ForecastBaseSensor(BaseEntity):
    """Basis für Load-Forecast Sensoren. Liest aus ctrl.forecaster."""

    def __init__(self, ctrl, name: str, key: str, icon: str = "mdi:chart-bell-curve"):
        super().__init__(
            ctrl,
            name,
            key,
            unit="kWh",
            icon=icon,
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.ENERGY_STORAGE,
            device_type=DEVICE_FORECAST,
        )

    @property
    def available(self) -> bool:
        # available, sobald Forecaster existiert — Wert kann None sein (Warming-Up)
        return getattr(self.ctrl, "_restored", True) and self.ctrl.forecaster is not None

    @property
    def extra_state_attributes(self) -> dict:
        fc = self.ctrl.forecaster
        if fc is None:
            return {}
        attrs: dict[str, Any] = {
            "method": fc.method,
            "days_of_history": fc.days_of_history,
            "base_load_only": fc.base_load_only,
        }
        if fc.last_update is not None:
            attrs["last_update"] = fc.last_update.isoformat()
        if fc.last_error:
            attrs["last_error"] = fc.last_error
        return attrs


class LoadForecast1hSensor(_ForecastBaseSensor):
    """Verbrauchsprognose nächste Stunde."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose 1h", icon="mdi:clock-outline")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_next_hours(1) if fc is not None else None


class LoadForecast6hSensor(_ForecastBaseSensor):
    """Verbrauchsprognose nächste 6 Stunden."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose 6h", icon="mdi:clock-time-six-outline")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_next_hours(6) if fc is not None else None


class LoadForecastTodayRestSensor(_ForecastBaseSensor):
    """Verbrauchsprognose Rest des heutigen Tages."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose Heute Rest", icon="mdi:weather-sunset-down")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_today_rest() if fc is not None else None


class LoadForecastTomorrowSensor(_ForecastBaseSensor):
    """Verbrauchsprognose morgen (00:00–23:00)."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose Morgen", icon="mdi:calendar-arrow-right")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_tomorrow() if fc is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        fc = self.ctrl.forecaster
        if fc is None:
            return attrs
        # Stündliches Profil morgen (24 Werte)
        try:
            from datetime import timedelta
            from homeassistant.util import dt as dt_util
            start_tomorrow = (dt_util.as_local(dt_util.utcnow()) + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            attrs["forecast_hourly"] = fc.hourly_forecast(24, now=start_tomorrow)
            low, high = fc.confidence_band(24, now=start_tomorrow)
            if low is not None:
                attrs["confidence_low"] = low
            if high is not None:
                attrs["confidence_high"] = high
        except Exception:
            pass
        return attrs


class LoadForecast24hSensor(_ForecastBaseSensor):
    """Rollierende 24h-Prognose ab jetzt (für Batterie-/Lade-Logik)."""

    def __init__(self, ctrl, name: str):
        super().__init__(ctrl, name, "Verbrauch Prognose 24h", icon="mdi:chart-bell-curve")

    @property
    def native_value(self) -> float | None:
        fc = self.ctrl.forecaster
        return fc.forecast_next_hours(24) if fc is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        fc = self.ctrl.forecaster
        if fc is None:
            return attrs
        try:
            attrs["forecast_hourly"] = fc.hourly_forecast(24)
            low, high = fc.confidence_band(24)
            if low is not None:
                attrs["confidence_low"] = low
            if high is not None:
                attrs["confidence_high"] = high
        except Exception:
            pass
        return attrs
