"""
Runtime-экземпляр детали в имитационном моделировании.

Прямая реализация п.5.1 формализации:
    d_i = (uid, pos, phase, type, state, history)

Расширения относительно формализации:
- repair_count - счетчик повторных ремонтов (для автомата качества)
- created_at   - время создания (для метрик времени цикла)

Все поля, кроме uid и type_id, могут меняться по ходу симуляции.
Поле history заполняется при каждом посещении блока (см. VisitRecord).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class DetailQualityState(Enum):
    """
    Состояние качества детали (s.state из формализации).

    Соответствует автомату A_qual (см. simulation.automata.quality):
        UNCHECKED  - проверка еще не проводилась или пройдена успешно
        DEFECTIVE  - не прошла последний контроль
        REPAIRED   - была в ремонте, готова к повторному контролю
        ACCEPTED   - принята как готовая продукция (терминальное)
        SCRAPPED   - отправлена в утиль (терминальное)
    """
    UNCHECKED = auto()
    DEFECTIVE = auto()
    REPAIRED = auto()
    ACCEPTED = auto()
    SCRAPPED = auto()


@dataclass
class VisitRecord:
    """
    Запись о посещении блока.

    Заполняется при входе в блок (t_in) и при выходе (t_out).
    Используется для расчета времени цикла и других метрик.
    """
    block_id: str
    t_in: float
    t_out: Optional[float] = None
    was_returned: bool = False  # пришла по ребру с is_back_edge=True


@dataclass
class DetailInstance:
    """
    Экземпляр детали в runtime.

    Соответствует d_i из формализации (п.5.1) с добавлением
    счетчика ремонтов и времени создания для метрик.

    Поля:
        uid           - уникальный целочисленный идентификатор
        type_id       - ключ в model.detail_types (например, 'd_blank')
        pos           - id текущего блока (None до создания / после sink)
        quality_state - состояние качества (для автомата A_qual)
        repair_count  - сколько раз деталь была ремонтирована
        history       - список посещений блоков
        created_at    - время создания (для расчета общего времени цикла)
    """
    uid: int
    type_id: str
    pos: Optional[str] = None
    quality_state: DetailQualityState = DetailQualityState.UNCHECKED
    repair_count: int = 0
    history: list[VisitRecord] = field(default_factory=list)
    created_at: float = 0.0

    def enter_block(self, block_id: str, time: float, was_returned: bool = False) -> None:
        """Зафиксировать вход в блок."""
        self.pos = block_id
        self.history.append(
            VisitRecord(block_id=block_id, t_in=time, was_returned=was_returned)
        )

    def leave_block(self, time: float) -> None:
        """Зафиксировать выход из блока (закрыть текущий VisitRecord)."""
        if not self.history:
            raise ValueError(
                f"DetailInstance[{self.uid}]: leave_block без enter_block"
            )
        last = self.history[-1]
        if last.t_out is not None:
            raise ValueError(
                f"DetailInstance[{self.uid}]: предыдущий VisitRecord "
                f"уже закрыт (block_id={last.block_id})"
            )
        last.t_out = time

    def increment_repair_count(self) -> None:
        """Увеличить счетчик ремонтов на 1."""
        self.repair_count += 1

    def is_terminal(self) -> bool:
        """Деталь дошла до конца маршрута (принята или утилизирована)."""
        return self.quality_state in (
            DetailQualityState.ACCEPTED,
            DetailQualityState.SCRAPPED,
        )

    def total_time_in_system(self, current_time: float) -> float:
        """
        Время от создания до текущего момента.
        Используется как метрика времени цикла.
        """
        return current_time - self.created_at
