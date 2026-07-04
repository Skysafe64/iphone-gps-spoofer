# 📍 Spoofer GPS iPhone

[🇬🇧 English](README.md) · **🇫🇷 Français**

Une petite interface web locale pour simuler la position GPS de ton **propre iPhone**
(iOS 17+), en t'appuyant sur [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) —
le mécanisme officiel de simulation de localisation d'Apple (le même que celui utilisé par
Xcode et les outils payants).

Carte cliquable, favoris, recherche par nom, joystick temps réel, et un mode route qui suit
les vraies rues à vitesse réaliste.

> **Pour ton propre appareil, usage légitime.** Cet outil utilise le canal développeur
> officiel d'Apple : iOS marque alors la position comme simulée
> (`CLLocation.sourceInformation.isSimulatedBySoftware`). Il est donc crédible pour Plans,
> les réseaux sociaux, la météo… mais **pas** conçu pour tromper une app anti-triche/anti-fraude
> dédiée. Aucune fonction ne cherche à contourner ce marqueur.

---

## Fonctionnalités

- **Carte cliquable** — clique n'importe où pour t'y téléporter (tuiles OpenStreetMap, sans clé API).
- **Favoris** — enregistre des lieux, partagés entre tous tes appareils (stockés côté serveur).
- **Recherche par nom** — géocodage via Nominatim (« Tokyo » plutôt que des coordonnées).
- **Joystick temps réel** — déplace-toi en continu en tenant une direction, vitesse réglable.
- **Mode route** — pose un départ et une arrivée, suis le trajet routier réel à vitesse
  réaliste (accél/décél, allure qui varie), avec pause/reprise et curseur de vitesse en direct.
- **Pilotable depuis un autre appareil** — l'UI est servie sur le réseau local (ouvre-la
  depuis ton iPhone).

## Prérequis

- **macOS ou Linux** (Python pur ; tourne aussi sur Raspberry Pi / mini-PC).
- **Python 3.10+** (testé jusqu'à 3.14).
- Un **iPhone iOS 17+**, avec le **Mode Développeur activé**
  (Réglages → Confidentialité et sécurité → Mode développeur), connecté en USB.

## Installation

```bash
# 1. pymobiledevice3, isolé, via pipx
pipx install pymobiledevice3

# 2. La dépendance web du backend, dans le même environnement
pipx inject pymobiledevice3 aiohttp
```

## Lancement

```bash
# 1. Monter le Developer Disk Image (iPhone déverrouillé, Mode Dev actif)
pymobiledevice3 mounter auto-mount

# 2. Ouvrir le tunnel (le laisser tourner ; nécessite sudo). Note l'adresse + le port RSD affichés.
sudo pymobiledevice3 lockdown start-tunnel
#   → RSD Address: fdXX:XXXX:XXXX::1
#   → RSD Port:    NNNNN

# 3. Lancer le backend avec ces valeurs (python de l'environnement pipx)
RSD_HOST=<adresse_rsd> RSD_PORT=<port_rsd> HTTP_PORT=8765 \
  ~/.local/pipx/venvs/pymobiledevice3/bin/python backend.py
```

Ouvre ensuite **http://localhost:8765** (ou `http://<ip-locale-du-mac>:8765` depuis ton iPhone).

## Architecture

- **`backend.py`** — serveur [aiohttp](https://docs.aiohttp.org/) qui garde **une** session DVT
  `LocationSimulation` ouverte en continu vers l'iPhone et y pousse les coordonnées. Le mode
  route joue le trajet côté serveur (~1 Hz, la cadence à laquelle iOS émet ses positions).
- **`index.html`** — interface [Leaflet](https://leafletjs.com/) (carte, favoris, joystick, route).
- **`favorites.json`** — favoris (créé au premier ajout ; ignoré par git, voir `.gitignore`).

## Limites connues

- La primitive DVT n'accepte que **latitude/longitude** : l'altitude, la vitesse et le cap ne
  sont pas injectés directement — iOS les recalcule à partir de la *cadence* des points poussés.
- Le tunnel manuel doit rester ouvert ; s'il tombe, la position revient au vrai GPS.
- Serveur de routing public (OSRM démo) : profil voiture uniquement, débit limité.

## Crédits

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) — accès à l'appareil et canal DVT
- [Leaflet](https://leafletjs.com/) + [OpenStreetMap](https://www.openstreetmap.org/) — carte et tuiles
- [Nominatim](https://nominatim.org/) — géocodage · [OSRM](http://project-osrm.org/) — routing

## Licence

[MIT](./LICENSE)
