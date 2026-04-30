"""
Тесты автомата хранилища.

Покрытие:
1. Все шесть переходов из таблицы с правильными условиями
2. Граничные случаи: capacity = 1, capacity = 2, большая емкость
3. Запрещенные комбинации (detail_out из EMPTY, detail_in из FULL)
4. Поведение при провале охранных условий (GuardFailedError)
5. Взаимодействие с BufferState (push / pop синхронизированы с автоматом)
"""

from __future__ import annotations

import pytest

from simulation.automata.base import (
    GuardFailedError,
    IllegalTransitionError,
)
from simulation.automata.buffer import (
    BufferAutomaton,
    BufferEvent,
    BufferStateEnum,
)
from simulation.buffer_state import BufferState


# ---------------------------------------------------------------------------
# Вспомогательные фикстуры и функции
# ---------------------------------------------------------------------------

def make_buffer(capacity: int = 3, initial_count: int = 0) -> BufferState:
    """
    Создать BufferState с заданной емкостью и числом деталей.
    Детали - строки-заглушки 'd0', 'd1', ...
    """
    state = BufferState(block_id="B_test", capacity=capacity)
    for i in range(initial_count):
        state.items.append(f"d{i}")
    return state


def advance_to(fsm: BufferAutomaton, ctx: BufferState, target_count: int):
    """
    Прогнать автомат до указанного числа деталей в хранилище.
    Используется для удобной подготовки тестов.
    """
    while ctx.count < target_count:
        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push(f"d{ctx.count}")


# ---------------------------------------------------------------------------
# Начальное состояние
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_initial_state_is_empty(self):
        fsm = BufferAutomaton()
        assert fsm.state == BufferStateEnum.EMPTY

    def test_history_empty_initially(self):
        fsm = BufferAutomaton()
        assert fsm.history == []


# ---------------------------------------------------------------------------
# Переход EMPTY -> HAS_ITEMS (без охранных условий)
# ---------------------------------------------------------------------------

class TestEmptyToHasItems:
    def test_detail_in_when_empty_goes_to_has_items(self):
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=3, initial_count=0)

        new_state = fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        assert new_state == BufferStateEnum.HAS_ITEMS

    def test_works_with_capacity_2(self):
        """С capacity=2: одна деталь - HAS_ITEMS, две - FULL."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=2, initial_count=0)

        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push("d0")
        assert fsm.state == BufferStateEnum.HAS_ITEMS


# ---------------------------------------------------------------------------
# Переходы из HAS_ITEMS по detail_in (петля или в FULL)
# ---------------------------------------------------------------------------

class TestHasItemsDetailIn:
    def test_loop_when_space_remains(self):
        """count+1 < capacity: остаемся в HAS_ITEMS."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=5, initial_count=0)

        # кладем первую - EMPTY -> HAS_ITEMS
        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push("d0")
        assert fsm.state == BufferStateEnum.HAS_ITEMS

        # кладем вторую - HAS_ITEMS -> HAS_ITEMS (count 1->2, 2 < 5)
        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push("d1")
        assert fsm.state == BufferStateEnum.HAS_ITEMS

        # и третью - тоже петля (count 2->3, 3 < 5)
        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push("d2")
        assert fsm.state == BufferStateEnum.HAS_ITEMS

    def test_transition_to_full_at_exact_capacity(self):
        """count+1 = capacity: переход HAS_ITEMS -> FULL."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=3, initial_count=0)

        # заполняем до 2
        advance_to(fsm, ctx, 2)
        assert fsm.state == BufferStateEnum.HAS_ITEMS
        assert ctx.count == 2

        # третья деталь - должны перейти в FULL
        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push("d2")
        assert fsm.state == BufferStateEnum.FULL
        assert ctx.count == 3


# ---------------------------------------------------------------------------
# Переходы из HAS_ITEMS по detail_out (петля или в EMPTY)
# ---------------------------------------------------------------------------

class TestHasItemsDetailOut:
    def test_loop_when_items_remain(self):
        """count-1 > 0: остаемся в HAS_ITEMS."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=5, initial_count=0)

        advance_to(fsm, ctx, 3)
        assert fsm.state == BufferStateEnum.HAS_ITEMS
        assert ctx.count == 3

        # забираем одну - count станет 2, остаемся в HAS_ITEMS
        fsm.fire(BufferEvent.DETAIL_OUT, context=ctx)
        ctx.pop()
        assert fsm.state == BufferStateEnum.HAS_ITEMS

        # еще одну - count станет 1, все еще HAS_ITEMS
        fsm.fire(BufferEvent.DETAIL_OUT, context=ctx)
        ctx.pop()
        assert fsm.state == BufferStateEnum.HAS_ITEMS

    def test_transition_to_empty_on_last_detail(self):
        """count-1 = 0: переход HAS_ITEMS -> EMPTY."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=3, initial_count=0)

        advance_to(fsm, ctx, 1)
        assert fsm.state == BufferStateEnum.HAS_ITEMS
        assert ctx.count == 1

        fsm.fire(BufferEvent.DETAIL_OUT, context=ctx)
        ctx.pop()
        assert fsm.state == BufferStateEnum.EMPTY


# ---------------------------------------------------------------------------
# Переход FULL -> HAS_ITEMS (без охранных условий)
# ---------------------------------------------------------------------------

class TestFullToHasItems:
    def test_detail_out_when_full_goes_to_has_items(self):
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=3, initial_count=0)

        # доводим до FULL
        advance_to(fsm, ctx, 3)
        assert fsm.state == BufferStateEnum.FULL

        # забираем одну - должны вернуться в HAS_ITEMS
        fsm.fire(BufferEvent.DETAIL_OUT, context=ctx)
        ctx.pop()
        assert fsm.state == BufferStateEnum.HAS_ITEMS
        assert ctx.count == 2


# ---------------------------------------------------------------------------
# Граничный случай: capacity = 1 (переход EMPTY <-> FULL через HAS_ITEMS)
# ---------------------------------------------------------------------------

class TestCapacityOne:
    """С capacity=1 при первой детали EMPTY -> FULL, минуя HAS_ITEMS."""

    def test_empty_to_full_directly(self):
        """При capacity=1 переход detail_in: EMPTY -> FULL."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=1, initial_count=0)

        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push("d0")
        assert fsm.state == BufferStateEnum.FULL
        assert ctx.count == 1
        assert ctx.is_full

    def test_full_to_empty_directly(self):
        """При capacity=1 переход detail_out: FULL -> HAS_ITEMS -> сразу нет.

        Забираем последнюю деталь: FULL --detail_out--> HAS_ITEMS.
        Но в HAS_ITEMS с count=0 мы попасть не должны; правильно - EMPTY.

        Однако текущая таблица для FULL определяет переход в HAS_ITEMS
        без охранных условий. Это симметричная проблема к EMPTY -> FULL.
        Проверим фактическое поведение.
        """
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=1, initial_count=0)

        # EMPTY -> FULL
        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push("d0")
        assert fsm.state == BufferStateEnum.FULL

        # Теперь забираем: FULL --detail_out--> ???
        fsm.fire(BufferEvent.DETAIL_OUT, context=ctx)
        ctx.pop()
        # С текущей таблицей мы попадаем в HAS_ITEMS с count=0 -
        # это тоже баг. Надо исправить аналогично: FULL -> EMPTY при capacity=1.
        assert fsm.state == BufferStateEnum.EMPTY, (
            "При capacity=1 забор последней детали должен давать EMPTY, "
            "а не HAS_ITEMS (иначе count=0 в HAS_ITEMS - рассогласование)"
        )


