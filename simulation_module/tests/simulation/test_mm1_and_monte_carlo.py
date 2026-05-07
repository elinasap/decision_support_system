"""
Верификация симулятора на модели M/M/1 и тесты обёртки Монте-Карло.

M/M/1 — простейшая система массового обслуживания:
- Пуассоновский поток заявок (экспоненциальный интервал, среднее = 1/λ)
- Экспоненциальное время обслуживания (среднее = 1/μ)
- Один сервер, одна очередь, бесконечная ёмкость

Аналитические формулы (Эрланга):
    ρ = λ/μ                              — загрузка сервера
    L_q = ρ² / (1 - ρ)                   — средняя длина очереди
    W = 1 / (μ - λ)                       — среднее время в системе
    W_q = ρ / (μ - λ)                     — среднее время ожидания

Эти формулы сравниваются с эмпирическими результатами симуляции.
При достаточном числе деталей (10 000+) отклонение должно быть < 10%.
"""

import pytest
from simulation.engine import Simulator
from simulation.monte_carlo import monte_carlo_run, MonteCarloSummary


# ══════════════════════════════════════════════════════════════
# Утилиты
# ══════════════════════════════════════════════════════════════

def make_mm1_model(lam: float, mu: float, n_details: int = 10000):
    """
    Создать модель M/M/1:
        SOURCE(exponential, interval=1/λ) → BUF(∞) → PROCESS(exponential, 1/μ) → BUF → SINK

    lam — интенсивность потока (деталей/сек)
    mu  — интенсивность обслуживания (деталей/сек)
    """
    inter_arrival = 1.0 / lam    # средний интервал между заявками
    service_time = 1.0 / mu      # среднее время обслуживания

    blocks = {
        "B1": {
            "id": "B1", "type": "source", "label": "Поток заявок",
            "params": {
                "capacity": n_details,
                "detail_type": "d_blank",
                "interval_sec": inter_arrival,
                "arrival_mode": "exponential",
            },
            "ports": {"in": [], "out": ["out"], "used": []},
        },
        "B2": {
            "id": "B2", "type": "buffer", "label": "Очередь",
            "params": {"capacity": 999999},
            "ports": {"in": ["in"], "out": ["out"], "used": []},
        },
        "B3": {
            "id": "B3", "type": "process", "label": "Сервер",
            "params": {
                "operation_time_sec": service_time,
                "service_mode": "exponential",
            },
            "ports": {"in": ["in"], "out": ["out"], "used": []},
        },
        "B4": {
            "id": "B4", "type": "buffer", "label": "Выход",
            "params": {"capacity": 999999},
            "ports": {"in": ["in"], "out": ["out"], "used": []},
        },
        "B5": {
            "id": "B5", "type": "sink", "label": "Завершено",
            "params": {},
            "ports": {"in": ["in"], "out": [], "used": []},
        },
    }
    edges = {
        "E1": {"id": "E1", "from_block": "B1", "from_port": "out",
               "to_block": "B2", "to_port": "in", "is_back_edge": False,
               "detail_type": "", "defect_type": "repairable",
               "repair_time_sec": 0, "comment": ""},
        "E2": {"id": "E2", "from_block": "B2", "from_port": "out",
               "to_block": "B3", "to_port": "in", "is_back_edge": False,
               "detail_type": "", "defect_type": "repairable",
               "repair_time_sec": 0, "comment": ""},
        "E3": {"id": "E3", "from_block": "B3", "from_port": "out",
               "to_block": "B4", "to_port": "in", "is_back_edge": False,
               "detail_type": "", "defect_type": "repairable",
               "repair_time_sec": 0, "comment": ""},
        "E4": {"id": "E4", "from_block": "B4", "from_port": "out",
               "to_block": "B5", "to_port": "in", "is_back_edge": False,
               "detail_type": "", "defect_type": "repairable",
               "repair_time_sec": 0, "comment": ""},
    }
    return {
        "name": "M/M/1",
        "detail_types": {"d_blank": {"label": "Заявка", "unit": "шт",
                                      "max_repair": 0}},
        "blocks": blocks,
        "edges": edges,
    }


# ══════════════════════════════════════════════════════════════
# Верификация M/M/1
# ══════════════════════════════════════════════════════════════

