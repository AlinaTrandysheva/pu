from datetime import datetime, timedelta
from typing import Protocol

from booking_states import TransitionNotAllowed
from rooms import (Booking, BookingId, RoomId, TimeSlot, ParticipantCount,
                   BookingEvent, BookingRepository, RoomRepository,
                   EmployeeRepository, GatewayUnresolved, DomainInvariantViolation)


class Clock(Protocol):
    def now(self) -> datetime: ...


class EmployeeMessages(Protocol):
    # отправить сотруднику событие бронирования
    def send(self, employee_id: int, event: BookingEvent) -> None: ...

# согласовал ли руководитель заявку
def manager_approved(result) -> bool:
    return result is True

# отклонил ли руководитель заявку
def manager_rejected(result) -> bool:
    return result is False

# нужны ли оборудование или кейтеринг
def services_are_required(booking: Booking) -> bool:
    return booking.services_required

# проверяем, что дополнительные услуги не нужны
def services_are_not_required(booking: Booking) -> bool:
    return not booking.services_required

# проверяем, пришла ли команда отмены
def cancellation_received(action: str) -> bool:
    return action == "cancel"

# проверяем, пришла ли команда начала встречи
def meeting_started(action: str) -> bool:
    return action == "start"

# ограничение крупных комнат требуется после 3 неявок
def restriction_is_required(count: int) -> bool:
    return count >= 3

# ограничение пока не требуется
def restriction_is_not_required(count: int) -> bool:
    return count < 3

