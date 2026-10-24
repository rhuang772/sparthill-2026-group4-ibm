"""
app/providers/http_client.py — shared httpx.AsyncClient for async providers.

main.py injects the app-wide client at startup. Outside the app (tests, scripts)
client() falls back to a short-lived client.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import httpx

_client: Optional[httpx.AsyncClient] = None


def set_http_client(c: Optional[httpx.AsyncClient]) -> None:
    global _client
    _client = c


@asynccontextmanager
async def client() -> AsyncIterator[httpx.AsyncClient]:
    if _client is not None:
        yield _client
    else:
        async with httpx.AsyncClient() as c:
            yield c
