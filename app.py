import logging
import os
from datetime import datetime, time

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from booking_states import TransitionNotAllowed
from rooms import (BookingId, RoomId, TimeSlot, ParticipantCount, Employee,
                   MeetingRoom, DomainError, DomainInvariantViolation,
                   InvalidValueObject, EntityNotFound, GatewayUnresolved)
from rooms_adapters import ShiftedClock, ClockMovedBack, InMemoryEmployeeMessages
from rooms_repository import (InMemoryRoomRepository, InMemoryBookingRepository,
                              InMemoryEmployeeRepository)
from rooms_process import BookingProcess


def parse_time(value) -> datetime:
    if not isinstance(value, str):
        raise InvalidValueObject("Дата должна быть строкой ISO 8601")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise InvalidValueObject("Некорректная дата ISO 8601") from None
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise InvalidValueObject("Тело запроса должно быть JSON-объектом")
    return data


def required(data: dict, key: str):
    if key not in data:
        raise InvalidValueObject(f"Отсутствует поле {key}")
    return data[key]


def boolean(data: dict, key: str, default=None) -> bool:
    value = data.get(key, default)
    if type(value) is not bool:
        raise InvalidValueObject(f"Поле {key} должно быть true или false")
    return value


def booking_json(booking) -> dict:
    return {
        "id": booking.id.value,
        "room_id": booking.room_id.value,
        "employee_id": booking.employee_id,
        "start": booking.time_slot.start.isoformat(),
        "end": booking.time_slot.end.isoformat(),
        "status": booking.status,
        "allowed_events": sorted(booking.allowed_events),
        "events": [{"booking_id": e.booking_id.value,
                    "occurred_at": e.occurred_at.isoformat(), "name": e.name}
                   for e in booking.events],
    }


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    app.logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    clock = ShiftedClock()
    rooms = InMemoryRoomRepository()
    bookings = InMemoryBookingRepository()
    employees = InMemoryEmployeeRepository()
    rooms.save(MeetingRoom(RoomId(1), "Малая переговорная", 6, time(9), time(18)))
    rooms.save(MeetingRoom(RoomId(2), "Большая переговорная", 12, time(9), time(18)))
    employees.save(Employee(1))
    process = BookingProcess(rooms, bookings, employees, clock, InMemoryEmployeeMessages())
    app.extensions["booking_process"] = process
    app.extensions["bookings"] = bookings
    app.extensions["clock"] = clock

    @app.errorhandler(Exception)
    def handle_error(error):
        if isinstance(error, TransitionNotAllowed):
            code = 409
        elif isinstance(error, (DomainInvariantViolation, InvalidValueObject, ClockMovedBack)):
            code = 422
        elif isinstance(error, EntityNotFound):
            code = 404
        elif isinstance(error, GatewayUnresolved):
            code = 500
        elif isinstance(error, HTTPException):
            code = error.code
        else:
            code = 500
            app.logger.exception("Необработанная ошибка")
        message = str(error) if isinstance(error, (DomainError, HTTPException)) else "Внутренняя ошибка сервера"
        return jsonify(error=type(error).__name__, message=message), code

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.post("/bookings")
    def submit_booking():
        data = json_body()
        booking = process.submit_booking(
            BookingId(required(data, "id")), RoomId(required(data, "room_id")),
            TimeSlot(parse_time(required(data, "start")), parse_time(required(data, "end"))),
            ParticipantCount(required(data, "participants")), required(data, "employee_id"),
            equipment=boolean(data, "equipment", False), catering=boolean(data, "catering", False))
        return jsonify(booking_json(booking)), 201

    @app.get("/bookings/<int:booking_id>")
    def get_booking(booking_id):
        return jsonify(booking_json(bookings.get(BookingId(booking_id))))

    def result(booking_id):
        return jsonify(booking_json(bookings.get(BookingId(booking_id))))

    @app.post("/bookings/<int:booking_id>/manager-review")
    def manager_review(booking_id):
        process.review_manager_application(BookingId(booking_id), boolean(json_body(), "approved"))
        return result(booking_id)

    @app.post("/bookings/<int:booking_id>/services-confirmation")
    def services_confirmation(booking_id):
        process.confirm_services_order(BookingId(booking_id), boolean(json_body(), "confirmed"))
        return result(booking_id)

    @app.post("/bookings/<int:booking_id>/cancel")
    def cancel(booking_id):
        process.cancel_booking(BookingId(booking_id))
        return result(booking_id)

    @app.post("/bookings/<int:booking_id>/start")
    def start(booking_id):
        process.before_meeting(BookingId(booking_id), "start")
        return result(booking_id)

    @app.post("/bookings/<int:booking_id>/check-in")
    def check_in(booking_id):
        process.wait_for_check_in(BookingId(booking_id))
        return result(booking_id)

    @app.post("/bookings/<int:booking_id>/finish")
    def finish(booking_id):
        process.finish_meeting(BookingId(booking_id))
        return result(booking_id)

    @app.post("/internal/tick")
    def tick():
        data = json_body() if request.content_length else {}
        if "now" in data:
            clock.move_to(parse_time(data["now"]))
        now = clock.now()
        process.on_approval_timeout(now)
        process.on_meeting_started(now)
        process.on_check_in_timeout(now)
        process.on_meeting_finished(now)
        return jsonify(now=now.isoformat())

    return app


app = create_app()
