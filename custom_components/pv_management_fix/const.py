from __future__ import annotations

from typing import Final
from homeassistant.const import Platform

# --- Domain / Platforms -------------------------------------------------------
DOMAIN: Final[str] = "pv_management_fix"
DATA_CTRL: Final[str] = "ctrl"

# Only Sensor and Button - no Switches (no battery management for fixed price)
PLATFORMS: Final[tuple[Platform, ...]] = (
    Platform.SENSOR,
    Platform.BUTTON,
)

# --- Config keys (Setup) ------------------------------------------------------
CONF_NAME: Final[str] = "name"
CONF_PV_PRODUCTION_ENTITY: Final[str] = "pv_production_entity"
CONF_GRID_EXPORT_ENTITY: Final[str] = "grid_export_entity"
CONF_GRID_IMPORT_ENTITY: Final[str] = "grid_import_entity"
CONF_CONSUMPTION_ENTITY: Final[str] = "consumption_entity"

# --- Option keys (can be changed later) ---------------------------------------
CONF_ELECTRICITY_PRICE: Final[str] = "electricity_price"
CONF_ELECTRICITY_PRICE_ENTITY: Final[str] = "electricity_price_entity"
CONF_ELECTRICITY_PRICE_UNIT: Final[str] = "electricity_price_unit"
CONF_FEED_IN_TARIFF: Final[str] = "feed_in_tariff"
CONF_FEED_IN_TARIFF_ENTITY: Final[str] = "feed_in_tariff_entity"
CONF_FEED_IN_TARIFF_UNIT: Final[str] = "feed_in_tariff_unit"

# --- Price units --------------------------------------------------------------
PRICE_UNIT_EUR: Final[str] = "eur"
PRICE_UNIT_CENT: Final[str] = "cent"
CONF_INSTALLATION_COST: Final[str] = "installation_cost"
CONF_SAVINGS_OFFSET: Final[str] = "savings_offset"
CONF_ENERGY_OFFSET_SELF: Final[str] = "energy_offset_self_consumption"
CONF_ENERGY_OFFSET_EXPORT: Final[str] = "energy_offset_export"
CONF_INSTALLATION_DATE: Final[str] = "installation_date"

# --- Fixed price (main feature of this integration) --------------------------
CONF_FIXED_PRICE: Final[str] = "fixed_price"  # Fixed price in ct/kWh (net energy price)
CONF_MARKUP_FACTOR: Final[str] = "markup_factor"  # Legacy: markup factor (kept for backwards compat)
CONF_GRID_FEE: Final[str] = "grid_fee"  # Grid fees (Netzentgelt) in ct/kWh
CONF_TAXES_LEVIES: Final[str] = "taxes_levies"  # Taxes & levies (Steuern & Abgaben) in ct/kWh
CONF_VAT_PERCENT: Final[str] = "vat_percent"  # VAT (MwSt) in percent

# --- Amortisation Helper Sync -------------------------------------------------
CONF_AMORTISATION_HELPER: Final[str] = "amortisation_helper"
CONF_RESTORE_FROM_HELPER: Final[str] = "restore_from_helper"
CONF_YEARLY_COST: Final[str] = "yearly_cost"
DEFAULT_YEARLY_COST: Final[float] = 0.0  # €/Jahr (z.B. Versicherung, Wartung)

# --- Electricity quota (yearly kWh budget) ------------------------------------
CONF_QUOTA_ENABLED: Final[str] = "quota_enabled"
CONF_QUOTA_YEARLY_KWH: Final[str] = "quota_yearly_kwh"
CONF_QUOTA_START_DATE: Final[str] = "quota_start_date"
CONF_QUOTA_START_METER: Final[str] = "quota_start_meter"
CONF_QUOTA_MONTHLY_RATE: Final[str] = "quota_monthly_rate"
CONF_QUOTA_SEASONAL: Final[str] = "quota_seasonal"

# --- Battery ------------------------------------------------------------------
CONF_BATTERY_SOC_ENTITY: Final[str] = "battery_soc_entity"
CONF_BATTERY_CHARGE_ENTITY: Final[str] = "battery_charge_entity"
CONF_BATTERY_DISCHARGE_ENTITY: Final[str] = "battery_discharge_entity"
CONF_BATTERY_CAPACITY: Final[str] = "battery_capacity"
DEFAULT_BATTERY_CAPACITY: Final[float] = 10.0  # kWh

# --- Defaults -----------------------------------------------------------------
DEFAULT_NAME: Final[str] = "PV Fixpreis"
DEFAULT_ELECTRICITY_PRICE: Final[float] = 0.1092  # €/kWh (Grünwelt classic rate)
DEFAULT_ELECTRICITY_PRICE_UNIT: Final[str] = PRICE_UNIT_EUR
DEFAULT_FEED_IN_TARIFF: Final[float] = 0.08  # €/kWh
DEFAULT_FEED_IN_TARIFF_UNIT: Final[str] = PRICE_UNIT_EUR
DEFAULT_INSTALLATION_COST: Final[float] = 10000.0  # €
DEFAULT_SAVINGS_OFFSET: Final[float] = 0.0  # € already amortised
DEFAULT_ENERGY_OFFSET_SELF: Final[float] = 0.0  # kWh self-consumption before tracking
DEFAULT_ENERGY_OFFSET_EXPORT: Final[float] = 0.0  # kWh export before tracking

