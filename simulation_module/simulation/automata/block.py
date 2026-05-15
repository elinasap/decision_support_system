"""
Конечный автомат состояния блока техоперации.

Описывает поведение производственной операции (PROCESS, ASSEMBLY,
CONTROL, TRANSPORT) во времени. Это тот самый "конечный автомат
состояний производственной операции", который указан в плане
диссертации как отдельный пункт.

Состояния:
    IDLE     - блок свободен, в нем нет деталей, ждет когда в upstream
               BUFFER появится подходящая деталь
    BUSY     - блок обрабатывает деталь
    BLOCKED  - обработка завершена, но downstream BUFFER переполнен,
               деталь некуда отдать; блок физически не работает,
               но и не свободен

События:
    BUFFER_HAS_DETAIL  - в upstream-буфере появилась подходящая деталь
                         (генерируется автоматом BufferAutomaton при
                         переходе EMPTY -> HAS_ITEMS / FULL)
    SERVICE_FINISHED   - время обработки t_proc истекло
    DOWNSTREAM_FREE    - downstream-буфер освободил место
                         (генерируется автоматом BufferAutomaton при
                         переходе FULL -> HAS_ITEMS / EMPTY)

Формальное определение:
    A_op = (S, Sigma, delta, s_0, F)

где:
    S      = {IDLE, BUSY, BLOCKED}
    Sigma  = {BUFFER_HAS_DETAIL, SERVICE_FINISHED, DOWNSTREAM_FREE}
    s_0    = IDLE
    F      = {}  (нет терминальных состояний - блок работает бесконечно)

Таблица переходов (4 правила):
    IDLE     --buffer_has_detail---------------------------> BUSY
    BUSY     --service_finished [downstream свободен]------> IDLE
    BUSY     --service_finished [downstream полон]---------> BLOCKED
    BLOCKED  --downstream_free-----------------------------> IDLE

Состояние BLOCKED критично для корректного моделирования узких мест:
без него непонятно, чем именно занят блок - работой или ожиданием
освобождения downstream. С ним метрики прозрачны: total_busy_time
(производительная работа) и total_blocked_time (вынужденный простой
из-за затора).
"""

from __future__ import annotations

from enum import Enum, auto

from simulation.automata.base import StateMachine, Transition
from simulation.block_operation_state import BlockOperationState


class BlockState(Enum):
    """Состояния блока техоперации."""
    IDLE = auto()
    BUSY = auto()
    BLOCKED = auto()
    MAINTENANCE = auto()   # ТО или аварийный ремонт


class BlockEvent(Enum):
    """События, вызывающие смену состояния блока."""
    BUFFER_HAS_DETAIL = auto()  # в upstream BUFFER появилась деталь
    SERVICE_FINISHED = auto()   # обработка завершена
    DOWNSTREAM_FREE = auto()    # downstream BUFFER освободил место
    FAILURE_OCCURRED = auto()   # произошёл отказ оборудования
    REPAIR_COMPLETE = auto()    # ремонт завершён


# --- охранные условия ---
#
# Все условия проверяют состояние СОСЕДНИХ хранилищ через context.

def _downstream_free(ctx: BlockOperationState) -> bool:
    """downstream-буфер имеет свободное место - можно отдать деталь."""
    return ctx.downstream_has_space


def _downstream_full(ctx: BlockOperationState) -> bool:
    """downstream-буфер переполнен - деталь некуда отдать."""
    return ctx.downstream_is_full


class BlockAutomaton(StateMachine):
    """Автомат состояния блока техоперации."""

    INITIAL_STATE = BlockState.IDLE

    TRANSITIONS = [
        # IDLE: в upstream появилась деталь, начинаем обработку
        Transition(
            from_state=BlockState.IDLE,
            event=BlockEvent.BUFFER_HAS_DETAIL,
            to_state=BlockState.BUSY,
            guard=None,
            guard_description="без условия",
        ),

        # BUSY: обработка закончилась, downstream свободен - отдаем деталь
        Transition(
            from_state=BlockState.BUSY,
            event=BlockEvent.SERVICE_FINISHED,
            to_state=BlockState.IDLE,
            guard=_downstream_free,
            guard_description="downstream свободен",
        ),
        # BUSY: обработка закончилась, downstream полон - блокируемся
        Transition(
            from_state=BlockState.BUSY,
            event=BlockEvent.SERVICE_FINISHED,
            to_state=BlockState.BLOCKED,
            guard=_downstream_full,
            guard_description="downstream полон",
        ),

        # BLOCKED: downstream освободился - отдаем деталь, освобождаемся
        Transition(
            from_state=BlockState.BLOCKED,
            event=BlockEvent.DOWNSTREAM_FREE,
            to_state=BlockState.IDLE,
            guard=None,
            guard_description="без условия",
        ),

        # Из любого рабочего состояния → MAINTENANCE при отказе
        Transition(
            from_state=BlockState.IDLE,
            event=BlockEvent.FAILURE_OCCURRED,
            to_state=BlockState.MAINTENANCE,
            guard=None,
            guard_description="без условия",
        ),
        Transition(
            from_state=BlockState.BUSY,
            event=BlockEvent.FAILURE_OCCURRED,
            to_state=BlockState.MAINTENANCE,
            guard=None,
            guard_description="без условия",
        ),
        Transition(
            from_state=BlockState.BLOCKED,
            event=BlockEvent.FAILURE_OCCURRED,
            to_state=BlockState.MAINTENANCE,
            guard=None,
            guard_description="без условия",
        ),

        # MAINTENANCE → IDLE после завершения ремонта
        Transition(
            from_state=BlockState.MAINTENANCE,
            event=BlockEvent.REPAIR_COMPLETE,
            to_state=BlockState.IDLE,
            guard=None,
            guard_description="без условия",
        ),
    ]

    TERMINAL_STATES: set = set()
