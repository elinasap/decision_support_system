"""
Конечный автомат хранилища (BUFFER).

Описывает состояние заполненности хранилища. События:
- detail_in  - в хранилище положили деталь
- detail_out - из хранилища забрали деталь

Формальное определение:
    A_buffer = (S, Sigma, delta, s_0, F)

где:
    S      = {EMPTY, HAS_ITEMS, FULL}
    Sigma  = {DETAIL_IN, DETAIL_OUT}
    s_0    = EMPTY
    F      = {}  (нет терминальных состояний)

Таблица переходов (8 правил):
    EMPTY     --detail_in  [capacity > 1]-------> HAS_ITEMS
    EMPTY     --detail_in  [capacity = 1]-------> FULL       (вырожд. случай)
    HAS_ITEMS --detail_in  [count+1 < capacity]-> HAS_ITEMS  (петля)
    HAS_ITEMS --detail_in  [count+1 = capacity]-> FULL
    HAS_ITEMS --detail_out [count-1 > 0]--------> HAS_ITEMS  (петля)
    HAS_ITEMS --detail_out [count-1 = 0]--------> EMPTY
    FULL      --detail_out [capacity > 1]-------> HAS_ITEMS
    FULL      --detail_out [capacity = 1]-------> EMPTY      (вырожд. случай)

Граничный случай capacity=1: хранилище не может быть в HAS_ITEMS,
оно всегда либо EMPTY, либо FULL (емкость 1 = двоичное состояние).

Охранные условия проверяют context.count и context.capacity, где context -
это экземпляр BufferState. Проверяется СОСТОЯНИЕ ДО перехода: в момент
вызова fire() деталь еще не положена / не забрана, автомат только решает,
куда переходить.
"""

from __future__ import annotations

from enum import Enum, auto

from simulation.automata.base import StateMachine, Transition
from simulation.buffer_state import BufferState


class BufferStateEnum(Enum):
    """Состояния хранилища."""
    EMPTY = auto()
    HAS_ITEMS = auto()
    FULL = auto()


class BufferEvent(Enum):
    """События хранилища."""
    DETAIL_IN = auto()   # положили деталь
    DETAIL_OUT = auto()  # забрали деталь


# --- охранные условия ---
#
# Все условия проверяют СОСТОЯНИЕ ДО перехода.
# В момент fire() автомат принимает решение, куда переходить;
# фактическое изменение count произойдет уже после, в действиях
# on_enter_<state>.
#
# Ключевой момент: автомат смотрит на count, КАКИМ ОН БУДЕТ ПОСЛЕ события.
# Например, если count = 3, capacity = 5, приходит detail_in:
#   "будущий count" = 3 + 1 = 4, что < capacity -> остаемся в HAS_ITEMS
# Если count = 4, capacity = 5, detail_in:
#   "будущий count" = 4 + 1 = 5 = capacity -> переход в FULL

def _capacity_gt_one(ctx: BufferState) -> bool:
    """detail_in из EMPTY: хранилище на 2+ деталей, идем в HAS_ITEMS."""
    return ctx.capacity > 1


def _capacity_eq_one(ctx: BufferState) -> bool:
    """detail_in из EMPTY: хранилище на одну деталь, сразу FULL."""
    return ctx.capacity == 1


def _in_will_fit(ctx: BufferState) -> bool:
    """detail_in: после добавления еще будет место."""
    return ctx.count + 1 < ctx.capacity


def _in_will_fill(ctx: BufferState) -> bool:
    """detail_in: после добавления хранилище станет полным."""
    return ctx.count + 1 == ctx.capacity


def _out_will_remain(ctx: BufferState) -> bool:
    """detail_out: после забора еще останется хотя бы одна деталь."""
    return ctx.count - 1 > 0


def _out_will_empty(ctx: BufferState) -> bool:
    """detail_out: после забора хранилище станет пустым."""
    return ctx.count - 1 == 0


class BufferAutomaton(StateMachine):
    """Автомат состояния хранилища."""

    INITIAL_STATE = BufferStateEnum.EMPTY

    TRANSITIONS = [
        # EMPTY: пришла первая деталь, хранилище на 2+
        Transition(
            from_state=BufferStateEnum.EMPTY,
            event=BufferEvent.DETAIL_IN,
            to_state=BufferStateEnum.HAS_ITEMS,
            guard=_capacity_gt_one,
            guard_description="capacity > 1",
        ),
        # EMPTY: пришла первая деталь в хранилище на одну (сразу FULL)
        Transition(
            from_state=BufferStateEnum.EMPTY,
            event=BufferEvent.DETAIL_IN,
            to_state=BufferStateEnum.FULL,
            guard=_capacity_eq_one,
            guard_description="capacity = 1",
        ),

        # HAS_ITEMS: пришла деталь, место еще есть
        Transition(
            from_state=BufferStateEnum.HAS_ITEMS,
            event=BufferEvent.DETAIL_IN,
            to_state=BufferStateEnum.HAS_ITEMS,
            guard=_in_will_fit,
            guard_description="count+1 < capacity",
        ),
        # HAS_ITEMS: пришла деталь, стало ровно capacity
        Transition(
            from_state=BufferStateEnum.HAS_ITEMS,
            event=BufferEvent.DETAIL_IN,
            to_state=BufferStateEnum.FULL,
            guard=_in_will_fill,
            guard_description="count+1 = capacity",
        ),

        # HAS_ITEMS: забрали деталь, еще осталось
        Transition(
            from_state=BufferStateEnum.HAS_ITEMS,
            event=BufferEvent.DETAIL_OUT,
            to_state=BufferStateEnum.HAS_ITEMS,
            guard=_out_will_remain,
            guard_description="count-1 > 0",
        ),
        # HAS_ITEMS: забрали последнюю деталь
        Transition(
            from_state=BufferStateEnum.HAS_ITEMS,
            event=BufferEvent.DETAIL_OUT,
            to_state=BufferStateEnum.EMPTY,
            guard=_out_will_empty,
            guard_description="count-1 = 0",
        ),

        # FULL: забрали деталь при capacity > 1 - в HAS_ITEMS
        Transition(
            from_state=BufferStateEnum.FULL,
            event=BufferEvent.DETAIL_OUT,
            to_state=BufferStateEnum.HAS_ITEMS,
            guard=_capacity_gt_one,
            guard_description="capacity > 1",
        ),
        # FULL: забрали последнюю деталь из хранилища на одну
        Transition(
            from_state=BufferStateEnum.FULL,
            event=BufferEvent.DETAIL_OUT,
            to_state=BufferStateEnum.EMPTY,
            guard=_capacity_eq_one,
            guard_description="capacity = 1",
        ),
    ]

    TERMINAL_STATES: set = set()