# Fixed price default (Grünwelt classic net energy price)
DEFAULT_FIXED_PRICE: Final[float] = 10.92  # ct/kWh net
DEFAULT_MARKUP_FACTOR: Final[float] = 2.0  # Legacy factor (kept for backwards compat)
DEFAULT_GRID_FEE: Final[float] = 0.0  # ct/kWh grid fees
DEFAULT_TAXES_LEVIES: Final[float] = 0.0  # ct/kWh taxes & levies
DEFAULT_VAT_PERCENT: Final[float] = 20.0  # % VAT (Austria default)

# Electricity quota defaults
DEFAULT_QUOTA_ENABLED: Final[bool] = False
DEFAULT_QUOTA_YEARLY_KWH: Final[float] = 4000.0  # kWh per year
DEFAULT_QUOTA_START_METER: Final[float] = 0.0  # Meter reading at start
DEFAULT_QUOTA_MONTHLY_RATE: Final[float] = 0.0  # €/month advance payment
DEFAULT_QUOTA_SEASONAL: Final[bool] = False

# Seasonal weighting factors (German residential electricity average)
# Normalised to sum = 12 (factor 1.0 = average)
SEASONAL_FACTORS: Final[dict[int, float]] = {
    1: 1.20,   # January
    2: 1.15,   # February
    3: 1.05,   # March
    4: 0.95,   # April
    5: 0.85,   # May
    6: 0.75,   # June
    7: 0.75,   # July
    8: 0.80,   # August
    9: 0.90,   # September
    10: 1.00,  # October
    11: 1.15,  # November
    12: 1.45,  # December
}

# --- Ranges for Config Flow / Options -----------------------------------------
RANGE_PRICE_EUR: Final[dict] = {"min": 0.01, "max": 1.0, "step": 0.001}
RANGE_PRICE_CENT: Final[dict] = {"min": 1.0, "max": 100.0, "step": 0.01}
RANGE_TARIFF_EUR: Final[dict] = {"min": 0.0, "max": 0.5, "step": 0.001}
RANGE_TARIFF_CENT: Final[dict] = {"min": 0.0, "max": 50.0, "step": 0.01}
RANGE_COST: Final[dict] = {"min": 0.0, "max": 200000.0, "step": 1.0}
RANGE_OFFSET: Final[dict] = {"min": 0.0, "max": 100000.0, "step": 0.01}
RANGE_ENERGY_OFFSET: Final[dict] = {"min": 0.0, "max": 500000.0, "step": 0.01}
RANGE_MARKUP_FACTOR: Final[dict] = {"min": 1.0, "max": 5.0, "step": 0.1}
RANGE_GRID_FEE: Final[dict] = {"min": 0.0, "max": 30.0, "step": 0.01}
RANGE_TAXES_LEVIES: Final[dict] = {"min": 0.0, "max": 30.0, "step": 0.01}
RANGE_VAT_PERCENT: Final[dict] = {"min": 0.0, "max": 30.0, "step": 0.1}

# Electricity quota ranges
RANGE_QUOTA_KWH: Final[dict] = {"min": 100.0, "max": 100000.0, "step": 1.0}
RANGE_QUOTA_METER: Final[dict] = {"min": 0.0, "max": 9999999.0, "step": 0.01}
RANGE_QUOTA_RATE: Final[dict] = {"min": 0.0, "max": 10000.0, "step": 0.01}
RANGE_BATTERY_CAPACITY: Final[dict] = {"min": 0.1, "max": 200.0, "step": 0.1}

# --- Benchmark ----------------------------------------------------------------
CONF_BENCHMARK_ENABLED: Final[str] = "benchmark_enabled"
CONF_BENCHMARK_HOUSEHOLD_SIZE: Final[str] = "benchmark_household_size"
CONF_BENCHMARK_COUNTRY: Final[str] = "benchmark_country"

DEFAULT_BENCHMARK_ENABLED: Final[bool] = False
DEFAULT_BENCHMARK_HOUSEHOLD_SIZE: Final[int] = 3
DEFAULT_BENCHMARK_COUNTRY: Final[str] = "AT"

# Heat pump (optional, for fair benchmark comparison)
CONF_BENCHMARK_HEATPUMP: Final[str] = "benchmark_heatpump"
CONF_BENCHMARK_HEATPUMP_ENTITY: Final[str] = "benchmark_heatpump_entity"
CONF_BENCHMARK_HEATPUMP_DATE: Final[str] = "benchmark_heatpump_date"
DEFAULT_BENCHMARK_HEATPUMP: Final[bool] = False

