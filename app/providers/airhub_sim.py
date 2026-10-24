"""
Offline simulator + client for the Airspace Link AirHub sandbox API.

WHAT IS REAL vs ASSUMED
- REAL (copied from the AirHub docs you pasted): the OAuth flow. POST /v1/oauth/token,
  form-encoded, x-api-key header, grant_type=client_credentials, space-separated scopes,
  response envelope {"status","message","data":{"accessToken","expires","scope"}}.
  The scope names are also from the docs.
- ASSUMED (not in the pasted docs): every other path, parameter name, response field and
  error body. They are marked "ASSUMED" below. Replace them with the real shapes once you
  have the Briefing / Advisories pages or one real response.
- SYNTHETIC: all zones are made-up circles around real-ish coordinates. They are NOT real
  FAA boundaries and must never be shown as real airspace data.

Usage:  python3 airhub_sim.py          # runs the demo scenarios
        python3 test_airhub_sim.py     # runs assertions
Swap to the real API by constructing AirHubClient(base_url=SANDBOX, ...) with no transport.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import time
import uuid
from urllib.parse import parse_qs

import httpx

SANDBOX = "https://airhub-api-sandbox.airspacelink.com"
SIM_API_KEY = "sim-api-key"
SIM_CLIENT_ID = "sim-client-id"
SIM_CLIENT_SECRET = "sim-client-secret"

ALL_SCOPES = {  # from the docs
    "advisory:read", "aviation:read", "briefing:area:read", "briefing:location:read",
    "hazar:read", "operation:create", "route:create", "surface:create",
}
# What this simulated client was "granted" (mirrors the scopes recommended for the MVP).
DEFAULT_GRANTED = {"briefing:location:read", "briefing:area:read", "advisory:read", "aviation:read"}
TOKEN_TTL_S = 3600

# ASSUMED endpoint -> required scope
ENDPOINT_SCOPES = {
    ("GET", "/v1/briefing/location"): "briefing:location:read",
    ("POST", "/v1/briefing/area"): "briefing:area:read",
    ("GET", "/v1/advisories"): "advisory:read",
    ("POST", "/v1/advisories/geojson"): "advisory:read",
    ("GET", "/v1/aviation/facility-map"): "aviation:read",
}

# ---------------------------------------------------------------- synthetic world
# kind: airspace | facility | advisory ; radius in km (circles are a simplification)
_NOW = lambda: dt.datetime.now(dt.timezone.utc)

ZONES = [
    {"id": "SIM-B-1", "kind": "airspace", "airspace_class": "B", "name": "Simulated Class B (SFO-like)",
     "center": (37.6213, -122.3790), "radius_km": 15.0,
     # facility-map ceilings by distance ring (km -> ft AGL): synthetic
     "rings": [(4.0, 0), (8.0, 100), (15.0, 200)]},
    {"id": "SIM-D-1", "kind": "airspace", "airspace_class": "D", "name": "Simulated Class D tower",
     "center": (35.0400, -106.6100), "radius_km": 6.0, "rings": [(2.0, 0), (6.0, 150)]},
    {"id": "SIM-NSUFR-1", "kind": "advisory", "type": "nsufr", "severity": "restricted",
     "name": "Simulated national-security UAS flight restriction",
     "center": (38.2627, -121.9275), "radius_km": 3.0,
     "description": "Simulated special security instruction airspace (stand-in for a 14 CFR 99.7 restriction). "
                    "Contact the designated facility; do not fly without approval.",
     "source": "simulated-FAA-NSUFR"},
    {"id": "SIM-TFR-FIRE-1", "kind": "advisory", "type": "tfr", "severity": "restricted",
     "name": "Simulated wildfire TFR", "center": (39.9000, -121.6000), "radius_km": 10.0,
     "description": "Simulated wildfire TFR, surface to 18,000 ft.", "source": "simulated-FAA-TFR",
     "starts": lambda: _NOW() - dt.timedelta(hours=6), "ends": lambda: _NOW() + dt.timedelta(hours=48)},
    {"id": "SIM-TFR-EXPIRED", "kind": "advisory", "type": "tfr", "severity": "restricted",
     "name": "Simulated EXPIRED TFR (must not be reported as active)", "center": (36.0, -115.0),
     "radius_km": 8.0, "description": "Expired event TFR.", "source": "simulated-FAA-TFR",
     "starts": lambda: _NOW() - dt.timedelta(days=3), "ends": lambda: _NOW() - dt.timedelta(days=2)},
    {"id": "SIM-LOCAL-PARK-1", "kind": "advisory", "type": "local", "severity": "caution",
     "name": "Simulated city park drone rule", "center": (37.7700, -122.4500), "radius_km": 2.0,
     "description": "Simulated local advisory: takeoff and landing may require a permit. Check the land manager.",
     "source": "simulated-local-geo-portal"},
]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _dist(zone, lat, lon) -> float:
    return haversine_km(lat, lon, zone["center"][0], zone["center"][1])


def _active(zone) -> bool:
    if "starts" not in zone:
        return True
    return zone["starts"]() <= _NOW() <= zone["ends"]()


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def evaluate_point(lat: float, lon: float) -> dict:
    """ASSUMED briefing payload for one point (field names are invented)."""
    airspace = {"class": "G", "controlled": False, "facility": None}
    facility_map = {"in_grid": False, "ceiling_ft": None, "facility": None}
    for z in ZONES:
        if z["kind"] != "airspace":
            continue
        d = _dist(z, lat, lon)
        if d <= z["radius_km"]:
            airspace = {"class": z["airspace_class"], "controlled": True, "facility": z["name"]}
            ceiling = next(c for r, c in z["rings"] if d <= r)
            facility_map = {"in_grid": True, "ceiling_ft": ceiling, "facility": z["name"]}
            break
    advisories = []
    for z in ZONES:
        if z["kind"] != "advisory" or _dist(z, lat, lon) > z["radius_km"] or not _active(z):
            continue
        adv = {k: z[k] for k in ("id", "type", "severity", "name", "description", "source")}
        if "ends" in z:
            adv["effective"] = {"start": _iso(z["starts"]()), "end": _iso(z["ends"]())}
        advisories.append(adv)
    return {"location": {"latitude": lat, "longitude": lon}, "airspace": airspace,
            "facility_map": facility_map, "advisories": advisories, "generated_at": _iso(_NOW()),
            "simulated": True}


def _ok(data, status=200):
    return httpx.Response(status, json={"status": status, "message": "success", "data": data})


def _err(status, message):  # ASSUMED error envelope (mirrors the success envelope)
    return httpx.Response(status, json={"status": status, "message": message, "data": None})


# ---------------------------------------------------------------- simulator
class AirHubSimulator:
    """httpx transport handler that behaves like the AirHub sandbox (see the header caveats)."""

    def __init__(self, granted_scopes=None, ttl_s=TOKEN_TTL_S):
        self.granted = set(granted_scopes or DEFAULT_GRANTED)
        self.ttl_s = ttl_s
        self.tokens: dict[str, dict] = {}
        self.failures: list[int] = []     # queue of HTTP statuses to return on the next API calls
        self.calls: list[tuple[str, str]] = []
        self.token_requests = 0

    # test helpers
    def fail_next(self, n=1, status=503):
        self.failures += [status] * n

    def expire_all_tokens(self):
        for t in self.tokens.values():
            t["expires_at"] = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        self.calls.append((method, path))
        if (method, path) == ("POST", "/v1/oauth/token"):
            return self._token(req)
        key = (method, path)
        if key not in ENDPOINT_SCOPES:
            return _err(404, "not found (path unknown to the simulator; real path may differ)")
        if req.headers.get("x-api-key") != SIM_API_KEY:
            return _err(401, "invalid or missing x-api-key")
        auth = req.headers.get("authorization", "")
        tok = self.tokens.get(auth[7:]) if auth.lower().startswith("bearer ") else None
        if not tok or tok["expires_at"] < time.time():
            return _err(401, "invalid or expired access token")
        if ENDPOINT_SCOPES[key] not in tok["scopes"]:
            return _err(403, f"token lacks required scope {ENDPOINT_SCOPES[key]}")
        if self.failures:
            status = self.failures.pop(0)
            return _err(status, "simulated upstream failure")
        try:
            return self._route(req, key)
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
            return _err(400, f"bad request: {e}")

    def _token(self, req: httpx.Request) -> httpx.Response:
        self.token_requests += 1
        if req.headers.get("x-api-key") != SIM_API_KEY:
            return _err(401, "invalid or missing x-api-key")
        if "application/x-www-form-urlencoded" not in req.headers.get("content-type", ""):
            return _err(400, "Content-Type must be application/x-www-form-urlencoded")
        form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
        if form.get("grant_type") != "client_credentials":
            return _err(400, "unsupported grant_type")
        if form.get("client_id") != SIM_CLIENT_ID or form.get("client_secret") != SIM_CLIENT_SECRET:
            return _err(401, "invalid client credentials")
        asked = set(form.get("scope", "").split())
        if not asked or not asked <= ALL_SCOPES:
            return _err(400, f"invalid scope(s): {sorted(asked - ALL_SCOPES) or 'none requested'}")
        if not asked <= self.granted:   # ASSUMED behavior: ungranted scopes are rejected
            return _err(403, f"scope(s) not enabled for this client: {sorted(asked - self.granted)}")
        token = uuid.uuid4().hex
        exp = time.time() + self.ttl_s
        self.tokens[token] = {"scopes": asked, "expires_at": exp}
        return _ok({"accessToken": token, "expires": _iso(dt.datetime.fromtimestamp(exp, dt.timezone.utc)),
                    "scope": " ".join(sorted(asked))})

    def _route(self, req: httpx.Request, key) -> httpx.Response:
        q = {k: v[0] for k, v in parse_qs(req.url.query.decode()).items()}
        if key == ("GET", "/v1/briefing/location"):
            lat, lon = float(q["latitude"]), float(q["longitude"])
            _check_coords(lat, lon)
            return _ok(evaluate_point(lat, lon))
        if key == ("GET", "/v1/aviation/facility-map"):
            lat, lon = float(q["latitude"]), float(q["longitude"])
            _check_coords(lat, lon)
            return _ok(evaluate_point(lat, lon)["facility_map"])
        if key == ("POST", "/v1/briefing/area"):
            return _ok(self._area(json.loads(req.content)))
        if key == ("GET", "/v1/advisories"):
            w, s, e, n = (float(x) for x in q["bbox"].split(","))   # minLon,minLat,maxLon,maxLat
            return _ok({"advisories": self._in_bbox(w, s, e, n)})
        if key == ("POST", "/v1/advisories/geojson"):
            w, s, e, n = _bbox(json.loads(req.content))
            return _ok({"advisories": self._in_bbox(w, s, e, n)})
        return _err(404, "not found")

    def _in_bbox(self, w, s, e, n):
        out = []
        for z in ZONES:
            if z["kind"] != "advisory" or not _active(z):
                continue
            clat = min(max(z["center"][0], s), n)       # nearest point of the box to the circle center
            clon = min(max(z["center"][1], w), e)
            if haversine_km(z["center"][0], z["center"][1], clat, clon) <= z["radius_km"]:
                out.append({k: z[k] for k in ("id", "type", "severity", "name", "description", "source")})
        return out

    def _area(self, gj: dict) -> dict:
        ring = _ring(gj)
        pts = ring[:-1] + [(sum(p[0] for p in ring[:-1]) / (len(ring) - 1),
                            sum(p[1] for p in ring[:-1]) / (len(ring) - 1))]   # vertices + centroid (rough)
        results = [evaluate_point(lat, lon) for lon, lat in pts]
        advisories = {a["id"]: a for r in results for a in r["advisories"]}
        ceilings = [r["facility_map"]["ceiling_ft"] for r in results if r["facility_map"]["in_grid"]]
        classes = sorted({r["airspace"]["class"] for r in results})
        return {"airspace_classes": classes, "controlled": any(r["airspace"]["controlled"] for r in results),
                "min_ceiling_ft": min(ceilings) if ceilings else None,
                "advisories": list(advisories.values()), "points_sampled": len(pts),
                "generated_at": _iso(_NOW()), "simulated": True}


def _check_coords(lat, lon):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordinates out of range")


def _ring(gj: dict):
    geom = gj.get("geometry", gj)
    if geom["type"] != "Polygon":
        raise ValueError("expected a GeoJSON Polygon")
    return [tuple(p) for p in geom["coordinates"][0]]


def _bbox(gj: dict):
    ring = _ring(gj)
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------- client
class AirHubError(Exception):
    def __init__(self, status, message):
        super().__init__(f"AirHub {status}: {message}")
        self.status, self.message = status, message


class AirHubClient:
    """Token-caching client. Works against the simulator (transport=...) or the real sandbox (omit it)."""

    def __init__(self, api_key, client_id, client_secret, scopes, base_url=SANDBOX, transport=None):
        self.api_key, self.client_id, self.client_secret = api_key, client_id, client_secret
        self.scopes = " ".join(scopes)
        self.http = httpx.Client(base_url=base_url, transport=transport, timeout=10)
        self._token, self._exp = None, 0.0

    def _ensure_token(self, force=False):
        if not force and self._token and time.time() < self._exp - 60:   # refresh 60s early
            return
        r = self.http.post("/v1/oauth/token", headers={"x-api-key": self.api_key},
                           data={"grant_type": "client_credentials", "client_id": self.client_id,
                                 "client_secret": self.client_secret, "scope": self.scopes})
        body = r.json()
        if r.status_code != 200:
            raise AirHubError(r.status_code, body.get("message", r.text))
        self._token = body["data"]["accessToken"]
        exp = dt.datetime.strptime(body["data"]["expires"], "%Y-%m-%dT%H:%M:%S.%fZ")
        self._exp = exp.replace(tzinfo=dt.timezone.utc).timestamp()

    def _call(self, method, path, **kw):
        self._ensure_token()
        for attempt in (1, 2):
            r = self.http.request(method, path, headers={"x-api-key": self.api_key,
                                  "Authorization": f"Bearer {self._token}"}, **kw)
            if r.status_code == 401 and attempt == 1:     # token expired server-side: refresh once
                self._ensure_token(force=True)
                continue
            body = r.json()
            if r.status_code != 200:
                raise AirHubError(r.status_code, body.get("message", r.text))
            return body["data"]

    def briefing_location(self, lat, lon):
        return self._call("GET", "/v1/briefing/location", params={"latitude": lat, "longitude": lon})

    def briefing_area(self, polygon_geojson):
        return self._call("POST", "/v1/briefing/area", json=polygon_geojson)

    def advisories_bbox(self, west, south, east, north):
        return self._call("GET", "/v1/advisories", params={"bbox": f"{west},{south},{east},{north}"})

    def advisories_geojson(self, polygon_geojson):
        return self._call("POST", "/v1/advisories/geojson", json=polygon_geojson)

    def facility_map(self, lat, lon):
        return self._call("GET", "/v1/aviation/facility-map", params={"latitude": lat, "longitude": lon})


def make_sim_client(sim: AirHubSimulator | None = None, scopes=None):
    sim = sim or AirHubSimulator()
    scopes = scopes or sorted(DEFAULT_GRANTED)
    return sim, AirHubClient(SIM_API_KEY, SIM_CLIENT_ID, SIM_CLIENT_SECRET, scopes, transport=sim.transport())


# ---------------------------------------------------------------- demo
SCENARIOS = [
    ("Controlled airspace, near airport", 37.6300, -122.3900),
    ("Open Class G, nothing active",      39.5000, -117.0000),
    ("Inside simulated NSUFR",            38.2650, -121.9300),
    ("Inside active wildfire TFR",        39.9100, -121.6100),
    ("Inside EXPIRED TFR (should be clear)", 36.0000, -115.0000),
    ("Local park advisory",               37.7710, -122.4510),
]

if __name__ == "__main__":
    sim, client = make_sim_client()
    print("SIMULATED DATA - synthetic zones, not real FAA/AirHub results\n")
    for name, lat, lon in SCENARIOS:
        #print(name, lat, lon)
        b = client.briefing_location(lat, lon)
        #print("B RETURNS,",  b)
        fm = b["facility_map"]
        advs = ", ".join(f'{a["type"]}/{a["severity"]}' for a in b["advisories"]) or "none"
        print(f"{name:40s} class={b['airspace']['class']:2s} ceiling={fm['ceiling_ft']!s:5s} advisories={advs}")

    print("\nFailure modes:")
    for label, fn in [
        ("ungranted scope", lambda: AirHubClient(SIM_API_KEY, SIM_CLIENT_ID, SIM_CLIENT_SECRET,
                                                 ["operation:create"], transport=sim.transport()).briefing_location(37, -122)),
        ("bad api key", lambda: AirHubClient("wrong", SIM_CLIENT_ID, SIM_CLIENT_SECRET,
                                             ["advisory:read"], transport=sim.transport()).briefing_location(37, -122)),
        ("upstream 503", lambda: (sim.fail_next(1, 503), client.briefing_location(37, -122))[1]),
    ]:
        try:
            fn()
        except AirHubError as e:
            print(f"  {label:16s} -> {e}")
    sim.expire_all_tokens()
    client.briefing_location(37.63, -122.39)
    print(f"  expired token    -> auto-refreshed (token requests so far: {sim.token_requests})")
