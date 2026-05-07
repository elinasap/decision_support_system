"""
Интеграционные тесты движка симуляции.

Каждый тест создаёт модель (как dict, аналог model.to_dict()),
запускает Simulator и проверяет результат.

Тесты идут от простого к сложному:
1. Линейная цепочка: SOURCE → BUFFER → PROCESS → BUFFER → SINK
2. С контролем качества: + CONTROL + SINK(утиль)
3. С петлёй возврата брака
4. С несколькими деталями и интервалом
5. С блокировкой (маленький downstream-буфер)
"""

import pytest
from simulation.engine import Simulator


# ══════════════════════════════════════════════════════════════
# Утилиты для создания моделей
# ══════════════════════════════════════════════════════════════

def make_block(bid, btype, label="", **params):
    """Сделать описание блока для model_dict."""
    # Автоматически определить порты по типу
    if btype == "source":
        ports = {"in": [], "out": ["out"], "used": []}
    elif btype == "buffer":
        n = int(params.get("inputs_count", 1))
        in_ports = [f"in{i+1}" for i in range(n)] if n > 1 else ["in"]
        ports = {"in": in_ports, "out": ["out"], "used": []}
    elif btype == "sink":
        ports = {"in": ["in"], "out": [], "used": []}
    elif btype == "transport":
        ports = {"in": ["in"], "out": ["out"], "used": []}
    elif btype == "process":
        out_ports = ["out"]
        if params.get("has_internal_control"):
            out_ports.append("out_defect")
        ports = {"in": ["in"], "out": out_ports, "used": []}
    elif btype == "assembly":
        n = int(params.get("inputs_count", 2))
        ports = {"in": [f"in{i+1}" for i in range(n)], "out": ["out_good"], "used": []}
    elif btype == "control":
        ports = {"in": ["in"], "out": ["out_good", "out_defect"], "used": []}
    else:
        ports = {"in": [], "out": [], "used": []}

    return {
        "id": bid,
        "type": btype,
        "label": label or bid,
        "params": params,
        "ports": ports,
    }


def make_edge(eid, from_block, from_port, to_block, to_port,
              is_back_edge=False, detail_type=""):
    """Сделать описание связи."""
    return {
        "id": eid,
        "from_block": from_block,
        "from_port": from_port,
        "to_block": to_block,
        "to_port": to_port,
        "is_back_edge": is_back_edge,
        "detail_type": detail_type,
        "defect_type": "repairable",
        "repair_time_sec": 0.0,
        "comment": "",
    }


def make_model(name, blocks, edges, detail_types=None):
    """Собрать model_dict."""
    if detail_types is None:
        detail_types = {"d_blank": {"label": "Заготовка", "unit": "шт", "max_repair": 0}}
    return {
        "name": name,
        "detail_types": detail_types,
        "blocks": {b["id"]: b for b in blocks},
        "edges": {e["id"]: e for e in edges},
    }


# ══════════════════════════════════════════════════════════════
# Тест 1: Простейшая линейная цепочка
# SOURCE → BUFFER → PROCESS → BUFFER → SINK
# 1 деталь, обработка 10 сек
# ══════════════════════════════════════════════════════════════

class TestLinearChain:
    """SOURCE → BUF1 → PROCESS → BUF2 → SINK, 1 деталь."""

    def _make_model(self, capacity=1, t_proc=10.0):
        blocks = [
            make_block("B1", "source", "Склад", capacity=capacity,
                       detail_type="d_blank"),
            make_block("B2", "buffer", "Буфер1", capacity=100),
            make_block("B3", "process", "Станок", operation_time_sec=t_proc),
            make_block("B4", "buffer", "Буфер2", capacity=100),
            make_block("B5", "sink", "Готовое"),
        ]
        edges = [
            make_edge("E1", "B1", "out", "B2", "in"),
            make_edge("E2", "B2", "out", "B3", "in"),
            make_edge("E3", "B3", "out", "B4", "in"),
            make_edge("E4", "B4", "out", "B5", "in"),
        ]
        return make_model("linear", blocks, edges)

    def test_one_detail_accepted(self):
        model = self._make_model(capacity=1, t_proc=10.0)
        sim = Simulator(model, max_time=1000, seed=42)
        result = sim.run()

        assert result.total_created == 1
        assert result.total_accepted == 1
        assert result.total_scrapped == 0
        assert result.total_in_progress == 0

    def test_one_detail_cycle_time(self):
        model = self._make_model(capacity=1, t_proc=10.0)
        sim = Simulator(model, max_time=1000, seed=42)
        result = sim.run()

        assert result.avg_cycle_time == pytest.approx(10.0)

    def test_multiple_details_sequential(self):
        """5 деталей, все сразу (interval=0), обработка 10 сек каждая."""
        model = self._make_model(capacity=5, t_proc=10.0)
        sim = Simulator(model, max_time=1000, seed=42)
        result = sim.run()

        assert result.total_created == 5
        assert result.total_accepted == 5
        assert result.total_in_progress == 0
        # Время: 5 деталей * 10 сек = 50 сек последовательно
        assert result.elapsed_model_time == pytest.approx(50.0, abs=1.0)

    def test_utilization_single_block(self):
        """Станок должен быть загружен при непрерывном потоке."""
        model = self._make_model(capacity=5, t_proc=10.0)
        sim = Simulator(model, max_time=1000, seed=42)
        result = sim.run()

        m = result.block_metrics.get("B3")
        assert m is not None
        # Станок работал 50 сек из ~50 сек → utilization ≈ 1.0
        assert m.total_busy_time == pytest.approx(50.0)


