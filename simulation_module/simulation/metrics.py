"""
Сборщик метрик по ходу симуляции.

MetricsCollector слушает события движка и накапливает статистику:
- время в каждом состоянии для блоков (BUSY/IDLE/BLOCKED)
- заполненность буферов (для средней длины очереди)
- время цикла для каждой детали

Принцип: при каждом изменении состояния записываем, сколько времени
объект провёл в предыдущем состоянии. Это даёт точные метрики
без необходимости «тикать» на каждую секунду модельного времени.

Пример: блок был IDLE с t=0 до t=10, потом стал BUSY.
При переходе IDLE→BUSY записываем: idle_time += 10 - 0 = 10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from simulation.result import (
    SimulationResult,
    BlockMetrics,
    BufferMetrics,
    DetailResult,
)


@dataclass
class _BlockTracker:
    """Трекер состояния одного блока техоперации."""
    block_id: str
    block_label: str = ""
    block_type: str = ""
    current_state: str = "idle"        # idle / busy / blocked / maintenance
    state_entered_at: float = 0.0      # когда вошли в текущее состояние
    total_busy: float = 0.0
    total_blocked: float = 0.0
    total_idle: float = 0.0
    total_maintenance: float = 0.0
    details_processed: int = 0
    failure_count: int = 0


@dataclass
class _BufferTracker:
    """Трекер состояния одного буфера."""
    block_id: str
    block_label: str = ""
    capacity: int = 0
    current_count: int = 0
    count_changed_at: float = 0.0      # когда последний раз менялся count
    max_count: int = 0
    time_full: float = 0.0
    time_empty: float = 0.0
    weighted_count_sum: float = 0.0    # сумма (count * duration)
    total_observed_time: float = 0.0


class MetricsCollector:
    """
    Собирает метрики по ходу прогона симуляции.

    Использование:
        collector = MetricsCollector()
        collector.register_block("B3", "Станок", "process")
        collector.register_buffer("B2", "Буфер", capacity=10)
        ...
        # По ходу симуляции:
        collector.block_state_changed("B3", "busy", time=5.0)
        collector.buffer_count_changed("B2", new_count=3, time=5.0)
        collector.detail_finished(detail, time=100.0)
        ...
        # В конце:
        result = collector.build_result(elapsed_time=500.0)
    """

    def __init__(self):
        self._blocks: dict[str, _BlockTracker] = {}
        self._buffers: dict[str, _BufferTracker] = {}
        self._detail_results: list[DetailResult] = []
        self._total_created: int = 0
        self._total_accepted: int = 0
        self._total_scrapped: int = 0
        self._total_events: int = 0

    # ── Регистрация объектов ──────────────────────────────────

    def register_block(self, block_id: str, label: str = "",
                       block_type: str = "") -> None:
        """Зарегистрировать блок техоперации для сбора метрик."""
        self._blocks[block_id] = _BlockTracker(
            block_id=block_id,
            block_label=label,
            block_type=block_type,
        )

    def register_buffer(self, block_id: str, label: str = "",
                        capacity: int = 0, initial_count: int = 0) -> None:
        """Зарегистрировать буфер для сбора метрик."""
        self._buffers[block_id] = _BufferTracker(
            block_id=block_id,
            block_label=label,
            capacity=capacity,
            current_count=initial_count,
            max_count=initial_count,
        )

    # ── Обновления по ходу симуляции ──────────────────────────

    def block_state_changed(self, block_id: str, new_state: str,
                            time: float) -> None:
        """
        Блок сменил состояние (idle/busy/blocked).
        Записываем, сколько времени он провёл в предыдущем состоянии.
        """
        tracker = self._blocks.get(block_id)
        if tracker is None:
            return

        duration = time - tracker.state_entered_at
        if duration > 0:
            if tracker.current_state == "busy":
                tracker.total_busy += duration
            elif tracker.current_state == "blocked":
                tracker.total_blocked += duration
            elif tracker.current_state == "maintenance":
                tracker.total_maintenance += duration
            else:  # idle
                tracker.total_idle += duration

        if new_state == "maintenance" and tracker.current_state != "maintenance":
            tracker.failure_count += 1

        tracker.current_state = new_state
        tracker.state_entered_at = time

    def block_detail_processed(self, block_id: str) -> None:
        """Блок завершил обработку одной детали."""
        tracker = self._blocks.get(block_id)
        if tracker is not None:
            tracker.details_processed += 1

    def buffer_count_changed(self, block_id: str, new_count: int,
                             time: float) -> None:
        """
        Число деталей в буфере изменилось.
        Записываем взвешенный вклад предыдущего count.
        """
        tracker = self._buffers.get(block_id)
        if tracker is None:
            return

        duration = time - tracker.count_changed_at
        if duration > 0:
            tracker.weighted_count_sum += tracker.current_count * duration
            tracker.total_observed_time += duration

            # Время в полном / пустом состоянии
            if tracker.current_count >= tracker.capacity:
                tracker.time_full += duration
            if tracker.current_count == 0:
                tracker.time_empty += duration

        tracker.current_count = new_count
        tracker.max_count = max(tracker.max_count, new_count)
        tracker.count_changed_at = time

    def detail_created(self) -> None:
        """Зафиксировать создание детали."""
        self._total_created += 1

    def detail_finished(self, uid: int, type_id: str, final_state: str,
                        cycle_time: float, repair_count: int,
                        blocks_visited: int) -> None:
        """Зафиксировать завершение пути детали (ACCEPTED или SCRAPPED)."""
        self._detail_results.append(DetailResult(
            uid=uid,
            type_id=type_id,
            final_state=final_state,
            cycle_time=cycle_time,
            repair_count=repair_count,
            blocks_visited=blocks_visited,
        ))
        if final_state == "ACCEPTED":
            self._total_accepted += 1
        elif final_state == "SCRAPPED":
            self._total_scrapped += 1

    def event_processed(self) -> None:
        """Счётчик обработанных событий."""
        self._total_events += 1

    # ── Финализация ───────────────────────────────────────────

    def finalize(self, end_time: float) -> None:
        """
        Закрыть последние интервалы.
        Вызывается в конце симуляции, чтобы учесть время
        в последнем состоянии (от последнего перехода до end_time).
        """
        for tracker in self._blocks.values():
            self.block_state_changed(tracker.block_id, tracker.current_state,
                                     end_time)
        for tracker in self._buffers.values():
            self.buffer_count_changed(tracker.block_id, tracker.current_count,
                                      end_time)

    def build_result(self, max_time: float, elapsed_time: float,
                     seed: Optional[int] = None,
                     total_in_progress: int = 0) -> SimulationResult:
        """Собрать итоговый SimulationResult."""
        block_metrics = {}
        for t in self._blocks.values():
            block_metrics[t.block_id] = BlockMetrics(
                block_id=t.block_id,
                block_label=t.block_label,
                block_type=t.block_type,
                total_busy_time=t.total_busy,
                total_blocked_time=t.total_blocked,
                total_idle_time=t.total_idle,
                total_maintenance_time=t.total_maintenance,
                details_processed=t.details_processed,
                failure_count=t.failure_count,
            )

        buffer_metrics = {}
        for t in self._buffers.values():
            buffer_metrics[t.block_id] = BufferMetrics(
                block_id=t.block_id,
                block_label=t.block_label,
                capacity=t.capacity,
                max_count=t.max_count,
                time_full=t.time_full,
                time_empty=t.time_empty,
                _weighted_count_sum=t.weighted_count_sum,
                _total_observed_time=t.total_observed_time,
            )

        return SimulationResult(
            max_time=max_time,
            seed=seed,
            elapsed_model_time=elapsed_time,
            total_events_processed=self._total_events,
            block_metrics=block_metrics,
            buffer_metrics=buffer_metrics,
            detail_results=self._detail_results,
            total_created=self._total_created,
            total_accepted=self._total_accepted,
            total_scrapped=self._total_scrapped,
            total_in_progress=total_in_progress,
        )
