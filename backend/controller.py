from fastapi import APIRouter, Depends, HTTPException, Query, Request

from models import Weather, HeightLimit, TfrResult
from service.weather_service import WeatherService, WeatherUnavailable
from service.faa_service import FaaService, FaaUnavailable
from service.tfr_service import TfrService

#--------------- Weather API ----------------

router = APIRouter(prefix="/api/weather", tags=["weather"])

def get_weather_service(request: Request) -> WeatherService:
    return WeatherService(request.app.state.http_client)

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
    service: TfrService = Depends(get_tfr_service),
):
    return await service.get_tfrs(lat, lon, radius_m)


@tfr_router.get("/raw")
async def get_tfr_raw(service: TfrService = Depends(get_tfr_service)):
    """Debug: shows the start of the raw FAA TFR list."""
    try:
        data = await service.fetch_raw()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TFR feed error: {e}")
    return {"count": len(data), "sample": data[:3]}