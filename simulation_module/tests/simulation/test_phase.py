"""
Тесты автомата фазы детали.

Покрытие:
1. Начальное состояние - WAITING
2. Все разрешенные переходы из таблицы
3. Все запрещенные комбинации (state, event) возбуждают IllegalTransitionError
4. История переходов корректно фиксируется
5. reset() возвращает автомат в начальное состояние
"""

from __future__ import annotations

import pytest

from simulation.automata.base import IllegalTransitionError
from simulation.automata.phase import Phase, PhaseAutomaton, PhaseEvent


class TestInitialState:
    """Начальное состояние."""

    def test_initial_state_is_waiting(self):
        fsm = PhaseAutomaton()
        assert fsm.state == Phase.WAITING

    def test_history_is_empty_initially(self):
        fsm = PhaseAutomaton()
        assert fsm.history == []

    def test_not_terminal_initially(self):
        fsm = PhaseAutomaton()
        assert not fsm.is_terminal()


class TestAllowedTransitions:
    """Все переходы из таблицы должны работать."""

    def test_waiting_to_processing(self):
        fsm = PhaseAutomaton()
        new_state = fsm.fire(PhaseEvent.START_SERVICE)
        assert new_state == Phase.PROCESSING
        assert fsm.state == Phase.PROCESSING

    def test_processing_to_done(self):
        fsm = PhaseAutomaton()
        fsm.fire(PhaseEvent.START_SERVICE)
        new_state = fsm.fire(PhaseEvent.SERVICE_COMPLETE)
        assert new_state == Phase.DONE
        assert fsm.state == Phase.DONE

    def test_done_to_waiting_on_depart(self):
        """После depart деталь снова waiting - уже в следующем хранилище."""
        fsm = PhaseAutomaton()
        fsm.fire(PhaseEvent.START_SERVICE)
        fsm.fire(PhaseEvent.SERVICE_COMPLETE)
        new_state = fsm.fire(PhaseEvent.DEPART)
        assert new_state == Phase.WAITING

    def test_full_cycle(self):
        """Полный цикл: W -> P -> D -> W (вход в следующий блок)."""
        fsm = PhaseAutomaton()
        assert fsm.state == Phase.WAITING

        fsm.fire(PhaseEvent.START_SERVICE)
        assert fsm.state == Phase.PROCESSING

        fsm.fire(PhaseEvent.SERVICE_COMPLETE)
        assert fsm.state == Phase.DONE

        fsm.fire(PhaseEvent.DEPART)
        assert fsm.state == Phase.WAITING


class TestIllegalTransitions:
    """Все комбинации (state, event), не указанные в таблице, запрещены."""

    @pytest.mark.parametrize(
        "bad_event",
        [PhaseEvent.SERVICE_COMPLETE, PhaseEvent.DEPART],
    )
    def test_illegal_events_in_waiting(self, bad_event):
        fsm = PhaseAutomaton()
        with pytest.raises(IllegalTransitionError):
            fsm.fire(bad_event)

    @pytest.mark.parametrize(
        "bad_event",
        [PhaseEvent.START_SERVICE, PhaseEvent.DEPART],
    )
    def test_illegal_events_in_processing(self, bad_event):
        fsm = PhaseAutomaton()
        fsm.fire(PhaseEvent.START_SERVICE)  # теперь в PROCESSING
        with pytest.raises(IllegalTransitionError):
            fsm.fire(bad_event)

    @pytest.mark.parametrize(
        "bad_event",
        [PhaseEvent.START_SERVICE, PhaseEvent.SERVICE_COMPLETE],
    )
    def test_illegal_events_in_done(self, bad_event):
        fsm = PhaseAutomaton()
        fsm.fire(PhaseEvent.START_SERVICE)
        fsm.fire(PhaseEvent.SERVICE_COMPLETE)  # теперь в DONE
        with pytest.raises(IllegalTransitionError):
            fsm.fire(bad_event)


class TestHistory:
    """История переходов фиксируется корректно."""

    def test_history_records_all_transitions(self):
        fsm = PhaseAutomaton()
        fsm.fire(PhaseEvent.START_SERVICE)
        fsm.fire(PhaseEvent.SERVICE_COMPLETE)
        fsm.fire(PhaseEvent.DEPART)

        expected = [
            (Phase.WAITING, PhaseEvent.START_SERVICE, Phase.PROCESSING),
            (Phase.PROCESSING, PhaseEvent.SERVICE_COMPLETE, Phase.DONE),
            (Phase.DONE, PhaseEvent.DEPART, Phase.WAITING),
        ]
        assert fsm.history == expected

    def test_history_not_recorded_on_failed_transition(self):
        fsm = PhaseAutomaton()
        with pytest.raises(IllegalTransitionError):
            fsm.fire(PhaseEvent.SERVICE_COMPLETE)
        assert fsm.history == []


class TestReset:
    """Сброс автомата."""

    def test_reset_returns_to_initial_state(self):
        fsm = PhaseAutomaton()
        fsm.fire(PhaseEvent.START_SERVICE)
        fsm.fire(PhaseEvent.SERVICE_COMPLETE)
        assert fsm.state == Phase.DONE

        fsm.reset()
        assert fsm.state == Phase.WAITING

    def test_reset_clears_history(self):
        fsm = PhaseAutomaton()
        fsm.fire(PhaseEvent.START_SERVICE)
        assert len(fsm.history) == 1

        fsm.reset()
        assert fsm.history == []


class TestCanHandle:
    """Проверка can_handle для принятия решений в движке симуляции."""

    def test_can_handle_valid_event(self):
        fsm = PhaseAutomaton()
        assert fsm.can_handle(PhaseEvent.START_SERVICE) is True

    def test_cannot_handle_invalid_event(self):
        fsm = PhaseAutomaton()
        assert fsm.can_handle(PhaseEvent.DEPART) is False
