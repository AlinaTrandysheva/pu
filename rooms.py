from dataclasses import dataclass
from datetime import datetime, time, date, timedelta
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

# не определилась ветка BPMN-шлюза
class GatewayUnresolved(DomainError):
    pass


@dataclass(frozen=True)
class BookingEvent:
    booking_id: "BookingId"
    occurred_at: datetime
    name: str


class Employee:
    def __init__(self, employee_id: int):
        _validate_id(employee_id, "ID сотрудника")
        self._id = employee_id
        self._no_shows: list[date] = []
        self._restricted_until: date | None = None

    @property
    def id(self) -> int:
        return self._id

    @property
    def restricted_until(self) -> date | None:
        return self._restricted_until

    def record_no_show(self, meeting_date: date) -> None:
        self._no_shows.append(meeting_date)

    def no_show_count(self, month: date) -> int:
        return sum((day.year, day.month) == (month.year, month.month)
                   for day in self._no_shows)

    def restrict_large_rooms(self, month: date) -> None:
        if self.no_show_count(month) < 3:
            raise DomainInvariantViolation("Для ограничения нужны три неявки за месяц")
        self._restricted_until = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

    def is_restricted(self, now: datetime) -> bool:
        return (self._restricted_until is not None
                and now.date() < self._restricted_until
                and now.date().replace(day=1) ==
                (self._restricted_until - timedelta(days=1)).replace(day=1))


# функции-предикаты для условий на искл шлюзах

def room_is_free(available) -> bool:
    return available is True


def room_is_busy(available) -> bool:
    return available is False


def large_room_is_restricted(capacity: int, restricted: bool) -> bool:
    return capacity > 10 and restricted


def large_room_is_allowed(capacity: int, restricted: bool) -> bool:
    return not large_room_is_restricted(capacity, restricted)


def approval_is_required(capacity: int, slot: "TimeSlot") -> bool:
    return capacity > 10 or slot.end - slot.start > timedelta(hours=4)


def approval_is_not_required(capacity: int, slot: "TimeSlot") -> bool:
    return not approval_is_required(capacity, slot)


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
        self._reservations: dict[BookingId, TimeSlot] = {}

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
        return tuple(self._reservations)

    def is_available(self, time_slot: TimeSlot) -> bool:
        return all(time_slot.end <= slot.start or time_slot.start >= slot.end
                   for slot in self._reservations.values())

    def release(self, booking_id: BookingId) -> None:
        if booking_id not in self._reservations:
            raise DomainInvariantViolation("Комната не занята этой бронью")
        del self._reservations[booking_id]

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
        if booking_id in self._reservations or not self.is_available(time_slot):
            raise DomainInvariantViolation("Интервал комнаты уже занят")
        self._reservations[booking_id] = time_slot


