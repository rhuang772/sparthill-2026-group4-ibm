"""
app/providers/tfr.py — live FAA Temporary Flight Restriction lookup.

await get_tfrs(lat, lon, radius_m, start, end) -> TFRResult

Pulls the TFR list from tfr.faa.gov, then each NOTAM's AIXM XML detail for its
shapes, altitudes and schedule. The list is cached for 5 minutes and details for
30 minutes; data older than 1 hour is refused (status="failed").

finding:
  restricted — a TFR overlaps the search area, is active (or of unknown timing) during
               the flight window, and reaches down to drone altitudes (floor <= 400 ft)
  none_found — no such TFR in the parsed data
  unknown    — some TFRs could not be loaded or parsed, so absence cannot be confirmed
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone, time as dtime
from typing import Optional

import httpx

from app.providers import http_client
from app.providers.base import TFRArea, TFRResult

log = logging.getLogger("tfr")

LIST_URL = "https://tfr.faa.gov/tfrapi/exportTfrList"
DETAIL_URL = "https://tfr.faa.gov/download/detail_{}.xml"
HEADERS = {"User-Agent": "Mozilla/5.0"}

CACHE_TTL_S = 300        # re-fetch the list every 5 minutes
DETAIL_TTL_S = 1800      # re-fetch a NOTAM's detail every 30 minutes
MAX_STALE_S = 3600       # beyond 1 hour, refuse to answer
DRONE_ALT_FT = 400
DEFAULT_RADIUS_M = 100

_state: dict = {"at": None, "tfrs": None, "unresolved": []}
_detail_cache: dict = {}
_lock = asyncio.Lock()

_COORD = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([NSEW])\s*$")


def _coord(s: str) -> float:
    m = _COORD.match(s or "")
    if not m:
        raise ValueError(f"bad coordinate: {s!r}")
    v = float(m.group(1))
    return -v if m.group(2) in "SW" else v


def _search_bbox(lat: float, lon: float, radius_m: float):
    """(min_lon, min_lat, max_lon, max_lat) around the point."""
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def _boxes_overlap(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _bbox_from_abd(abd):
    avx = abd.findall("Avx")
    if not avx:
        return None
    # Circle given as center + radius (AIXM arc form; not seen in a real sample yet)
    if avx[0].find("geoLatArc") is not None and len(avx) <= 2:
        lat, lon = _coord(avx[0].findtext("geoLatArc")), _coord(avx[0].findtext("geoLongArc"))
        r = float(avx[0].findtext("valRadiusArc"))
        uom = (avx[0].findtext("uomRadiusArc") or "NM").upper()
        meters = r * 1852 if uom == "NM" else r * 1000 if uom == "KM" else r
        return _search_bbox(lat, lon, meters)
    lons = [_coord(v.findtext("geoLong")) for v in avx]
    lats = [_coord(v.findtext("geoLat")) for v in avx]
    return (min(lons), min(lats), max(lons), max(lats))


def _alt(area, side: str):
    v = area.findtext(f"valDistVer{side}")
    if v in (None, ""):
        return None, None
    ft = float(v)
    if (area.findtext(f"uomDistVer{side}") or "").upper() == "FL":
        ft *= 100
    code = (area.findtext(f"codeDistVer{side}") or "").upper()
    return ft, {"ALT": "MSL", "HEI": "AGL"}.get(code, code or None)


def _parse_time(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_detail(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    n = root.find(".//Not")
    if n is None:
        raise ValueError("no <Not> element")
    meta = {
        "effective": n.findtext("dateEffective"),
        "expires": n.findtext("dateExpire"),
        "tz": (n.findtext("codeTimeZone") or "").strip().upper(),
    }

    boxes = {}
    for abd in n.iter("abdMergedArea"):
        cid = abd.findtext("AbdUid/AseUid/codeId")
        box = _bbox_from_abd(abd)
        if cid and box is not None:
            boxes[cid] = box

    areas = []
    for a in n.iter("aseTFRArea"):
        box = boxes.get(a.findtext("AseUid/codeId"))
        if box is None:
            continue
        floor_ft, floor_datum = _alt(a, "Lower")
        ceil_ft, ceil_datum = _alt(a, "Upper")
        sched = a.find("ScheduleGroup")
        daily = None
        if sched is not None and (a.findtext("dayCode") or "").lower() == "daily":
            s_, e_ = sched.findtext("startTime"), sched.findtext("endTime")
            if s_ and e_:
                daily = (s_[11:19], e_[11:19])
        areas.append({
            "name": a.findtext("txtName"), "bbox": box,
            "floor_ft": floor_ft, "floor_datum": floor_datum,
            "ceiling_ft": ceil_ft, "ceiling_datum": ceil_datum,
            "daily": daily,
        })
    return {**meta, "areas": areas}


def _time_status(detail: dict, area: dict, win_start: datetime, win_end: datetime) -> str:
    if detail["tz"] != "UTC":
        return "unknown"                     # can't convert local times reliably
    start, end = _parse_time(detail["effective"]), _parse_time(detail["expires"])
    if end and win_start > end:
        return "expired"
    if start and win_end < start:
        return "scheduled"

    if area["daily"]:
        s = dtime.fromisoformat(area["daily"][0])
        e = dtime.fromisoformat(area["daily"][1])
        day = win_start.date() - timedelta(days=1)       # start a day early for overnight windows
        while day <= win_end.date():
            ds = datetime.combine(day, s, tzinfo=timezone.utc)
            de = datetime.combine(day if s <= e else day + timedelta(days=1), e, tzinfo=timezone.utc)
            in_range = (not end or ds <= end) and (not start or de >= start)
            if in_range and ds <= win_end and win_start <= de:
                return "active"
            day += timedelta(days=1)
        return "outside_hours"

    return "active" if (start or end) else "unknown"


async def _fetch_list(client: httpx.AsyncClient):
    r = await client.get(LIST_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


async def _refresh(client: httpx.AsyncClient):
    listing = await _fetch_list(client)
    if not isinstance(listing, list):
        raise ValueError("TFR list is not a JSON array")
    by_id = {t["notam_id"]: t for t in listing}
    for k in list(_detail_cache):
        if k not in by_id:
            del _detail_cache[k]

    sem = asyncio.Semaphore(8)

    async def load(nid):
        cached = _detail_cache.get(nid)
        if cached and time.time() - cached["at"] < DETAIL_TTL_S:
            return nid, cached["data"]
        async with sem:
            try:
                resp = await client.get(
                    DETAIL_URL.format(nid.replace("/", "_")), headers=HEADERS, timeout=15)
                resp.raise_for_status()
                data = _parse_detail(resp.text)
                _detail_cache[nid] = {"at": time.time(), "data": data}
                return nid, data
            except (httpx.HTTPError, ET.ParseError, ValueError, TypeError) as e:
                log.warning("TFR detail %s failed: %s", nid, e)
                return nid, (cached["data"] if cached else None)

    results = await asyncio.gather(*(load(n) for n in by_id))
    tfrs = [{"meta": by_id[nid], "detail": d} for nid, d in results if d is not None]
    unresolved = [nid for nid, d in results if d is None]
    return tfrs, unresolved


async def _load() -> None:
    if _state["at"] and time.time() - _state["at"] < CACHE_TTL_S:
        return
    async with _lock:
        if _state["at"] and time.time() - _state["at"] < CACHE_TTL_S:
            return
        try:
            async with http_client.client() as c:
                _state["tfrs"], _state["unresolved"] = await _refresh(c)
            _state["at"] = time.time()
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
            log.warning("TFR refresh failed: %s", e)   # keep serving the old state


async def get_tfrs(
    lat: float,
    lon: float,
    radius_m: Optional[float] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> TFRResult:
    """TFRs overlapping a circle around (lat, lon) during [start, end].

    Naive datetimes are treated as UTC. start defaults to now, end to start + 1 hour.
    """
    await _load()
    now = datetime.now(timezone.utc)
    if start is not None and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    radius_m = radius_m or DEFAULT_RADIUS_M
    win_start = start or now
    win_end = end or (win_start + timedelta(hours=1))

    base = dict(checked_at=now, radius_m=radius_m,
                window_start=win_start.isoformat(), window_end=win_end.isoformat())
    tfrs, fetched_at = _state["tfrs"], _state["at"]

    if tfrs is None or fetched_at is None:
        return TFRResult(**base, status="failed", error="TFR data unavailable from tfr.faa.gov",
                         note="Check tfr.faa.gov before flying.")

    age = int(time.time() - fetched_at)
    stale = age > CACHE_TTL_S
    common = dict(
        **base, tfrs_checked=len(tfrs), unresolved_notams=_state["unresolved"],
        data_fetched_at=datetime.fromtimestamp(fetched_at, timezone.utc).isoformat(),
        data_age_s=age)

    if age > MAX_STALE_S:
        return TFRResult(**common, status="failed", error="TFR data is over an hour old",
                         note="Check tfr.faa.gov before flying.")
    if not any(r["detail"]["areas"] for r in tfrs):
        return TFRResult(**common, status="failed", error="No TFR shapes were parsed from the FAA feed",
                         note="Check tfr.faa.gov before flying.")

    notes = []
    if stale:
        notes.append("Stale data, refresh failed.")
    if win_start > now + timedelta(hours=1):
        notes.append("TFRs are often issued on short notice, so none being known now does not "
                     "mean none will apply then. Recheck close to flight time.")
    status = "stale" if stale else "ok"

    area_box = _search_bbox(lat, lon, radius_m)
    hits = []
    for rec in tfrs:
        meta, det = rec["meta"], rec["detail"]
        for area in det["areas"]:
            if not _boxes_overlap(area["bbox"], area_box):
                continue
            hits.append(TFRArea(
                notam_id=meta["notam_id"], type=meta.get("type"),
                description=meta.get("description"), area_name=area["name"],
                floor_ft=area["floor_ft"], floor_datum=area["floor_datum"],
                ceiling_ft=area["ceiling_ft"], ceiling_datum=area["ceiling_datum"],
                effective=det["effective"], expires=det["expires"],
                time_status=_time_status(det, area, win_start, win_end),
                reaches_drone_altitudes=area["floor_ft"] is None or area["floor_ft"] <= DRONE_ALT_FT,
            ))

    relevant = [h for h in hits
                if h.time_status in ("active", "unknown") and h.reaches_drone_altitudes]
    if relevant:
        finding = "restricted"
    elif _state["unresolved"]:
        finding = "unknown"
        notes.append(f"{len(_state['unresolved'])} TFR(s) could not be checked. "
                     "Check tfr.faa.gov before flying.")
    else:
        finding = "none_found"
    return TFRResult(**common, status=status, finding=finding, tfrs=hits,
                     note=" ".join(notes) or None)
