"""
Runtime-состояние блока техоперации (PROCESS, ASSEMBLY, CONTROL, TRANSPORT).

В отличие от model.Block (статическая конфигурация: тип, параметры, порты),
BlockOperationState хранит то, что меняется во время симуляции:
- какая деталь сейчас обрабатывается
- ссылки на соседние хранилища (upstream / downstream)
- метрики времени для расчета загрузки

Используется автоматом BlockAutomaton через context-параметр метода fire().

Архитектурные решения:
- upstream_buffers - СПИСОК, потому что у ASSEMBLY несколько входов.
  Для PROCESS/CONTROL/TRANSPORT в списке всегда ровно один буфер.
- downstream_buffer - один, потому что блок техоперации имеет один основной
  выход (out или out_good). Для CONTROL и PROCESS с has_internal_control
  есть еще out_defect, но он ведет в отдельный sink или обратно в свой
  upstream BUFFER через is_back_edge - этот случай обрабатывается на
  уровне движка симуляции, а не автомата блока.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from simulation.buffer_state import BufferState


@dataclass
class BlockOperationState:
    """
    Состояние экземпляра блока техоперации в runtime.

    Поля:
        block_id            - идентификатор блока (для связи с моделью)
        upstream_buffers    - входные хранилища (несколько у ASSEMBLY)
        downstream_buffer   - основное выходное хранилище
        service_time        - длительность обработки (из параметров блока)
        current_detail      - деталь, которая сейчас в обработке (или None)
        service_start_time  - время начала текущей обработки
        total_busy_time     - суммарное время в состоянии BUSY (для utilization)
        total_blocked_time  - суммарное время в состоянии BLOCKED (для метрик)
        total_idle_time     - суммарное время в состоянии IDLE
    """
    block_id: str
    upstream_buffers: list[BufferState]
    downstream_buffer: BufferState
    service_time: float
    current_detail: Any = None
    service_start_time: Optional[float] = None
    total_busy_time: float = 0.0
    total_blocked_time: float = 0.0
    total_idle_time: float = 0.0
    total_maintenance_time: float = 0.0   # суммарное время в MAINTENANCE
    failure_count: int = 0                # сколько раз произошёл отказ
    last_failure_time: Optional[float] = None
    interrupted_detail: Any = None        # деталь, прерванная отказом

    @property
    def has_upstream_detail(self) -> bool:
        """Есть ли хотя бы в одном из upstream-буферов деталь."""
        return any(not buf.is_empty for buf in self.upstream_buffers)

    @property
    def all_upstream_have_details(self) -> bool:
        """Во всех upstream-буферах есть деталь (для ASSEMBLY)."""
        return all(not buf.is_empty for buf in self.upstream_buffers)

    @property
    def downstream_has_space(self) -> bool:
        """В downstream-буфере есть место принять деталь."""
        return self.downstream_buffer.has_free_space

    @property
    def downstream_is_full(self) -> bool:
        """downstream-буфер переполнен."""
        return self.downstream_buffer.is_full

    @property
    def is_processing(self) -> bool:
        """Идет ли обработка прямо сейчас."""
        return self.current_detail is not None

    def take_detail_from_upstream(self, buffer_index: int = 0) -> Any:
        """
        Забрать деталь из upstream-буфера и поставить ее в обработку.

        buffer_index - индекс буфера в upstream_buffers.
        Для PROCESS/CONTROL/TRANSPORT всегда 0.
        Для ASSEMBLY используется в цикле по всем буферам.
        """
        if self.is_processing:
            raise ValueError(
                f"BlockOperationState[{self.block_id}]: попытка взять "
                f"новую деталь, пока идет обработка предыдущей"
            )
        buf = self.upstream_buffers[buffer_index]
        self.current_detail = buf.pop()
        return self.current_detail

    def push_detail_to_downstream(self) -> Any:
        """Передать обработанную деталь в downstream-буфер."""
        if not self.is_processing:
            raise ValueError(
                f"BlockOperationState[{self.block_id}]: нет детали для "
                f"передачи в downstream"
            )
        if self.downstream_is_full:
            raise ValueError(
                f"BlockOperationState[{self.block_id}]: downstream-буфер "
                f"переполнен, передача невозможна"
            )
        detail = self.current_detail
        self.downstream_buffer.push(detail)
        self.current_detail = None
        self.service_start_time = None
        return detail
