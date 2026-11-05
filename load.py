"""Нагрузка: независимый поток /health, фиксированные входные данные и прогрев."""
import argparse
import asyncio
import json
import math
import random
import time
from datetime import timedelta
import httpx
from app.flights import AIRPORTS, START_DATE, DAYS

def statistics(rows, duration, end):
    times = sorted(row['latency_ms'] for row in rows)
    def percentile(p):
        return times[max(0, math.ceil(p*len(times))-1)] if times else None
    finished = sum(row['finished_s'] <= end for row in rows)
    return {'count': len(rows), 'rps': finished/duration,
            'p50_ms': percentile(.5), 'p95_ms': percentile(.95),
            'p99_ms': percentile(.99), 'max_ms': max(times) if times else None,
            'mean_ms': sum(times)/len(times) if times else None,
            'error_percent': 100*sum(row['error'] for row in rows)/len(rows) if rows else None}

async def run(args):
    query_rng = random.Random(args.seed)
    arrivals_rng = random.Random(args.seed + 1)
    search_rows, health_rows = [], []
    pending = set()
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=200)
    async with httpx.AsyncClient(base_url=args.url, timeout=args.timeout, limits=limits) as client, \
               httpx.AsyncClient(base_url=args.url, timeout=args.timeout, limits=limits) as health_client:
        start = time.perf_counter()
        measure_start = start + args.warmup
        end = measure_start + args.duration

        async def request(path, params, rows, http_client):
            sent = time.perf_counter()
            error = False
            try:
                # В отличие от отдельных тайм-аутов HTTPX, ограничивает запрос целиком.
                async with asyncio.timeout(args.timeout):
                    response = await http_client.get(path, params=params)
                    error = response.status_code >= 400
            except (TimeoutError, httpx.HTTPError):
                error = True
            finished = time.perf_counter()
            if measure_start <= sent < end:
                rows.append({'finished_s': finished-start,
                             'latency_ms': (finished-sent)*1000, 'error': error})

        def params():
            origin, destination = query_rng.sample(AIRPORTS, 2)
            day = START_DATE + timedelta(days=query_rng.randrange(DAYS))
            return {'origin': origin, 'destination': destination, 'date': day.isoformat()}

        def spawn(coroutine):
            task = asyncio.create_task(coroutine)
            pending.add(task)
            task.add_done_callback(pending.discard)

        async def closed_client():
            while time.perf_counter() < end:
                await request('/search', params(), search_rows, client)

        async def open_stream():
            scheduled = start
            while True:
                scheduled += arrivals_rng.expovariate(args.rate)
                if scheduled >= end:
                    break
                await asyncio.sleep(max(0, scheduled-time.perf_counter()))
                spawn(request('/search', params(), search_rows, client))

        async def health_stream():
            scheduled = start
            while scheduled < end:
                await asyncio.sleep(max(0, scheduled-time.perf_counter()))
                spawn(request('/health', None, health_rows, health_client))
                scheduled += .1

        workers = [closed_client() for _ in range(args.clients)] if args.mode == 'closed' else [open_stream()]
        await asyncio.gather(*workers, health_stream())
        if pending:
            await asyncio.gather(*list(pending))
    data = {'search': statistics(search_rows, args.duration, args.warmup+args.duration),
            'health': statistics(health_rows, args.duration, args.warmup+args.duration)}
    print(json.dumps(data, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:8000')
    parser.add_argument('--mode', choices=['closed','open'], required=True)
    parser.add_argument('--clients', type=int, default=1)
    parser.add_argument('--rate', type=float, default=5)
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--warmup', type=float, default=10)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    asyncio.run(run(args))
