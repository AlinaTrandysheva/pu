from dataclasses import dataclass
from datetime import datetime, time
from typing import Protocol


# базовая ошибка объединяет все ошибки предметной области
class DomainError(Exception):
    pass


# ошибка сообщает о некорректном объекте значении
class InvalidValueObject(DomainError):
    pass


# ошибка сообщает о нарушении бизнес правила
class DomainInvariantViolation(DomainError):
    pass


# ошибка сообщает что агрегат не найден в репозитории
class EntityNotFound(DomainError):
    pass


# общая проверка используется объектами идентификаторами
def _validate_id(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise InvalidValueObject(
            f"{name} должен быть положительным целым числом"
        )


# первый объект значение хранит идентификатор комнаты
@dataclass(frozen=True)
class RoomId:
    value: int

    def __post_init__(self) -> None:
        _validate_id(self.value, "ID комнаты")


# второй объект значение хранит идентификатор бронирования
@dataclass(frozen=True)
class BookingId:
    value: int

    def __post_init__(self) -> None:
        _validate_id(self.value, "ID бронирования")


# третий объект значение хранит число участников
@dataclass(frozen=True)
class ParticipantCount:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or self.value <= 0:
            raise InvalidValueObject(
                "Количество участников должно быть положительным целым числом"
            )


# четвёртый объект значение хранит временной интервал
@dataclass(frozen=True)
class TimeSlot:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if type(self.start) is not datetime or type(self.end) is not datetime:
            raise InvalidValueObject(
                "Начало и окончание должны иметь тип datetime"
            )
        if self.end <= self.start:
            raise InvalidValueObject(
                "Окончание бронирования должно быть позже начала"
            )


# первый агрегат содержит правила переговорной комнаты
class MeetingRoom:
    def __init__(
        self,
        room_id: RoomId,
        name: str,
        capacity: int,
        open_time: time,
        close_time: time,
    ) -> None:
        # сначала проверяем входные данные
        if not isinstance(room_id, RoomId):
            raise InvalidValueObject("Нужен корректный RoomId")
        if type(name) is not str or not name.strip():
            raise InvalidValueObject("Название комнаты не может быть пустым")
        if type(capacity) is not int or capacity <= 0:
            raise InvalidValueObject("Вместимость должна быть положительной")
        if type(open_time) is not time or type(close_time) is not time:
            raise InvalidValueObject(
                "Начало и окончание рабочего дня должны иметь тип time"
            )
        if close_time <= open_time:
            raise InvalidValueObject(
                "Окончание рабочего дня должно быть позже его начала"
            )

        # внутреннее состояние закрыто от прямого изменения
        self._id = room_id
        self._name = name.strip()
        self._capacity = capacity
        self._open_time = open_time
        self._close_time = close_time
        # комната хранит только идентификаторы связанных бронирований
        self._booking_ids: list[BookingId] = []

    # свойства дают доступ к данным только для чтения
    @property
    def id(self) -> RoomId:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def booking_ids(self) -> tuple[BookingId, ...]:
        # кортеж не позволяет изменить внутренний список снаружи
        return tuple(self._booking_ids)

    def check_capacity(self, participants: ParticipantCount) -> None:
        # первый инвариант запрещает превышать вместимость комнаты
        if not isinstance(participants, ParticipantCount):
            raise InvalidValueObject("Нужен корректный ParticipantCount")
        if participants.value > self._capacity:
            raise DomainInvariantViolation(
                "Количество участников превышает вместимость комнаты"
            )

    def check_office_hours(self, time_slot: TimeSlot) -> None:
        # второй инвариант ограничивает бронь часами работы
        if not isinstance(time_slot, TimeSlot):
            raise InvalidValueObject("Нужен корректный TimeSlot")

        # интервал должен полностью находиться внутри одного рабочего дня
        is_allowed = (
            time_slot.start.date() == time_slot.end.date()
            and self._open_time <= time_slot.start.time()
            and time_slot.end.time() <= self._close_time
        )
        if not is_allowed:
            raise DomainInvariantViolation(
                "Бронирование должно находиться в пределах часов работы офиса"
            )

    def reserve(
        self,
        booking_id: BookingId,
        participants: ParticipantCount,
        time_slot: TimeSlot,
    ) -> None:
        # метод изменяет комнату только после проверки двух инвариантов
        if not isinstance(booking_id, BookingId):
            raise InvalidValueObject("Нужен корректный BookingId")
        self.check_capacity(participants)
        self.check_office_hours(time_slot)
        self._booking_ids.append(booking_id)


# второй агрегат связан с комнатой только через room_id
class Booking:
    def __init__(
        self,
        booking_id: BookingId,
        room_id: RoomId,
        time_slot: TimeSlot,
        participants: ParticipantCount,
    ) -> None:
        # агрегат принимает только проверенные объекты значения
        if not isinstance(booking_id, BookingId):
            raise InvalidValueObject("Нужен корректный BookingId")
        if not isinstance(room_id, RoomId):
            raise InvalidValueObject("Нужен корректный RoomId")
        if not isinstance(time_slot, TimeSlot):
            raise InvalidValueObject("Нужен корректный TimeSlot")
        if not isinstance(participants, ParticipantCount):
            raise InvalidValueObject("Нужен корректный ParticipantCount")

        self._id = booking_id
        self._room_id = room_id
        self._time_slot = time_slot
        self._participants = participants

    # свойства позволяют только читать состояние бронирования
    @property
    def id(self) -> BookingId:
        return self._id

    @property
    def room_id(self) -> RoomId:
        return self._room_id

    @property
    def time_slot(self) -> TimeSlot:
        return self._time_slot

    @property
    def participants(self) -> ParticipantCount:
        return self._participants


# порты описывают работу с агрегатами без привязки к хранилищу
class RoomRepository(Protocol):
    def get(self, room_id: RoomId) -> MeetingRoom:
        ...

    def save(self, room: MeetingRoom) -> None:
        ...


class BookingRepository(Protocol):
    def get(self, booking_id: BookingId) -> Booking:
        ...

    def save(self, booking: Booking) -> None:
        ...


# доменный сервис выполняет одну операцию с двумя агрегатами
class BookingService:
    def book_room(
        self,
        room: MeetingRoom,
        booking: Booking,
    ) -> Booking:
        # сервис получает готовые агрегаты 
        room.reserve(booking.id, booking.participants, booking.time_slot)

        return booking
