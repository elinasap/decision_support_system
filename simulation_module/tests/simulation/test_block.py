"""
Тесты автомата состояния блока техоперации.

Покрытие:
1. Начальное состояние IDLE
2. Все четыре перехода из таблицы
3. Охранные условия downstream_free / downstream_full работают корректно
4. Запрещенные комбинации (state, event)
5. Реалистичный сценарий с заполнением и освобождением downstream
6. Корректная работа с несколькими upstream-буферами (ASSEMBLY-кейс)
7. История переходов
"""

from __future__ import annotations

import pytest

from simulation.automata.base import (
    GuardFailedError,
    IllegalTransitionError,
)
from simulation.automata.block import (
    BlockAutomaton,
    BlockEvent,
    BlockState,
)
from simulation.block_operation_state import BlockOperationState
from simulation.buffer_state import BufferState


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def make_block_state(
    upstream_capacity: int = 5,
    downstream_capacity: int = 5,
    upstream_initial: int = 0,
    downstream_initial: int = 0,
    n_upstream_buffers: int = 1,
) -> BlockOperationState:
    """Создать BlockOperationState с upstream и downstream буферами."""
    upstream = []
    for i in range(n_upstream_buffers):
        buf = BufferState(block_id=f"upstream_{i}", capacity=upstream_capacity)
        for j in range(upstream_initial):
            buf.items.append(f"u{i}_d{j}")
        upstream.append(buf)

    downstream = BufferState(block_id="downstream", capacity=downstream_capacity)
    for j in range(downstream_initial):
        downstream.items.append(f"out_d{j}")

    return BlockOperationState(
        block_id="B_op_test",
        upstream_buffers=upstream,
        downstream_buffer=downstream,
        service_time=10.0,
    )


# ---------------------------------------------------------------------------
# Начальное состояние
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_initial_state_is_idle(self):
        fsm = BlockAutomaton()
        assert fsm.state == BlockState.IDLE

    def test_history_empty_initially(self):
        fsm = BlockAutomaton()
        assert fsm.history == []


# ---------------------------------------------------------------------------
# IDLE -> BUSY
# ---------------------------------------------------------------------------

class TestIdleToBusy:
    def test_buffer_has_detail_starts_processing(self):
        fsm = BlockAutomaton()
        ctx = make_block_state(upstream_initial=1)

        new_state = fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, context=ctx)
        assert new_state == BlockState.BUSY


# ---------------------------------------------------------------------------
# BUSY -> IDLE (downstream свободен)
# ---------------------------------------------------------------------------

class TestBusyToIdle:
    def test_service_finished_with_free_downstream(self):
        fsm = BlockAutomaton()
        ctx = make_block_state(
            upstream_initial=1,
            downstream_initial=0,    # downstream полностью свободен
            downstream_capacity=5,
        )

        # IDLE -> BUSY
        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        assert fsm.state == BlockState.BUSY

        # BUSY -> IDLE (downstream свободен)
        new_state = fsm.fire(BlockEvent.SERVICE_FINISHED, ctx)
        assert new_state == BlockState.IDLE

    def test_service_finished_with_partially_full_downstream(self):
        """downstream частично заполнен, но место есть - тоже IDLE."""
        fsm = BlockAutomaton()
        ctx = make_block_state(
            upstream_initial=1,
            downstream_initial=2,
            downstream_capacity=5,
        )

        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        new_state = fsm.fire(BlockEvent.SERVICE_FINISHED, ctx)
        assert new_state == BlockState.IDLE


# ---------------------------------------------------------------------------
# BUSY -> BLOCKED (downstream полон)
# ---------------------------------------------------------------------------

class TestBusyToBlocked:
    def test_service_finished_with_full_downstream(self):
        fsm = BlockAutomaton()
        ctx = make_block_state(
            upstream_initial=1,
            downstream_capacity=3,
            downstream_initial=3,    # downstream полностью забит
        )

        # IDLE -> BUSY
        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        assert fsm.state == BlockState.BUSY

        # BUSY -> BLOCKED (downstream полон)
        new_state = fsm.fire(BlockEvent.SERVICE_FINISHED, ctx)
        assert new_state == BlockState.BLOCKED

    def test_blocked_when_capacity_one_and_full(self):
        """Граничный случай: downstream емкостью 1, в нем уже одна деталь."""
        fsm = BlockAutomaton()
        ctx = make_block_state(
            upstream_initial=1,
            downstream_capacity=1,
            downstream_initial=1,
        )

        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        new_state = fsm.fire(BlockEvent.SERVICE_FINISHED, ctx)
        assert new_state == BlockState.BLOCKED


# ---------------------------------------------------------------------------
# BLOCKED -> IDLE (downstream освободился)
# ---------------------------------------------------------------------------

class TestBlockedToIdle:
    def test_downstream_free_releases_block(self):
        fsm = BlockAutomaton()
        ctx = make_block_state(
            upstream_initial=1,
            downstream_capacity=3,
            downstream_initial=3,
        )

        # доводим до BLOCKED
        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        fsm.fire(BlockEvent.SERVICE_FINISHED, ctx)
        assert fsm.state == BlockState.BLOCKED

        # downstream освободился
        new_state = fsm.fire(BlockEvent.DOWNSTREAM_FREE, ctx)
        assert new_state == BlockState.IDLE


