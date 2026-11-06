from datetime import datetime, time

from rooms import (
    Booking,
    BookingId,
    BookingService,
    MeetingRoom,
    ParticipantCount,
    RoomId,
    TimeSlot,
)
from rooms_repository import (
    InMemoryBookingRepository,
    InMemoryRoomRepository,
)


def main() -> None:
    # main создаёт in-memory репозитории и доменный сервис
    rooms = InMemoryRoomRepository()
    bookings = InMemoryBookingRepository()
    service = BookingService()

    # создаём и сохраняем переговорную комнату
    room_id = RoomId(1)
    room = MeetingRoom(
        room_id,
        "Сибирь",
        6,
        time(9, 0),
        time(18, 0),
    )
    rooms.save(room)

    # получаем комнату и создаём связанное с ней бронирование
    room = rooms.get(room_id)
    booking = Booking(
        BookingId(1),
        room.id,
        TimeSlot(
            datetime(2026, 10, 1, 10, 0),
            datetime(2026, 10, 1, 11, 0),
        ),
        ParticipantCount(4),
    )

    # доменный сервис работает с двумя агрегатами
    service.book_room(room, booking)

    # main сохраняет изменённую комнату и новое бронирование
    rooms.save(room)
    bookings.save(booking)
    print(f"Создано бронирование {booking.id.value}")


if __name__ == "__main__":
    main()
