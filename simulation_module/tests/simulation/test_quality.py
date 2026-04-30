"""
Тесты автомата качества детали.

Покрытие:
1. Начальное состояние UNCHECKED
2. Терминальные состояния ACCEPTED и SCRAPPED
3. Все 7 переходов из таблицы с правильными условиями
4. Счетчик repair_count корректно инкрементируется
5. quality_state детали синхронизируется с состоянием автомата
6. Логика max_repair работает как ожидается:
   - max_repair = 0 - любой брак сразу в утиль (через ENTER_SCRAP_SINK)
   - max_repair = N - после N ремонтов и провала контроля - в утиль
7. Запрещенные переходы
8. Полные сценарии: успешный путь, путь с одним ремонтом, путь до утиля
"""

from __future__ import annotations

import pytest

from simulation.automata.base import (
    GuardFailedError,
    IllegalTransitionError,
)
from simulation.automata.quality import (
    QualityAutomaton,
    QualityCheckContext,
    QualityEvent,
    QualityState,
)
from simulation.detail_instance import DetailInstance, DetailQualityState


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def make_context(
    type_id: str = "d_blank",
    max_repair: int = 2,
    repair_count: int = 0,
) -> QualityCheckContext:
    """Создать контекст для тестов."""
    detail = DetailInstance(uid=1, type_id=type_id, repair_count=repair_count)
    detail_types = {
        type_id: {"label": "Тестовая деталь", "unit": "шт", "max_repair": max_repair}
    }
    return QualityCheckContext(detail=detail, detail_types=detail_types)


# ---------------------------------------------------------------------------
# Начальное состояние
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_initial_state_is_unchecked(self):
        fsm = QualityAutomaton()
        assert fsm.state == QualityState.UNCHECKED

    def test_history_empty_initially(self):
        fsm = QualityAutomaton()
        assert fsm.history == []

    def test_not_terminal_initially(self):
        fsm = QualityAutomaton()
        assert not fsm.is_terminal()


# ---------------------------------------------------------------------------
# UNCHECKED -> ... (три перехода)
# ---------------------------------------------------------------------------

class TestUncheckedTransitions:
    def test_control_passed_stays_in_unchecked(self):
        """Прошел контроль - остается UNCHECKED, готова к следующему контролю."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        new_state = fsm.fire(QualityEvent.CONTROL_PASSED, ctx)
        assert new_state == QualityState.UNCHECKED
        assert ctx.detail.quality_state == DetailQualityState.UNCHECKED

    def test_control_failed_goes_to_defective(self):
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        new_state = fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        assert new_state == QualityState.DEFECTIVE
        assert ctx.detail.quality_state == DetailQualityState.DEFECTIVE

    def test_enter_product_sink_goes_to_accepted(self):
        fsm = QualityAutomaton()
        ctx = make_context()

        new_state = fsm.fire(QualityEvent.ENTER_PRODUCT_SINK, ctx)
        assert new_state == QualityState.ACCEPTED
        assert fsm.is_terminal()
        assert ctx.detail.quality_state == DetailQualityState.ACCEPTED


# ---------------------------------------------------------------------------
# DEFECTIVE -> ... (два перехода)
# ---------------------------------------------------------------------------

class TestDefectiveTransitions:
    def test_repair_complete_goes_to_repaired(self):
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        assert fsm.state == QualityState.DEFECTIVE
        assert ctx.detail.repair_count == 0  # пока не было ремонтов

        new_state = fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)
        assert new_state == QualityState.REPAIRED
        assert ctx.detail.quality_state == DetailQualityState.REPAIRED
        assert ctx.detail.repair_count == 1   # счетчик инкрементировался

    def test_enter_scrap_sink_goes_to_scrapped(self):
        """Дефектная деталь, попавшая в sink утиля, становится SCRAPPED."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        new_state = fsm.fire(QualityEvent.ENTER_SCRAP_SINK, ctx)
        assert new_state == QualityState.SCRAPPED
        assert fsm.is_terminal()
        assert ctx.detail.quality_state == DetailQualityState.SCRAPPED


