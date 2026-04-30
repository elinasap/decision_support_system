"""
Runtime-состояние хранилища (BUFFER).

В отличие от model.Block (статическая конфигурация: тип, параметры, порты),
BufferState хранит то, что меняется во время симуляции:
- текущее число деталей (count)
- очередь деталей (FIFO)
- ссылку на блок-конфигурацию, из которого берется capacity

Используется автоматом BufferAutomaton через context-параметр метода fire().
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BufferState:
    """
    Состояние экземпляра хранилища в runtime.

    Поля:
        block_id   - идентификатор блока-хранилища (для связи с моделью)
        capacity   - максимальная емкость (из параметров блока)
        items      - FIFO-очередь деталей (дисциплина хранилища)
    """
    block_id: str
    capacity: int
    items: deque = field(default_factory=deque)

    @property
    def count(self) -> int:
        """Текущее число деталей в хранилище."""
        return len(self.items)

    @property
    def is_empty(self) -> bool:
        return self.count == 0

    @property
    def is_full(self) -> bool:
        return self.count >= self.capacity

    @property
    def has_free_space(self) -> bool:
        return self.count < self.capacity

    def push(self, detail: Any) -> None:
        """Положить деталь в хранилище (в хвост очереди)."""
        if self.is_full:
            raise ValueError(
                f"BufferState[{self.block_id}]: переполнение "
                f"(count={self.count}, capacity={self.capacity})"
            )
        self.items.append(detail)

    def pop(self) -> Any:
        """Забрать деталь из хранилища (из головы очереди, FIFO)."""
        if self.is_empty:
            raise ValueError(
                f"BufferState[{self.block_id}]: попытка забрать "
                f"деталь из пустого хранилища"
            )
        return self.items.popleft()

    def peek(self) -> Any:
        """Посмотреть первую деталь, не забирая."""
        if self.is_empty:
            raise ValueError(
                f"BufferState[{self.block_id}]: пустое хранилище"
            )
        return self.items[0]