# прикладной сервис управляет всем процессом бронирования
class BookingProcess:
     # получаем репозитории, часы и сервис сообщений
    def __init__(self, rooms: RoomRepository, bookings: BookingRepository,
                 employees: EmployeeRepository, clock: Clock,
                 messages: EmployeeMessages):
        self._rooms = rooms
        self._bookings = bookings
        self._employees = employees
        self._clock = clock
        self._messages = messages
    
    # записываем событие в историю и при необходимости отправляем сотруднику
    def _message(self, booking: Booking, name: str, now: datetime,
                 to_employee: bool = False) -> None:
        event = booking.record_message(name, now)
        if to_employee:
            self._messages.send(booking.employee_id, event)

     # сохраняем бронирование в репозитории
    def _save(self, booking: Booking) -> None:
        self._bookings.save(booking)

    def submit_booking(self, booking_id: BookingId, room_id: RoomId,
                       slot: TimeSlot, participants: ParticipantCount,
                       employee_id: int, equipment=False, catering=False) -> Booking:
        if any(b.id == booking_id for b in self._bookings.all()):
            raise DomainInvariantViolation("ID бронирования уже существует")
        self._employees.get(employee_id)
        booking = Booking(booking_id, room_id, slot, participants,
                          submitted_at=self._clock.now(), employee_id=employee_id,
                          equipment=equipment, catering=catering)
        available = self.check_room_availability(booking)
        restricted = self.check_employee_restriction(booking)
        booking.review_application(room_available=available,
                                   room_capacity=self._rooms.get(room_id).capacity,
                                   employee_restricted=restricted)
        if "approve_booking" in booking.allowed_events:
            self._message(booking, "Заявка направлена руководителю", self._clock.now())
        elif not booking.allowed_events:
            self._message(booking, booking.status,
                          self._clock.now(), True)
        else:
            self._prepare_booking(booking)
        self._save(booking)
        return booking

    def check_room_availability(self, booking: Booking) -> bool:
        room = self._rooms.get(booking.room_id)
        room.check_capacity(booking.participants)
        room.check_office_hours(booking.time_slot)
        return room.is_available(booking.time_slot)

    def check_employee_restriction(self, booking: Booking) -> bool:
        employee = self._employees.get(booking.employee_id)
        return employee.is_restricted(self._clock.now())

    def review_manager_application(self, booking_id: BookingId, approved: bool) -> None:
        booking = self._bookings.get(booking_id)
        now = self._clock.now()
        if "approve_booking" in booking.allowed_events and now >= booking.submitted_at + timedelta(hours=24):
            self.on_approval_timeout(now)
            return
        if manager_approved(approved):
            booking.approve_booking(now)
            self._message(booking, "Заявка согласована руководителем", now)
            self._prepare_booking(booking)
        elif manager_rejected(approved):
            booking.reject_booking(now)
            self._message(booking, "Заявка отклонена руководителем", now, True)
        else:
            raise GatewayUnresolved("Руководитель согласовал заявку?")
        self._save(booking)

    def _prepare_booking(self, booking: Booking) -> None:
        # Параллельные ветви выполняются последовательно; слияние — после обеих.
        if services_are_required(booking):
            self.confirm_room(booking)
            requested = []
            if booking.equipment:
                requested.append("оборудование")
            if booking.catering:
                requested.append("кейтеринг")
            self._message(booking, "Администратору направлен заказ: " + ", ".join(requested),
                          self._clock.now())
        elif services_are_not_required(booking):
            self.confirm_room(booking)
            self.notify_booking_ready(booking)
        else:
            raise GatewayUnresolved("Нужны оборудование или кейтеринг?")

    def confirm_room(self, booking: Booking) -> None:
        if "confirm_booking" not in booking.allowed_events:
            raise TransitionNotAllowed(booking.status, "confirm_booking")
        room = self._rooms.get(booking.room_id)
        room.reserve(booking.id, booking.participants, booking.time_slot)
        booking.mark_room_confirmed()
        self._rooms.save(room)

    def confirm_services_order(self, booking_id: BookingId, confirmed: bool) -> None:
        booking = self._bookings.get(booking_id)
        booking.mark_order_confirmed(confirmed)
        if confirmed:
            self._message(booking, "Заказ услуг подтверждён",
                          self._clock.now())
            if booking.room_confirmed:
                self.notify_booking_ready(booking)
        self._save(booking)

    def notify_booking_ready(self, booking: Booking) -> None:
        booking.confirm_booking(room_confirmed=booking.room_confirmed,
                                services_required=booking.services_required,
                                order_confirmed=booking.order_confirmed)
        self._message(booking, "Готовность брони подтверждена", self._clock.now(), True)

    def before_meeting(self, booking_id: BookingId, action: str) -> None:
        if cancellation_received(action):
            self.cancel_booking(booking_id)
        elif meeting_started(action):
            booking = self._bookings.get(booking_id)
            now = self._clock.now()
            booking.start_meeting(now)
            self._message(booking, "Встреча началась", now)
            self._save(booking)
        else:
            raise GatewayUnresolved("Что произошло до начала встречи?")

    def cancel_booking(self, booking_id: BookingId) -> None:
        booking = self._bookings.get(booking_id)
        now = self._clock.now()
        booking.cancel_booking(now)
        self.free_room(booking)
        self._message(booking, "Бронь отменена сотрудником", now, True)
        self._save(booking)

    def wait_for_check_in(self, booking_id: BookingId) -> None:
        """Результат задачи ожидания — полученная отметка о присутствии."""
        booking = self._bookings.get(booking_id)
        now = self._clock.now()
        booking.check_in(now)
        self._message(booking, "Присутствие сотрудника подтверждено", now)
        self._save(booking)

    def free_room(self, booking: Booking) -> None:
        room = self._rooms.get(booking.room_id)
        room.release(booking.id)
        self._rooms.save(room)

    def finish_meeting(self, booking_id: BookingId) -> None:
        booking = self._bookings.get(booking_id)
        now = self._clock.now()
        booking.finish_meeting(now)
        self.free_room(booking)
        self._message(booking, "Встреча завершена, комната освобождена", now, True)
        self._save(booking)

    def notify_automatic_rejection(self, booking: Booking, now: datetime) -> None:
        self._message(booking, "Заявка отклонена автоматически", now, True)

    def remove_no_show_booking(self, booking: Booking, now: datetime) -> None:
        booking.check_in_timeout(now)

    def record_no_show(self, booking: Booking):
        employee = self._employees.get(booking.employee_id)
        employee.record_no_show(booking.time_slot.start.date())
        self._employees.save(employee)
        return employee

    def restrict_large_rooms(self, employee, booking: Booking, now: datetime) -> None:
        employee.restrict_large_rooms(booking.time_slot.start.date())
        self._employees.save(employee)
        self._message(booking, "Бронирование крупных комнат ограничено до конца месяца",
                      now, True)

    def on_approval_timeout(self, now: datetime) -> None:
        for booking in self._bookings.all():
            if ("approval_timeout" in booking.allowed_events
                    and now >= booking.submitted_at + timedelta(hours=24)):
                booking.approval_timeout(now)
                self.notify_automatic_rejection(booking, now)
                self._save(booking)

    def on_meeting_started(self, now: datetime) -> None:
        for booking in self._bookings.all():
            if "start_meeting" in booking.allowed_events and now >= booking.time_slot.start:
                booking.start_meeting(now)
                self._message(booking, "Встреча началась", now)
                self._save(booking)

    def on_check_in_timeout(self, now: datetime) -> None:
        for booking in self._bookings.all():
            if ("check_in_timeout" in booking.allowed_events
                    and now >= booking.time_slot.start + timedelta(minutes=15)):
                self.remove_no_show_booking(booking, now)
                self.free_room(booking)
                employee = self.record_no_show(booking)
                count = employee.no_show_count(booking.time_slot.start.date())
                self._message(booking, "Бронь снята из-за неявки, комната освобождена", now, True)
                if restriction_is_required(count):
                    self.restrict_large_rooms(employee, booking, now)
                elif not restriction_is_not_required(count):
                    raise GatewayUnresolved("Это третья неявка за месяц?")
                self._save(booking)

    def on_meeting_finished(self, now: datetime) -> None:
        for booking in self._bookings.all():
            if "finish_meeting" in booking.allowed_events and now >= booking.time_slot.end:
                booking.finish_meeting(now)
                self.free_room(booking)
                self._message(booking, "Встреча завершена, комната освобождена", now, True)
                self._save(booking)