# ══════════════════════════════════════════════════════════════
# Тест 2: С интервалом между деталями
# ══════════════════════════════════════════════════════════════

class TestWithInterval:
    """SOURCE генерирует детали с интервалом."""

    def _make_model(self, capacity=3, interval=20.0, t_proc=10.0):
        blocks = [
            make_block("B1", "source", "Склад", capacity=capacity,
                       detail_type="d_blank", interval_sec=interval),
            make_block("B2", "buffer", "Буфер1", capacity=100),
            make_block("B3", "process", "Станок", operation_time_sec=t_proc),
            make_block("B4", "buffer", "Буфер2", capacity=100),
            make_block("B5", "sink", "Готовое"),
        ]
        edges = [
            make_edge("E1", "B1", "out", "B2", "in"),
            make_edge("E2", "B2", "out", "B3", "in"),
            make_edge("E3", "B3", "out", "B4", "in"),
            make_edge("E4", "B4", "out", "B5", "in"),
        ]
        return make_model("interval", blocks, edges)

    def test_details_arrive_at_intervals(self):
        """3 детали с интервалом 20 сек, обработка 10 сек."""
        model = self._make_model(capacity=3, interval=20.0, t_proc=10.0)
        sim = Simulator(model, max_time=1000, seed=42)
        result = sim.run()

        assert result.total_created == 3
        assert result.total_accepted == 3

    def test_no_queuing_when_interval_large(self):
        """Интервал > время обработки → очередь не копится."""
        model = self._make_model(capacity=3, interval=20.0, t_proc=10.0)
        sim = Simulator(model, max_time=1000, seed=42)
        result = sim.run()

        buf_m = result.buffer_metrics.get("B2")
        if buf_m is not None:
            # Буфер почти всегда пуст: деталь пришла → сразу ушла на станок
            assert buf_m.max_count <= 1


# ══════════════════════════════════════════════════════════════
# Тест 3: С контролем качества
# SOURCE → BUF1 → PROCESS → BUF2 → CONTROL → BUF3 → SINK(готовое)
#                                      ↓
#                                   SINK(утиль)
# ══════════════════════════════════════════════════════════════

class TestWithControl:
    """Линейная цепочка с контролем, без петли возврата."""

    def _make_model(self, capacity=10, threshold=0.8):
        """threshold=0.8 → ~80% проходят контроль."""
        blocks = [
            make_block("B1", "source", "Склад", capacity=capacity,
                       detail_type="d_blank"),
            make_block("B2", "buffer", "Буфер1", capacity=100),
            make_block("B3", "process", "Станок", operation_time_sec=10.0),
            make_block("B4", "buffer", "Буфер2", capacity=100),
            make_block("B5", "control", "ОТК",
                       control_time_sec=5.0, defect_prob=0.2, threshold=threshold),
            make_block("B6", "buffer", "Буфер3", capacity=100),
            make_block("B7", "sink", "Готовое"),
            make_block("B8", "sink", "Утиль"),
        ]
        edges = [
            make_edge("E1", "B1", "out", "B2", "in"),
            make_edge("E2", "B2", "out", "B3", "in"),
            make_edge("E3", "B3", "out", "B4", "in"),
            make_edge("E4", "B4", "out", "B5", "in"),
            make_edge("E5", "B5", "out_good", "B6", "in"),
            make_edge("E6", "B6", "out", "B7", "in"),
            make_edge("E7", "B5", "out_defect", "B8", "in"),
        ]
        return make_model("control", blocks, edges)

    def test_all_details_finish(self):
        """Все детали должны дойти до одного из sink."""
        model = self._make_model(capacity=10)
        sim = Simulator(model, max_time=10000, seed=42)
        result = sim.run()

        assert result.total_created == 10
        assert result.total_accepted + result.total_scrapped == 10
        assert result.total_in_progress == 0

    def test_some_defects_with_threshold_half(self):
        """threshold=0.5 → примерно 50% брака."""
        model = self._make_model(capacity=100, threshold=0.5)
        sim = Simulator(model, max_time=100000, seed=42)
        result = sim.run()

        assert result.total_created == 100
        # С threshold=0.5 примерно половина должна пройти
        assert result.total_accepted > 20
        assert result.total_scrapped > 20

    def test_threshold_one_all_pass(self):
        """threshold=1.0 → все детали проходят контроль."""
        model = self._make_model(capacity=10, threshold=1.0)
        sim = Simulator(model, max_time=10000, seed=42)
        result = sim.run()

        assert result.total_accepted == 10
        assert result.total_scrapped == 0

    def test_threshold_zero_all_fail(self):
        """threshold=0.0 → все детали бракуются."""
        model = self._make_model(capacity=10, threshold=0.0)
        sim = Simulator(model, max_time=10000, seed=42)
        result = sim.run()

        assert result.total_accepted == 0
        assert result.total_scrapped == 10