# второй агрегат связан с комнатой только через room_id
class Booking:
    def __init__(
        self,
        booking_id: BookingId,
        room_id: RoomId,
        time_slot: TimeSlot,
        participants: ParticipantCount,
        *,
        submitted_at: datetime,
        employee_id: int,
        equipment: bool = False,
        catering: bool = False,
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
        if type(submitted_at) is not datetime:
            raise InvalidValueObject("Дата подачи должна иметь тип datetime")
        if submitted_at >= time_slot.start:
            raise DomainInvariantViolation("Заявка подаётся до начала встречи")
        self._submitted_at = submitted_at
        _validate_id(employee_id, "ID сотрудника")
        self._employee_id = employee_id
        self._equipment = equipment
        self._catering = catering
        self._room_confirmed = False
        self._order_confirmed = False
        self._events: list[BookingEvent] = []
        from booking_states import Submitted
        self._state = Submitted()
        self.record_message("Заявка подана", submitted_at)

    @property
    def employee_id(self) -> int:
        return self._employee_id

    @property
    def services_required(self) -> bool:
        return self._equipment or self._catering

    @property
    def equipment(self) -> bool:
        return self._equipment

    @property
    def catering(self) -> bool:
        return self._catering

    @property
    def room_confirmed(self) -> bool:
        return self._room_confirmed

    @property
    def order_confirmed(self) -> bool:
        return self._order_confirmed

    @property
    def events(self) -> tuple[BookingEvent, ...]:
        return tuple(self._events)

    # добавляет событие в историю бронирования
    def record_message(self, name: str, now: datetime) -> BookingEvent:
        event = BookingEvent(self.id, now, name)
        self._events.append(event)
        return event

    # отмечает, что сама комната подтверждена
    def mark_room_confirmed(self) -> None:
        # проверяем, разрешено ли подтверждение в текущем состоянии
        if "confirm_booking" not in self.allowed_events:
            from booking_states import TransitionNotAllowed
            raise TransitionNotAllowed(self.status, "confirm_booking")
        self._room_confirmed = True

    # отмечает результат подтверждения оборудования/кейтеринга
    def mark_order_confirmed(self, confirmed: bool) -> None:

        if "confirm_booking" not in self.allowed_events:
            from booking_states import TransitionNotAllowed
            raise TransitionNotAllowed(self.status, "confirm_booking")
        self._order_confirmed = confirmed

    # время подачи заявки
    @property
    def submitted_at(self) -> datetime:
        return self._submitted_at

    # текущее состояние бронирования
    @property
    def status(self) -> str:
        return self._state.name
    
    # события, разрешённые в текущем состоянии
    @property
    def allowed_events(self) -> frozenset[str]:
        return self._state.allowed

    # рассматриваем новую заявку и переводим её в следующее состояние
    def review_application(self, *, now: datetime, room_available: bool,
                           room_capacity: int, employee_restricted: bool) -> None:
        self._state = self._state.review_application(
            self, room_available=room_available,
            room_capacity=room_capacity, employee_restricted=employee_restricted)
        self.record_message(f"Заявка рассмотрена: {self.status}", now)

    # руководитель согласовал заявку
    def approve_booking(self, now: datetime) -> None:
        self._state = self._state.approve_booking(self, now=now)
        self.record_message("Заявка согласована руководителем", now)

    # руководитель отклонил заявку
    def reject_booking(self, now: datetime) -> None:
        self._state = self._state.reject_booking(self, now=now)
        self.record_message("Заявка отклонена руководителем", now)

    # 24 часа на согласование истекли
    def approval_timeout(self, now: datetime) -> None:
        self._state = self._state.approval_timeout(self, now=now)
        self.record_message("Заявка отклонена автоматически", now)

    # подтверждаем готовность брони
    def confirm_booking(self, *, now: datetime, room_confirmed: bool,
                        services_required: bool, order_confirmed: bool) -> None:
        self._state = self._state.confirm_booking(
            self, room_confirmed=room_confirmed,
            services_required=services_required, order_confirmed=order_confirmed)
        self.record_message("Готовность брони подтверждена", now)

    # сотрудник отменяет бронь
    def cancel_booking(self, now: datetime) -> None:
        self._state = self._state.cancel_booking(self, now=now)
        self.record_message("Бронь отменена сотрудником", now)

    # наступает время начала встречи
    def start_meeting(self, now: datetime) -> None:
        self._state = self._state.start_meeting(self, now=now)
        self.record_message("Встреча началась", now)

    # сотрудник отмечает присутствие
    def check_in(self, now: datetime) -> None:
        self._state = self._state.check_in(self, now=now)
        self.record_message("Присутствие сотрудника подтверждено", now)

    # сотрудник не отметился в течение 15 минут
    def check_in_timeout(self, now: datetime) -> None:
        self._state = self._state.check_in_timeout(self, now=now)
        self.record_message("Бронь снята из-за неявки", now)

    # встреча завершена
    def finish_meeting(self, now: datetime) -> None:
        self._state = self._state.finish_meeting(self, now=now)
        self.record_message("Встреча завершена", now)

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

    def all(self) -> tuple[Booking, ...]:
        ...


class EmployeeRepository(Protocol):
    def get(self, employee_id: int) -> Employee: ...
    def save(self, employee: Employee) -> None: ...


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
