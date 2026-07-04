#!/usr/bin/env python3
"""
GPS Spoofer — Brick 1
Minimal backend: opens ONE live DVT session to the iPhone (via the RSD tunnel)
and keeps it open. The web page pushes coordinates into it, without respawning
a process every time.

Launch (inside the pymobiledevice3 venv):
    RSD_HOST=<addr> RSD_PORT=<port> python backend.py

RSD_HOST / RSD_PORT come from the tunnel output:
    sudo pymobiledevice3 lockdown start-tunnel
"""
import asyncio
import json
import math
import os
import random
from contextlib import AsyncExitStack
from pathlib import Path

import aiohttp

from aiohttp import web

from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
from pymobiledevice3.tunneld.api import get_tunneld_device_by_udid, get_tunneld_devices

HERE = Path(__file__).resolve().parent
FAV_FILE = HERE / "favorites.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM = "https://router.project-osrm.org/route/v1"

# Manual mode: RSD_HOST/RSD_PORT copied from `lockdown start-tunnel`.
# Auto mode (recommended): leave them unset -> discovery via the `tunneld` daemon.
RSD_HOST = os.environ.get("RSD_HOST")
RSD_PORT = os.environ.get("RSD_PORT")
UDID = os.environ.get("UDID")  # targets the right device when tunneld sees several
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8765"))


async def _open_rsd():
    """Connect the RSD: manual mode (RSD_HOST/PORT) or auto-discovery via tunneld."""
    if RSD_HOST and RSD_PORT:
        rsd = RemoteServiceDiscoveryService((RSD_HOST, int(RSD_PORT)))
        await rsd.connect()
        return rsd, f"manual RSD {RSD_HOST}:{RSD_PORT}"
    # Auto: query the `sudo pymobiledevice3 remote tunneld` daemon
    if UDID:
        rsd = await get_tunneld_device_by_udid(UDID)
    else:
        devices = await get_tunneld_devices()
        rsd = devices[0] if devices else None
    if rsd is None:
        raise RuntimeError(
            "tunneld: no device found. Is the daemon running? "
            "Run: sudo pymobiledevice3 remote tunneld"
        )
    return rsd, f"tunneld ({rsd.udid})"


async def on_startup(app):
    """Open the DVT session once and keep it in app['loc']."""
    stack = AsyncExitStack()
    rsd, label = await _open_rsd()
    stack.push_async_callback(rsd.close)
    dvt = await stack.enter_async_context(DvtProvider(rsd))
    loc = await stack.enter_async_context(LocationSimulation(dvt))
    app["stack"] = stack
    app["loc"] = loc
    app["connected"] = True
    app["rsd_label"] = label
    app["current"] = None  # posted position, shared across all devices
    app["route"] = None    # armed route (route mode), kept across a pause
    app["trip"] = None     # playback state for /status
    app["trip_task"] = None
    print(f"[startup] DVT session opened via {label}", flush=True)


async def on_cleanup(app):
    route_reset(app)
    if "stack" in app:
        await app["stack"].aclose()
    app["connected"] = False


async def handle_index(request):
    return web.Response(text=(HERE / "index.html").read_text(encoding="utf-8"),
                        content_type="text/html")


async def handle_status(request):
    return web.json_response({"connected": request.app.get("connected", False),
                              "rsd": request.app.get("rsd_label", "?"),
                              "current": request.app.get("current"),
                              "trip": request.app.get("trip")})


async def handle_set(request):
    try:
        data = await request.json()
        lat, lng = float(data["lat"]), float(data["lng"])
        if not data.get("_trip"):      # a manual send abandons an ongoing trip
            route_reset(request.app)
        await request.app["loc"].set(lat, lng)
        request.app["current"] = {"lat": lat, "lng": lng}
        return web.json_response({"ok": True, "lat": lat, "lng": lng})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_clear(request):
    try:
        route_reset(request.app)
        await request.app["loc"].clear()
        request.app["current"] = None
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# --- Favorites (stored server-side -> shared across all devices) ---

def load_favorites():
    if FAV_FILE.exists():
        try:
            return json.loads(FAV_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_favorites(favs):
    FAV_FILE.write_text(json.dumps(favs, ensure_ascii=False, indent=2), encoding="utf-8")


async def handle_fav_list(request):
    return web.json_response(load_favorites())


async def handle_fav_add(request):
    try:
        data = await request.json()
        name = str(data.get("name", "")).strip() or "Unnamed"
        lat, lng = float(data["lat"]), float(data["lng"])
        favs = load_favorites()
        new_id = max([f["id"] for f in favs], default=0) + 1
        fav = {"id": new_id, "name": name, "lat": lat, "lng": lng}
        favs.append(fav)
        save_favorites(favs)
        return web.json_response({"ok": True, "favorite": fav})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_fav_delete(request):
    try:
        fid = int(request.match_info["fid"])
        save_favorites([f for f in load_favorites() if f["id"] != fid])
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# --- Search by name (geocoding via Nominatim / OpenStreetMap) ---

async def handle_search(request):
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response([])
    params = {"q": q, "format": "jsonv2", "limit": "6", "accept-language": "en"}
    # User-Agent required by Nominatim's usage policy
    headers = {"User-Agent": "gps-spoofer-local/1.0 (personal use)"}
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(NOMINATIM, params=params, headers=headers) as r:
                data = await r.json()
        results = [{"name": d["display_name"], "lat": float(d["lat"]), "lng": float(d["lon"])}
                   for d in data]
        return web.json_response(results)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# --- Route mode: OSRM routing + server-side trip playback ---

def _haversine(a, b):
    """Distance in meters between (lat, lng) a and b."""
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _point_at(coords, segs, target):
    """Point at `target` meters along the polyline (linear interpolation)."""
    acc = 0.0
    for i, d in enumerate(segs):
        if acc + d >= target:
            f = (target - acc) / d if d > 0 else 0.0
            return (coords[i][0] + (coords[i + 1][0] - coords[i][0]) * f,
                    coords[i][1] + (coords[i + 1][1] - coords[i][1]) * f)
        acc += d
    return coords[-1]


async def fetch_route(frm, to, profile):
    """Query OSRM, return (coords [[lat,lng]...], distance_m)."""
    url = f"{OSRM}/{profile}/{frm[1]},{frm[0]};{to[1]},{to[0]}"
    params = {"overview": "full", "geometries": "geojson"}
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as r:
            data = await r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"routing: {data.get('code', 'error')}")
    route = data["routes"][0]
    coords = [[c[1], c[0]] for c in route["geometry"]["coordinates"]]  # [lng,lat] -> [lat,lng]
    return coords, float(route["distance"])