# ---------------------------------------------------------------------------
# Запрещенные переходы
# ---------------------------------------------------------------------------

class TestIllegalTransitions:
    @pytest.mark.parametrize(
        "bad_event",
        [BlockEvent.SERVICE_FINISHED, BlockEvent.DOWNSTREAM_FREE],
    )
    def test_illegal_events_in_idle(self, bad_event):
        fsm = BlockAutomaton()
        ctx = make_block_state()
        with pytest.raises(IllegalTransitionError):
            fsm.fire(bad_event, ctx)

    @pytest.mark.parametrize(
        "bad_event",
        [BlockEvent.BUFFER_HAS_DETAIL, BlockEvent.DOWNSTREAM_FREE],
    )
    def test_illegal_events_in_busy(self, bad_event):
        fsm = BlockAutomaton()
        ctx = make_block_state(upstream_initial=1)
        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)  # теперь BUSY
        with pytest.raises(IllegalTransitionError):
            fsm.fire(bad_event, ctx)

    @pytest.mark.parametrize(
        "bad_event",
        [BlockEvent.BUFFER_HAS_DETAIL, BlockEvent.SERVICE_FINISHED],
    )
    def test_illegal_events_in_blocked(self, bad_event):
        fsm = BlockAutomaton()
        ctx = make_block_state(
            upstream_initial=1,
            downstream_capacity=1,
            downstream_initial=1,
        )
        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        fsm.fire(BlockEvent.SERVICE_FINISHED, ctx)  # теперь BLOCKED
        with pytest.raises(IllegalTransitionError):
            fsm.fire(bad_event, ctx)


# ---------------------------------------------------------------------------
# Реалистичный сценарий: блок попадает в BLOCKED и выходит
# ---------------------------------------------------------------------------

class TestRealisticScenario:
    def test_full_cycle_with_blocking(self):
        """
        Сценарий: блок начинает обработку, downstream-буфер забивается
        деталями от других источников, блок блокируется,
        downstream освобождается, блок продолжает.
        """
        fsm = BlockAutomaton()
        ctx = make_block_state(
            upstream_capacity=10,
            upstream_initial=2,        # есть детали для обработки
            downstream_capacity=2,
            downstream_initial=2,       # downstream УЖЕ полон
        )

        # IDLE -> BUSY: начинаем обработку первой детали
        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        assert fsm.state == BlockState.BUSY

        # service_finished: downstream полон -> BLOCKED
        fsm.fire(BlockEvent.SERVICE_FINISHED, ctx)
        assert fsm.state == BlockState.BLOCKED

        # имитируем освобождение downstream (например, следующий блок взял деталь)
        ctx.downstream_buffer.pop()

        # downstream_free -> IDLE
        fsm.fire(BlockEvent.DOWNSTREAM_FREE, ctx)
        assert fsm.state == BlockState.IDLE

        # начинаем следующую обработку
        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        assert fsm.state == BlockState.BUSY


# ---------------------------------------------------------------------------
# Несколько upstream-буферов (ASSEMBLY-кейс)
# ---------------------------------------------------------------------------

class TestMultipleUpstreamBuffers:
    """Для ASSEMBLY у блока несколько upstream-буферов."""

    def test_works_with_multiple_upstreams(self):
        fsm = BlockAutomaton()
        ctx = make_block_state(
            n_upstream_buffers=3,
            upstream_initial=1,
            downstream_capacity=5,
        )

        # все три upstream-буфера имеют по детали
        assert ctx.all_upstream_have_details
        assert len(ctx.upstream_buffers) == 3

        # автомат блока сам по себе не различает 1 или N upstream-буферов;
        # это забота движка симуляции - решать, когда генерировать событие.
        # Проверяем, что автомат корректно переходит при срабатывании события.
        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        assert fsm.state == BlockState.BUSY

    def test_partial_upstream_availability(self):
        """Только часть upstream-буферов имеют детали (не все)."""
        ctx = make_block_state(
            n_upstream_buffers=3,
            upstream_initial=0,    # пустые
            downstream_capacity=5,
        )
        # положим деталь только в первый
        ctx.upstream_buffers[0].items.append("only_one")

        assert ctx.has_upstream_detail        # есть хотя бы в одном
        assert not ctx.all_upstream_have_details  # но не во всех


# ---------------------------------------------------------------------------
# История переходов
# ---------------------------------------------------------------------------

class TestHistory:
    def test_history_records_all_transitions(self):
        fsm = BlockAutomaton()
        ctx = make_block_state(
            upstream_initial=1,
            downstream_capacity=1,
            downstream_initial=1,
        )

        fsm.fire(BlockEvent.BUFFER_HAS_DETAIL, ctx)
        fsm.fire(BlockEvent.SERVICE_FINISHED, ctx)
        ctx.downstream_buffer.pop()
        fsm.fire(BlockEvent.DOWNSTREAM_FREE, ctx)

        expected = [
            (BlockState.IDLE, BlockEvent.BUFFER_HAS_DETAIL, BlockState.BUSY),
            (BlockState.BUSY, BlockEvent.SERVICE_FINISHED, BlockState.BLOCKED),
            (BlockState.BLOCKED, BlockEvent.DOWNSTREAM_FREE, BlockState.IDLE),
        ]
        assert fsm.history == expected
