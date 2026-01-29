from __future__ import annotations

from typing import Final
from homeassistant.const import Platform

# --- Domain / Platforms -------------------------------------------------------
DOMAIN: Final[str] = "pv_management_fix"
DATA_CTRL: Final[str] = "ctrl"

# Nur Sensor und Button - keine Switches (kein Batterie-Management bei Fixpreis)
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

# --- EPEX Spot Integration (nur für Spot vs Fix Vergleich) --------------------
CONF_EPEX_PRICE_ENTITY: Final[str] = "epex_price_entity"

# --- Option keys (können später geändert werden) ------------------------------
CONF_ELECTRICITY_PRICE: Final[str] = "electricity_price"
CONF_ELECTRICITY_PRICE_ENTITY: Final[str] = "electricity_price_entity"
CONF_ELECTRICITY_PRICE_UNIT: Final[str] = "electricity_price_unit"
CONF_FEED_IN_TARIFF: Final[str] = "feed_in_tariff"
CONF_FEED_IN_TARIFF_ENTITY: Final[str] = "feed_in_tariff_entity"
CONF_FEED_IN_TARIFF_UNIT: Final[str] = "feed_in_tariff_unit"

# --- Preis-Einheiten ----------------------------------------------------------
PRICE_UNIT_EUR: Final[str] = "eur"
PRICE_UNIT_CENT: Final[str] = "cent"
CONF_INSTALLATION_COST: Final[str] = "installation_cost"
CONF_SAVINGS_OFFSET: Final[str] = "savings_offset"
CONF_ENERGY_OFFSET_SELF: Final[str] = "energy_offset_self_consumption"
CONF_ENERGY_OFFSET_EXPORT: Final[str] = "energy_offset_export"
CONF_INSTALLATION_DATE: Final[str] = "installation_date"

# --- Fixpreis (Haupt-Feature dieser Integration) ------------------------------
CONF_FIXED_PRICE: Final[str] = "fixed_price"  # Der Fixpreis in ct/kWh

# --- Stromkontingent (Jahres-kWh-Budget) --------------------------------------
CONF_QUOTA_ENABLED: Final[str] = "quota_enabled"
CONF_QUOTA_YEARLY_KWH: Final[str] = "quota_yearly_kwh"
CONF_QUOTA_START_DATE: Final[str] = "quota_start_date"
CONF_QUOTA_START_METER: Final[str] = "quota_start_meter"
CONF_QUOTA_MONTHLY_RATE: Final[str] = "quota_monthly_rate"

# --- Defaults -----------------------------------------------------------------
DEFAULT_NAME: Final[str] = "PV Fixpreis"
DEFAULT_ELECTRICITY_PRICE: Final[float] = 0.1092  # €/kWh (Grünwelt classic)
DEFAULT_ELECTRICITY_PRICE_UNIT: Final[str] = PRICE_UNIT_EUR
DEFAULT_FEED_IN_TARIFF: Final[float] = 0.08  # €/kWh
DEFAULT_FEED_IN_TARIFF_UNIT: Final[str] = PRICE_UNIT_EUR
DEFAULT_INSTALLATION_COST: Final[float] = 10000.0  # €
DEFAULT_SAVINGS_OFFSET: Final[float] = 0.0  # € bereits amortisiert
DEFAULT_ENERGY_OFFSET_SELF: Final[float] = 0.0  # kWh Eigenverbrauch vor Tracking
DEFAULT_ENERGY_OFFSET_EXPORT: Final[float] = 0.0  # kWh Export vor Tracking

# Fixpreis Default (Grünwelt classic brutto)
DEFAULT_FIXED_PRICE: Final[float] = 10.92  # ct/kWh

# Stromkontingent Defaults
DEFAULT_QUOTA_ENABLED: Final[bool] = False
DEFAULT_QUOTA_YEARLY_KWH: Final[float] = 4000.0  # kWh pro Jahr
DEFAULT_QUOTA_START_METER: Final[float] = 0.0  # Zählerstand bei Start
DEFAULT_QUOTA_MONTHLY_RATE: Final[float] = 0.0  # €/Monat Abschlag

# --- Ranges für Config Flow / Options -----------------------------------------
RANGE_PRICE_EUR: Final[dict] = {"min": 0.01, "max": 1.0, "step": 0.001}
RANGE_PRICE_CENT: Final[dict] = {"min": 1.0, "max": 100.0, "step": 0.01}
RANGE_TARIFF_EUR: Final[dict] = {"min": 0.0, "max": 0.5, "step": 0.001}
RANGE_TARIFF_CENT: Final[dict] = {"min": 0.0, "max": 50.0, "step": 0.01}
RANGE_COST: Final[dict] = {"min": 0.0, "max": 200000.0, "step": 1.0}
RANGE_OFFSET: Final[dict] = {"min": 0.0, "max": 100000.0, "step": 0.01}
RANGE_ENERGY_OFFSET: Final[dict] = {"min": 0.0, "max": 500000.0, "step": 0.01}

# Stromkontingent Ranges
RANGE_QUOTA_KWH: Final[dict] = {"min": 100.0, "max": 100000.0, "step": 1.0}
RANGE_QUOTA_METER: Final[dict] = {"min": 0.0, "max": 9999999.0, "step": 0.01}
RANGE_QUOTA_RATE: Final[dict] = {"min": 0.0, "max": 10000.0, "step": 0.01}
