# PV Management Fixpreis

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/hoizi89/pv_management_fix)](https://github.com/hoizi89/pv_management_fix/releases)

Home Assistant Integration für **Fixpreis-Stromtarife** (z.B. Grünwelt classic, Energie AG).

Berechnet die Amortisation deiner PV-Anlage und vergleicht optional mit Spot-Preisen.

## Features

- **Amortisationsberechnung** - Wieviel deiner PV-Anlage ist bereits abbezahlt?
- **Energie-Tracking** - Eigenverbrauch und Einspeisung (inkrementell, persistent)
- **Ersparnis-Statistiken** - Pro Tag, Monat, Jahr + Prognose
- **Spot-Vergleich** (optional) - War Fixpreis günstiger als Spot gewesen wäre?

## Installation

### HACS (empfohlen)

1. HACS öffnen → Integrationen → 3-Punkte-Menü → **Benutzerdefinierte Repositories**
2. URL eingeben: `https://github.com/hoizi89/pv_management_fix`
3. Kategorie: **Integration**
4. Integration suchen und installieren
5. Home Assistant **neu starten**

### Manuell

1. `custom_components/pv_management_fix` Ordner nach `config/custom_components/` kopieren
2. Home Assistant neu starten

## Konfiguration

1. Einstellungen → Geräte & Dienste → **Integration hinzufügen**
2. "PV Management Fixpreis" suchen
3. Sensoren auswählen:
   - **PV Produktion** (Pflicht) - kWh Zähler
   - **Netzeinspeisung** (optional) - für Einspeisevergütung
   - **Netzbezug** (optional) - für Spot-Vergleich
4. **Fixpreis** eingeben (Default: 10.92 ct/kWh)
5. **Anschaffungskosten** eingeben

## Sensoren

| Sensor | Beschreibung |
|--------|--------------|
| Amortisation | Prozent der abbezahlten Anlage |
| Gesamtersparnis | Euro gespart durch PV |
| Restbetrag | Euro bis zur vollständigen Amortisation |
| Status | Text ("45% amortisiert" / "Amortisiert! +500€ Gewinn") |
| Restlaufzeit | Tage bis Amortisation (Prognose) |
| Amortisationsdatum | Geschätztes Datum |
| Eigenverbrauch | kWh selbst verbraucht |
| Einspeisung | kWh ins Netz eingespeist |
| Eigenverbrauchsquote | % der PV-Produktion selbst verbraucht |
| Autarkiegrad | % des Verbrauchs durch PV gedeckt |
| Ersparnis pro Tag/Monat/Jahr | Durchschnittswerte |
| CO2 Ersparnis | kg CO2 eingespart |
| Fixpreis vs Spot | Euro gespart gegenüber Spot-Tarif (optional) |

## Options (nachträglich änderbar)

### Sensoren
- PV Produktion, Netzeinspeisung, Netzbezug, Verbrauch
- EPEX Spot Preis (optional, für Vergleich)

### Strompreise & Amortisation
- **Fixpreis** (ct/kWh) - dein Tarif
- **Einspeisevergütung** (€/kWh oder ct/kWh)
- **Anschaffungskosten** (€)
- **Installationsdatum**

### Historische Daten
- Bereits amortisierter Betrag (€)
- Eigenverbrauch/Einspeisung vor Tracking (kWh)

## Beispiel Dashboard

```yaml
type: entities
title: PV Fixpreis
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

## Unterschied zu pv_management

Diese Integration ist für **Fixpreis-Tarife** optimiert.

Für **Spot-Tarife** (aWATTar, smartENERGY) mit Batterie-Management verwende:
👉 [pv_management](https://github.com/hoizi89/pv_management)

| Feature | pv_management | pv_management_fix |
|---------|--------------|-------------------|
| Amortisation | ✅ | ✅ |
| Energie-Tracking | ✅ | ✅ |
| Empfehlungsampel | ✅ | ❌ |
| Auto-Charge | ✅ | ❌ |
| Discharge Control | ✅ | ❌ |
| EPEX Quantile | ✅ | ❌ |
| Solcast | ✅ | ❌ |
| Spot-Vergleich | ✅ | ✅ (optional) |

## Changelog

### v1.0.0
- Initial Release
- Amortisationsberechnung mit Fixpreis
- Energie-Tracking (Eigenverbrauch, Einspeisung)
- Ersparnis-Statistiken (Tag/Monat/Jahr)
- Optional: Spot-Vergleich mit EPEX

## Support

[Issues melden](https://github.com/hoizi89/pv_management_fix/issues)

## Lizenz

MIT License - siehe [LICENSE](LICENSE)