# ---------------------------------------------------------------------------
# REPAIRED -> ... (три перехода с условиями)
# ---------------------------------------------------------------------------

class TestRepairedTransitions:
    def test_control_passed_after_repair_goes_to_accepted(self):
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)
        assert fsm.state == QualityState.REPAIRED

        new_state = fsm.fire(QualityEvent.CONTROL_PASSED, ctx)
        assert new_state == QualityState.ACCEPTED
        assert fsm.is_terminal()

    def test_control_failed_with_remaining_attempts(self):
        """count=1 < max_repair=3 - возврат в DEFECTIVE."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=3)

        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)
        assert ctx.detail.repair_count == 1

        new_state = fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        assert new_state == QualityState.DEFECTIVE
        # счетчик не инкрементируется тут, только при следующем REPAIR_COMPLETE
        assert ctx.detail.repair_count == 1

    def test_control_failed_with_no_attempts_left(self):
        """count=2 = max_repair=2 - в SCRAPPED."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        # делаем 2 ремонта
        for _ in range(2):
            fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
            fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)
        assert ctx.detail.repair_count == 2
        assert fsm.state == QualityState.REPAIRED

        # третий провал контроля - попыток больше нет
        new_state = fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        assert new_state == QualityState.SCRAPPED
        assert fsm.is_terminal()


# ---------------------------------------------------------------------------
# Логика max_repair = 0 (ремонт запрещен)
# ---------------------------------------------------------------------------

class TestMaxRepairZero:
    """Если max_repair = 0, любой брак сразу в утиль через ENTER_SCRAP_SINK."""

    def test_unchecked_to_defective_to_scrapped(self):
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=0)

        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        assert fsm.state == QualityState.DEFECTIVE

        # пытаться ремонтировать неправильно - но автомат это разрешает,
        # потому что REPAIR_COMPLETE не зависит от max_repair напрямую.
        # Однако если в системе max_repair=0, то по логике движка деталь
        # вообще не должна идти на ремонт. Проверим что произойдет, если
        # все же отправить ее на ремонт:
        fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)
        assert fsm.state == QualityState.REPAIRED
        assert ctx.detail.repair_count == 1

        # теперь после ремонта при провале контроля:
        # repair_count = 1, max_repair = 0 - 1 >= 0 -> SCRAPPED
        new_state = fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        assert new_state == QualityState.SCRAPPED


# ---------------------------------------------------------------------------
# Запрещенные переходы
# ---------------------------------------------------------------------------

class TestIllegalTransitions:
    def test_unchecked_repair_complete_raises(self):
        """Из UNCHECKED нельзя завершить ремонт - не было поломки."""
        fsm = QualityAutomaton()
        ctx = make_context()
        with pytest.raises(IllegalTransitionError):
            fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)

    def test_unchecked_enter_scrap_sink_raises(self):
        """Нормальная деталь не должна попадать в sink утиля."""
        fsm = QualityAutomaton()
        ctx = make_context()
        with pytest.raises(IllegalTransitionError):
            fsm.fire(QualityEvent.ENTER_SCRAP_SINK, ctx)

    def test_defective_control_passed_raises(self):
        """Брак не может пройти контроль без ремонта."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)
        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        with pytest.raises(IllegalTransitionError):
            fsm.fire(QualityEvent.CONTROL_PASSED, ctx)

    def test_defective_control_failed_raises(self):
        """В DEFECTIVE контроль повторно проходить нельзя - сначала ремонт."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)
        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        with pytest.raises(IllegalTransitionError):
            fsm.fire(QualityEvent.CONTROL_FAILED, ctx)

    def test_defective_enter_product_sink_raises(self):
        """Брак не может попасть в sink готовой продукции."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)
        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        with pytest.raises(IllegalTransitionError):
            fsm.fire(QualityEvent.ENTER_PRODUCT_SINK, ctx)

    def test_repaired_repair_complete_raises(self):
        """Из REPAIRED нельзя снова в ремонт - сначала контроль."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)
        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)
        with pytest.raises(IllegalTransitionError):
            fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)

    def test_terminal_states_block_all_events(self):
        """Из ACCEPTED и SCRAPPED никаких переходов не должно быть."""
        for event in QualityEvent:
            # ACCEPTED
            fsm = QualityAutomaton()
            ctx = make_context()
            fsm.fire(QualityEvent.ENTER_PRODUCT_SINK, ctx)
            assert fsm.state == QualityState.ACCEPTED
            with pytest.raises(IllegalTransitionError):
                fsm.fire(event, ctx)

            # SCRAPPED
            fsm = QualityAutomaton()
            ctx = make_context(max_repair=2)
            fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
            fsm.fire(QualityEvent.ENTER_SCRAP_SINK, ctx)
            assert fsm.state == QualityState.SCRAPPED
            with pytest.raises(IllegalTransitionError):
                fsm.fire(event, ctx)


