import unittest
from datetime import datetime, time

# импортируем элементы доменной модели переговорных комнат
from rooms import (
    Booking,
    BookingId,
    BookingService,
    DomainInvariantViolation,
    InvalidValueObject,
    MeetingRoom,
    ParticipantCount,
    RoomId,
    TimeSlot,
)
from rooms_repository import (
    InMemoryBookingRepository,
    InMemoryRoomRepository,
)


class MeetingRoomTests(unittest.TestCase):
    def setUp(self) -> None:
        # для каждого теста создаём чистые репозитории
        self.rooms = InMemoryRoomRepository()
        self.bookings = InMemoryBookingRepository()
        self.service = BookingService()

        # создаём комнату и стандартный интервал бронирования
        self.room_id = RoomId(1)
        self.booking_id = BookingId(1)
        self.participants = ParticipantCount(4)
        self.slot = TimeSlot(
            datetime(2026, 10, 1, 10, 0),
            datetime(2026, 10, 1, 11, 0),
        )
        self.rooms.save(
            MeetingRoom(
                self.room_id,
                "Сибирь",
                6,
                time(9, 0),
                time(18, 0),
            )
        )

    # доменный сервис работает с комнатой и бронированием
    def test_book_room(self):
        room = self.rooms.get(self.room_id)
        booking = Booking(
            self.booking_id,
            room.id,
            self.slot,
            self.participants,
        )
        self.service.book_room(room, booking)

        # сохранение выполняется снаружи доменного сервиса
        self.rooms.save(room)
        self.bookings.save(booking)

        self.assertEqual(self.room_id, booking.room_id)
        self.assertEqual(booking.id, self.bookings.get(self.booking_id).id)
        room = self.rooms.get(self.room_id)
        self.assertEqual((self.booking_id,), room.booking_ids)

    # первый инвариант запрещает превышать вместимость комнаты
    def test_room_capacity_cannot_be_exceeded(self):
        room = self.rooms.get(self.room_id)
        booking = Booking(
            self.booking_id,
            room.id,
            self.slot,
            ParticipantCount(7),
        )

        with self.assertRaises(DomainInvariantViolation):
            self.service.book_room(room, booking)

    # второй инвариант запрещает бронь вне часов работы
    def test_booking_outside_office_hours_is_forbidden(self):
        early_slot = TimeSlot(
            datetime(2026, 10, 1, 8, 30),
            datetime(2026, 10, 1, 9, 30),
        )
        room = self.rooms.get(self.room_id)
        booking = Booking(
            self.booking_id,
            room.id,
            early_slot,
            self.participants,
        )

        with self.assertRaises(DomainInvariantViolation):
            self.service.book_room(room, booking)

    # каждый объект значение проверяет себя при создании
    def test_invalid_value_objects(self):
        with self.assertRaises(InvalidValueObject):
            RoomId(0)
        with self.assertRaises(InvalidValueObject):
            BookingId(-1)
        with self.assertRaises(InvalidValueObject):
            ParticipantCount(0)
        with self.assertRaises(InvalidValueObject):
            TimeSlot(
                datetime(2026, 10, 1, 11, 0),
                datetime(2026, 10, 1, 10, 0),
            )


if __name__ == "__main__":
    unittest.main()
