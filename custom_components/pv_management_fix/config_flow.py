from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

import logging

from .const import (
    DOMAIN, DATA_CTRL,
    CONF_NAME, CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_ELECTRICITY_PRICE, CONF_ELECTRICITY_PRICE_ENTITY, CONF_ELECTRICITY_PRICE_UNIT,
    CONF_FEED_IN_TARIFF, CONF_FEED_IN_TARIFF_ENTITY, CONF_FEED_IN_TARIFF_UNIT,
    CONF_INSTALLATION_COST, CONF_INSTALLATION_DATE,
    CONF_SAVINGS_OFFSET, CONF_FIXED_PRICE, CONF_MARKUP_FACTOR,
    CONF_GRID_FEE, CONF_TAXES_LEVIES, CONF_VAT_PERCENT,
    CONF_ENERGY_OFFSET_SELF, CONF_ENERGY_OFFSET_EXPORT,
    CONF_AMORTISATION_HELPER, CONF_RESTORE_FROM_HELPER,
    CONF_QUOTA_ENABLED, CONF_QUOTA_YEARLY_KWH, CONF_QUOTA_START_DATE,
    CONF_QUOTA_START_METER, CONF_QUOTA_MONTHLY_RATE,
    CONF_BATTERY_SOC_ENTITY, CONF_BATTERY_CHARGE_ENTITY,
    CONF_BATTERY_DISCHARGE_ENTITY, CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY,
    CONF_PV_POWER_ENTITY, CONF_HOUSE_POWER_ENTITY,
    CONF_PV_PEAK_POWER, DEFAULT_PV_PEAK_POWER,
    CONF_SHIFTABLE_LOAD_ENTITY,
    CONF_BENCHMARK_ENABLED, CONF_BENCHMARK_HOUSEHOLD_SIZE, CONF_BENCHMARK_COUNTRY,
    CONF_BENCHMARK_HEATPUMP, CONF_BENCHMARK_HEATPUMP_ENTITY, CONF_BENCHMARK_HEATPUMP_DATE,
    DEFAULT_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_HOUSEHOLD_SIZE, DEFAULT_BENCHMARK_COUNTRY,
    DEFAULT_BENCHMARK_HEATPUMP,
    CONF_FORECAST_ENABLED, CONF_FORECAST_WEEKS, CONF_FORECAST_MODAL_DROP,
    CONF_FORECAST_HP_ENTITY, CONF_FORECAST_EV_ENTITY,
    DEFAULT_FORECAST_ENABLED, DEFAULT_FORECAST_WEEKS, DEFAULT_FORECAST_MODAL_DROP,
    FORECAST_WEEKS_CHOICES,
    CONF_YEARLY_COST, DEFAULT_YEARLY_COST,
    RANGE_BATTERY_CAPACITY, RANGE_HOUSEHOLD_SIZE,
    DEFAULT_NAME, DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET, DEFAULT_FIXED_PRICE, DEFAULT_MARKUP_FACTOR,
    DEFAULT_GRID_FEE, DEFAULT_TAXES_LEVIES, DEFAULT_VAT_PERCENT,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_EXPORT,
    DEFAULT_QUOTA_ENABLED, DEFAULT_QUOTA_YEARLY_KWH,
    DEFAULT_QUOTA_START_METER, DEFAULT_QUOTA_MONTHLY_RATE,
    RANGE_COST, RANGE_OFFSET, RANGE_ENERGY_OFFSET, RANGE_MARKUP_FACTOR,
    RANGE_GRID_FEE, RANGE_TAXES_LEVIES, RANGE_VAT_PERCENT,
    RANGE_QUOTA_KWH, RANGE_QUOTA_METER, RANGE_QUOTA_RATE,
    PRICE_UNIT_EUR, PRICE_UNIT_CENT,
    CONF_PV_STRING_1_NAME, CONF_PV_STRING_1_ENTITY,
    CONF_PV_STRING_2_NAME, CONF_PV_STRING_2_ENTITY,
    CONF_PV_STRING_3_NAME, CONF_PV_STRING_3_ENTITY,
    CONF_PV_STRING_4_NAME, CONF_PV_STRING_4_ENTITY,
    CONF_PV_STRING_1_POWER, CONF_PV_STRING_2_POWER,
    CONF_PV_STRING_3_POWER, CONF_PV_STRING_4_POWER,
    CONF_PV_STRING_1_KWP, CONF_PV_STRING_2_KWP,
    CONF_PV_STRING_3_KWP, CONF_PV_STRING_4_KWP,
)


class PVManagementFixConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow für PV Management Fixpreis."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Erster Schritt: Basis-Konfiguration."""
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,

                # === ENERGIE-SENSOREN ===
                vol.Required(CONF_PV_PRODUCTION_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Required(CONF_GRID_EXPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Required(CONF_GRID_IMPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Optional(CONF_CONSUMPTION_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),

                # === FIXPREIS (Fallback wenn kein Sensor) ===
                vol.Optional(CONF_FIXED_PRICE, default=DEFAULT_FIXED_PRICE):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=100.0, step=0.01,
                            unit_of_measurement="ct/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # === KOSTENAUFSCHLÜSSELUNG (pro kWh, von Rechnung ablesen) ===
                vol.Optional(CONF_GRID_FEE, default=DEFAULT_GRID_FEE):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_GRID_FEE["min"],
                            max=RANGE_GRID_FEE["max"],
                            step=RANGE_GRID_FEE["step"],
                            unit_of_measurement="ct/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_TAXES_LEVIES, default=DEFAULT_TAXES_LEVIES):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_TAXES_LEVIES["min"],
                            max=RANGE_TAXES_LEVIES["max"],
                            step=RANGE_TAXES_LEVIES["step"],
                            unit_of_measurement="ct/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_VAT_PERCENT, default=DEFAULT_VAT_PERCENT):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_VAT_PERCENT["min"],
                            max=RANGE_VAT_PERCENT["max"],
                            step=RANGE_VAT_PERCENT["step"],
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # === ALTERNATIVE: Pauschaler Aufschlagfaktor ===
                vol.Optional(CONF_MARKUP_FACTOR, default=DEFAULT_MARKUP_FACTOR):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_MARKUP_FACTOR["min"],
                            max=RANGE_MARKUP_FACTOR["max"],
                            step=RANGE_MARKUP_FACTOR["step"],
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # === DYNAMISCHER STROMPREIS (optional) ===
                vol.Optional(CONF_ELECTRICITY_PRICE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "input_number"])
                ),

                # === EINSPEISEVERGÜTUNG ===
                vol.Required(CONF_FEED_IN_TARIFF_UNIT, default=DEFAULT_FEED_IN_TARIFF_UNIT):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Required(CONF_FEED_IN_TARIFF, default=DEFAULT_FEED_IN_TARIFF):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=50.0, step=0.001,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                # Einspeisevergütung als Sensor (optional, überschreibt den Fixwert)
                vol.Optional(CONF_FEED_IN_TARIFF_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "input_number"])
                ),

                # === AMORTISATION ===
                vol.Required(CONF_INSTALLATION_COST, default=DEFAULT_INSTALLATION_COST):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_COST["min"], max=RANGE_COST["max"], step=RANGE_COST["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_INSTALLATION_DATE): selector.DateSelector(),
                vol.Optional(CONF_YEARLY_COST, default=DEFAULT_YEARLY_COST):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=5000.0, step=1.0,
                            unit_of_measurement="€/Jahr",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # === AMORTISATION HELPER (optional, empfohlen für Persistenz) ===
                vol.Optional(CONF_AMORTISATION_HELPER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="input_number")
                ),
                vol.Optional(CONF_RESTORE_FROM_HELPER, default=False): selector.BooleanSelector(),
            })
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return PVManagementFixOptionsFlow()


