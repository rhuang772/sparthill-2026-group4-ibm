from fastapi import APIRouter, Depends, HTTPException, Query, Request
from service import WeatherService, WeatherUnavailable, FaaService, FaaUnavailable
from models import Weather, HeightLimit

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