# Average annual electricity consumption WITHOUT heat pump per household size (kWh/year)
# Sources: E-Control (AT), BDEW (DE), BFE (CH), URE (PL) — 2023/2024 data
BENCHMARK_CONSUMPTION: Final[dict[str, dict[int, int]]] = {
    "AT": {1: 2200, 2: 3500, 3: 4000, 4: 4500, 5: 5500, 6: 6500},
    "DE": {1: 2000, 2: 3200, 3: 3900, 4: 4400, 5: 5400, 6: 6300},
    "CH": {1: 2500, 2: 3800, 3: 4400, 4: 5000, 5: 6000, 6: 7000},
    "PL": {1: 1500, 2: 2200, 3: 2800, 4: 3500, 5: 4200, 6: 5000},
}

# Average heat pump electricity consumption (kWh/year) — single-family house
# Sources: Austrian Energy Agency, BDEW heat pump study 2023
BENCHMARK_HEATPUMP_CONSUMPTION: Final[dict[str, int]] = {
    "AT": 4000,  # ~160m² single-family house, SCOP ~3.5
    "DE": 4500,  # colder climate on average
    "CH": 3500,  # well-insulated houses
    "PL": 5000,
}

# CO2 factor electricity mix (kg CO2/kWh) — Umweltbundesamt AT/DE, BFE CH
BENCHMARK_CO2_FACTORS: Final[dict[str, float]] = {
    "AT": 0.150,  # mostly hydropower
    "DE": 0.380,  # still coal/gas
    "CH": 0.030,  # nuclear + hydropower
    "PL": 0.700,
}

RANGE_HOUSEHOLD_SIZE: Final[dict] = {"min": 1, "max": 6, "step": 1}

# --- Load Forecast (24x7 hour-of-day x day-of-week profile) -------------------
CONF_FORECAST_ENABLED: Final[str] = "forecast_enabled"
CONF_FORECAST_WEEKS: Final[str] = "forecast_weeks"
CONF_FORECAST_MODAL_DROP: Final[str] = "forecast_modal_drop"
CONF_FORECAST_HP_ENTITY: Final[str] = "forecast_hp_entity"
CONF_FORECAST_EV_ENTITY: Final[str] = "forecast_ev_entity"

DEFAULT_FORECAST_ENABLED: Final[bool] = False
DEFAULT_FORECAST_WEEKS: Final[int] = 4  # 2 / 4 / 6 supported
DEFAULT_FORECAST_MODAL_DROP: Final[bool] = True

# Allowed discrete values for weeks selector
FORECAST_WEEKS_CHOICES: Final[tuple[int, ...]] = (2, 4, 6)

# Refresh cadence for the forecast matrix (seconds). 1h = enough for household patterns.
FORECAST_REFRESH_SECONDS: Final[int] = 3600

# Minimum days of history required for full 24x7 matrix mode; below, we fallback.
FORECAST_MIN_DAYS_FULL: Final[int] = 14   # <14d => 7-day-mean fallback
FORECAST_MIN_DAYS_ANY: Final[int] = 3     # <3d  => persistence fallback


# --- PV Strings (comparison of multiple strings) -----------------------------
CONF_PV_STRING_1_NAME: Final[str] = "pv_string_1_name"
CONF_PV_STRING_1_ENTITY: Final[str] = "pv_string_1_entity"
CONF_PV_STRING_2_NAME: Final[str] = "pv_string_2_name"
CONF_PV_STRING_2_ENTITY: Final[str] = "pv_string_2_entity"
CONF_PV_STRING_3_NAME: Final[str] = "pv_string_3_name"
CONF_PV_STRING_3_ENTITY: Final[str] = "pv_string_3_entity"
CONF_PV_STRING_4_NAME: Final[str] = "pv_string_4_name"
CONF_PV_STRING_4_ENTITY: Final[str] = "pv_string_4_entity"
CONF_PV_STRING_1_POWER: Final[str] = "pv_string_1_power"
CONF_PV_STRING_2_POWER: Final[str] = "pv_string_2_power"
CONF_PV_STRING_3_POWER: Final[str] = "pv_string_3_power"
CONF_PV_STRING_4_POWER: Final[str] = "pv_string_4_power"
CONF_PV_STRING_1_KWP: Final[str] = "pv_string_1_kwp"
CONF_PV_STRING_2_KWP: Final[str] = "pv_string_2_kwp"
CONF_PV_STRING_3_KWP: Final[str] = "pv_string_3_kwp"
CONF_PV_STRING_4_KWP: Final[str] = "pv_string_4_kwp"

PV_STRING_CONFIGS = [
    (CONF_PV_STRING_1_NAME, CONF_PV_STRING_1_ENTITY, CONF_PV_STRING_1_POWER, CONF_PV_STRING_1_KWP),
    (CONF_PV_STRING_2_NAME, CONF_PV_STRING_2_ENTITY, CONF_PV_STRING_2_POWER, CONF_PV_STRING_2_KWP),
    (CONF_PV_STRING_3_NAME, CONF_PV_STRING_3_ENTITY, CONF_PV_STRING_3_POWER, CONF_PV_STRING_3_KWP),
    (CONF_PV_STRING_4_NAME, CONF_PV_STRING_4_ENTITY, CONF_PV_STRING_4_POWER, CONF_PV_STRING_4_KWP),
]