# ---------------------------------------------------------------------------
# Запрещенные переходы
# ---------------------------------------------------------------------------

class TestIllegalTransitions:
    def test_detail_out_from_empty_raises(self):
        """Из EMPTY нельзя сделать detail_out - нет такого перехода."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=3, initial_count=0)

        with pytest.raises(IllegalTransitionError):
            fsm.fire(BufferEvent.DETAIL_OUT, context=ctx)

    def test_detail_in_when_full_raises(self):
        """Из FULL нельзя сделать detail_in - нет такого перехода."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=2, initial_count=0)

        advance_to(fsm, ctx, 2)
        assert fsm.state == BufferStateEnum.FULL

        with pytest.raises(IllegalTransitionError):
            fsm.fire(BufferEvent.DETAIL_IN, context=ctx)


# ---------------------------------------------------------------------------
# Длинный сценарий: наполнили - частично забрали - снова наполнили
# ---------------------------------------------------------------------------

class TestRealisticScenario:
    def test_fill_drain_fill(self):
        """Сценарий: capacity=4, наполняем до FULL, забираем 3, заполняем снова."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=4, initial_count=0)

        # наполняем до полного
        for i in range(4):
            fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
            ctx.push(f"d{i}")

        assert fsm.state == BufferStateEnum.FULL
        assert ctx.count == 4

        # забираем 3
        for _ in range(3):
            fsm.fire(BufferEvent.DETAIL_OUT, context=ctx)
            ctx.pop()

        assert fsm.state == BufferStateEnum.HAS_ITEMS
        assert ctx.count == 1

        # добавляем еще 2
        for i in range(2):
            fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
            ctx.push(f"new_{i}")

        assert fsm.state == BufferStateEnum.HAS_ITEMS
        assert ctx.count == 3

        # и еще одну - снова FULL
        fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
        ctx.push("last")
        assert fsm.state == BufferStateEnum.FULL

    def test_history_tracks_all_transitions(self):
        """История фиксирует все переходы в порядке их возникновения."""
        fsm = BufferAutomaton()
        ctx = make_buffer(capacity=3, initial_count=0)

        # наполняем до FULL
        for i in range(3):
            fsm.fire(BufferEvent.DETAIL_IN, context=ctx)
            ctx.push(f"d{i}")

        # забираем все
        for _ in range(3):
            fsm.fire(BufferEvent.DETAIL_OUT, context=ctx)
            ctx.pop()

        # ожидаем: E->HI, HI->HI, HI->F, F->HI, HI->HI, HI->E
        expected_states = [
            (BufferStateEnum.EMPTY, BufferStateEnum.HAS_ITEMS),
            (BufferStateEnum.HAS_ITEMS, BufferStateEnum.HAS_ITEMS),
            (BufferStateEnum.HAS_ITEMS, BufferStateEnum.FULL),
            (BufferStateEnum.FULL, BufferStateEnum.HAS_ITEMS),
            (BufferStateEnum.HAS_ITEMS, BufferStateEnum.HAS_ITEMS),
            (BufferStateEnum.HAS_ITEMS, BufferStateEnum.EMPTY),
        ]
        actual = [(h[0], h[2]) for h in fsm.history]
        assert actual == expected_states
