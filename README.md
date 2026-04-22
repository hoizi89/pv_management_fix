# PV Energy Management+

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/hoizi89/pv_management_fix)](https://github.com/hoizi89/pv_management_fix/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> The all-in-one Home Assistant integration for your PV system with **fixed-price tariffs**.

> **For spot/variable tariffs** (aWATTar, smartENERGY, Tibber) with battery management:
> [pv_management](https://github.com/hoizi89/pv_management)

---

## What Can This Integration Do?

| Feature | Description |
|---------|-------------|
| **Amortization** | See in real-time how much of your PV system is paid off |
| **Energy Benchmark** | Compare your consumption with AT/DE/CH averages |
| **Battery Tracking** | SOC, efficiency, cycles — all at a glance |
| **Electricity Quota** | Yearly kWh budget with seasonal weighting |
| **ROI Calculation** | Return on Investment — before and after amortization |
| **Daily Costs** | Grid import, feed-in, and net electricity cost per day |
| **PV-Strings** | Compare up to 4 PV strings — production, peak power, efficiency (kWh/kWp) |
| **Load Forecast** *(v2.0)* | 24×7 hour-of-day × day-of-week profile — predicts 1 h / 6 h / today / tomorrow / 24 h consumption |
| **Notifications** | Milestones, quota warnings, monthly reports |

---

## New in v2.0.0: Load Forecast (24×7 Profile) 🆕

Your house consumption follows a pattern — mornings, evenings, weekends differ. The integration now
learns that pattern automatically and produces **5 new sensors** to drive battery / charge / discharge
decisions alongside your solar forecast and dynamic prices.

### How it works

1. **Data source**: Your `consumption_entity` (house consumption kWh), pulled hourly from HA's built-in
   `recorder.statistics_during_period` API — no external service, no ML model, no additional containers.
2. **24×7 matrix**: for every combination of `(hour-of-day, weekday)` we keep a rolling window of
   2 / 4 / 6 weeks (you choose) and take the mean of that cell.
3. **Modal-drop** (on by default): per cell the single highest and single lowest value are thrown away
   before averaging. This cleans out holidays, power-outages, one-off EV charges.
4. **Optional subtraction**: if you configure a heat-pump or EV total-energy sensor they are subtracted
   from the whole-house consumption before the matrix is built — you get a clean "base-load" forecast.
5. **Graceful fallbacks**: <14 days of history → 7-day rolling mean. <3 days → persistence ("this
   hour last week"). No history → sensors become `unavailable` instead of crashing.

Typical accuracy (MAPE) for residential loads at 24 h horizon: **18–30%** — same ballpark as the
algorithms inside Predbat / EMHASS, but with zero setup.

### The 5 new sensors

| Sensor | Returns | Typical use |
|---|---|---|
| `sensor.*_verbrauch_prognose_1h` | kWh expected next hour | Short-term battery dispatch |
| `sensor.*_verbrauch_prognose_6h` | kWh over the next 6 h | Evening peak planning |
| `sensor.*_verbrauch_prognose_heute_rest` | kWh from now until midnight | Rest-of-today budget |
| `sensor.*_verbrauch_prognose_morgen` | kWh tomorrow (00:00 – 23:00) | Overnight charge decision |
| `sensor.*_verbrauch_prognose_24h` | rolling 24 h from now | Main signal for charge logic |

**Bonus**: the *Morgen* and *24h* sensors carry a `forecast_hourly` attribute (list of 24 values) —
drop it into ApexCharts to get the Victron-style side-by-side "solar vs. load" bar chart shown in the
feature request that inspired this. They also expose `confidence_low` / `confidence_high` (±1σ over
the history window) so your automations can stay on the safe side.

### How to enable

`Settings → Devices → PV Energy Management+ → Configure → Load Forecast`

1. Toggle **Enable load forecast** on.
2. Pick **History window** — 4 weeks is the sweet spot.
3. Leave **Filter outlier days** on unless you know why not.
4. Optionally point **Heat pump** / **EV charger** to the respective total-energy sensors.

The forecaster rebuilds once per hour in the background — it never blocks the event loop.

> **Not available when**: no `consumption_entity` is configured. Set one under Options → Sensors first.

### Attributes at a glance

```yaml
method: 24x7_profile        # or fallback_7d_mean / fallback_persistence / warming_up
days_of_history: 28
base_load_only: true        # true if HP/EV are subtracted
last_update: '2026-04-22T07:00:00+00:00'
forecast_hourly: [0.25, 0.23, 0.22, ..., 1.1, 0.9]  # 24 values (on Morgen/24h sensors)
confidence_low: 18.4        # sum − 1σ
confidence_high: 23.1       # sum + 1σ
```

Planned for a later release: a binary-sensor that combines this with Solcast + price for an explicit
charge/discharge recommendation. For now you build that yourself via a template — the building blocks
are here.

---

## New in v1.14.0: Annual PV Production & Specific Yield

Track how well your PV system performs!

- **Annual PV Production (kWh/year):** Extrapolated from benchmark tracking period
- **Specific Yield (kWh/kWp):** Annual production per installed capacity — the standard metric for PV performance
- **Per-string Specific Yield:** Compare strings fairly based on their installed kWp
- **Performance Ratio (%):** Measured peak vs. installed capacity — shows how close a string gets to nameplate power
- **Installed capacity (kWp)** per string as optional config — falls back to measured peaks if not set
- Uses the sum of all string kWp for the system-wide specific yield

| Sensor | What it shows | Example |
|--------|--------------|---------|
| Jahresproduktion | Annual PV production (extrapolated) | 14,200 kWh/year |
| Spezifischer Ertrag | Annual production per kWp | 967 kWh/kWp |
| Osten Spez. Ertrag | Per-string specific yield | 890 kWh/kWp |
| Osten Performance Ratio | Peak vs. installed capacity | 92.5% |

> Tip: In Austria/Germany, 900-1100 kWh/kWp per year is typical. Specific yield helps you spot underperforming strings.

---

## PV-String Comparison

Compare up to 4 PV strings — with optional power sensor and installed capacity.

| Sensor | What it shows | Example |
|--------|--------------|---------|
| {Name} Produktion | Total tracked kWh | 670 kWh |
| {Name} Tagesproduktion | Average kWh per day | 4.5 kWh/day |
| {Name} Anteil | Share of total production | 35% |
| {Name} Peak | Highest power ever recorded (requires power sensor) | 3.2 kW |
| {Name} Spez. Ertrag | Annual kWh per installed kWp (requires kWp or power sensor) | 890 kWh/kWp |
| {Name} Performance Ratio | Measured peak vs. installed capacity (requires both) | 92.5% |

---

## New in v1.9.0: Energy Benchmark

Compare your electricity consumption with the average for your country — **completely offline**, no cloud needed.

- **Countries:** Austria, Germany, Switzerland
- **Household size:** 1-6 persons
- **6 sensors:** Average, own consumption, comparison (%), CO2 avoided, efficiency score (0-100), rating
- **Heat pump optional:** HP consumption is benchmarked separately for fair comparison

| Sensor | What it shows | Example |
|--------|--------------|---------|
| Benchmark Average | Reference consumption for your country/household | 4000 kWh/year |
| Benchmark Own Consumption | Your consumption extrapolated to 1 year | 3200 kWh/year |
| Benchmark Comparison | Deviation from average | -20% |
| Benchmark CO2 Avoided | CO2 savings from PV per year | 180 kg/year |
| Benchmark Efficiency Score | Overall rating 0-100 | 72 points |
| Benchmark Rating | Text classification | "Sehr gut" |

---

## Installation

### HACS (recommended)

1. Open HACS > Integrations > 3-dot menu > **Custom repositories**
2. URL: `https://github.com/hoizi89/pv_management_fix`
3. Category: **Integration**
4. Install and **restart** Home Assistant

### Manual

Copy `custom_components/pv_management_fix` to `config/custom_components/`, then restart.

---

## Quick Start

1. **Settings** > Devices & Services > **Add Integration**
2. Search for "PV Energy Management+"
3. Select your sensors:
   - **PV Production** (required) — kWh counter
   - **Grid Export** (optional) — for earnings calculation
   - **Grid Import** (optional) — for quota & cost tracking
   - **Consumption** (optional) — for autarky rate
4. Enter **fixed price** (e.g. 10.92 ct/kWh net)
5. Set **markup factor** (default: 2.0 — turns 10ct net into 20ct gross)
6. Configure **installation cost** and **Amortization Helper** (input_number)

> All settings can be changed later under **Options**.

---

## Sensors Overview

### Main Device: PV Fixpreis

| Sensor | Unit | Description |
|--------|------|-------------|
| Amortization | % | How much of the system is paid off |
| Total Savings | EUR | Savings from self-consumption + feed-in |
| Remaining Cost | EUR | Remaining until amortization |
| Status | — | e.g. "45.2% amortized" or "Amortized! +500 EUR profit" |
| Remaining Days | Days | Estimated days until amortization |
| Amortization Date | Date | When the system will be paid off |
| Self Consumption | kWh | PV electricity consumed directly |
| Feed-in | kWh | PV electricity exported to grid |
| Self Consumption Ratio | % | Share of PV production used directly |
| Autarky Rate | % | Share of consumption covered by PV |
| Savings per Day/Month/Year | EUR | Average savings |
| CO2 Savings | kg | Avoided CO2 emissions |
| ROI | % | Return on Investment |
| ROI per Year | %/year | Annual ROI |
| Electricity Price Gross | EUR/kWh | For Energy Dashboard |

### Device: Electricity Prices

| Sensor | Unit | Description |
|--------|------|-------------|
| Feed-in Today | EUR | Today's feed-in earnings |
| Grid Import Today | EUR | Today's grid import cost |
| Net Electricity Cost Today | EUR | Grid import minus feed-in |

### Device: Energy Benchmark (optional)

Appears when enabled under Options > Energy Benchmark.

| Sensor | Unit | Description |
|--------|------|-------------|
| Durchschnitt | kWh/year | Reference consumption (E-Control/BDEW/BFE) |
| Eigener Verbrauch | kWh/year | Your household consumption extrapolated |
| Netzbezug Jahres | kWh/year | Annual grid import extrapolated |
| Jahresproduktion | kWh/year | Annual PV production extrapolated |
| Spezifischer Ertrag | kWh/kWp | Annual production per installed kWp (requires PV strings) |
| Vergleich | % | Deviation (negative = better than average) |
| CO2 Vermieden | kg/year | CO2 savings from PV |
| Effizienz Score | Points | 0-100 overall rating (see breakdown below) |
| Bewertung | — | Hervorragend / Sehr gut / Gut / Durchschnittlich |
| WP Durchschnitt | kWh/year | Reference HP consumption (only with HP) |
| WP Verbrauch | kWh/year | Your HP consumption (only with HP) |

#### Efficiency Score Breakdown

The score (0-100 points) measures how well your PV system is performing. The sensor attributes show the detailed breakdown.

| Component | Max Points | How it works |
|-----------|-----------|--------------|
| **Autarky Rate** | 35 | How independent you are from the grid. 100% autarky = 35 points |
| **Specific Yield** | 25 | How well your system is utilized. 900 kWh/kWp (good for Central Europe) = 25 points |
| **Self-Consumption Ratio** | 20 | How much PV production you use yourself. 100% = 20 points |
| **Consumption vs Average** | 20 | Your consumption compared to country average. -50% below avg = 20 points |

**Score interpretation:**
- **80-100**: Excellent — highly optimized system with good autarky and utilization
- **60-79**: Very good — solid performance, minor optimization potential
- **40-59**: Good — typical residential PV system
- **20-39**: Average — significant room for improvement
- **0-19**: Needs improvement — consider battery storage or load shifting

**Tips to improve your score:**
- A battery improves both autarky and self-consumption
- Shift heavy loads to daytime (dishwasher, washing machine, EV charging)
- Smart heat pump control (heat during solar hours)
- Check your string orientation — specific yield shows how well each string performs

### Device: PV-Strings (optional)

Appears when at least one PV string is configured under Options > PV-Strings.

| Sensor | Unit | Description |
|--------|------|-------------|
| {Name} Produktion | kWh | Total tracked production for this string |
| {Name} Tagesproduktion | kWh/day | Average daily production |
| {Name} Anteil | % | Share of total string production |
| {Name} Peak | kW | Highest power ever recorded (requires power sensor) |
| {Name} Spez. Ertrag | kWh/kWp | Annual production per kWp (requires kWp or power sensor) |
| {Name} Performance Ratio | % | Measured peak vs. installed capacity (requires kWp + power) |

### Device: Battery (optional)

Appears when at least one battery sensor is configured.

| Sensor | Unit | Description |
|--------|------|-------------|
| Battery SOC | % | State of charge with dynamic icon |
| Battery Charge Total | kWh | Total energy charged into battery |
| Battery Discharge Total | kWh | Total energy discharged from battery |
| Battery Efficiency | % | Discharge / Charge x 100 |
| Battery Cycles | Cycles | Estimated: Charge / Capacity |

### Device: Electricity Quota (optional)

Appears when the quota is enabled.

| Sensor | Unit | Description |
|--------|------|-------------|
| Quota Remaining | kWh | Remaining kWh in yearly budget |
| Quota Usage | % | Percent of quota used |
| Quota Reserve | kWh | Over/under budget (positive = good) |
| Quota Daily Budget | kWh/day | Allowed daily consumption |
| Quota Today Remaining | kWh | Daily budget minus today's consumption |
| Quota Forecast | kWh | Yearly consumption projection |
| Quota Remaining Days | Days | Remaining days in period |
| Quota Status | — | Text summary |

---

## Options (configurable after setup)

Under **Settings > Devices & Services > PV Energy Management+ > Configure**:

| Category | What you can configure |
|----------|----------------------|
| **Sensors** | PV Production, Grid Export, Grid Import, Consumption |
| **Electricity Prices** | Fixed price, markup factor, dynamic sensor, feed-in tariff |
| **Amortization Helper** | input_number for persistent storage |
| **Historical Data** | Already amortized amount, energy offsets |
| **Electricity Quota** | Yearly kWh, start date, meter reading, seasonal calculation |
| **Battery** | SOC, charge/discharge sensors, capacity |
| **Energy Benchmark** | Country, household size, heat pump |
| **PV-Strings** | Up to 4 strings with name, kWh sensor, optional power sensor (W), and optional installed capacity (kWp) |

---

## Energy Dashboard

Use `sensor.pv_fixpreis_strompreis_brutto` as the electricity price entity in the Home Assistant Energy Dashboard. The sensor outputs the gross price in `EUR/kWh`.

---

## Dashboard Examples

### Amortization

```yaml
type: entities
title: PV Amortization
entities:
  - entity: sensor.pv_fixpreis_status
  - entity: sensor.pv_fixpreis_amortisation
  - entity: sensor.pv_fixpreis_gesamtersparnis
  - entity: sensor.pv_fixpreis_restbetrag
  - entity: sensor.pv_fixpreis_restlaufzeit
  - entity: sensor.pv_fixpreis_roi
  - type: divider
  - entity: sensor.pv_fixpreis_eigenverbrauch
  - entity: sensor.pv_fixpreis_einspeisung
  - entity: sensor.pv_fixpreis_eigenverbrauchsquote
  - type: divider
  - entity: sensor.pv_fixpreis_ersparnis_pro_monat
  - entity: sensor.pv_fixpreis_co2_ersparnis
```

### Energy Benchmark

```yaml
type: entities
title: Energy Benchmark
entities:
  - entity: sensor.pv_fixpreis_benchmark_effizienz_score
  - entity: sensor.pv_fixpreis_benchmark_bewertung
  - type: divider
  - entity: sensor.pv_fixpreis_benchmark_eigener_verbrauch
  - entity: sensor.pv_fixpreis_benchmark_durchschnitt
  - entity: sensor.pv_fixpreis_benchmark_vergleich
  - type: divider
  - entity: sensor.pv_fixpreis_benchmark_co2_vermieden
```

### Battery

```yaml
type: entities
title: Battery
entities:
  - entity: sensor.pv_fixpreis_batterie_ladestand
  - entity: sensor.pv_fixpreis_batterie_effizienz
  - entity: sensor.pv_fixpreis_batterie_zyklen
  - entity: sensor.pv_fixpreis_batterie_ladung_gesamt
  - entity: sensor.pv_fixpreis_batterie_entladung_gesamt
```

### Electricity Quota

```yaml
type: entities
title: Electricity Quota
entities:
  - entity: sensor.pv_fixpreis_kontingent_status
  - entity: sensor.pv_fixpreis_kontingent_verbleibend
  - entity: sensor.pv_fixpreis_kontingent_verbrauch
  - entity: sensor.pv_fixpreis_kontingent_reserve
  - entity: sensor.pv_fixpreis_kontingent_tagesbudget
  - entity: sensor.pv_fixpreis_kontingent_heute_verbleibend
  - entity: sensor.pv_fixpreis_kontingent_prognose
```

### Daily Costs

```yaml
type: entities
title: Electricity Costs Today
entities:
  - entity: sensor.pv_fixpreis_netzbezug_heute
  - entity: sensor.pv_fixpreis_einspeisung_heute
  - entity: sensor.pv_fixpreis_stromkosten_netto_heute
```

---

## Events (Notifications)

The integration fires `pv_management_event` events for custom automations:

### Milestone Events (25%, 50%, 75%, 100%)

```yaml
trigger:
  - platform: event
    event_type: pv_management_event
    event_data:
      type: amortisation_milestone
action:
  - service: notify.mobile_app
    data:
      title: "PV Milestone!"
      message: "{{ trigger.event.data.message }}"
```

### Quota Warnings

```yaml
trigger:
  - platform: event
    event_type: pv_management_event
    event_data:
      type: quota_warning_80
action:
  - service: notify.mobile_app
    data:
      title: "Electricity Quota"
      message: "{{ trigger.event.data.message }}"
```

---

## Comparison: pv_management vs pv_management_fix

| Feature | pv_management (Spot) | pv_management_fix (Fixed) |
|---------|:--------------------:|:-------------------------:|
| Amortization | Yes | Yes |
| Energy Tracking | Yes | Yes |
| **Energy Benchmark** | **Yes** | **Yes** |
| **PV-Strings** | **Yes** | **Yes** |
| Battery Tracking | No | **Yes** |
| ROI Calculation | No | **Yes** |
| Electricity Quota | No | **Yes** |
| Daily Costs | Yes | **Yes** |
| Recommendation Signal | **Yes** | No |
| Auto-Charge | **Yes** | No |
| Discharge Control | **Yes** | No |
| EPEX Quantile | **Yes** | No |
| Solcast | **Yes** | No |

For **spot tariffs** (aWATTar, smartENERGY) with battery management:
[pv_management](https://github.com/hoizi89/pv_management)

---

## Changelog

### v1.14.0
- **NEW: Annual PV Production** — Extrapolated yearly PV production from benchmark tracking
- **NEW: Specific Yield (kWh/kWp)** — System-wide and per-string, using installed capacity or measured peaks as fallback
- **NEW: Performance Ratio** — Per-string comparison of measured peak vs. installed nameplate capacity
- **NEW: Installed capacity (kWp)** — Optional config per PV string for accurate specific yield
- **NEW: Netzbezug Jahres** — Annual grid import extrapolated from benchmark period
- Benchmark now uses snapshot-based tracking (independent lifecycle, proper reset)
- Removed "Benchmark" prefix from sensor names (device grouping provides context)
- WP sensor Wh→kWh auto-conversion safety net

### v1.9.6
- **NEW: PV-String Peak & Efficiency** — Optional power sensor (W) per string for automatic peak tracking (kW) and efficiency calculation (kWh/kWp)
- Fair comparison of strings with different module counts

### v1.9.0
- **NEW: Energy Benchmark** — Compare with DACH averages (AT/DE/CH), CO2 savings, efficiency score 0-100
- **NEW: Heat Pump** — Optional HP sensor for fair benchmark comparison
- **Rename:** "PV Management Fixpreis" -> "PV Energy Management+"
- Domain and entity IDs remain unchanged (no breaking change)

### v1.8.1
- Fix: `remaining_amount` -> `remaining_cost` (crash on milestones)
- Fix: Missing "Helper" menu translation

### v1.8.0
- NEW: Battery tracking (SOC, charge, discharge, efficiency, cycles)
- NEW: ROI sensors (Return on Investment + annual ROI)
- Fix: Quota sensors appear without HA restart

### v1.7.1
- Battery-compatible self-consumption and autarky rate calculation

### v1.5.0
- NEW: Markup factor for automatic gross price calculation
- NEW: Energy Dashboard sensor (EUR/kWh)

### v1.4.0
- NEW: Helper sync, milestone events, quota warnings, monthly summary

### v1.1.0
- NEW: Electricity quota (yearly kWh budget)

### v1.0.0
- Initial release

---

## Support

[Report issues](https://github.com/hoizi89/pv_management_fix/issues) | [Discussions](https://github.com/hoizi89/pv_management_fix/discussions)

## License

MIT License — see [LICENSE](LICENSE)
