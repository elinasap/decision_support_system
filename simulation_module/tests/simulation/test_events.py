"""
Тесты для EventQueue и SimEvent.
"""

import pytest
from simulation.events import EventQueue, EventType, SimEvent


class TestSimEvent:
    """Тесты сортировки событий."""

    def test_events_ordered_by_time(self):
        e1 = SimEvent(time=5.0, event_type=EventType.DETAIL_CREATED, _seq=0)
        e2 = SimEvent(time=3.0, event_type=EventType.DETAIL_CREATED, _seq=1)
        assert e2 < e1

    def test_same_time_ordered_by_seq(self):
        e1 = SimEvent(time=5.0, event_type=EventType.DETAIL_CREATED, _seq=0)
        e2 = SimEvent(time=5.0, event_type=EventType.SERVICE_FINISHED, _seq=1)
        assert e1 < e2

    def test_equal_events(self):
        e1 = SimEvent(time=5.0, event_type=EventType.DETAIL_CREATED, _seq=0)
        e2 = SimEvent(time=5.0, event_type=EventType.DETAIL_CREATED, _seq=0)
        assert not (e1 < e2)
        assert not (e2 < e1)


class TestEventQueue:
    """Тесты очереди событий."""

    def test_empty_queue(self):
        q = EventQueue()
        assert q.is_empty
        assert len(q) == 0

    def test_schedule_and_pop(self):
        q = EventQueue()
        q.schedule(time=10.0, event_type=EventType.DETAIL_CREATED, block_id="B1")
        assert not q.is_empty
        assert len(q) == 1

        event = q.pop()
        assert event.time == 10.0
        assert event.event_type == EventType.DETAIL_CREATED
        assert event.block_id == "B1"
        assert q.is_empty

    def test_pop_returns_earliest_event(self):
        q = EventQueue()
        q.schedule(time=20.0, event_type=EventType.SERVICE_FINISHED, block_id="B2")
        q.schedule(time=5.0, event_type=EventType.DETAIL_CREATED, block_id="B1")
        q.schedule(time=15.0, event_type=EventType.SERVICE_STARTED, block_id="B3")

        e1 = q.pop()
        e2 = q.pop()
        e3 = q.pop()

        assert e1.time == 5.0
        assert e2.time == 15.0
        assert e3.time == 20.0

    def test_same_time_fifo_order(self):
        q = EventQueue()
        q.schedule(time=10.0, event_type=EventType.DETAIL_CREATED, block_id="first")
        q.schedule(time=10.0, event_type=EventType.SERVICE_STARTED, block_id="second")
        q.schedule(time=10.0, event_type=EventType.SERVICE_FINISHED, block_id="third")

        e1 = q.pop()
        e2 = q.pop()
        e3 = q.pop()

        assert e1.block_id == "first"
        assert e2.block_id == "second"
        assert e3.block_id == "third"

    def test_peek_does_not_remove(self):
        q = EventQueue()
        q.schedule(time=5.0, event_type=EventType.DETAIL_CREATED)
        peeked = q.peek()
        assert peeked.time == 5.0
        assert len(q) == 1

    def test_pop_empty_raises(self):
        q = EventQueue()
        with pytest.raises(IndexError):
            q.pop()

    def test_peek_empty_raises(self):
        q = EventQueue()
        with pytest.raises(IndexError):
            q.peek()

    def test_clear(self):
        q = EventQueue()
        q.schedule(time=1.0, event_type=EventType.DETAIL_CREATED)
        q.schedule(time=2.0, event_type=EventType.DETAIL_CREATED)
        q.clear()
        assert q.is_empty
        assert len(q) == 0

    def test_schedule_returns_event(self):
        q = EventQueue()
        event = q.schedule(
            time=10.0,
            event_type=EventType.SERVICE_FINISHED,
            block_id="B5",
            detail_uid=42,
            data={"foo": "bar"},
        )
        assert event.time == 10.0
        assert event.block_id == "B5"
        assert event.detail_uid == 42
        assert event.data == {"foo": "bar"}

    def test_many_events_stress(self):
        """100 событий в случайном порядке должны извлекаться отсортированно."""
        import random
        q = EventQueue()
        rng = random.Random(123)
        times = [rng.uniform(0, 1000) for _ in range(100)]
        for t in times:
            q.schedule(time=t, event_type=EventType.DETAIL_CREATED)

        extracted = []
        while not q.is_empty:
            extracted.append(q.pop().time)

        assert extracted == sorted(extracted)
