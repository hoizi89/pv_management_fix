# PV Management Fixpreis

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/hoizi89/pv_management_fix)](https://github.com/hoizi89/pv_management_fix/releases)

Home Assistant integration for **fixed-price electricity tariffs** (e.g. Gruenwelt classic, Energie AG).

Calculates the amortization of your PV system and optionally compares with spot prices.

## Features

- **Amortization calculation** - How much of your PV system is already paid off?
- **Energy tracking** - Self-consumption and feed-in (incremental, persistent)
- **Savings statistics** - Per day, month, year + forecast
- **Spot comparison** (optional) - Would spot pricing have been cheaper than your fixed price?
- **Electricity quota** (new in v1.1.0) - Yearly kWh budget tracking for fixed-price tariffs

## Installation

### HACS (recommended)

1. Open HACS > Integrations > 3-dot menu > **Custom repositories**
2. Enter URL: `https://github.com/hoizi89/pv_management_fix`
3. Category: **Integration**
4. Search for the integration and install
5. **Restart** Home Assistant

### Manual

1. Copy `custom_components/pv_management_fix` folder to `config/custom_components/`
2. Restart Home Assistant

## Configuration

1. Settings > Devices & Services > **Add Integration**
2. Search for "PV Management Fixpreis"
3. Select sensors:
   - **PV Production** (required) - kWh counter
   - **Grid Export** (optional) - for feed-in earnings
   - **Grid Import** (optional) - for spot comparison & electricity quota
4. Enter your **fixed price** (default: 10.92 ct/kWh)
5. Enter **installation cost**

## Sensors

| Sensor | Description |
|--------|-------------|
| Amortisation | Percentage of system paid off |
| Gesamtersparnis | Total savings in EUR |
| Restbetrag | Remaining EUR until full amortization |
| Status | Text ("45% amortisiert" / "Amortisiert! +500 EUR") |
| Restlaufzeit | Days until amortization (forecast) |
| Amortisationsdatum | Estimated payback date |
| Eigenverbrauch | kWh self-consumed |
| Einspeisung | kWh fed into grid |
| Eigenverbrauchsquote | % of PV production self-consumed |
| Autarkiegrad | % of consumption covered by PV |
| Ersparnis pro Tag/Monat/Jahr | Average savings |
| CO2 Ersparnis | kg CO2 saved |
| Fixpreis vs Spot | EUR saved vs. spot tariff (optional) |

### Electricity Quota Sensors (v1.1.0)

When enabled, these sensors appear under a separate "Stromkontingent" device:

| Sensor | Description |
|--------|-------------|
| Kontingent Verbleibend | Remaining kWh in yearly quota |
| Kontingent Verbrauch | Percentage of yearly quota consumed |
| Kontingent Reserve | kWh ahead/behind linear budget (positive = good) |
| Kontingent Tagesbudget | Daily kWh budget for remaining period |
| Kontingent Prognose | Projected yearly consumption at current rate |
| Kontingent Restlaufzeit | Days remaining in tariff period |
| Kontingent Status | Text summary ("Im Budget (+180 kWh)" or "Ueber Budget (-50 kWh)") |

## Options (changeable after setup)

### Sensors
- PV Production, Grid Export, Grid Import, Consumption
- EPEX Spot Price (optional, for comparison)

### Electricity Prices & Amortization
- **Fixed price** (ct/kWh) - your tariff
- **Feed-in tariff** (EUR/kWh or ct/kWh)
- **Installation cost** (EUR)
- **Installation date**

### Historical Data
- Already amortized amount (EUR)
- Self-consumption / export before tracking (kWh)

### Electricity Quota
- **Enable/disable** quota tracking
- **Yearly quota** in kWh (e.g. 4000)
- **Period start date** (from your invoice, doesn't have to be Jan 1)
- **Meter reading at start** (grid import counter at period start)
- **Monthly payment** (optional, display only)

## Dashboard Example

```yaml
type: entities
title: PV Fixed Price
entities:
  - entity: sensor.pv_fixpreis_status
  - entity: sensor.pv_fixpreis_amortisation
  - entity: sensor.pv_fixpreis_gesamtersparnis
  - entity: sensor.pv_fixpreis_restbetrag
  - entity: sensor.pv_fixpreis_restlaufzeit
  - type: divider
  - entity: sensor.pv_fixpreis_eigenverbrauch
  - entity: sensor.pv_fixpreis_einspeisung
  - entity: sensor.pv_fixpreis_eigenverbrauchsquote
  - type: divider
  - entity: sensor.pv_fixpreis_ersparnis_pro_monat
  - entity: sensor.pv_fixpreis_co2_ersparnis
```

### Electricity Quota Dashboard

```yaml
type: entities
title: Electricity Quota
entities:
  - entity: sensor.pv_fixpreis_kontingent_status
  - entity: sensor.pv_fixpreis_kontingent_verbleibend
  - entity: sensor.pv_fixpreis_kontingent_verbrauch
  - entity: sensor.pv_fixpreis_kontingent_reserve
  - entity: sensor.pv_fixpreis_kontingent_tagesbudget
  - entity: sensor.pv_fixpreis_kontingent_prognose
  - entity: sensor.pv_fixpreis_kontingent_restlaufzeit
```

## Difference to pv_management

This integration is optimized for **fixed-price tariffs**.

For **spot tariffs** (aWATTar, smartENERGY) with battery management use:
[pv_management](https://github.com/hoizi89/pv_management)

| Feature | pv_management | pv_management_fix |
|---------|--------------|-------------------|
| Amortization | Yes | Yes |
| Energy Tracking | Yes | Yes |
| Electricity Quota | No | Yes |
| Recommendation Signal | Yes | No |
| Auto-Charge | Yes | No |
| Discharge Control | Yes | No |
| EPEX Quantile | Yes | No |
| Solcast | Yes | No |
| Spot Comparison | Yes | Yes (optional) |

## Changelog

### v1.1.0
- New: Electricity quota (Stromkontingent) - yearly kWh budget tracking
- 7 new sensors: remaining, consumed %, reserve, daily budget, forecast, days remaining, status
- New options page for quota configuration
- Translations DE/EN

### v1.0.0
- Initial release
- Amortization calculation with fixed price
- Energy tracking (self-consumption, feed-in)
- Savings statistics (day/month/year)
- Optional: Spot comparison with EPEX

## Support

[Report issues](https://github.com/hoizi89/pv_management_fix/issues)

## License

MIT License - see [LICENSE](LICENSE)
