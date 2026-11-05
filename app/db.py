from datetime import datetime, time, timedelta, timezone
from sqlalchemy import MetaData, Table, Column, String, DateTime, Integer, Index, select
from .flights import Flight

metadata = MetaData()
flights = Table('flights', metadata,
    Column('carrier', String(16), primary_key=True),
    Column('number', String(16), primary_key=True),
    Column('origin', String(3), nullable=False),
    Column('destination', String(3), nullable=False),
    Column('departure', DateTime(timezone=True), primary_key=True),
    Column('arrival', DateTime(timezone=True), nullable=False),
    Column('price', Integer, nullable=False))
Index('ix_flights_departure', flights.c.departure)

def query(day):
    start = datetime.combine(day, time(), timezone.utc)
    return select(flights).where(flights.c.departure >= start,
                                flights.c.departure < start + timedelta(days=1))

def read_sync(engine, day):
    with engine.connect() as connection:
        rows = connection.execute(query(day)).all()
    return [Flight(*row) for row in rows]

async def read_async(engine, day):
    async with engine.connect() as connection:
        result = await connection.execute(query(day))
        rows = result.all()
    return [Flight(*row) for row in rows]
