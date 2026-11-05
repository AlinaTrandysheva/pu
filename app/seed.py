import os
from dataclasses import asdict
from datetime import timedelta
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert
from .db import metadata, flights
from .flights import generate, START_DATE, DAYS

def main():
    engine = create_engine(os.environ['DATABASE_URL'])
    metadata.create_all(engine)
    with engine.begin() as connection:
        for offset in range(DAYS):
            day = START_DATE + timedelta(days=offset)
            rows = [asdict(f) for f in generate(day, 'OWN', 1500)]
            statement = insert(flights).values(rows).on_conflict_do_nothing()
            connection.execute(statement)
    with engine.connect() as connection:
        print('Рейсов в базе:', connection.execute(select(func.count()).select_from(flights)).scalar())
    engine.dispose()

if __name__ == '__main__':
    main()
