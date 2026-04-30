"""
Конечный автомат фазы детали.

Описывает, в каком состоянии находится деталь на текущий момент:
ожидает в хранилище, обрабатывается в блоке техоперации, или закончила
обработку и готова к передаче дальше.

Формальное определение:
    A_phase = (S, Sigma, delta, s_0, F)

где:
    S      = {WAITING, PROCESSING, DONE}
    Sigma  = {start_service, service_complete, depart}
    s_0    = WAITING
    F      = {}  (нет терминального состояния; после depart деталь
                 переходит в следующий блок и получает новый автомат фазы)

Таблица переходов:
    WAITING    --start_service----> PROCESSING
    PROCESSING --service_complete-> DONE
    DONE       --depart-----------> (выход из автомата, переход в след. блок)

Примечание: фаза WAITING фактически означает "лежит в предыдущем хранилище",
фаза PROCESSING - "находится в блоке техоперации, идет обработка",
фаза DONE - "обработка завершена, ожидает передачи в следующее хранилище".
"""

from __future__ import annotations

from enum import Enum, auto

from simulation.automata.base import StateMachine, Transition


class Phase(Enum):
    """Фазы нахождения детали в блоке."""
    WAITING = auto()
    PROCESSING = auto()
    DONE = auto()


class PhaseEvent(Enum):
    """События, вызывающие смену фазы."""
    START_SERVICE = auto()      # блок техоперации взял деталь в обработку
    SERVICE_COMPLETE = auto()   # время обработки истекло
    DEPART = auto()             # деталь передана в следующий блок


class PhaseAutomaton(StateMachine):
    """Автомат фазы детали в пределах одного блока обработки."""

    INITIAL_STATE = Phase.WAITING

    TRANSITIONS = [
        Transition(
            from_state=Phase.WAITING,
            event=PhaseEvent.START_SERVICE,
            to_state=Phase.PROCESSING,
        ),
        Transition(
            from_state=Phase.PROCESSING,
            event=PhaseEvent.SERVICE_COMPLETE,
            to_state=Phase.DONE,
        ),
        Transition(
            from_state=Phase.DONE,
            event=PhaseEvent.DEPART,
            to_state=Phase.WAITING,  # деталь снова WAITING в след. хранилище
        ),
    ]

    # Терминальных состояний нет: автомат циклически проходит фазы
    # для каждого нового блока по маршруту.
    TERMINAL_STATES: set = set()
