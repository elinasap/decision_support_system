"""
Обёртка Монте-Карло для многократного прогона DES.

Один прогон DES — одна случайная реализация. Монте-Карло запускает
N прогонов с разными seed и агрегирует результаты: средние,
стандартные отклонения, доверительные интервалы.

Использование:
    from simulation.monte_carlo import monte_carlo_run

    summary = monte_carlo_run(
        model_dict=model.to_dict(),
        max_time=10000,
        n_runs=100,
        base_seed=42,
    )
    print(f"Пропускная способность: {summary.mean_throughput:.4f} "
          f"± {summary.ci_throughput:.4f}")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from simulation.engine import Simulator
from simulation.result import SimulationResult


@dataclass
class MonteCarloSummary:
    """
    Агрегированные результаты N прогонов Монте-Карло.

    Содержит средние значения, стандартные отклонения и 95%-е
    доверительные интервалы (±) для ключевых метрик.
    """
    n_runs: int = 0

    # Пропускная способность (принятых деталей / время)
    mean_throughput: float = 0.0
    std_throughput: float = 0.0
    ci_throughput: float = 0.0          # полуширина 95% ДИ

    # Процент брака
    mean_defect_rate: float = 0.0
    std_defect_rate: float = 0.0
    ci_defect_rate: float = 0.0

    # Среднее время цикла
    mean_cycle_time: float = 0.0
    std_cycle_time: float = 0.0
    ci_cycle_time: float = 0.0

    # Среднее число принятых / забракованных
    mean_accepted: float = 0.0
    mean_scrapped: float = 0.0

    # Загрузка блоков: {block_id: (mean_utilization, std_utilization)}
    block_utilizations: dict[str, tuple[float, float]] = field(
        default_factory=dict)

    # Средняя длина очередей: {block_id: (mean_avg_count, std_avg_count)}
    buffer_avg_counts: dict[str, tuple[float, float]] = field(
        default_factory=dict)

    # Все результаты (для дальнейшего анализа)
    all_results: list[SimulationResult] = field(default_factory=list)


def monte_carlo_run(
    model_dict: dict,
    max_time: float = 10000.0,
    n_runs: int = 100,
    base_seed: int = 0,
) -> MonteCarloSummary:
    """
    Запустить N прогонов DES с разными seed и агрегировать результаты.

    Аргументы:
        model_dict — словарь модели (из model.to_dict())
        max_time   — максимальное модельное время каждого прогона
        n_runs     — число прогонов
        base_seed  — базовый seed; прогон i получает seed = base_seed + i

    Возвращает MonteCarloSummary с агрегированными метриками.
    """
    results: list[SimulationResult] = []

    for i in range(n_runs):
        seed = base_seed + i
        sim = Simulator(model_dict, max_time=max_time, seed=seed)
        result = sim.run()
        results.append(result)

    return _aggregate(results)


def _aggregate(results: list[SimulationResult]) -> MonteCarloSummary:
    """Агрегировать список SimulationResult в MonteCarloSummary."""
    n = len(results)
    if n == 0:
        return MonteCarloSummary()

    # Собрать массивы значений
    throughputs = [r.throughput for r in results]
    defect_rates = [r.defect_rate for r in results]
    cycle_times = [r.avg_cycle_time for r in results]
    accepted = [r.total_accepted for r in results]
    scrapped = [r.total_scrapped for r in results]

    summary = MonteCarloSummary(
        n_runs=n,
        mean_throughput=_mean(throughputs),
        std_throughput=_std(throughputs),
        ci_throughput=_ci95(throughputs),
        mean_defect_rate=_mean(defect_rates),
        std_defect_rate=_std(defect_rates),
        ci_defect_rate=_ci95(defect_rates),
        mean_cycle_time=_mean(cycle_times),
        std_cycle_time=_std(cycle_times),
        ci_cycle_time=_ci95(cycle_times),
        mean_accepted=_mean(accepted),
        mean_scrapped=_mean(scrapped),
        all_results=results,
    )

    # Загрузка блоков
    block_ids = set()
    for r in results:
        block_ids.update(r.block_metrics.keys())

    for bid in block_ids:
        utils = [r.block_metrics[bid].utilization
                 for r in results if bid in r.block_metrics]
        if utils:
            summary.block_utilizations[bid] = (_mean(utils), _std(utils))

    # Средняя длина очередей
    buffer_ids = set()
    for r in results:
        buffer_ids.update(r.buffer_metrics.keys())

    for bid in buffer_ids:
        avgs = [r.buffer_metrics[bid].avg_count
                for r in results if bid in r.buffer_metrics]
        if avgs:
            summary.buffer_avg_counts[bid] = (_mean(avgs), _std(avgs))

    return summary


# ── Вспомогательные функции статистики ────────────────────────

def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    """Стандартное отклонение (выборочное, с делением на n-1)."""
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / (n - 1)
    return math.sqrt(variance)


def _ci95(values: list[float]) -> float:
    """
    Полуширина 95%-го доверительного интервала.
    CI = t * std / sqrt(n), где t ≈ 1.96 для большого n.
    """
    n = len(values)
    if n < 2:
        return 0.0
    return 1.96 * _std(values) / math.sqrt(n)
