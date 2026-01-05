# PV Management

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/hoizi89/pv_management.svg)](https://github.com/hoizi89/pv_management/releases)

Eine Home Assistant Integration für PV-Anlagen Management mit Amortisationsberechnung und intelligenter Verbrauchsempfehlung.

## Features

### Amortisation
- **Amortisationsberechnung** - Wie viel % der Anlage ist bereits abbezahlt
- **Inkrementelle Berechnung** - Korrekt auch bei dynamischen Strompreisen
- **Eigenverbrauch & Einspeisung** - Automatische Berechnung
- **Persistente Speicherung** - Daten bleiben nach Neustart erhalten
- **Euro oder Cent** - Preise in €/kWh oder ct/kWh

### Verbrauchsempfehlung (Ampel)
- **Intelligente Ampel** - Zeigt ob jetzt ein guter Zeitpunkt zum Verbrauchen ist
- **Basiert auf:**
  - Aktuelle PV-Leistung
  - Batterie-Ladestand
  - Aktueller Strompreis
  - Tageszeit
  - PV-Prognose
- **Konfigurierbare Schwellwerte** - Passe die Empfehlung an deine Anlage an

### Statistiken
- Ersparnis pro Tag/Monat/Jahr
- Restlaufzeit bis Amortisation
- CO2-Ersparnis
- Eigenverbrauchsquote & Autarkiegrad

## Sensoren

| Sensor | Beschreibung |
|--------|--------------|
| **Verbrauchsempfehlung** | Ampel (Jetzt verbrauchen / Neutral / Vermeiden) |
| **Amortisation** | Amortisation in % |
| **Gesamtersparnis** | Gesamte Ersparnis in € |
| **Restbetrag** | Verbleibender Betrag bis Amortisation |
| **Status** | Text-Status (z.B. "45.2% amortisiert") |
| **Eigenverbrauch** | Selbst verbrauchter PV-Strom in kWh |
| **Einspeisung** | Ins Netz eingespeister Strom in kWh |
| **Eigenverbrauchsquote** | Anteil der PV-Produktion der selbst verbraucht wird |
| **Autarkiegrad** | Anteil des Verbrauchs der durch PV gedeckt wird |
| **Ersparnis pro Tag/Monat/Jahr** | Durchschnittliche Ersparnis |
| **Restlaufzeit** | Geschätzte Tage bis Amortisation |
| **Amortisationsdatum** | Geschätztes Datum der vollständigen Amortisation |
| **CO2 Ersparnis** | Eingesparte CO2-Emissionen in kg |

## Installation

### HACS (empfohlen)

1. Öffne HACS in Home Assistant
2. Klicke auf "Integrationen"
3. Klicke auf die drei Punkte oben rechts -> "Benutzerdefinierte Repositories"
4. Füge `https://github.com/hoizi89/pv_management` als Repository hinzu (Kategorie: Integration)
5. Suche nach "PV Management" und installiere es
6. Starte Home Assistant neu

### Manuell

1. Kopiere den `custom_components/pv_management` Ordner in dein `config/custom_components/` Verzeichnis
2. Starte Home Assistant neu

## Konfiguration

1. Gehe zu Einstellungen -> Geräte & Dienste
2. Klicke auf "Integration hinzufügen"
3. Suche nach "PV Management"
4. Folge dem Setup-Assistenten

### Sensoren für Amortisation

| Sensor | Pflicht | Beschreibung |
|--------|---------|--------------|
| **PV Produktion** | Ja | Gesamte PV-Produktion in kWh |
| **Netzeinspeisung** | Nein | Grid-Export in kWh |
| **Netzbezug** | Nein | Grid-Import in kWh |
| **Hausverbrauch** | Nein | Gesamtverbrauch in kWh |

### Sensoren für Verbrauchsempfehlung (optional)

| Sensor | Beschreibung |
|--------|--------------|
| **Batterie-Ladestand** | Aktueller SOC in % |
| **PV-Leistung** | Aktuelle PV-Leistung in W |
| **PV-Prognose** | Tagesprognose in kWh |

### Schwellwerte (in Options konfigurierbar)

| Einstellung | Standard | Beschreibung |
|-------------|----------|--------------|
| **Batterie Hoch** | 80% | Ab hier gilt Batterie als "voll" |
| **Batterie Niedrig** | 20% | Ab hier gilt Batterie als "leer" |
| **PV-Leistung Hoch** | 1000W | Ab hier "viel PV" |
| **Preis Niedrig** | 0.15 €/kWh | Darunter ist Strom "günstig" |
| **Preis Hoch** | 0.30 €/kWh | Darüber ist Strom "teuer" |

## Beispiel Dashboard

```yaml
type: entities
title: PV Management
entities:
  - entity: sensor.pv_management_verbrauchsempfehlung
  - type: divider
  - entity: sensor.pv_management_status
  - entity: sensor.pv_management_amortisation
  - entity: sensor.pv_management_gesamtersparnis
  - entity: sensor.pv_management_restbetrag
  - entity: sensor.pv_management_restlaufzeit
  - type: divider
  - entity: sensor.pv_management_eigenverbrauch
  - entity: sensor.pv_management_einspeisung
  - entity: sensor.pv_management_eigenverbrauchsquote
  - type: divider
  - entity: sensor.pv_management_ersparnis_pro_tag
  - entity: sensor.pv_management_ersparnis_pro_monat
  - entity: sensor.pv_management_co2_ersparnis
```

## Changelog

### v2.0.0
- Umbenannt zu "PV Management"
- Neuer Verbrauchsempfehlungs-Sensor (Ampel)
- Batterie-Integration
- PV-Prognose-Integration
- Konfigurierbare Schwellwerte

### v1.1.0
- Inkrementelle Berechnung für dynamische Preise
- Persistente Speicherung via RestoreEntity
- Sensoren nachträglich änderbar
- Diagnose-Sensor

### v1.0.0
- Initiales Release
- Amortisationsberechnung
- Euro/Cent Unterstützung
- 21 verschiedene Sensoren

## Lizenz

MIT License - siehe [LICENSE](LICENSE)
