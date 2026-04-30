"""
Конечный автомат качества детали.

Описывает изменение состояния качества по мере прохождения детали через
блоки контроля и операций ремонта. Соответствует п.5.1 (поле state) и
п.10 (обработка брака) формализации.

Состояния:
    UNCHECKED  - проверка еще не проводилась или пройдена успешно
                 (имя выбрано вместо normal, чтобы не утверждать "деталь
                 нормальная" - до контроля мы этого не знаем)
    DEFECTIVE  - не прошла последний контроль качества
    REPAIRED   - была ремонтирована, готова к повторному контролю
    ACCEPTED   - принята как готовая продукция (терминальное)
    SCRAPPED   - отправлена в утиль (терминальное)

События:
    CONTROL_PASSED       - деталь прошла контроль (defect_prob <= threshold)
    CONTROL_FAILED       - деталь не прошла контроль
    REPAIR_COMPLETE      - ремонт завершен, деталь готова к повторному контролю
    ENTER_PRODUCT_SINK   - деталь поступила в sink готовой продукции
    ENTER_SCRAP_SINK     - деталь поступила в sink утиля

Параметр max_repair:
    Хранится в словаре model.detail_types отдельно для каждого типа детали.
    Автомат читает его из контекста (QualityCheckContext.max_repair).
    max_repair = 0 означает "ремонт невозможен" - любая дефектная деталь
    сразу идет в утиль.

Формальное определение:
    A_qual = (S, Sigma, delta, s_0, F)

где:
    S      = {UNCHECKED, DEFECTIVE, REPAIRED, ACCEPTED, SCRAPPED}
    Sigma  = {CONTROL_PASSED, CONTROL_FAILED, REPAIR_COMPLETE,
              ENTER_PRODUCT_SINK, ENTER_SCRAP_SINK}
    s_0    = UNCHECKED
    F      = {ACCEPTED, SCRAPPED}

Таблица переходов (7 правил):
    UNCHECKED  --control_passed-----------------> UNCHECKED  (петля; контроль пройден)
    UNCHECKED  --control_failed-----------------> DEFECTIVE
    UNCHECKED  --enter_product_sink-------------> ACCEPTED
    DEFECTIVE  --repair_complete----------------> REPAIRED
    DEFECTIVE  --enter_scrap_sink---------------> SCRAPPED   (неремонтопригодный)
    REPAIRED   --control_passed-----------------> ACCEPTED
    REPAIRED   --control_failed [count<max]-----> DEFECTIVE  (есть еще попытки)
    REPAIRED   --control_failed [count>=max]----> SCRAPPED   (исчерпан лимит)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from simulation.automata.base import StateMachine, Transition
from simulation.detail_instance import DetailInstance, DetailQualityState


class QualityState(Enum):
    """Состояния качества детали (как в автомате)."""
    UNCHECKED = auto()
    DEFECTIVE = auto()
    REPAIRED = auto()
    ACCEPTED = auto()
    SCRAPPED = auto()


class QualityEvent(Enum):
    """События автомата качества."""
    CONTROL_PASSED = auto()       # контроль пройден (r <= threshold)
    CONTROL_FAILED = auto()       # контроль не пройден (r > threshold)
    REPAIR_COMPLETE = auto()      # ремонт завершен
    ENTER_PRODUCT_SINK = auto()   # деталь дошла до sink готовой продукции
    ENTER_SCRAP_SINK = auto()     # деталь дошла до sink утиля


@dataclass
class QualityCheckContext:
    """
    Контекст для автомата качества.

    Связывает экземпляр детали с глобальным словарем типов деталей,
    откуда автомат читает max_repair конкретного типа.

    Соглашение: если в словаре типа нет ключа max_repair или его
    значение 0 - ремонт невозможен.
    """
    detail: DetailInstance
    detail_types: dict[str, dict]

    @property
    def max_repair(self) -> int:
        """
        Сколько раз можно ремонтировать деталь данного типа.
        0 = не подлежит ремонту.
        """
        return self.detail_types.get(self.detail.type_id, {}).get("max_repair", 0)

    @property
    def repair_count(self) -> int:
        """Сколько раз уже ремонтировали данный экземпляр."""
        return self.detail.repair_count


# --- охранные условия ---

def _can_repair_again(ctx: QualityCheckContext) -> bool:
    """Лимит ремонтов еще не исчерпан - можно отправить на повторный ремонт."""
    return ctx.repair_count < ctx.max_repair


def _no_more_repairs(ctx: QualityCheckContext) -> bool:
    """Лимит ремонтов исчерпан - деталь в утиль."""
    return ctx.repair_count >= ctx.max_repair


class QualityAutomaton(StateMachine):
    """Автомат качества детали."""

    INITIAL_STATE = QualityState.UNCHECKED

    TRANSITIONS = [
        # UNCHECKED: контроль пройден - остаемся в UNCHECKED (готовы к след. контролю)
        Transition(
            from_state=QualityState.UNCHECKED,
            event=QualityEvent.CONTROL_PASSED,
            to_state=QualityState.UNCHECKED,
            guard=None,
            guard_description="без условия (петля)",
        ),
        # UNCHECKED: контроль не пройден - в брак
        Transition(
            from_state=QualityState.UNCHECKED,
            event=QualityEvent.CONTROL_FAILED,
            to_state=QualityState.DEFECTIVE,
            guard=None,
            guard_description="без условия",
        ),
        # UNCHECKED: дошла до sink готовой продукции - принята
        Transition(
            from_state=QualityState.UNCHECKED,
            event=QualityEvent.ENTER_PRODUCT_SINK,
            to_state=QualityState.ACCEPTED,
            guard=None,
            guard_description="без условия (терминал)",
        ),

        # DEFECTIVE: ремонт завершен - готова к повторному контролю
        Transition(
            from_state=QualityState.DEFECTIVE,
            event=QualityEvent.REPAIR_COMPLETE,
            to_state=QualityState.REPAIRED,
            guard=None,
            guard_description="без условия",
        ),
        # DEFECTIVE: неремонтопригодная - сразу в sink утиля
        Transition(
            from_state=QualityState.DEFECTIVE,
            event=QualityEvent.ENTER_SCRAP_SINK,
            to_state=QualityState.SCRAPPED,
            guard=None,
            guard_description="без условия (терминал)",
        ),

        # REPAIRED: контроль пройден после ремонта - принята
        Transition(
            from_state=QualityState.REPAIRED,
            event=QualityEvent.CONTROL_PASSED,
            to_state=QualityState.ACCEPTED,
            guard=None,
            guard_description="без условия (терминал)",
        ),
        # REPAIRED: контроль провален, есть еще попытки - снова в брак
        Transition(
            from_state=QualityState.REPAIRED,
            event=QualityEvent.CONTROL_FAILED,
            to_state=QualityState.DEFECTIVE,
            guard=_can_repair_again,
            guard_description="repair_count < max_repair",
        ),
        # REPAIRED: контроль провален, лимит исчерпан - в утиль
        Transition(
            from_state=QualityState.REPAIRED,
            event=QualityEvent.CONTROL_FAILED,
            to_state=QualityState.SCRAPPED,
            guard=_no_more_repairs,
            guard_description="repair_count >= max_repair",
        ),
    ]

    TERMINAL_STATES = {QualityState.ACCEPTED, QualityState.SCRAPPED}

    # Действия при входе в новое состояние:
    # инкрементируем repair_count при входе в REPAIRED
    # синхронизируем quality_state детали с состоянием автомата

    def on_enter_repaired(self, context: QualityCheckContext) -> None:
        """При завершении ремонта - инкрементируем счетчик."""
        context.detail.increment_repair_count()
        context.detail.quality_state = DetailQualityState.REPAIRED

    def on_enter_defective(self, context: QualityCheckContext) -> None:
        """При попадании в брак - синхронизируем state детали."""
        context.detail.quality_state = DetailQualityState.DEFECTIVE

    def on_enter_unchecked(self, context: QualityCheckContext) -> None:
        """Возврат в UNCHECKED - синхронизируем state детали."""
        context.detail.quality_state = DetailQualityState.UNCHECKED

    def on_enter_accepted(self, context: QualityCheckContext) -> None:
        """Терминальное состояние - принята как готовая продукция."""
        context.detail.quality_state = DetailQualityState.ACCEPTED

    def on_enter_scrapped(self, context: QualityCheckContext) -> None:
        """Терминальное состояние - утилизирована."""
        context.detail.quality_state = DetailQualityState.SCRAPPED
