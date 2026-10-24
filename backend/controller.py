from fastapi import APIRouter, Depends, HTTPException, Query, Request
from datetime import datetime, timedelta, timezone

from models import Weather, WeatherForecast, HeightLimit, TfrResult, WaterResult
from service.water_service import WaterService, WaterUnavailable
from service.weather_service import WeatherService, WeatherUnavailable
from service.faa_service import FaaService, FaaUnavailable
from service.tfr_service import TfrService

#--------------- Weather API ----------------

router = APIRouter(prefix="/api/weather", tags=["weather"])

def get_weather_service(request: Request) -> WeatherService:
    return WeatherService(request.app.state.http_client)

@router.get("/forecast", response_model=WeatherForecast)
async def get_weather_forecast(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start: datetime | None = Query(None, description="Flight start, ISO 8601 (e.g. 2026-10-25T15:00:00Z). Default: now."),
    end: datetime | None = Query(None, description="Flight end. Default: start + 1 hour."),
    service: WeatherService = Depends(get_weather_service),
):
    now = datetime.now(timezone.utc)
    if start is not None and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)       # no zone given: assume UTC
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    win_start = start or now
    win_end = end or (win_start + timedelta(hours=1))

    if start is not None and start < now - timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="start cannot be in the past")
    if win_end <= win_start:
        raise HTTPException(status_code=400, detail="end must be after start")
    if win_end - win_start > timedelta(hours=48):
        raise HTTPException(status_code=400, detail="flight window cannot exceed 48 hours")
    if win_start > now + timedelta(days=15):
        raise HTTPException(status_code=400, detail="forecast is only available about 15 days ahead")

    try:
        return await service.get_window(lat, lon, win_start, win_end)
    except WeatherUnavailable:
        raise HTTPException(status_code=502, detail="Weather provider unavailable")

@router.get("", response_model=Weather)
async def get_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    service: WeatherService = Depends(get_weather_service),
):
    try:
        return await service.get_current(lat, lon)
    except WeatherUnavailable:
        raise HTTPException(status_code=502, detail="Weather provider unavailable")
    
    
#--------------- FAA Height Limit API ----------------

faa_router = APIRouter(prefix="/api/height-limit", tags=["faa"])

def get_faa_service(request: Request) -> FaaService:
    return FaaService(request.app.state.http_client)

@faa_router.get("", response_model=HeightLimit)
async def get_height_limit(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: float = Query(100, ge=0, le=5000),
    service: FaaService = Depends(get_faa_service),
):
    try:
        return await service.get_height_limit(lat, lon, radius_m)
    except FaaUnavailable:
        raise HTTPException(status_code=502, detail="FAA data service unavailable")
    
#--------------- TFR API ----------------
tfr_router = APIRouter(prefix="/api/tfr", tags=["tfr"])


def get_tfr_service(request: Request) -> TfrService:
    return TfrService(request.app.state.http_client)


@tfr_router.get("", response_model=TfrResult)
async def get_tfrs(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: float = Query(100, ge=0, le=20000),
    start: datetime | None = Query(None, description="Flight start, ISO 8601 (e.g. 2026-10-25T15:00:00Z). Default: now."),
    end: datetime | None = Query(None, description="Flight end. Default: start + 1 hour."),
    service: TfrService = Depends(get_tfr_service),
):
    now = datetime.now(timezone.utc)
    if start is not None and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)       # no zone given: assume UTC
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    effective_start = start or now
    if start is not None and start < now - timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="start cannot be in the past (the feed only has current and future TFRs)")
    if end is not None and end <= effective_start:
        raise HTTPException(status_code=400, detail="end must be after start")
    if end is not None and end - effective_start > timedelta(days=7):
        raise HTTPException(status_code=400, detail="flight window cannot exceed 7 days")

    return await service.get_tfrs(lat, lon, radius_m, start, end)


@tfr_router.get("/raw")
async def get_tfr_raw(service: TfrService = Depends(get_tfr_service)):
    """Debug: shows the start of the raw FAA TFR list."""
    try:
        data = await service.fetch_raw()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TFR feed error: {e}")
    return {"count": len(data), "sample": data[:3]}


#--------------- Water API ----------------

water_router = APIRouter(prefix="/api/water", tags=["water"])

def get_water_service(request: Request) -> WaterService:
    return WaterService(request.app.state.http_client)

@water_router.get("", response_model=WaterResult)
async def get_water(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: float = Query(500, ge=0, le=5000),
    include_flowlines: bool = Query(True, description="Include rivers, creeks and channels. Set false for lakes and ponds only"),
    service: WaterService = Depends(get_water_service),
):
    try:
        return await service.get_water(lat, lon, radius_m, include_flowlines)
    except WaterUnavailable as e:
        raise HTTPException(status_code=502, detail=f"Water data service unavailable: {e}")
@water_router.get("/raw")
async def get_water_raw(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: float = Query(500, ge=0, le=5000),
    service: WaterService = Depends(get_water_service),
):
    """Debug: the start of the raw Overpass response."""
    try:
        data = await service.fetch_raw(lat, lon, radius_m)
    except WaterUnavailable as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"remark": data.get("remark"), "count": len(data.get("elements", [])),
            "sample": data.get("elements", [])[:3]}