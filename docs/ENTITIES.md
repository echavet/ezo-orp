# Entités — EZO Complete-ORP

Toutes les entités appartiennent à un appareil Home Assistant  
`manufacturer=Atlas Scientific`, `model=EZO Complete-ORP`.

Préfixe unique : `{serial_ftdi}_orp_{key}`

## Sensor

| Entité | Commande EZO | Unité | Notes |
|--------|--------------|-------|-------|
| ORP | `R` ou flux `C,n` | mV | Valeur principale. Attributs : `calibrated`, `extended_scale`, `continuous` |
| Infos appareil | `i` | — | Diagnostic. Ex. `ORP,1.98` |
| Raison du dernier reset | `Status` | enum | `power` / `software` / `brownout` / `watchdog` / `unknown` (`P/S/B/W/U`) |
| Tension d'alimentation | `Status` | V | Diagnostic, device class `voltage` |
| Calibration | `Cal,?` | enum | `calibrated` / `not_calibrated` |
| Firmware | `i` | — | Diagnostic, désactivé par défaut |

## Switches

| Entité | Commande | Notes |
|--------|----------|-------|
| Mode continu | `C,n` / `C,0` / `C,?` | Activé par défaut au démarrage (option) |
| LED | `L,1` / `L,0` / `L,?` | LED du circuit EZO |
| Échelle ORP étendue | `ORPext,1/0/?` | Diagnostic, désactivé par défaut |

## Numbers

| Entité | Plage | Notes |
|--------|-------|-------|
| Valeur de calibration personnalisée | −2000 … 2000 mV | **Locale** (restaurée). N’est envoyée que via le bouton *Calibrer custom* |
| Intervalle du mode continu | 1–99 s | Écrit `C,<n>` |

## Buttons

| Entité | Commande | Notes |
|--------|----------|-------|
| Calibrer 225 mV | `Cal,225` | Regarder l’ORP live avant d’appuyer |
| Calibrer la valeur personnalisée | `Cal,<n>` | Utilise le number ci-dessus |
| Effacer la calibration | `Cal,clear` | |
| Trouver l'appareil | `Find` | LED blanche clignotante |
| Veille | `Sleep` | Toute commande suivante réveille le circuit |
| Exporter la calibration | `Export` | Diagnostic, désactivé par défaut. Résultat dans les diagnostics |
| Reset usine | `Factory` | Diagnostic, désactivé par défaut. **Double appui sous 30 s** |

## Text

| Entité | Commande | Notes |
|--------|----------|-------|
| Nom de l'appareil | `Name,<xxx>` / `Name,?` | Config, désactivé par défaut, 16 caractères max |

## Services

| Service | Champs | Notes |
|---------|--------|-------|
| `ezo_complete.send_command` | `device_id`, `command` | Commande UART brute sans CR |
| `ezo_complete.factory_reset` | `device_id`, `confirm` | `confirm` doit être `true` |
| `ezo_complete.export_calibration` | `device_id` | Dump dans le snapshot diagnostics |
| `ezo_complete.import_calibration` | `device_id`, `payload` | Une ligne par rangée |

## Catégories

- **Principales** : ORP, mode continu, calibration 225 / custom / clear, number custom
- **Config** : intervalle continu, Sleep, nom
- **Diagnostic** (certaines off par défaut) : infos, status, firmware, ORPext, export, factory

## Exemple d’automatisation

Notifier si l’ORP de la piscine passe sous 650 mV :

```yaml
alias: ORP trop bas
triggers:
  - trigger: numeric_state
    entity_id: sensor.ezo_complete_orp_orp
    below: 650
actions:
  - action: notify.persistent_notification
    data:
      title: ORP
      message: "ORP = {{ states('sensor.ezo_complete_orp_orp') }} mV"
```
