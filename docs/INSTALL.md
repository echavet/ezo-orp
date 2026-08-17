# Installation — EZO Complete-ORP

## Prérequis

- Home Assistant **2026.5** ou plus récent (bibliothèque **serialx**, sélecteur de port série)
- Kit **Atlas Scientific EZO Complete-ORP** (USB isolé + FTDI)
- Accès USB au serveur HA (HAOS, Supervised, Container avec `/dev` mappé, ou Core)

## Via HACS

1. HACS → ⋮ → **Custom repositories**
2. Ajouter `https://github.com/echavet/ezo-orp` (type **Integration**)
3. Installer **EZO Complete-ORP**
4. Redémarrer Home Assistant
5. Brancher le module USB
6. Accepter la découverte **ou** *Paramètres → Appareils et services → Ajouter une intégration → EZO Complete-ORP*
7. Vérifier le nom friendly — le port et le baudrate 9600 sont préremplis

## Installation manuelle

1. Copier le dossier `custom_components/ezo_complete` dans `config/custom_components/`
2. Redémarrer Home Assistant
3. Ajouter l’intégration comme ci-dessus

## Paramètres d’installation

| Paramètre | Obligatoire | Description |
|-----------|-------------|-------------|
| Port série | oui | Liste USB + saisie libre (sélecteur HA 2026) |
| Baudrate | non | 9600 par défaut |
| Nom | non | Nom de l’appareil HA |

L’intégration envoie `i` et **refuse** le port si la réponse ne contient pas `ORP`.

## Paramètres de configuration (Options)

Voir le tableau dans le [README](../README.md#options). Reconfiguration du port : menu ⋮ de l’entrée → **Reconfigurer**.

## Multi-appareils

Répéter *Ajouter une intégration* pour chaque EZO Complete-ORP. Chaque FTDI a un numéro de série distinct.

## Désinstallation

1. *Paramètres → Appareils et services* → EZO Complete-ORP → ⋮ → **Supprimer**
2. Optionnel : HACS → EZO Complete-ORP → **Remove**
3. Redémarrer HA pour décharger `serialx` si plus aucun autre consommateur

Les entités et l’appareil disparaissent. Aucun fichier n’est laissé dans `.storage` hors l’historique d’enregistrements HA standard.

## Conteneur / permissions USB

Sur Docker, mapper le périphérique :

```yaml
devices:
  - /dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_XXXXXXXX-if00-port0
```

ou le bus USB complet, et ajouter le user au groupe `dialout`.
