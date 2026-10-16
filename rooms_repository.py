from copy import deepcopy

from rooms import (
    Booking,
    BookingId,
    EntityNotFound,
    MeetingRoom,
    RoomId,
    Employee,
)


# in-memory репозиторий комнат хранит агрегаты в словаре
class InMemoryRoomRepository:
    def __init__(self) -> None:
        self._data: dict[int, MeetingRoom] = {}

    def get(self, room_id: RoomId) -> MeetingRoom:
        if room_id.value not in self._data:
            raise EntityNotFound("Переговорная комната не найдена")
        return deepcopy(self._data[room_id.value])

    def save(self, room: MeetingRoom) -> None:
        self._data[room.id.value] = deepcopy(room)


# in-memory репозиторий бронирований 
class InMemoryBookingRepository:
    def __init__(self) -> None:
        self._data: dict[int, Booking] = {}

    def get(self, booking_id: BookingId) -> Booking:
        if booking_id.value not in self._data:
            raise EntityNotFound("Бронирование не найдено")
        return deepcopy(self._data[booking_id.value])

    def save(self, booking: Booking) -> None:
        self._data[booking.id.value] = deepcopy(booking)

    def all(self) -> tuple[Booking, ...]:
        return tuple(deepcopy(booking) for booking in self._data.values())


class InMemoryEmployeeRepository:
    def __init__(self):
        self._data: dict[int, Employee] = {}

    def get(self, employee_id: int) -> Employee:
        if employee_id not in self._data:
            raise EntityNotFound("Сотрудник не найден")
        return deepcopy(self._data[employee_id])

    def save(self, employee: Employee) -> None:
        self._data[employee.id] = deepcopy(employee)
