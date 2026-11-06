from datetime import timedelta

from rooms import (
    DomainError, DomainInvariantViolation, GatewayUnresolved,
    room_is_free, room_is_busy, large_room_is_restricted,
    large_room_is_allowed, approval_is_required, approval_is_not_required,
)


class TransitionNotAllowed(DomainError):
    def __init__(self, state: str, event: str):
        self.state = state
        self.event = event
        super().__init__(f"Событие {event} недопустимо в состоянии «{state}»")

# базовый класс для всех состояний бронирования
class BookingState:
    name = "" 
    allowed: frozenset[str] = frozenset() # разрешённые события в текущем состоянии

    def review_application(self, booking, *, room_available, #  рассмотрение заявки
                           room_capacity, employee_restricted):
        raise TransitionNotAllowed(self.name, "review_application")

    def approve_booking(self, booking, *, now): # согласование
        raise TransitionNotAllowed(self.name, "approve_booking")

    def reject_booking(self, booking, *, now): # отклонение
        raise TransitionNotAllowed(self.name, "reject_booking")

    def approval_timeout(self, booking, *, now): # таймаут согласования
        raise TransitionNotAllowed(self.name, "approval_timeout")

    def confirm_booking(self, booking, *, room_confirmed, # подтверждение брони
                        services_required, order_confirmed):
        raise TransitionNotAllowed(self.name, "confirm_booking")

    def cancel_booking(self, booking, *, now): # отмена брони
        raise TransitionNotAllowed(self.name, "cancel_booking")

    def start_meeting(self, booking, *, now): # начало встречи
        raise TransitionNotAllowed(self.name, "start_meeting")

    def check_in(self, booking, *, now): # отметка присутствия
        raise TransitionNotAllowed(self.name, "check_in")

    def check_in_timeout(self, booking, *, now): # таймаут отметки
        raise TransitionNotAllowed(self.name, "check_in_timeout")

    def finish_meeting(self, booking, *, now): # завершение встречи
        raise TransitionNotAllowed(self.name, "finish_meeting")


class Submitted(BookingState):
    name = "Запрошена"
    allowed = frozenset({"review_application"})

    def review_application(self, booking, *, room_available,
                           room_capacity, employee_restricted):
        if room_is_busy(room_available):
            return RejectedBusy()
        if not room_is_free(room_available):
            raise GatewayUnresolved("Комната свободна?")
        if large_room_is_restricted(room_capacity, employee_restricted):
            return RejectedLimit()
        if not large_room_is_allowed(room_capacity, employee_restricted):
            raise GatewayUnresolved("Действует запрет на крупную комнату?")
        if approval_is_required(room_capacity, booking.time_slot):
            return AwaitingApproval()
        if approval_is_not_required(room_capacity, booking.time_slot):
            return Approved()
        raise GatewayUnresolved("Нужно согласование руководителя?")


class AwaitingApproval(BookingState):
    name = "Ожидающая согласования"
    allowed = frozenset({"approve_booking", "reject_booking", "approval_timeout"})

    def _check_response_time(self, booking, now):
        if not booking.submitted_at <= now < booking.submitted_at + timedelta(hours=24):
            raise DomainInvariantViolation("Ответ должен поступить до истечения 24 часов")

    def approve_booking(self, booking, *, now): # руководитель согласовал заявку
        self._check_response_time(booking, now)
        return Approved()

    def reject_booking(self, booking, *, now): # руководитель отклонил заявку
        self._check_response_time(booking, now)
        return RejectedManager()

    def approval_timeout(self, booking, *, now):
        if now < booking.submitted_at + timedelta(hours=24):
            raise DomainInvariantViolation("24 часа ожидания ещё не истекли")
        return RejectedTimeout()


class Approved(BookingState):
    name = "Согласована"
    allowed = frozenset({"confirm_booking"}) # подтвердить готовность брони

    def confirm_booking(self, booking, *, room_confirmed,
                        services_required, order_confirmed):
        if not room_confirmed or (services_required and not order_confirmed):
            raise DomainInvariantViolation("Не завершены все необходимые ветви подтверждения")
        return Confirmed()


class Confirmed(BookingState):
    name = "Подтверждена"
    allowed = frozenset({"cancel_booking", "start_meeting"})

    def cancel_booking(self, booking, *, now): # отменить бронь
        if now >= booking.time_slot.start:
            raise DomainInvariantViolation("Отмена допустима только до начала встречи")
        return Cancelled()

    def start_meeting(self, booking, *, now): # начало встречи
        if now < booking.time_slot.start:
            raise DomainInvariantViolation("Время начала встречи ещё не наступило")
        return AwaitingCheckIn()


class AwaitingCheckIn(BookingState):
    name = "Ожидающая отметки"
    allowed = frozenset({"check_in", "check_in_timeout"})

    def check_in(self, booking, *, now): # сотрудник отметила
        if not booking.time_slot.start <= now <= booking.time_slot.start + timedelta(minutes=15):
            raise DomainInvariantViolation("Отметка допустима не позднее 15 минут")
        return Active()

    def check_in_timeout(self, booking, *, now):  # сотрудник не отметился после 15 мин
        if now <= booking.time_slot.start + timedelta(minutes=15):
            raise DomainInvariantViolation("Срок отметки ещё не истёк")
        return NoShow()


class Active(BookingState):
    name = "Активна"
    allowed = frozenset({"finish_meeting"}) #завершена

    def finish_meeting(self, booking, *, now):
        if now < booking.time_slot.end:
            raise DomainInvariantViolation("Время окончания встречи ещё не наступило")
        return Completed()


class Completed(BookingState):
    name = "Завершена"


class RejectedBusy(BookingState):
    name = "Отклонена: комната занята"


class RejectedLimit(BookingState):
    name = "Отклонена: действует ограничение"


class RejectedManager(BookingState):
    name = "Отклонена руководителем"


class RejectedTimeout(BookingState):
    name = "Отклонена автоматически"


class Cancelled(BookingState):
    name = "Отменена сотрудником"


class NoShow(BookingState):
    name = "Снята из-за неявки"
