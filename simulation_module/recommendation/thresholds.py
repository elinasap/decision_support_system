"""
Пороговые значения для диагностики (θ).

Все значения параметрические — пользователь может переопределить
любое из них, передав нужные аргументы в Thresholds().

Значения по умолчанию:
    θ_U  = 0.85  — загрузка блока (utilization)
    θ_B  = 0.20  — доля блокировки (blocked_ratio)
    θ_I  = 0.40  — доля простоя (idle_ratio)
    θ_L  = 0.70  — средняя заполненность буфера (avg_count / capacity)
    θ_F  = 0.10  — доля времени переполнения (full_ratio)
    θ_CT = None  — среднее время цикла (задаётся пользователем)
    θ_TP = None  — пропускная способность (задаётся пользователем)
    θ_DR = 0.05  — процент брака (defect_rate)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Thresholds:
    """Набор пороговых значений для алгоритма диагностики."""

    # Блоки (техоперации и транспортные позиции)
    utilization: float = 0.85       # θ_U: перегрузка
    blocked_ratio: float = 0.20     # θ_B: блокировка
    idle_ratio: float = 0.40        # θ_I: простой

    # Буферы
    avg_fill_ratio: float = 0.70    # θ_L: средняя заполненность (avg_count / capacity)
    full_ratio: float = 0.10        # θ_F: доля времени переполнения

    # Системные метрики (None = порог не задан, проверка пропускается)
    avg_cycle_time: Optional[float] = None   # θ_CT
    throughput: Optional[float] = None       # θ_TP (минимальная допустимая)
    defect_rate: float = 0.05               # θ_DR
