from __future__ import annotations

from datetime import date
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_NAME, CONF_PV_PRODUCTION_ENTITY, CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY, CONF_CONSUMPTION_ENTITY,
    CONF_ELECTRICITY_PRICE, CONF_ELECTRICITY_PRICE_ENTITY, CONF_ELECTRICITY_PRICE_UNIT,
    CONF_FEED_IN_TARIFF, CONF_FEED_IN_TARIFF_ENTITY, CONF_FEED_IN_TARIFF_UNIT,
    CONF_INSTALLATION_COST, CONF_SAVINGS_OFFSET,
    CONF_ENERGY_OFFSET_SELF, CONF_ENERGY_OFFSET_EXPORT,
    CONF_INSTALLATION_DATE,
    DEFAULT_NAME, DEFAULT_ELECTRICITY_PRICE, DEFAULT_FEED_IN_TARIFF,
    DEFAULT_INSTALLATION_COST, DEFAULT_SAVINGS_OFFSET,
    DEFAULT_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_EXPORT,
    DEFAULT_ELECTRICITY_PRICE_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT,
    RANGE_PRICE_EUR, RANGE_PRICE_CENT, RANGE_TARIFF_EUR, RANGE_TARIFF_CENT,
    RANGE_COST, RANGE_OFFSET, RANGE_ENERGY_OFFSET,
    PRICE_UNIT_EUR, PRICE_UNIT_CENT,
)


class PVAmortisationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow für PV Amortisation."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Erster Schritt: Basis-Konfiguration."""
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,

                # PV Produktion (Pflicht)
                vol.Required(CONF_PV_PRODUCTION_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),

                # Grid Export (Optional, für genaue Eigenverbrauchsberechnung)
                vol.Optional(CONF_GRID_EXPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),

                # Grid Import (Optional)
                vol.Optional(CONF_GRID_IMPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),

                # Hausverbrauch (Optional)
                vol.Optional(CONF_CONSUMPTION_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),

                # Strompreis-Einheit
                vol.Required(CONF_ELECTRICITY_PRICE_UNIT, default=DEFAULT_ELECTRICITY_PRICE_UNIT):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh (€/kWh)"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh (ct/kWh)"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),

                # Strompreis
                vol.Required(CONF_ELECTRICITY_PRICE, default=DEFAULT_ELECTRICITY_PRICE):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0,
                            max=100.0,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # Dynamischer Strompreis (Optional)
                vol.Optional(CONF_ELECTRICITY_PRICE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                # Einspeisevergütung-Einheit
                vol.Required(CONF_FEED_IN_TARIFF_UNIT, default=DEFAULT_FEED_IN_TARIFF_UNIT):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh (€/kWh)"),
                                selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh (ct/kWh)"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),

                # Einspeisevergütung
                vol.Required(CONF_FEED_IN_TARIFF, default=DEFAULT_FEED_IN_TARIFF):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0,
                            max=50.0,
                            step=0.001,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # Dynamische Einspeisevergütung (Optional)
                vol.Optional(CONF_FEED_IN_TARIFF_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                # Anschaffungskosten
                vol.Required(CONF_INSTALLATION_COST, default=DEFAULT_INSTALLATION_COST):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_COST["min"],
                            max=RANGE_COST["max"],
                            step=RANGE_COST["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # Installations-Datum (Optional)
                vol.Optional(CONF_INSTALLATION_DATE): selector.DateSelector(),

                # Bereits amortisierter Betrag (Offset)
                vol.Optional(CONF_SAVINGS_OFFSET, default=DEFAULT_SAVINGS_OFFSET):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_OFFSET["min"],
                            max=RANGE_OFFSET["max"],
                            step=RANGE_OFFSET["step"],
                            unit_of_measurement="€",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # Energie-Offset Eigenverbrauch
                vol.Optional(CONF_ENERGY_OFFSET_SELF, default=DEFAULT_ENERGY_OFFSET_SELF):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_ENERGY_OFFSET["min"],
                            max=RANGE_ENERGY_OFFSET["max"],
                            step=RANGE_ENERGY_OFFSET["step"],
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),

                # Energie-Offset Einspeisung
                vol.Optional(CONF_ENERGY_OFFSET_EXPORT, default=DEFAULT_ENERGY_OFFSET_EXPORT):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RANGE_ENERGY_OFFSET["min"],
                            max=RANGE_ENERGY_OFFSET["max"],
                            step=RANGE_ENERGY_OFFSET["step"],
                            unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
            })
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return PVAmortisationOptionsFlow(config_entry)