# ══════════════════════════════════════════════════════════════
# Тест 4: Блокировка (маленький downstream-буфер)
# ══════════════════════════════════════════════════════════════

class TestBlocking:
    """Downstream-буфер маленький → блок должен блокироваться."""

    def _make_model(self):
        """
        SOURCE(5 деталей) → BUF1(cap=100) → PROCESS(10 сек)
        → BUF2(cap=1) → PROCESS2(20 сек) → BUF3(cap=100) → SINK

        BUF2 вмещает только 1 деталь. PROCESS1 обрабатывает за 10 сек,
        PROCESS2 — за 20 сек. PROCESS1 будет блокироваться.
        """
        blocks = [
            make_block("B1", "source", "Склад", capacity=5,
                       detail_type="d_blank"),
            make_block("B2", "buffer", "Буфер1", capacity=100),
            make_block("B3", "process", "Станок1", operation_time_sec=10.0),
            make_block("B4", "buffer", "Буфер2", capacity=1),
            make_block("B5", "process", "Станок2", operation_time_sec=20.0),
            make_block("B6", "buffer", "Буфер3", capacity=100),
            make_block("B7", "sink", "Готовое"),
        ]
        edges = [
            make_edge("E1", "B1", "out", "B2", "in"),
            make_edge("E2", "B2", "out", "B3", "in"),
            make_edge("E3", "B3", "out", "B4", "in"),
            make_edge("E4", "B4", "out", "B5", "in"),
            make_edge("E5", "B5", "out", "B6", "in"),
            make_edge("E6", "B6", "out", "B7", "in"),
        ]
        return make_model("blocking", blocks, edges)

    def test_all_details_finish(self):
        model = self._make_model()
        sim = Simulator(model, max_time=10000, seed=42)
        result = sim.run()

        assert result.total_created == 5
        assert result.total_accepted == 5

    def test_first_block_has_blocked_time(self):
        """Станок1 должен иметь ненулевое blocked_time."""
        model = self._make_model()
        sim = Simulator(model, max_time=10000, seed=42)
        result = sim.run()

        m3 = result.block_metrics.get("B3")
        assert m3 is not None
        assert m3.total_blocked_time > 0, \
            "Станок1 должен блокироваться из-за маленького буфера"

    def test_bottleneck_is_slower_block(self):
        """Станок2 (20 сек) — узкое место, загрузка выше."""
        model = self._make_model()
        sim = Simulator(model, max_time=10000, seed=42)
        result = sim.run()

        m3 = result.block_metrics.get("B3")
        m5 = result.block_metrics.get("B5")
        assert m3 is not None and m5 is not None
        # Станок2 загружен больше (он медленнее)
        assert m5.utilization >= m3.utilization


# ══════════════════════════════════════════════════════════════
# Тест 5: Воспроизводимость (seed)
# ══════════════════════════════════════════════════════════════