class TestMM1Verification:
    """
    Сравнение эмпирических метрик симулятора с аналитическими формулами M/M/1.

    Параметры: λ=0.8, μ=1.0 → ρ=0.8.
    При ρ=0.8 система стабильна, очереди заметны, но не бесконечны.
    """

    LAM = 0.8   # интенсивность потока
    MU = 1.0    # интенсивность обслуживания
    RHO = LAM / MU  # = 0.8

    # Аналитические значения M/M/1
    EXPECTED_UTILIZATION = RHO                          # 0.8
    EXPECTED_L_Q = RHO ** 2 / (1 - RHO)                # 3.2
    EXPECTED_W = 1.0 / (MU - LAM)                       # 5.0
    EXPECTED_W_Q = RHO / (MU - LAM)                     # 4.0

    def test_utilization(self):
        """
        Загрузка сервера ≈ ρ = λ/μ = 0.8.
        Допуск: ±10% (стохастика).
        """
        model = make_mm1_model(self.LAM, self.MU, n_details=5000)
        result = Simulator(model, max_time=999999, seed=42).run()

        empirical_util = result.block_metrics["B3"].utilization
        assert empirical_util == pytest.approx(
            self.EXPECTED_UTILIZATION, abs=0.08
        ), (f"Загрузка: эмпирическая={empirical_util:.3f}, "
            f"ожидаемая={self.EXPECTED_UTILIZATION:.3f}")

    def test_avg_queue_length(self):
        """
        Средняя длина очереди ≈ L_q = ρ²/(1-ρ) = 3.2.
        Допуск: ±30% (L_q чувствительна к хвостам распределений).
        """
        model = make_mm1_model(self.LAM, self.MU, n_details=5000)
        result = Simulator(model, max_time=999999, seed=42).run()

        empirical_lq = result.buffer_metrics["B2"].avg_count
        assert empirical_lq == pytest.approx(
            self.EXPECTED_L_Q, rel=0.3
        ), (f"L_q: эмпирическая={empirical_lq:.2f}, "
            f"ожидаемая={self.EXPECTED_L_Q:.2f}")

    def test_avg_cycle_time(self):
        """
        Среднее время в системе ≈ W = 1/(μ-λ) = 5.0.
        Допуск: ±25%.
        """
        model = make_mm1_model(self.LAM, self.MU, n_details=5000)
        result = Simulator(model, max_time=999999, seed=42).run()

        empirical_w = result.avg_cycle_time
        assert empirical_w == pytest.approx(
            self.EXPECTED_W, rel=0.25
        ), (f"W: эмпирическая={empirical_w:.2f}, "
            f"ожидаемая={self.EXPECTED_W:.2f}")

    def test_all_details_processed(self):
        """Все 5000 деталей должны пройти через систему."""
        model = make_mm1_model(self.LAM, self.MU, n_details=5000)
        result = Simulator(model, max_time=999999, seed=42).run()

        assert result.total_created == 5000
        assert result.total_accepted == 5000
        assert result.total_in_progress == 0

    def test_monte_carlo_narrows_confidence(self):
        """
        Монте-Карло из 30 прогонов (по 1000 деталей) должен дать
        более узкий ДИ, чем разброс одиночных прогонов.
        """
        model = make_mm1_model(self.LAM, self.MU, n_details=1000)
        summary = monte_carlo_run(model, max_time=999999,
                                  n_runs=30, base_seed=100)

        # Средняя загрузка должна быть ≈ 0.8
        util_mean, util_std = summary.block_utilizations["B3"]
        assert util_mean == pytest.approx(
            self.EXPECTED_UTILIZATION, abs=0.05
        ), f"MC utilization: {util_mean:.3f} ± {util_std:.3f}"

        # ДИ для throughput должен быть < 10% от среднего
        if summary.mean_throughput > 0:
            relative_ci = summary.ci_throughput / summary.mean_throughput
            assert relative_ci < 0.1, (
                f"Относительный ДИ throughput = {relative_ci:.2%}, "
                f"ожидалось < 10%")


# ══════════════════════════════════════════════════════════════
# Верификация M/M/1 при малой нагрузке (ρ=0.5)
# ══════════════════════════════════════════════════════════════

class TestMM1LowLoad:
    """ρ=0.5: половина времени сервер свободен."""

    LAM = 0.5
    MU = 1.0
    RHO = 0.5
    EXPECTED_UTILIZATION = 0.5
    EXPECTED_L_Q = 0.5       # ρ²/(1-ρ) = 0.25/0.5 = 0.5
    EXPECTED_W = 2.0          # 1/(μ-λ) = 1/0.5 = 2.0

    def test_utilization_low_load(self):
        model = make_mm1_model(self.LAM, self.MU, n_details=5000)
        result = Simulator(model, max_time=999999, seed=42).run()

        empirical_util = result.block_metrics["B3"].utilization
        assert empirical_util == pytest.approx(
            self.EXPECTED_UTILIZATION, abs=0.05)

    def test_cycle_time_low_load(self):
        model = make_mm1_model(self.LAM, self.MU, n_details=5000)
        result = Simulator(model, max_time=999999, seed=42).run()

        assert result.avg_cycle_time == pytest.approx(
            self.EXPECTED_W, rel=0.2)


# ══════════════════════════════════════════════════════════════
# Тесты обёртки Монте-Карло
# ══════════════════════════════════════════════════════════════

