from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_NAME, CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_ELECTRICITY_PRICE, CONF_ELECTRICITY_PRICE_UNIT,
    CONF_FEED_IN_TARIFF, CONF_FEED_IN_TARIFF_ENTITY, CONF_FEED_IN_TARIFF_UNIT,
    CONF_INSTALLATION_COST, CONF_INSTALLATION_DATE,
    CONF_SAVINGS_OFFSET, CONF_FIXED_PRICE,
    CONF_ENERGY_OFFSET_SELF, CONF_ENERGY_OFFSET_EXPORT,
    CONF_EPEX_PRICE_ENTITY,
    CONF_QUOTA_ENABLED, CONF_QUOTA_YEARLY_KWH, CONF_QUOTA_START_DATE,
    CONF_QUOTA_START_METER, CONF_QUOTA_MONTHLY_RATE, CONF_QUOTA_SEASONAL,
    DEFAULT_NAME, DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET, DEFAULT_FIXED_PRICE,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    DEFAULT_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_EXPORT,
    DEFAULT_QUOTA_ENABLED, DEFAULT_QUOTA_YEARLY_KWH,
    DEFAULT_QUOTA_START_METER, DEFAULT_QUOTA_MONTHLY_RATE,
    DEFAULT_QUOTA_SEASONAL,
    RANGE_COST, RANGE_OFFSET, RANGE_ENERGY_OFFSET,
    RANGE_QUOTA_KWH, RANGE_QUOTA_METER, RANGE_QUOTA_RATE,
    PRICE_UNIT_EUR, PRICE_UNIT_CENT,
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
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_GRID_EXPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_GRID_IMPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_CONSUMPTION_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                # === FIXPREIS ===
                vol.Required(CONF_FIXED_PRICE, default=DEFAULT_FIXED_PRICE):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1.0, max=100.0, step=0.01,
                            unit_of_measurement="ct/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
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
                "sensors": "Sensoren",
                "prices": "Strompreise & Amortisation",
                "offsets": "Historische Daten",
                "quota": "Stromkontingent",
                "save": "Speichern & Schließen",
            },
        )

    async def _save_and_return_to_menu(self, user_input):
        """Speichert die Options und zeigt das Menü wieder an."""
        self._data.update(user_input)
        final_data = {}
        final_data.update(self.config_entry.options)
        final_data.update(self._data)
        self.hass.config_entries.async_update_entry(self.config_entry, options=final_data)
        return await self.async_step_init()

    async def async_step_sensors(self, user_input=None):
        """Energie-Sensoren konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema({
                vol.Required(CONF_PV_PRODUCTION_ENTITY, default=self._get_val(CONF_PV_PRODUCTION_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_GRID_EXPORT_ENTITY, default=self._get_val(CONF_GRID_EXPORT_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_GRID_IMPORT_ENTITY, default=self._get_val(CONF_GRID_IMPORT_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_CONSUMPTION_ENTITY, default=self._get_val(CONF_CONSUMPTION_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),

                # EPEX Spot (optional, für Vergleich)
                vol.Optional(CONF_EPEX_PRICE_ENTITY, default=self._get_val(CONF_EPEX_PRICE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            })
        )

    async def async_step_prices(self, user_input=None):
        """Strompreise und Amortisation konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="prices",
            data_schema=vol.Schema({
                # Fixpreis (Haupteinstellung)
                vol.Required(CONF_FIXED_PRICE, default=self._get_val(CONF_FIXED_PRICE, DEFAULT_FIXED_PRICE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1.0, max=100.0, step=0.01,
                            unit_of_measurement="ct/kWh",
                            mode=selector.NumberSelectorMode.BOX
                        )
                    ),

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
                vol.Optional(CONF_FEED_IN_TARIFF_ENTITY, default=self._get_val(CONF_FEED_IN_TARIFF_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),

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
            })
        )

    async def async_step_offsets(self, user_input=None):
        """Historische Daten (Offsets) konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="offsets",
            data_schema=vol.Schema({
                # Ersparnis-Offset (für bereits amortisierten Betrag)
                vol.Optional(CONF_SAVINGS_OFFSET, default=self._get_val(CONF_SAVINGS_OFFSET, DEFAULT_SAVINGS_OFFSET)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_OFFSET["min"], max=RANGE_OFFSET["max"], step=RANGE_OFFSET["step"],
                            unit_of_measurement="€", mode=selector.NumberSelectorMode.BOX
                        )
                    ),

                # Energie-Offsets (für historische Daten vor Tracking)
                vol.Optional(CONF_ENERGY_OFFSET_SELF, default=self._get_val(CONF_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_SELF)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_ENERGY_OFFSET["min"], max=RANGE_ENERGY_OFFSET["max"], step=RANGE_ENERGY_OFFSET["step"],
                            unit_of_measurement="kWh", mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                vol.Optional(CONF_ENERGY_OFFSET_EXPORT, default=self._get_val(CONF_ENERGY_OFFSET_EXPORT, DEFAULT_ENERGY_OFFSET_EXPORT)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_ENERGY_OFFSET["min"], max=RANGE_ENERGY_OFFSET["max"], step=RANGE_ENERGY_OFFSET["step"],
                            unit_of_measurement="kWh", mode=selector.NumberSelectorMode.BOX
                        )
                    ),
            })
        )

    async def async_step_quota(self, user_input=None):
        """Stromkontingent konfigurieren."""
        if user_input is not None:
            return await self._save_and_return_to_menu(user_input)

        return self.async_show_form(
            step_id="quota",
            data_schema=vol.Schema({
                vol.Required(CONF_QUOTA_ENABLED, default=self._get_val(CONF_QUOTA_ENABLED, DEFAULT_QUOTA_ENABLED)):
                    selector.BooleanSelector(),
                vol.Required(CONF_QUOTA_YEARLY_KWH, default=self._get_val(CONF_QUOTA_YEARLY_KWH, DEFAULT_QUOTA_YEARLY_KWH)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_QUOTA_KWH["min"], max=RANGE_QUOTA_KWH["max"], step=RANGE_QUOTA_KWH["step"],
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_QUOTA_START_DATE, default=self._get_val(CONF_QUOTA_START_DATE)):
                    selector.DateSelector(),
                vol.Required(CONF_QUOTA_START_METER, default=self._get_val(CONF_QUOTA_START_METER, DEFAULT_QUOTA_START_METER)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_QUOTA_METER["min"], max=RANGE_QUOTA_METER["max"], step=RANGE_QUOTA_METER["step"],
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Optional(CONF_QUOTA_MONTHLY_RATE, default=self._get_val(CONF_QUOTA_MONTHLY_RATE, DEFAULT_QUOTA_MONTHLY_RATE)):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_QUOTA_RATE["min"], max=RANGE_QUOTA_RATE["max"], step=RANGE_QUOTA_RATE["step"],
                            unit_of_measurement="€/Monat",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Required(CONF_QUOTA_SEASONAL, default=self._get_val(CONF_QUOTA_SEASONAL, DEFAULT_QUOTA_SEASONAL)):
                    selector.BooleanSelector(),
            })
        )

    async def async_step_save(self, user_input=None):
        """Speichert alle Änderungen."""
        final_data = {}
        final_data.update(self.config_entry.options)
        final_data.update(self._data)
        return self.async_create_entry(title="", data=final_data)