class PVAmortisationOptionsFlow(config_entries.OptionsFlow):
    """Options Flow für nachträgliche Anpassungen."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Options bearbeiten."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Aktuelle Werte laden
        opts = {**self.config_entry.data, **self.config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                # === SENSOREN (können nachträglich geändert werden) ===

                # PV Produktion
                vol.Required(
                    CONF_PV_PRODUCTION_ENTITY,
                    default=opts.get(CONF_PV_PRODUCTION_ENTITY)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),

                # Grid Export
                vol.Optional(
                    CONF_GRID_EXPORT_ENTITY,
                    description={"suggested_value": opts.get(CONF_GRID_EXPORT_ENTITY)}
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),

                # Grid Import
                vol.Optional(
                    CONF_GRID_IMPORT_ENTITY,
                    description={"suggested_value": opts.get(CONF_GRID_IMPORT_ENTITY)}
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),

                # Hausverbrauch
                vol.Optional(
                    CONF_CONSUMPTION_ENTITY,
                    description={"suggested_value": opts.get(CONF_CONSUMPTION_ENTITY)}
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),

                # === PREISE ===

                # Strompreis-Einheit
                vol.Required(
                    CONF_ELECTRICITY_PRICE_UNIT,
                    default=opts.get(CONF_ELECTRICITY_PRICE_UNIT, DEFAULT_ELECTRICITY_PRICE_UNIT)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh (€/kWh)"),
                            selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh (ct/kWh)"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),

                # Strompreis
                vol.Required(
                    CONF_ELECTRICITY_PRICE,
                    default=opts.get(CONF_ELECTRICITY_PRICE, DEFAULT_ELECTRICITY_PRICE)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=100.0,
                        step=0.01,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                # Dynamischer Strompreis
                vol.Optional(
                    CONF_ELECTRICITY_PRICE_ENTITY,
                    description={"suggested_value": opts.get(CONF_ELECTRICITY_PRICE_ENTITY)}
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                # Einspeisevergütung-Einheit
                vol.Required(
                    CONF_FEED_IN_TARIFF_UNIT,
                    default=opts.get(CONF_FEED_IN_TARIFF_UNIT, DEFAULT_FEED_IN_TARIFF_UNIT)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=PRICE_UNIT_EUR, label="Euro pro kWh (€/kWh)"),
                            selector.SelectOptionDict(value=PRICE_UNIT_CENT, label="Cent pro kWh (ct/kWh)"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),

                # Einspeisevergütung
                vol.Required(
                    CONF_FEED_IN_TARIFF,
                    default=opts.get(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=50.0,
                        step=0.001,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                # Dynamische Einspeisevergütung
                vol.Optional(
                    CONF_FEED_IN_TARIFF_ENTITY,
                    description={"suggested_value": opts.get(CONF_FEED_IN_TARIFF_ENTITY)}
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),

                # Anschaffungskosten
                vol.Required(
                    CONF_INSTALLATION_COST,
                    default=opts.get(CONF_INSTALLATION_COST, DEFAULT_INSTALLATION_COST)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=RANGE_COST["min"],
                        max=RANGE_COST["max"],
                        step=RANGE_COST["step"],
                        unit_of_measurement="€",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                # Installations-Datum
                vol.Optional(
                    CONF_INSTALLATION_DATE,
                    description={"suggested_value": opts.get(CONF_INSTALLATION_DATE)}
                ): selector.DateSelector(),

                # Ersparnis-Offset
                vol.Optional(
                    CONF_SAVINGS_OFFSET,
                    default=opts.get(CONF_SAVINGS_OFFSET, DEFAULT_SAVINGS_OFFSET)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=RANGE_OFFSET["min"],
                        max=RANGE_OFFSET["max"],
                        step=RANGE_OFFSET["step"],
                        unit_of_measurement="€",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                # Energie-Offset Eigenverbrauch
                vol.Optional(
                    CONF_ENERGY_OFFSET_SELF,
                    default=opts.get(CONF_ENERGY_OFFSET_SELF, DEFAULT_ENERGY_OFFSET_SELF)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=RANGE_ENERGY_OFFSET["min"],
                        max=RANGE_ENERGY_OFFSET["max"],
                        step=RANGE_ENERGY_OFFSET["step"],
                        unit_of_measurement="kWh",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                # Energie-Offset Einspeisung
                vol.Optional(
                    CONF_ENERGY_OFFSET_EXPORT,
                    default=opts.get(CONF_ENERGY_OFFSET_EXPORT, DEFAULT_ENERGY_OFFSET_EXPORT)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=RANGE_ENERGY_OFFSET["min"],
                        max=RANGE_ENERGY_OFFSET["max"],
                        step=RANGE_ENERGY_OFFSET["step"],
                        unit_of_measurement="kWh",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            })
        )