# ---------------------------------------------------------------------------
# Полные сценарии
# ---------------------------------------------------------------------------

class TestFullScenarios:
    def test_happy_path(self):
        """Успешный путь: UNCHECKED -> CONTROL_PASSED -> ... -> ACCEPTED."""
        fsm = QualityAutomaton()
        ctx = make_context()

        # пройти три контроля подряд
        for _ in range(3):
            fsm.fire(QualityEvent.CONTROL_PASSED, ctx)
            assert fsm.state == QualityState.UNCHECKED

        # затем войти в sink готовой продукции
        fsm.fire(QualityEvent.ENTER_PRODUCT_SINK, ctx)
        assert fsm.state == QualityState.ACCEPTED
        assert ctx.detail.repair_count == 0  # ремонтов не было

    def test_one_repair_then_accepted(self):
        """Один ремонт и принята."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)
        assert ctx.detail.repair_count == 1

        fsm.fire(QualityEvent.CONTROL_PASSED, ctx)
        assert fsm.state == QualityState.ACCEPTED

    def test_max_repairs_then_scrapped(self):
        """max_repair=2 ремонтов, провал контроля - в утиль."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)  # count=1
        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)  # count=2
        # дальше провал контроля - в утиль
        new_state = fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        assert new_state == QualityState.SCRAPPED
        assert ctx.detail.repair_count == 2

    def test_immediate_scrap_unrepairable(self):
        """Брак сразу в утиль через ENTER_SCRAP_SINK."""
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=5)  # лимит большой, но движок решил иначе

        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        fsm.fire(QualityEvent.ENTER_SCRAP_SINK, ctx)
        assert fsm.state == QualityState.SCRAPPED
        assert ctx.detail.repair_count == 0  # без ремонта


# ---------------------------------------------------------------------------
# Терминальность
# ---------------------------------------------------------------------------

class TestTerminalStates:
    def test_accepted_is_terminal(self):
        fsm = QualityAutomaton()
        ctx = make_context()
        fsm.fire(QualityEvent.ENTER_PRODUCT_SINK, ctx)
        assert fsm.is_terminal()

    def test_scrapped_is_terminal(self):
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)
        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        fsm.fire(QualityEvent.ENTER_SCRAP_SINK, ctx)
        assert fsm.is_terminal()


# ---------------------------------------------------------------------------
# Синхронизация с DetailInstance
# ---------------------------------------------------------------------------

class TestDetailSync:
    """quality_state детали должен идти в ногу с состоянием автомата."""

    def test_quality_state_reflects_automaton_state(self):
        fsm = QualityAutomaton()
        ctx = make_context(max_repair=2)

        # начало
        assert ctx.detail.quality_state == DetailQualityState.UNCHECKED

        # провал контроля
        fsm.fire(QualityEvent.CONTROL_FAILED, ctx)
        assert ctx.detail.quality_state == DetailQualityState.DEFECTIVE

        # ремонт
        fsm.fire(QualityEvent.REPAIR_COMPLETE, ctx)
        assert ctx.detail.quality_state == DetailQualityState.REPAIRED
        assert ctx.detail.repair_count == 1

        # успех
        fsm.fire(QualityEvent.CONTROL_PASSED, ctx)
        assert ctx.detail.quality_state == DetailQualityState.ACCEPTED
