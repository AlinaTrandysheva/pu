"""Общие данные рейсов. Время всех рейсов задаётся в UTC, цена — в рублях."""
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

AIRPORTS = 'OVB SVO DME VKO LED SVX KZN AER UFA KUF ROV KRR VOG CEK TJM OMS TOF KJA IKT UUD HTA YKS KHV VVO PKC UUS MMK ARH KGD MRV'.split()
START_DATE = date(2026, 10, 19)
DAYS = 120

@dataclass(frozen=True, slots=True)
class Flight:
    carrier: str
    number: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    price: int

    def json(self):
        return {'carrier': self.carrier, 'number': self.number,
                'origin': self.origin, 'destination': self.destination,
                'departure': self.departure.isoformat(),
                'arrival': self.arrival.isoformat(), 'price': self.price}

    @classmethod
    def from_json(cls, row):
        return cls(**{**row, 'departure': datetime.fromisoformat(row['departure']),
                      'arrival': datetime.fromisoformat(row['arrival'])})

def generate(day: date, source: str, count: int):
    rng = random.Random(f'42-{source}-{day.isoformat()}')
    midnight = datetime.combine(day, time(), timezone.utc)
    flights = []
    for i in range(count):
        origin, destination = rng.sample(AIRPORTS, 2)
        departure = midnight + timedelta(minutes=rng.randrange(1440))
        flights.append(Flight(source, f'{source}{i+1:04d}', origin, destination,
                              departure, departure + timedelta(minutes=rng.randint(60, 360)),
                              rng.randint(1500, 20000)))
    return flights