class TestMonteCarlo:
    """Тесты корректности самой обёртки."""

    def _make_simple_model(self):
        """Простая детерминированная модель для тестов MC."""
        blocks = {
            "B1": {"id": "B1", "type": "source", "label": "Склад",
                   "params": {"capacity": 10, "detail_type": "d_blank"},
                   "ports": {"in": [], "out": ["out"], "used": []}},
            "B2": {"id": "B2", "type": "buffer", "label": "Буфер",
                   "params": {"capacity": 100},
                   "ports": {"in": ["in"], "out": ["out"], "used": []}},
            "B3": {"id": "B3", "type": "process", "label": "Станок",
                   "params": {"operation_time_sec": 10.0},
                   "ports": {"in": ["in"], "out": ["out"], "used": []}},
            "B4": {"id": "B4", "type": "buffer", "label": "Буфер2",
                   "params": {"capacity": 100},
                   "ports": {"in": ["in"], "out": ["out"], "used": []}},
            "B5": {"id": "B5", "type": "sink", "label": "Готовое",
                   "params": {},
                   "ports": {"in": ["in"], "out": [], "used": []}},
        }
        edges = {
            "E1": {"id": "E1", "from_block": "B1", "from_port": "out",
                   "to_block": "B2", "to_port": "in", "is_back_edge": False,
                   "detail_type": "", "defect_type": "repairable",
                   "repair_time_sec": 0, "comment": ""},
            "E2": {"id": "E2", "from_block": "B2", "from_port": "out",
                   "to_block": "B3", "to_port": "in", "is_back_edge": False,
                   "detail_type": "", "defect_type": "repairable",
                   "repair_time_sec": 0, "comment": ""},
            "E3": {"id": "E3", "from_block": "B3", "from_port": "out",
                   "to_block": "B4", "to_port": "in", "is_back_edge": False,
                   "detail_type": "", "defect_type": "repairable",
                   "repair_time_sec": 0, "comment": ""},
            "E4": {"id": "E4", "from_block": "B4", "from_port": "out",
                   "to_block": "B5", "to_port": "in", "is_back_edge": False,
                   "detail_type": "", "defect_type": "repairable",
                   "repair_time_sec": 0, "comment": ""},
        }
        return {
            "name": "simple",
            "detail_types": {"d_blank": {"label": "Z", "unit": "шт",
                                          "max_repair": 0}},
            "blocks": blocks,
            "edges": edges,
        }

    def test_n_runs_matches(self):
        """Число прогонов совпадает с запрошенным."""
        model = self._make_simple_model()
        summary = monte_carlo_run(model, max_time=1000, n_runs=5,
                                  base_seed=0)
        assert summary.n_runs == 5
        assert len(summary.all_results) == 5

    def test_deterministic_model_zero_variance(self):
        """Для детерминированной модели дисперсия = 0."""
        model = self._make_simple_model()
        summary = monte_carlo_run(model, max_time=1000, n_runs=10,
                                  base_seed=0)
        # Без стохастики (нет CONTROL, нет exponential) —
        # все прогоны одинаковые
        assert summary.std_throughput == pytest.approx(0.0)
        assert summary.std_cycle_time == pytest.approx(0.0)

    def test_all_accepted_deterministic(self):
        """Все детали приняты в каждом прогоне."""
        model = self._make_simple_model()
        summary = monte_carlo_run(model, max_time=1000, n_runs=5,
                                  base_seed=0)
        assert summary.mean_accepted == 10
        assert summary.mean_scrapped == 0

    def test_stochastic_model_has_variance(self):
        """Модель со стохастикой даёт ненулевую дисперсию."""
        model = make_mm1_model(lam=0.8, mu=1.0, n_details=100)
        summary = monte_carlo_run(model, max_time=999999,
                                  n_runs=10, base_seed=0)
        # Время цикла меняется от прогона к прогону
        assert summary.std_cycle_time > 0

    def test_ci_shrinks_with_more_runs(self):
        """Больше прогонов → уже ДИ (закон больших чисел)."""
        model = make_mm1_model(lam=0.8, mu=1.0, n_details=200)

        s10 = monte_carlo_run(model, max_time=999999,
                              n_runs=10, base_seed=0)
        s50 = monte_carlo_run(model, max_time=999999,
                              n_runs=50, base_seed=0)

        # ДИ при 50 прогонах должен быть уже, чем при 10
        assert s50.ci_throughput < s10.ci_throughput

    def test_block_utilizations_populated(self):
        """MC-сводка содержит загрузки блоков."""
        model = self._make_simple_model()
        summary = monte_carlo_run(model, max_time=1000, n_runs=3,
                                  base_seed=0)
        assert "B3" in summary.block_utilizations
        mean_u, std_u = summary.block_utilizations["B3"]
        assert mean_u > 0

    def test_buffer_avg_counts_populated(self):
        """MC-сводка содержит средние длины очередей."""
        model = self._make_simple_model()
        summary = monte_carlo_run(model, max_time=1000, n_runs=3,
                                  base_seed=0)
        assert "B2" in summary.buffer_avg_counts
