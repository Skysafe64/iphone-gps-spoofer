# 📍 iPhone GPS Spoofer

**🇬🇧 English** · [🇫🇷 Français](README.fr.md)

A small local web interface to simulate the GPS location of your **own iPhone**
(iOS 17+), built on top of [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) —
Apple's official location-simulation mechanism (the same one used by Xcode and
commercial tools).

Clickable map, favorites, search by name, real-time joystick, and a route mode that
follows real streets at a realistic speed.

> **For your own device, legitimate use.** This tool uses Apple's official developer
> channel: iOS accordingly flags the location as simulated
> (`CLLocation.sourceInformation.isSimulatedBySoftware`). It is therefore convincing for
> Maps, social networks, weather… but **not** designed to fool a dedicated
> anti-cheat/anti-fraud app. No feature attempts to bypass this flag.

---

## Features

- **Clickable map** — click anywhere to teleport there (OpenStreetMap tiles, no API key).
- **Favorites** — save places, shared across all your devices (stored server-side).
- **Search by name** — geocoding via Nominatim ("Tokyo" instead of coordinates).
- **Real-time joystick** — move continuously by holding a direction, with adjustable speed.
- **Route mode** — set a start and a destination, follow the real road path at a realistic
  speed (acceleration/deceleration, varying pace), with pause/resume and a live speed slider.
- **Controllable from another device** — the UI is served on the local network (open it
  from your iPhone).

## Requirements

- **macOS or Linux** (pure Python; also runs on a Raspberry Pi / mini-PC).
- **Python 3.10+** (tested up to 3.14).
- An **iPhone on iOS 17+**, with **Developer Mode enabled**
  (Settings → Privacy & Security → Developer Mode), connected over USB.

## Installation

```bash
# 1. pymobiledevice3, isolated, via pipx
pipx install pymobiledevice3

# 2. The backend's web dependency, in the same environment
pipx inject pymobiledevice3 aiohttp
```

## Running

```bash
# 1. Mount the Developer Disk Image (iPhone unlocked, Developer Mode on)
pymobiledevice3 mounter auto-mount

# 2. Open the tunnel (leave it running; requires sudo). Note the RSD address + port shown.
sudo pymobiledevice3 lockdown start-tunnel
#   → RSD Address: fdXX:XXXX:XXXX::1
#   → RSD Port:    NNNNN

# 3. Start the backend with these values (the pipx environment's python)
RSD_HOST=<rsd_address> RSD_PORT=<rsd_port> HTTP_PORT=8765 \
  ~/.local/pipx/venvs/pymobiledevice3/bin/python backend.py
```

Then open **http://localhost:8765** (or `http://<mac-local-ip>:8765` from your iPhone).

## Architecture

- **`backend.py`** — an [aiohttp](https://docs.aiohttp.org/) server that keeps **one** DVT
  `LocationSimulation` session continuously open to the iPhone and pushes coordinates to it.
  Route mode plays the trip server-side (~1 Hz, the rate at which iOS emits its positions).
- **`index.html`** — a [Leaflet](https://leafletjs.com/) interface (map, favorites, joystick, route).
- **`favorites.json`** — favorites (created on the first entry; ignored by git, see `.gitignore`).

## Known limitations

- The DVT primitive only accepts **latitude/longitude**: altitude, speed, and heading are not
  injected directly — iOS recomputes them from the *cadence* of the pushed points.
- The manual tunnel must stay open; if it drops, the location reverts to the real GPS.
- Public routing server (OSRM demo): car profile only, rate-limited.

## Credits

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) — device access and DVT channel
- [Leaflet](https://leafletjs.com/) + [OpenStreetMap](https://www.openstreetmap.org/) — map and tiles
- [Nominatim](https://nominatim.org/) — geocoding · [OSRM](http://project-osrm.org/) — routing

## License

[MIT](./LICENSE)
