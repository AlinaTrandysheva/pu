import asyncio
import os
import random
from datetime import date
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .flights import generate

app = FastAPI()
PROVIDER_ID = os.environ['PROVIDER_ID']
MEAN_MS = float(os.environ['MEAN_DELAY_MS'])
JITTER = float(os.getenv('JITTER', '0.3'))
ERROR_RATE = float(os.getenv('ERROR_RATE', '0.05'))
SLOW_RATE = float(os.getenv('SLOW_RATE', '0'))
FLIGHTS_PER_DAY = int(os.getenv('FLIGHTS_PER_DAY', '500'))

@app.get('/flights')
async def flights(date: date):
    delay = 3.0 if random.random() < SLOW_RATE else random.uniform(1-JITTER, 1+JITTER)*MEAN_MS/1000
    error = random.random() < ERROR_RATE
    await asyncio.sleep(delay)
    if error:
        raise HTTPException(500, 'Ошибка поставщика')
    return JSONResponse([f.json() for f in generate(date, PROVIDER_ID, FLIGHTS_PER_DAY)])

@app.get('/health')
async def health():
    return {'status': 'ok'}
