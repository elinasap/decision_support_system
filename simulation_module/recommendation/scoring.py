"""
recommendation/scoring.py

Composite score — одно число [0, 1] для каждого блока и буфера,
показывающее «проблемность» позиции.

Используется:
  - для heatmap на вкладке «Схема»
  - как вспомогательная метрика в итоговом заключении

Формулы:
  Блок:   0.35 * utilization + 0.65 * blocked_ratio
  Буфер:  0.50 * full_ratio  + 0.50 * avg_fill_ratio

Веса отражают практическую значимость:
  blocked_ratio перевешивает utilization, потому что блокировка
  означает конкретный затор downstream, а не просто высокую загрузку.
"""

from __future__ import annotations

from simulation.result import SimulationResult
from recommendation.thresholds import Thresholds


def compute_block_score(
    result: SimulationResult,
    thresholds: Thresholds | None = None,
) -> dict[str, float]:
    """
    Composite score для каждой операционной позиции.

    Возвращает {block_id: score}, score in [0, 1].
    """
    scores: dict[str, float] = {}
    for bid, m in result.block_metrics.items():
        score = 0.35 * m.utilization + 0.65 * m.blocked_ratio
        scores[bid] = round(min(max(score, 0.0), 1.0), 3)
    return scores


def compute_buffer_score(
    result: SimulationResult,
    thresholds: Thresholds | None = None,
) -> dict[str, float]:
    """
    Composite score для каждого буфера.

    Возвращает {block_id: score}, score in [0, 1].
    """
    scores: dict[str, float] = {}
    for bid, m in result.buffer_metrics.items():
        avg_fill = m.avg_count / m.capacity if m.capacity > 0 else 0.0
        score = 0.5 * m.full_ratio + 0.5 * avg_fill
        scores[bid] = round(min(max(score, 0.0), 1.0), 3)
    return scores