class TestReproducibility:
    """Два прогона с одинаковым seed должны дать одинаковый результат."""

    def test_same_seed_same_result(self):
        blocks = [
            make_block("B1", "source", "Склад", capacity=20,
                       detail_type="d_blank"),
            make_block("B2", "buffer", "Буфер1", capacity=100),
            make_block("B3", "control", "ОТК",
                       control_time_sec=5.0, defect_prob=0.2, threshold=0.7),
            make_block("B4", "buffer", "Буфер2", capacity=100),
            make_block("B5", "sink", "Готовое"),
            make_block("B6", "sink", "Утиль"),
        ]
        edges = [
            make_edge("E1", "B1", "out", "B2", "in"),
            make_edge("E2", "B2", "out", "B3", "in"),
            make_edge("E3", "B3", "out_good", "B4", "in"),
            make_edge("E4", "B4", "out", "B5", "in"),
            make_edge("E5", "B3", "out_defect", "B6", "in"),
        ]
        model = make_model("repro", blocks, edges)

        r1 = Simulator(model, max_time=10000, seed=123).run()
        r2 = Simulator(model, max_time=10000, seed=123).run()

        assert r1.total_accepted == r2.total_accepted
        assert r1.total_scrapped == r2.total_scrapped
        assert r1.elapsed_model_time == r2.elapsed_model_time

    def test_different_seed_different_result(self):
        """С разными seed при наличии стохастики результат может отличаться."""
        blocks = [
            make_block("B1", "source", "Склад", capacity=50,
                       detail_type="d_blank"),
            make_block("B2", "buffer", "Буфер1", capacity=100),
            make_block("B3", "control", "ОТК",
                       control_time_sec=5.0, defect_prob=0.2, threshold=0.5),
            make_block("B4", "buffer", "Буфер2", capacity=100),
            make_block("B5", "sink", "Готовое"),
            make_block("B6", "sink", "Утиль"),
        ]
        edges = [
            make_edge("E1", "B1", "out", "B2", "in"),
            make_edge("E2", "B2", "out", "B3", "in"),
            make_edge("E3", "B3", "out_good", "B4", "in"),
            make_edge("E4", "B4", "out", "B5", "in"),
            make_edge("E5", "B3", "out_defect", "B6", "in"),
        ]
        model = make_model("repro2", blocks, edges)

        r1 = Simulator(model, max_time=10000, seed=1).run()
        r2 = Simulator(model, max_time=10000, seed=999).run()

        # С 50 деталями и threshold=0.5, результаты почти наверняка различаются
        # (но теоретически могут совпасть — это вероятностный тест)
        # Проверяем, что хотя бы один из показателей отличается
        differs = (r1.total_accepted != r2.total_accepted or
                   r1.total_scrapped != r2.total_scrapped)
        assert differs, "При разных seed результат должен отличаться (вероятностно)"


# ══════════════════════════════════════════════════════════════
# Тест 6: max_time ограничивает прогон
# ══════════════════════════════════════════════════════════════

class TestMaxTime:
    """Симуляция останавливается при достижении max_time."""

    def test_stops_at_max_time(self):
        blocks = [
            make_block("B1", "source", "Склад", capacity=100,
                       detail_type="d_blank", interval_sec=10.0),
            make_block("B2", "buffer", "Буфер", capacity=1000),
            make_block("B3", "process", "Станок", operation_time_sec=5.0),
            make_block("B4", "buffer", "Буфер2", capacity=1000),
            make_block("B5", "sink", "Готовое"),
        ]
        edges = [
            make_edge("E1", "B1", "out", "B2", "in"),
            make_edge("E2", "B2", "out", "B3", "in"),
            make_edge("E3", "B3", "out", "B4", "in"),
            make_edge("E4", "B4", "out", "B5", "in"),
        ]
        model = make_model("maxtime", blocks, edges)

        # max_time=50 → только 6 деталей создадутся (t=0,10,20,30,40,50)
        result = Simulator(model, max_time=50, seed=42).run()
        assert result.total_created <= 6
        assert result.elapsed_model_time <= 55.0  # 50 + время обработки последней


# ══════════════════════════════════════════════════════════════
# Тест 7: Два SOURCE (параллельные потоки)
# ══════════════════════════════════════════════════════════════

class TestMultipleSources:
    """Два SOURCE подают детали в один BUFFER."""

    def test_two_sources(self):
        blocks = [
            make_block("B1", "source", "Склад1", capacity=3,
                       detail_type="d_blank"),
            make_block("B2", "source", "Склад2", capacity=2,
                       detail_type="d_blank"),
            make_block("B3", "buffer", "Буфер", capacity=100, inputs_count=2),
            make_block("B4", "process", "Станок", operation_time_sec=10.0),
            make_block("B5", "buffer", "Буфер2", capacity=100),
            make_block("B6", "sink", "Готовое"),
        ]
        edges = [
            make_edge("E1", "B1", "out", "B3", "in1"),
            make_edge("E2", "B2", "out", "B3", "in2"),
            make_edge("E3", "B3", "out", "B4", "in"),
            make_edge("E4", "B4", "out", "B5", "in"),
            make_edge("E5", "B5", "out", "B6", "in"),
        ]
        model = make_model("multi_source", blocks, edges)

        result = Simulator(model, max_time=10000, seed=42).run()
        assert result.total_created == 5  # 3 + 2
        assert result.total_accepted == 5
