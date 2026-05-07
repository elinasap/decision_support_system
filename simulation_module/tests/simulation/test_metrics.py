"""
Тесты для MetricsCollector.
"""

import pytest
from simulation.metrics import MetricsCollector


class TestBlockMetrics:
    """Тесты отслеживания состояний блока."""

    def test_idle_time_accumulates(self):
        mc = MetricsCollector()
        mc.register_block("B1", "Станок", "process")
        # Блок простаивает с t=0 до t=100
        mc.finalize(100.0)
        result = mc.build_result(max_time=100, elapsed_time=100)
        m = result.block_metrics["B1"]
        assert m.total_idle_time == 100.0
        assert m.total_busy_time == 0.0

    def test_busy_then_idle(self):
        mc = MetricsCollector()
        mc.register_block("B1", "Станок", "process")
        mc.block_state_changed("B1", "busy", time=10.0)   # idle 0→10
        mc.block_state_changed("B1", "idle", time=25.0)    # busy 10→25
        mc.finalize(50.0)                                   # idle 25→50
        result = mc.build_result(max_time=50, elapsed_time=50)
        m = result.block_metrics["B1"]
        assert m.total_idle_time == 10.0 + 25.0  # 0-10 + 25-50
        assert m.total_busy_time == 15.0          # 10-25

    def test_blocked_time(self):
        mc = MetricsCollector()
        mc.register_block("B1", "Станок", "process")
        mc.block_state_changed("B1", "busy", time=0.0)
        mc.block_state_changed("B1", "blocked", time=10.0)
        mc.block_state_changed("B1", "idle", time=30.0)
        mc.finalize(50.0)
        result = mc.build_result(max_time=50, elapsed_time=50)
        m = result.block_metrics["B1"]
        assert m.total_busy_time == 10.0       # 0-10
        assert m.total_blocked_time == 20.0    # 10-30
        assert m.total_idle_time == 20.0       # 30-50

    def test_utilization_calculation(self):
        mc = MetricsCollector()
        mc.register_block("B1", "Станок", "process")
        mc.block_state_changed("B1", "busy", time=0.0)
        mc.block_state_changed("B1", "idle", time=50.0)
        mc.finalize(100.0)
        result = mc.build_result(max_time=100, elapsed_time=100)
        m = result.block_metrics["B1"]
        assert m.utilization == pytest.approx(0.5)

    def test_details_processed_counter(self):
        mc = MetricsCollector()
        mc.register_block("B1", "Станок", "process")
        mc.block_detail_processed("B1")
        mc.block_detail_processed("B1")
        mc.block_detail_processed("B1")
        result = mc.build_result(max_time=100, elapsed_time=100)
        assert result.block_metrics["B1"].details_processed == 3


class TestBufferMetrics:
    """Тесты отслеживания буфера."""

    def test_empty_buffer(self):
        mc = MetricsCollector()
        mc.register_buffer("B2", "Буфер", capacity=10)
        mc.finalize(100.0)
        result = mc.build_result(max_time=100, elapsed_time=100)
        m = result.buffer_metrics["B2"]
        assert m.avg_count == 0.0
        assert m.time_empty == 100.0

    def test_avg_count(self):
        mc = MetricsCollector()
        mc.register_buffer("B2", "Буфер", capacity=10)
        # 0 деталей с t=0 до t=50, потом 4 детали с t=50 до t=100
        mc.buffer_count_changed("B2", new_count=4, time=50.0)
        mc.finalize(100.0)
        result = mc.build_result(max_time=100, elapsed_time=100)
        m = result.buffer_metrics["B2"]
        # avg = (0*50 + 4*50) / 100 = 2.0
        assert m.avg_count == pytest.approx(2.0)

    def test_max_count(self):
        mc = MetricsCollector()
        mc.register_buffer("B2", "Буфер", capacity=10)
        mc.buffer_count_changed("B2", new_count=3, time=10.0)
        mc.buffer_count_changed("B2", new_count=7, time=20.0)
        mc.buffer_count_changed("B2", new_count=2, time=30.0)
        mc.finalize(50.0)
        result = mc.build_result(max_time=50, elapsed_time=50)
        assert result.buffer_metrics["B2"].max_count == 7

    def test_time_full(self):
        mc = MetricsCollector()
        mc.register_buffer("B2", "Буфер", capacity=5)
        mc.buffer_count_changed("B2", new_count=5, time=10.0)   # стал полным
        mc.buffer_count_changed("B2", new_count=3, time=30.0)   # перестал быть полным
        mc.finalize(50.0)
        result = mc.build_result(max_time=50, elapsed_time=50)
        m = result.buffer_metrics["B2"]
        assert m.time_full == 20.0       # 10-30
        assert m.full_ratio == pytest.approx(0.4)  # 20/50


class TestDetailResults:
    """Тесты результатов по деталям."""

    def test_detail_created_counter(self):
        mc = MetricsCollector()
        mc.detail_created()
        mc.detail_created()
        result = mc.build_result(max_time=100, elapsed_time=100)
        assert result.total_created == 2

    def test_detail_accepted(self):
        mc = MetricsCollector()
        mc.detail_finished(uid=1, type_id="d_blank", final_state="ACCEPTED",
                           cycle_time=50.0, repair_count=0, blocks_visited=3)
        result = mc.build_result(max_time=100, elapsed_time=100)
        assert result.total_accepted == 1
        assert result.total_scrapped == 0
        assert len(result.detail_results) == 1
        assert result.detail_results[0].cycle_time == 50.0

    def test_detail_scrapped(self):
        mc = MetricsCollector()
        mc.detail_finished(uid=1, type_id="d_blank", final_state="SCRAPPED",
                           cycle_time=20.0, repair_count=1, blocks_visited=5)
        result = mc.build_result(max_time=100, elapsed_time=100)
        assert result.total_accepted == 0
        assert result.total_scrapped == 1

    def test_defect_rate(self):
        mc = MetricsCollector()
        for i in range(8):
            mc.detail_finished(uid=i, type_id="d", final_state="ACCEPTED",
                               cycle_time=10, repair_count=0, blocks_visited=2)
        for i in range(2):
            mc.detail_finished(uid=100+i, type_id="d", final_state="SCRAPPED",
                               cycle_time=5, repair_count=0, blocks_visited=2)
        result = mc.build_result(max_time=100, elapsed_time=100)
        assert result.defect_rate == pytest.approx(0.2)  # 2/10

    def test_avg_cycle_time(self):
        mc = MetricsCollector()
        mc.detail_finished(uid=1, type_id="d", final_state="ACCEPTED",
                           cycle_time=30.0, repair_count=0, blocks_visited=2)
        mc.detail_finished(uid=2, type_id="d", final_state="ACCEPTED",
                           cycle_time=50.0, repair_count=0, blocks_visited=2)
        result = mc.build_result(max_time=100, elapsed_time=100)
        assert result.avg_cycle_time == pytest.approx(40.0)

    def test_throughput(self):
        mc = MetricsCollector()
        for i in range(10):
            mc.detail_finished(uid=i, type_id="d", final_state="ACCEPTED",
                               cycle_time=10, repair_count=0, blocks_visited=2)
        result = mc.build_result(max_time=100, elapsed_time=100)
        assert result.throughput == pytest.approx(0.1)  # 10/100


class TestEventCounter:
    """Тесты счётчика событий."""

    def test_events_counted(self):
        mc = MetricsCollector()
        mc.event_processed()
        mc.event_processed()
        mc.event_processed()
        result = mc.build_result(max_time=100, elapsed_time=100)
        assert result.total_events_processed == 3
