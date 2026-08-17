# Dépannage — EZO Complete-ORP

## La découverte USB n’apparaît pas

- HAOS / Supervised : le sous-système USB doit être actif
- VID/PID attendus : `0403:6015` (FT230X), éventuellement `0403:6001` / `0403:6014`
- Fallback : *Ajouter une intégration* et choisir le port dans la liste
- Préférez `/dev/serial/by-id/usb-FTDI_…` à `ttyUSB0`

## « Ce périphérique n’est pas un circuit ORP »

La commande `i` n’a pas renvoyé `ORP`. Causes fréquentes :

- Autre gadget FTDI (câble USB-série générique, autre EZO pH/EC/DO)
- Circuit encore en veille (`Sleep`) — l’intégration envoie un CR de réveil, réessayez
- Mauvais baudrate (défaut 9600)

## Entités indisponibles après un débranchement

Normal. Rebranchez le câble : l’intégration rouvre le port et relance `i`.  
Si le chemin `ttyUSB0` a changé, utilisez un chemin `by-id` ou **Reconfigurer**.

## Pas de valeur ORP

1. Vérifier que le **mode continu** est on (recommandé)
2. Sinon, l’intégration envoie `R` à chaque intervalle de polling
3. Télécharger les **diagnostics** (dernières lignes brutes)
4. Tester à la main : `R` doit renvoyer un nombre puis `*OK`

## Calibration qui « ne prend pas »

- Attendre la **stabilisation** du capteur ORP avant d’appuyer
- `Cal,?` doit passer à calibré (entité diagnostic)
- `Cal,clear` puis recommencer
- Solution 225 mV fraîche, sonde propre, connecteur BNC bien serré

## Reset usine

Le bouton diagnostic est **off par défaut**. Premier appui = armement 30 s, second = `Factory`.  
Le service `ezo_complete.factory_reset` exige `confirm: true`.

## Conflit de port

`serialx` ouvre le port en **exclusif**. Fermer Atlas Desktop, un add-on minicom, ou une autre intégration qui tient le même FTDI.

## Journaux utiles

Filtrer `ezo_complete` dans *Paramètres → Système → Journaux*.  
Une déconnexion est loguée **une fois**, puis une info au retour.