async def trip_player(app):
    """Advance along app['route'] at ~1 Hz, with a natural pace and live speed."""
    r = app["route"]
    coords, segs, total = r["coords"], r["segs"], r["total"]
    dt = 1.0            # 1 Hz: the rate at which iOS emits its updates
    factor = 1.0        # pace variation (correlated drift around 1)
    try:
        while r["traveled"] < total:
            # accel/decel over the first/last 40 meters
            ramp = max(0.3, min(1.0, min(r["traveled"], total - r["traveled"]) / 40.0))
            # natural pace: AR(1) reverting toward 1.0 with a bit of noise
            factor = 1.0 + 0.85 * (factor - 1.0) + random.gauss(0, 0.06)
            factor = max(0.75, min(1.25, factor))
            r["traveled"] = min(total, r["traveled"] + r["speed_mps"] * dt * ramp * factor)
            lat, lng = _point_at(coords, segs, r["traveled"])
            await app["loc"].set(lat, lng)
            app["current"] = {"lat": lat, "lng": lng}
            app["trip"] = {"running": True, "traveled": round(r["traveled"]),
                           "total": round(total)}
            await asyncio.sleep(dt)
        app["trip"] = {"running": False, "traveled": round(total), "total": round(total)}
    except asyncio.CancelledError:
        # pause: we keep r['traveled'] so we can resume
        app["trip"] = {"running": False, "traveled": round(r["traveled"]),
                       "total": round(total)}
        raise


def pause_trip(app):
    """Stop playback but keep the route and the distance traveled."""
    task = app.get("trip_task")
    if task and not task.done():
        task.cancel()
    app["trip_task"] = None


def route_reset(app):
    """Fully abandon the trip (used by a manual move)."""
    pause_trip(app)
    app["route"] = None
    app["trip"] = None


async def handle_route_preview(request):
    """Compute a route, arm it server-side (traveled=0) and return its geometry."""
    try:
        data = await request.json()
        frm = (float(data["from"]["lat"]), float(data["from"]["lng"]))
        to = (float(data["to"]["lat"]), float(data["to"]["lng"]))
        profile = data.get("profile", "driving")
        speed_kmh = float(data.get("speed_kmh", 30))
        coords, _ = await fetch_route(frm, to, profile)
        segs = [_haversine(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]
        total = sum(segs)
        pause_trip(request.app)
        request.app["route"] = {"coords": coords, "segs": segs, "total": total,
                                "traveled": 0.0, "speed_mps": speed_kmh * 1000 / 3600}
        request.app["trip"] = None
        return web.json_response({"ok": True, "coords": coords, "distance": total})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_route_play(request):
    """Start or resume playback of the armed route."""
    app = request.app
    if not app.get("route"):
        return web.json_response({"ok": False, "error": "no route defined"}, status=400)
    try:
        data = await request.json()
    except Exception:
        data = {}
    if "speed_kmh" in data:
        app["route"]["speed_mps"] = float(data["speed_kmh"]) * 1000 / 3600
    if app["route"]["traveled"] >= app["route"]["total"]:
        app["route"]["traveled"] = 0.0            # arrived -> restart from the beginning
    pause_trip(app)
    app["trip_task"] = asyncio.create_task(trip_player(app))
    return web.json_response({"ok": True})


async def handle_route_pause(request):
    pause_trip(request.app)
    r = request.app.get("route")
    return web.json_response({"ok": True, "traveled": round(r["traveled"]) if r else 0})


async def handle_route_reset(request):
    route_reset(request.app)
    return web.json_response({"ok": True})


async def handle_route_speed(request):
    """Change the speed live (slider)."""
    try:
        data = await request.json()
        r = request.app.get("route")
        if r:
            r["speed_mps"] = float(data["speed_kmh"]) * 1000 / 3600
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", handle_index)
    app.router.add_get("/status", handle_status)
    app.router.add_post("/set", handle_set)
    app.router.add_post("/clear", handle_clear)
    app.router.add_get("/favorites", handle_fav_list)
    app.router.add_post("/favorites", handle_fav_add)
    app.router.add_delete("/favorites/{fid}", handle_fav_delete)
    app.router.add_get("/search", handle_search)
    app.router.add_post("/route/preview", handle_route_preview)
    app.router.add_post("/route/play", handle_route_play)
    app.router.add_post("/route/pause", handle_route_pause)
    app.router.add_post("/route/reset", handle_route_reset)
    app.router.add_post("/route/speed", handle_route_speed)
    # 0.0.0.0: also reachable from your iPhone / other devices on the local network
    web.run_app(app, host="0.0.0.0", port=HTTP_PORT)


if __name__ == "__main__":
    main()
