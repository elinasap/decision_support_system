"""
Результат одного прогона симуляции.

SimulationResult — итоговый контейнер, который передаётся:
- в GUI для отображения метрик
- в алгоритм рекомендаций (шаг 3 диссертации)
- в обёртку Монте-Карло для агрегации по нескольким прогонам

Содержит:
- параметры прогона (max_time, seed, число деталей)
- метрики по блокам (загрузка, время простоя, время блокировки)
- метрики по буферам (средняя/макс длина очереди)
- метрики по деталям (время цикла, статус: принята/утиль)
- итоговые показатели (пропускная способность, процент брака)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BlockMetrics:
    """Метрики одного блока техоперации за прогон."""
    block_id: str
    block_label: str = ""
    block_type: str = ""

    total_busy_time: float = 0.0        # суммарное время обработки
    total_blocked_time: float = 0.0     # суммарное время блокировки
    total_idle_time: float = 0.0        # суммарное время простоя
    total_maintenance_time: float = 0.0 # суммарное время ТО и ремонта

    details_processed: int = 0          # сколько деталей обработано
    failure_count: int = 0              # сколько раз случался отказ

    @property
    def utilization(self) -> float:
        """Загрузка: доля рабочего времени (без учёта ТО)."""
        total = self.total_busy_time + self.total_blocked_time + self.total_idle_time
        if total == 0:
            return 0.0
        return self.total_busy_time / total

    @property
    def blocked_ratio(self) -> float:
        """Доля времени блокировки (downstream переполнен)."""
        total = self.total_busy_time + self.total_blocked_time + self.total_idle_time
        if total == 0:
            return 0.0
        return self.total_blocked_time / total

    @property
    def availability(self) -> float:
        """Коэффициент готовности: доля времени, когда оборудование не на ТО."""
        total = (self.total_busy_time + self.total_blocked_time
                 + self.total_idle_time + self.total_maintenance_time)
        if total == 0 or self.total_maintenance_time == 0:
            return 1.0
        return 1.0 - self.total_maintenance_time / total

    @property
    def required_machines(self) -> int:
        """Минимальное число станков с учётом загрузки и готовности."""
        import math
        if self.availability <= 0:
            return 1
        return max(1, math.ceil(self.utilization / self.availability))

    @property
    def failure_rate(self) -> float:
        """Частота отказов: количество отказов на час модельного времени."""
        total = (self.total_busy_time + self.total_blocked_time
                 + self.total_idle_time + self.total_maintenance_time)
        if total == 0:
            return 0.0
        return self.failure_count / (total / 3600)


@dataclass
class BufferMetrics:
    """Метрики одного буфера за прогон."""
    block_id: str
    block_label: str = ""
    capacity: int = 0

    max_count: int = 0                 # максимальное заполнение
    time_full: float = 0.0            # сколько времени буфер был полон
    time_empty: float = 0.0           # сколько времени буфер был пуст

    # Для расчёта средней длины очереди: сумма (count * duration)
    _weighted_count_sum: float = 0.0
    _total_observed_time: float = 0.0

    @property
    def avg_count(self) -> float:
        """Средняя длина очереди (среднее число деталей в буфере)."""
        if self._total_observed_time == 0:
            return 0.0
        return self._weighted_count_sum / self._total_observed_time

    @property
    def full_ratio(self) -> float:
        """Доля времени, когда буфер был полон. Высокое значение = узкое место."""
        if self._total_observed_time == 0:
            return 0.0
        return self.time_full / self._total_observed_time

    @property
    def empty_ratio(self) -> float:
        """Доля времени, когда буфер был пуст."""
        if self._total_observed_time == 0:
            return 0.0
        return self.time_empty / self._total_observed_time


@dataclass
class DetailResult:
    """Результат для одного экземпляра детали."""
    uid: int
    type_id: str
    final_state: str = ""        # ACCEPTED / SCRAPPED
    cycle_time: float = 0.0      # время от создания до выхода из системы
    repair_count: int = 0        # сколько раз ремонтировалась
    blocks_visited: int = 0      # сколько блоков прошла


@dataclass
class SimulationResult:
    """
    Полный результат одного прогона DES.

    Это интерфейсный объект: его потребляют GUI, алгоритм
    рекомендаций и обёртка Монте-Карло.
    """
    # Параметры прогона
    max_time: float = 0.0
    seed: Optional[int] = None
    elapsed_model_time: float = 0.0    # фактическое время окончания
    total_events_processed: int = 0

    # Метрики по блокам и буферам
    block_metrics: dict[str, BlockMetrics] = field(default_factory=dict)
    buffer_metrics: dict[str, BufferMetrics] = field(default_factory=dict)

    # Результаты по деталям
    detail_results: list[DetailResult] = field(default_factory=list)

    # Итоговые показатели
    total_created: int = 0         # сколько деталей создано
    total_accepted: int = 0        # сколько принято (ACCEPTED)
    total_scrapped: int = 0        # сколько в утиль (SCRAPPED)
    total_in_progress: int = 0     # сколько осталось в системе

    @property
    def throughput(self) -> float:
        """Пропускная способность: принятых деталей / время."""
        if self.elapsed_model_time == 0:
            return 0.0
        return self.total_accepted / self.elapsed_model_time

    @property
    def defect_rate(self) -> float:
        """Процент брака: утиль / (принято + утиль)."""
        total = self.total_accepted + self.total_scrapped
        if total == 0:
            return 0.0
        return self.total_scrapped / total

    @property
    def avg_cycle_time(self) -> float:
        """Среднее время цикла по завершённым деталям."""
        finished = [d for d in self.detail_results if d.cycle_time > 0]
        if not finished:
            return 0.0
        return sum(d.cycle_time for d in finished) / len(finished)
