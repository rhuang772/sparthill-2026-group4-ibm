from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from controller import router as weather_router, faa_router, tfr_router, water_router, population_router, park_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    yield
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)
app.include_router(weather_router)
app.include_router(faa_router)
app.include_router(tfr_router)
app.include_router(water_router)
app.include_router(population_router)
app.include_router(park_router)