class PVManagementFixOptionsFlow(config_entries.OptionsFlow):
    """Options Flow mit Menü-Struktur."""

    def __init__(self):
        self._data = {}

    def _get_val(self, key, default=None):
        """Holt aktuellen Wert aus Options oder Data."""
        if key in self._data:
            return self._data[key]
        if key in self.config_entry.options:
            return self.config_entry.options[key]
        if key in self.config_entry.data:
            return self.config_entry.data[key]
        return default

    async def async_step_init(self, user_input=None):
        """Hauptmenü mit Kategorien."""
        return self.async_show_menu(
            step_id="init",
            menu_options={
                "sensors": "Sensoren & Leistungen",
                "tariff": "Tarif & Kosten",
                "amortisation": "Amortisation-Persistenz",
                "battery": "Batterie",
                "benchmark": "Energie-Benchmark",
                "pv_strings": "PV-Strings",
                "forecast": "Lastvorhersage",
                "reset": "Zurücksetzen",
            },
        )

    async def _save_and_return_to_menu(self, user_input, optional_entity_keys=()):
        """Speichert die Options und zeigt das Menü wieder an."""
        # Nur die optionalen Entity-Keys der AKTUELLEN Seite auf None setzen,
        # damit ein entfernter Sensor gelöscht wird ohne andere Seiten zu beeinflussen
        for key in optional_entity_keys:
            if key not in user_input and key in self.config_entry.options:
                user_input[key] = None

        self._data.update(user_input)
        final_data = {}
        final_data.update(self.config_entry.options)
        final_data.update(self._data)

        # None-Werte aufräumen (verhindert "Entity None" Fehler)
        final_data = {k: v for k, v in final_data.items() if v is not None}

        self.hass.config_entries.async_update_entry(self.config_entry, options=final_data)
        return await self.async_step_init()

    async def async_step_sensors(self, user_input=None):
        """Energie-Sensoren konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input, optional_entity_keys=(
                CONF_GRID_EXPORT_ENTITY, CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
                CONF_PV_POWER_ENTITY, CONF_HOUSE_POWER_ENTITY, CONF_SHIFTABLE_LOAD_ENTITY,
            ))

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema({
                vol.Required(CONF_PV_PRODUCTION_ENTITY, default=self._get_val(CONF_PV_PRODUCTION_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy")),
                self._optional_entity(CONF_GRID_EXPORT_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy")),
                self._optional_entity(CONF_GRID_IMPORT_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy")),
                self._optional_entity(CONF_CONSUMPTION_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy")),
                # --- Live-Leistungen (W) fuer PV-Ueberschuss-Sensoren --------------
                self._optional_entity(CONF_PV_POWER_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="power")),
                self._optional_entity(CONF_HOUSE_POWER_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="power")),
                # PV-gesteuerter Verbraucher (z.B. WP) — wird vom Hausverbrauch
                # abgezogen, damit der Verbraucher sich nicht selbst durch eigene
                # Last unter die Schwelle treibt (Anti-Selbstaufzehrung)
                self._optional_entity(CONF_SHIFTABLE_LOAD_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="power")),
                # Leer lassen → auto-derive aus PV-Strings (kWp) oder gemessenem Peak
                vol.Optional(CONF_PV_PEAK_POWER,
                             description={"suggested_value": self._get_val(CONF_PV_PEAK_POWER)}):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=500, max=50000, step=100, unit_of_measurement="W",
                        mode=selector.NumberSelectorMode.BOX,
                    )),
            })
        )

    def _optional_entity(self, key):
        """Erstellt vol.Optional für Entity-Selector mit suggested_value (erlaubt Löschen)."""
        val = self._get_val(key)
        if val:
            return vol.Optional(key, description={"suggested_value": val})
        return vol.Optional(key)

    async def async_step_tariff(self, user_input=None):
        """Tarif, Kosten, Quota, Anschaffung konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input, optional_entity_keys=(
                CONF_ELECTRICITY_PRICE_ENTITY, CONF_FEED_IN_TARIFF_ENTITY))

        return self.async_show_form(
            step_id="tariff",
            data_schema=vol.Schema({
                # Fixpreis (Fallback wenn kein Sensor)
                vol.Optional(CONF_FIXED_PRICE, default=self._get_val(CONF_FIXED_PRICE, DEFAULT_FIXED_PRICE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=100.0, step=0.01,
                            unit_of_measurement="ct/kWh",
                            mode=selector.NumberSelectorMode.BOX
                        )
                    ),

                # Kostenaufschlüsselung (Netzentgelt + Steuern/Abgaben + MwSt)
                vol.Optional(CONF_GRID_FEE, default=self._get_val(CONF_GRID_FEE, DEFAULT_GRID_FEE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_GRID_FEE["min"],
                            max=RANGE_GRID_FEE["max"],
                            step=RANGE_GRID_FEE["step"],
                            unit_of_measurement="ct/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_TAXES_LEVIES, default=self._get_val(CONF_TAXES_LEVIES, DEFAULT_TAXES_LEVIES)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_TAXES_LEVIES["min"],
                            max=RANGE_TAXES_LEVIES["max"],
                            step=RANGE_TAXES_LEVIES["step"],
                            unit_of_measurement="ct/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_VAT_PERCENT, default=self._get_val(CONF_VAT_PERCENT, DEFAULT_VAT_PERCENT)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_VAT_PERCENT["min"],
                            max=RANGE_VAT_PERCENT["max"],
                            step=RANGE_VAT_PERCENT["step"],
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # Alternative: Pauschaler Aufschlagfaktor
                vol.Optional(CONF_MARKUP_FACTOR, default=self._get_val(CONF_MARKUP_FACTOR, DEFAULT_MARKUP_FACTOR)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_MARKUP_FACTOR["min"],
                            max=RANGE_MARKUP_FACTOR["max"],
                            step=RANGE_MARKUP_FACTOR["step"],
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # Dynamischer Strompreis (optional)
                self._optional_entity(CONF_ELECTRICITY_PRICE_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "input_number"])),

                # Einspeisevergütung
                vol.Required(CONF_FEED_IN_TARIFF_UNIT, default=self._get_val(CONF_FEED_IN_TARIFF_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Required(CONF_FEED_IN_TARIFF, default=self._get_val(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.0, max=50.0, step=0.001, mode=selector.NumberSelectorMode.BOX)
                    ),
                self._optional_entity(CONF_FEED_IN_TARIFF_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "input_number"])),

                # Amortisation
                vol.Required(CONF_INSTALLATION_COST, default=self._get_val(CONF_INSTALLATION_COST, DEFAULT_INSTALLATION_COST)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_COST["min"], max=RANGE_COST["max"], step=RANGE_COST["step"],
                            unit_of_measurement="€", mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                vol.Optional(CONF_INSTALLATION_DATE, default=self._get_val(CONF_INSTALLATION_DATE)):
                    selector.DateSelector(),

                # Jährliche Kosten (Versicherung, Wartung etc.)
                vol.Optional(CONF_YEARLY_COST, default=self._get_val(CONF_YEARLY_COST, DEFAULT_YEARLY_COST)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0, max=5000.0, step=1.0,
                            unit_of_measurement="€/Jahr", mode=selector.NumberSelectorMode.BOX
                        )
                    ),

                # --- Stromkontingent (Jahres-kWh-Budget) -----------------------
                vol.Required(CONF_QUOTA_ENABLED, default=self._get_val(CONF_QUOTA_ENABLED, DEFAULT_QUOTA_ENABLED)):
                    selector.BooleanSelector(),
                vol.Required(CONF_QUOTA_YEARLY_KWH, default=self._get_val(CONF_QUOTA_YEARLY_KWH, DEFAULT_QUOTA_YEARLY_KWH)):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=RANGE_QUOTA_KWH["min"], max=RANGE_QUOTA_KWH["max"], step=RANGE_QUOTA_KWH["step"],
                        unit_of_measurement="kWh", mode=selector.NumberSelectorMode.BOX,
                    )),
                vol.Optional(CONF_QUOTA_START_DATE, default=self._get_val(CONF_QUOTA_START_DATE)):
                    selector.DateSelector(),
                vol.Optional(CONF_QUOTA_START_METER, default=self._get_val(CONF_QUOTA_START_METER, DEFAULT_QUOTA_START_METER)):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=RANGE_QUOTA_METER["min"], max=RANGE_QUOTA_METER["max"], step=RANGE_QUOTA_METER["step"],
                        unit_of_measurement="kWh", mode=selector.NumberSelectorMode.BOX,
                    )),
                vol.Optional(CONF_QUOTA_MONTHLY_RATE, default=self._get_val(CONF_QUOTA_MONTHLY_RATE, DEFAULT_QUOTA_MONTHLY_RATE)):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=RANGE_QUOTA_RATE["min"], max=RANGE_QUOTA_RATE["max"], step=RANGE_QUOTA_RATE["step"],
                        unit_of_measurement="€/Monat", mode=selector.NumberSelectorMode.BOX,
                    )),
            })
        )

    async def async_step_amortisation(self, user_input=None):
        """Amortisation-Persistenz: Helper + Historische Daten / Offsets."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="amortisation",
            data_schema=vol.Schema({
                # Helper fuer Persistenz der Gesamtersparnis
                vol.Required(CONF_AMORTISATION_HELPER, default=self._get_val(CONF_AMORTISATION_HELPER)):
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="input_number")
                    ),
                vol.Optional(CONF_RESTORE_FROM_HELPER, default=self._get_val(CONF_RESTORE_FROM_HELPER, False)):
                    selector.BooleanSelector(),

                # --- Historische Daten / Offsets ----------------------------
                # Ersparnis-Offset (fuer bereits amortisierten Betrag)
                vol.Optional(CONF_SAVINGS_OFFSET, default=self._get_val(CONF_SAVINGS_OFFSET, DEFAULT_SAVINGS_OFFSET)):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=RANGE_OFFSET["min"], max=RANGE_OFFSET["max"], step=RANGE_OFFSET["step"],
                        unit_of_measurement="€", mode=selector.NumberSelectorMode.BOX
                    )),

                # Energie-Offsets (fuer historische Daten vor Tracking)
                vol.Optional(CONF_ENERGY_OFFSET_SELF, default=self._get_val(CONF_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_SELF)):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=RANGE_ENERGY_OFFSET["min"], max=RANGE_ENERGY_OFFSET["max"], step=RANGE_ENERGY_OFFSET["step"],
                        unit_of_measurement="kWh", mode=selector.NumberSelectorMode.BOX
                    )),
                vol.Optional(CONF_ENERGY_OFFSET_EXPORT, default=self._get_val(CONF_ENERGY_OFFSET_EXPORT, DEFAULT_ENERGY_OFFSET_EXPORT)):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=RANGE_ENERGY_OFFSET["min"], max=RANGE_ENERGY_OFFSET["max"], step=RANGE_ENERGY_OFFSET["step"],
                        unit_of_measurement="kWh", mode=selector.NumberSelectorMode.BOX
                    )),
            }),
            description_placeholders={
                "info": "Der Helper sichert die Gesamtersparnis dauerhaft. Offsets fuer historische Daten vor Tracking-Start."
            }
        )

    async def async_step_battery(self, user_input=None):
        """Batterie-Speicher konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input, optional_entity_keys=(
                CONF_BATTERY_SOC_ENTITY, CONF_BATTERY_CHARGE_ENTITY, CONF_BATTERY_DISCHARGE_ENTITY))

        return self.async_show_form(
            step_id="battery",
            data_schema=vol.Schema({
                self._optional_entity(CONF_BATTERY_SOC_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="battery")),
                self._optional_entity(CONF_BATTERY_CHARGE_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy")),
                self._optional_entity(CONF_BATTERY_DISCHARGE_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy")),
                vol.Required(CONF_BATTERY_CAPACITY, default=self._get_val(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_BATTERY_CAPACITY["min"],
                            max=RANGE_BATTERY_CAPACITY["max"],
                            step=RANGE_BATTERY_CAPACITY["step"],
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
            })
        )

    async def async_step_benchmark(self, user_input=None):
        """Energie-Benchmark konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input, optional_entity_keys=(
                CONF_BENCHMARK_HEATPUMP_ENTITY,))

        return self.async_show_form(
            step_id="benchmark",
            data_schema=vol.Schema({
                vol.Required(CONF_BENCHMARK_ENABLED, default=self._get_val(CONF_BENCHMARK_ENABLED, DEFAULT_BENCHMARK_ENABLED)):
                    selector.BooleanSelector(),
                vol.Required(CONF_BENCHMARK_COUNTRY, default=self._get_val(CONF_BENCHMARK_COUNTRY, DEFAULT_BENCHMARK_COUNTRY)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value="AT", label="Österreich"),
                                selector.SelectOptionDict(value="DE", label="Deutschland"),
                                selector.SelectOptionDict(value="CH", label="Schweiz"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Required(CONF_BENCHMARK_HOUSEHOLD_SIZE, default=self._get_val(CONF_BENCHMARK_HOUSEHOLD_SIZE, DEFAULT_BENCHMARK_HOUSEHOLD_SIZE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_HOUSEHOLD_SIZE["min"],
                            max=RANGE_HOUSEHOLD_SIZE["max"],
                            step=RANGE_HOUSEHOLD_SIZE["step"],
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Required(CONF_BENCHMARK_HEATPUMP, default=self._get_val(CONF_BENCHMARK_HEATPUMP, DEFAULT_BENCHMARK_HEATPUMP)):
                    selector.BooleanSelector(),
                self._optional_entity(CONF_BENCHMARK_HEATPUMP_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy")),
                vol.Optional(CONF_BENCHMARK_HEATPUMP_DATE, default=self._get_val(CONF_BENCHMARK_HEATPUMP_DATE)):
                    selector.DateSelector(),
            })
        )

    async def async_step_pv_strings(self, user_input=None):
        """PV-Strings konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input, optional_entity_keys=(
                CONF_PV_STRING_1_ENTITY, CONF_PV_STRING_2_ENTITY,
                CONF_PV_STRING_3_ENTITY, CONF_PV_STRING_4_ENTITY,
                CONF_PV_STRING_1_POWER, CONF_PV_STRING_2_POWER,
                CONF_PV_STRING_3_POWER, CONF_PV_STRING_4_POWER))

        schema = {}
        for i, (name_key, entity_key, power_key, kwp_key) in enumerate([
            (CONF_PV_STRING_1_NAME, CONF_PV_STRING_1_ENTITY, CONF_PV_STRING_1_POWER, CONF_PV_STRING_1_KWP),
            (CONF_PV_STRING_2_NAME, CONF_PV_STRING_2_ENTITY, CONF_PV_STRING_2_POWER, CONF_PV_STRING_2_KWP),
            (CONF_PV_STRING_3_NAME, CONF_PV_STRING_3_ENTITY, CONF_PV_STRING_3_POWER, CONF_PV_STRING_3_KWP),
            (CONF_PV_STRING_4_NAME, CONF_PV_STRING_4_ENTITY, CONF_PV_STRING_4_POWER, CONF_PV_STRING_4_KWP),
        ], 1):
            schema[vol.Optional(name_key, default=self._get_val(name_key, ""))] = selector.TextSelector()
            entity_val = self._get_val(entity_key)
            entity_schema = vol.Optional(entity_key, description={"suggested_value": entity_val}) if entity_val else vol.Optional(entity_key)
            schema[entity_schema] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy"))
            power_val = self._get_val(power_key)
            power_schema = vol.Optional(power_key, description={"suggested_value": power_val}) if power_val else vol.Optional(power_key)
            schema[power_schema] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power"))
            schema[vol.Optional(kwp_key, default=self._get_val(kwp_key, 0.0))] = selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=50.0, step=0.01, unit_of_measurement="kWp", mode="box"))

        return self.async_show_form(
            step_id="pv_strings",
            data_schema=vol.Schema(schema)
        )

    async def async_step_forecast(self, user_input=None):
        """Lastvorhersage (24×7 Profile) konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(
                user_input,
                optional_entity_keys=(CONF_FORECAST_HP_ENTITY, CONF_FORECAST_EV_ENTITY),
            )

        return self.async_show_form(
            step_id="forecast",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_FORECAST_ENABLED,
                    default=self._get_val(CONF_FORECAST_ENABLED, DEFAULT_FORECAST_ENABLED),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_FORECAST_WEEKS,
                    default=str(self._get_val(CONF_FORECAST_WEEKS, DEFAULT_FORECAST_WEEKS)),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=str(w), label=f"{w} Wochen")
                            for w in FORECAST_WEEKS_CHOICES
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_FORECAST_MODAL_DROP,
                    default=self._get_val(CONF_FORECAST_MODAL_DROP, DEFAULT_FORECAST_MODAL_DROP),
                ): selector.BooleanSelector(),
                self._optional_entity(CONF_FORECAST_HP_ENTITY):
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                    ),
                self._optional_entity(CONF_FORECAST_EV_ENTITY):
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                    ),
            }),
            description_placeholders={
                "info": (
                    "Die Lastvorhersage lernt dein Stundenprofil nach Wochentag und liefert "
                    "Verbrauchsprognosen für 1h / 6h / Rest heute / morgen / 24h. "
                    "Wird automatisch aus dem Hausverbrauch-Sensor gebaut. Optional können "
                    "Wärmepumpe und E-Auto abgezogen werden für realistischere Basis-Last."
                )
            },
        )

    async def async_step_reset(self, user_input=None):
        """Reset-Optionen."""
        _LOGGER = logging.getLogger(__name__)

        if user_input is not None:
            target = user_input.get("reset_target")
            ctrl = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {}).get(DATA_CTRL)
            if ctrl and target:
                if target == "amortisation":
                    ctrl._total_self_consumption_kwh = 0.0
                    ctrl._total_feed_in_kwh = 0.0
                    ctrl._accumulated_savings_self = 0.0
                    ctrl._accumulated_earnings_feed = 0.0
                    ctrl._first_seen_date = None
                    ctrl._initialize_from_sensors()
                    ctrl._last_pv_production_kwh = ctrl._pv_production_kwh
                    ctrl._last_grid_export_kwh = ctrl._grid_export_kwh
                    ctrl._notify_entities()
                    _LOGGER.info("Reset via Settings: Amortisation neu initialisiert")
                elif target == "grid_import":
                    ctrl.reset_grid_import_tracking()
                    _LOGGER.info("Reset via Settings: Strompreis-Tracking zurückgesetzt")
                elif target == "benchmark":
                    ctrl.reset_benchmark_tracking()
                    _LOGGER.info("Reset via Settings: Benchmark zurückgesetzt")
                elif target == "pv_strings":
                    ctrl.reset_pv_strings_tracking()
                    _LOGGER.info("Reset via Settings: PV-Strings zurückgesetzt")
            return await self.async_step_init()

        schema = vol.Schema({
            vol.Required("reset_target"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="amortisation", label="Amortisation (re-init from sensors)"),
                        selector.SelectOptionDict(value="grid_import", label="Electricity Price Tracking"),
                        selector.SelectOptionDict(value="benchmark", label="Energy Benchmark"),
                        selector.SelectOptionDict(value="pv_strings", label="PV Strings (tracking & peaks)"),
                    ],
                    mode="dropdown",
                )
            ),
        })
        return self.async_show_form(step_id="reset", data_schema=schema)

