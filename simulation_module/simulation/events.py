"""
Очередь событий для дискретно-событийного моделирования.

Событие — это запись: «что произошло, когда, с какой деталью, в каком блоке».
Все события хранятся в куче (heapq), упорядоченной по времени.
Движок в цикле достаёт ближайшее по времени событие и обрабатывает его.

Типы событий:
    DETAIL_CREATED     — деталь порождена из SOURCE и поступила в первый буфер
    SERVICE_STARTED    — блок техоперации взял деталь из upstream-буфера
    SERVICE_FINISHED   — обработка завершена (прошло t_proc секунд)
    DETAIL_DEPARTED    — деталь передана в downstream-буфер
    UNBLOCK_CHECK      — проверка: можно ли разблокировать заблокированный блок

Архитектурное решение: события — простые dataclass-записи без логики.
Вся логика обработки — в engine.py. Это делает события легко
сериализуемыми и тестируемыми.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


class EventType(Enum):
    """Типы событий симуляции."""
    DETAIL_CREATED = auto()     # деталь порождена из SOURCE
    SERVICE_STARTED = auto()    # блок начал обработку детали
    SERVICE_FINISHED = auto()   # блок закончил обработку
    DETAIL_DEPARTED = auto()    # деталь передана в downstream-буфер
    UNBLOCK_CHECK = auto()      # проверка разблокировки blocked-блока


@dataclass(order=False)
class SimEvent:
    """
    Одно событие в симуляции.

    Поля:
        time       — модельное время наступления события (секунды)
        event_type — тип события (EventType)
        block_id   — идентификатор блока, в котором происходит событие
        detail_uid — идентификатор детали (если применимо)
        data       — дополнительные данные (зависят от типа события)
        _seq       — порядковый номер для стабильной сортировки
                     (при одинаковом time события обрабатываются в порядке создания)
    """
    time: float
    event_type: EventType
    block_id: str = ""
    detail_uid: Optional[int] = None
    data: Any = None
    _seq: int = field(default=0, repr=False)

    def __lt__(self, other: SimEvent) -> bool:
        """Сравнение для heapq: сначала по времени, потом по порядку создания."""
        if self.time != other.time:
            return self.time < other.time
        return self._seq < other._seq

    def __le__(self, other: SimEvent) -> bool:
        return self == other or self < other


class EventQueue:
    """
    Очередь событий на основе кучи (heapq).

    Гарантирует:
    - O(log n) вставка и извлечение
    - стабильный порядок при одинаковом времени (по _seq)
    - события с одинаковым временем обрабатываются в порядке создания
    """

    def __init__(self):
        self._heap: list[SimEvent] = []
        self._counter: int = 0

    def schedule(self, time: float, event_type: EventType,
                 block_id: str = "", detail_uid: Optional[int] = None,
                 data: Any = None) -> SimEvent:
        """
        Запланировать новое событие.

        Возвращает созданное событие (для возможной отмены или диагностики).
        """
        event = SimEvent(
            time=time,
            event_type=event_type,
            block_id=block_id,
            detail_uid=detail_uid,
            data=data,
            _seq=self._counter,
        )
        self._counter += 1
        heapq.heappush(self._heap, event)
        return event

    def pop(self) -> SimEvent:
        """Достать ближайшее по времени событие."""
        if not self._heap:
            raise IndexError("EventQueue: очередь пуста")
        return heapq.heappop(self._heap)

    def peek(self) -> SimEvent:
        """Посмотреть ближайшее событие, не извлекая."""
        if not self._heap:
            raise IndexError("EventQueue: очередь пуста")
        return self._heap[0]

    @property
    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def __len__(self) -> int:
        return len(self._heap)

    def clear(self) -> None:
        """Очистить очередь."""
        self._heap.clear()
        self._counter = 0
