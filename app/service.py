import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import date
import httpx
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from .db import read_sync, read_async
from .flights import Flight
from .routes import build_routes

VERSION = os.getenv('SERVICE_VERSION', 'sync')
PROVIDERS = [(f'P{i}', os.getenv(f'PROVIDER_{i}_URL', f'http://provider{i}:8000')) for i in range(1, 4)]

@asynccontextmanager
async def lifespan(app):
    if VERSION == 'async':
        app.state.engine = create_async_engine(os.environ['ASYNC_DATABASE_URL'], pool_size=10, max_overflow=30)
        app.state.client = httpx.AsyncClient(timeout=None)
    else:
        app.state.engine = create_engine(os.environ['DATABASE_URL'], pool_size=10, max_overflow=30)
    yield
    if VERSION == 'async':
        await app.state.client.aclose()
        await app.state.engine.dispose()
    else:
        app.state.engine.dispose()

app = FastAPI(lifespan=lifespan)

def provider_sync(url, day):
    deadline = time.perf_counter() + 2.0
    for attempt in range(2):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return None
        try:
            response = requests.get(url + '/flights', params={'date': day.isoformat()}, timeout=remaining)
            response.raise_for_status()
            result = [Flight.from_json(row) for row in response.json()]
            return result if time.perf_counter() <= deadline else None
        except (requests.RequestException, ValueError, KeyError, TypeError):
            if attempt == 1 or deadline - time.perf_counter() <= .2:
                return None
            time.sleep(.2)
    return None

async def provider_async(client, url, day):
    try:
        async with asyncio.timeout(2.0):
            for attempt in range(2):
                try:
                    response = await client.get(url + '/flights', params={'date': day.isoformat()})
                    response.raise_for_status()
                    return [Flight.from_json(row) for row in response.json()]
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    if attempt == 1:
                        return None
                    await asyncio.sleep(.2)
    except TimeoutError:
        return None

def finish(own, results, origin, destination, day, started):
    missing = [name for (name, _), value in zip(PROVIDERS, results)
               if value is None or isinstance(value, Exception)]
    all_flights = list(own)
    for value in results:
        if value is not None and not isinstance(value, Exception):
            all_flights.extend(value)
    if not own and len(missing) == 3:
        return JSONResponse(status_code=503, content={'message': 'Поиск временно недоступен',
            'routes': [], 'unavailable_providers': missing,
            'processing_ms': round((time.perf_counter()-started)*1000, 3)})
    routes = build_routes(all_flights, origin, destination, day)
    return JSONResponse({'routes': routes, 'unavailable_providers': missing,
            'processing_ms': round((time.perf_counter()-started)*1000, 3)})

def search_sync(origin, destination, day):
    started = time.perf_counter()
    own = read_sync(app.state.engine, day)
    results = [provider_sync(url, day) for _, url in PROVIDERS]
    return finish(own, results, origin, destination, day, started)

if VERSION == 'sync':
    @app.get('/search')
    def search(origin: str, destination: str, date: date):
        return search_sync(origin, destination, date)

    @app.get('/health')
    def health():
        return {'status': 'ok'}
elif VERSION == 'blocking_async':
    # Задача 4.1: меняются только объявления обработчиков.
    @app.get('/search')
    async def search(origin: str, destination: str, date: date):
        return search_sync(origin, destination, date)

    @app.get('/health')
    async def health():
        return {'status': 'ok'}
elif VERSION == 'async':
    @app.get('/search')
    async def search(origin: str, destination: str, date: date):
        started = time.perf_counter()
        own, *results = await asyncio.gather(read_async(app.state.engine, date),
            *(provider_async(app.state.client, url, date) for _, url in PROVIDERS),
            return_exceptions=True)
        if isinstance(own, Exception):
            raise HTTPException(503, 'База данных недоступна')
        return finish(own, results, origin, destination, date, started)

    @app.get('/health')
    async def health():
        return {'status': 'ok'}
else:
    raise ValueError(f'Неизвестная версия: {VERSION}')
