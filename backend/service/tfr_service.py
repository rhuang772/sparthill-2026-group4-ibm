import asyncio
import logging
import math
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone, time as dtime

import httpx

from backend.models import TfrItem, TfrResult

log = logging.getLogger("tfr")

LIST_URL = "https://tfr.faa.gov/tfrapi/exportTfrList"
DETAIL_URL = "https://tfr.faa.gov/download/detail_{}.xml"
HEADERS = {"User-Agent": "Mozilla/5.0"}

CACHE_TTL_S = 300        # re-fetch the list every 5 minutes
DETAIL_TTL_S = 1800      # re-fetch a NOTAM's detail every 30 minutes
MAX_STALE_S = 3600       # beyond 1 hour, refuse to answer
DRONE_ALT_FT = 400

_state = {"at": None, "tfrs": None, "unresolved": []}
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


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
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


class TfrService:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch_raw(self):
        r = await self.client.get(LIST_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()

    async def _refresh(self):
        listing = await self.fetch_raw()
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
                    resp = await self.client.get(
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

    async def _load(self):
        now = time.time()
        if _state["at"] and now - _state["at"] < CACHE_TTL_S:
            return
        async with _lock:
            if _state["at"] and time.time() - _state["at"] < CACHE_TTL_S:
                return
            try:
                _state["tfrs"], _state["unresolved"] = await self._refresh()
                _state["at"] = time.time()
            except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
                log.warning("TFR refresh failed: %s", e)   # keep serving the old state

    async def get_tfrs(self, lat: float, lon: float, radius_m: float,
                       start: datetime | None = None, end: datetime | None = None) -> TfrResult:
        await self._load()
        now = datetime.now(timezone.utc)
        win_start = start or now
        win_end = end or (win_start + timedelta(hours=1))

        base = dict(lat=lat, lon=lon, radius_m=radius_m,
                    window_start=win_start.isoformat(), window_end=win_end.isoformat())
        tfrs, fetched_at = _state["tfrs"], _state["at"]

        if tfrs is None or fetched_at is None:
            return TfrResult(
                **base, status="unknown", tfrs=[], tfrs_checked=0, unresolved_notams=[],
                data_fetched_at=None, data_age_seconds=None, stale=True,
                note="TFR data unavailable. Check tfr.faa.gov before flying.")

        age = int(time.time() - fetched_at)
        common = dict(
            **base, tfrs_checked=len(tfrs), unresolved_notams=_state["unresolved"],
            data_fetched_at=datetime.fromtimestamp(fetched_at, timezone.utc).isoformat(),
            data_age_seconds=age, stale=age > CACHE_TTL_S)

        notes = []
        if common["stale"]:
            notes.append("Stale data, refresh failed.")
        if win_start > now + timedelta(hours=1):
            notes.append("TFRs are often issued on short notice, so none being known now does not "
                         "mean none will apply then. Recheck close to flight time.")
        note = " ".join(notes) or None

        if age > MAX_STALE_S:
            return TfrResult(**common, status="unknown", tfrs=[],
                             note="TFR data is over an hour old. Check tfr.faa.gov before flying.")
        if not any(r["detail"]["areas"] for r in tfrs):
            return TfrResult(**common, status="unknown", tfrs=[],
                             note="No TFR shapes were parsed, which is unexpected. Verify the parser.")

        area_box = _search_bbox(lat, lon, radius_m)
        hits = []
        for rec in tfrs:
            meta, det = rec["meta"], rec["detail"]
            for area in det["areas"]:
                if not _boxes_overlap(area["bbox"], area_box):
                    continue
                hits.append(TfrItem(
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
            return TfrResult(**common, status="restricted", tfrs=hits, note=note)
        if _state["unresolved"]:
            unresolved_note = (f"{len(_state['unresolved'])} TFR(s) could not be checked. "
                               "Check tfr.faa.gov before flying.")
            return TfrResult(**common, status="unknown", tfrs=hits,
                             note=" ".join(filter(None, [note, unresolved_note])))
        return TfrResult(**common, status="clear", tfrs=hits, note=note)