"""
Движок дискретно-событийного моделирования (DES).

Simulator — главный цикл симуляции. Связывает воедино:
- модель (model.Model) — статическая конфигурация блоков и связей
- автоматы (automata/) — правила поведения
- runtime-состояния (*_state.py) — динамические данные
- очередь событий (events.py) — расписание
- сборщик метрик (metrics.py) — статистика

Алгоритм:
1. Инициализация: создать runtime-объекты для всех блоков и буферов
2. Породить начальные события (детали из SOURCE)
3. Главный цикл:
   a. Достать из кучи событие с минимальным временем
   b. Передвинуть модельные часы
   c. Обработать событие (дёрнуть автоматы, изменить состояние)
   d. Запланировать порождённые события
4. Финализация: собрать метрики в SimulationResult

Архитектурное решение: движок работает с model.Model напрямую,
без промежуточного JSON. JSON остаётся интерфейсом между шагом 1
(GUI) и шагом 3 (оптимизатор), но симулятор — часть шага 2 и
работает с живыми объектами.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

# Модель
import sys
from pathlib import Path

# Автоматы
from simulation.automata.phase import PhaseAutomaton, Phase, PhaseEvent
from simulation.automata.block import BlockAutomaton, BlockState, BlockEvent
from simulation.automata.buffer import BufferAutomaton, BufferStateEnum, BufferEvent
from simulation.automata.quality import (
    QualityAutomaton, QualityState, QualityEvent, QualityCheckContext,
)

# Runtime-состояния
from simulation.detail_instance import DetailInstance, DetailQualityState
from simulation.buffer_state import BufferState
from simulation.block_operation_state import BlockOperationState

# Очередь событий и метрики
from simulation.events import EventQueue, EventType, SimEvent
from simulation.metrics import MetricsCollector
from simulation.result import SimulationResult


# ──────────────────────────────────────────────────────────────
# Runtime-обёртки: связывают модельный блок с автоматом и состоянием
# ──────────────────────────────────────────────────────────────

@dataclass
class BufferRuntime:
    """Буфер в runtime: автомат + физическое состояние."""
    block_id: str
    state: BufferState
    automaton: BufferAutomaton = field(default_factory=BufferAutomaton)


@dataclass
class OperationRuntime:
    """Блок техоперации в runtime: автомат + физическое состояние."""
    block_id: str
    block_type: str                    # process / assembly / control / transport
    op_state: BlockOperationState
    automaton: BlockAutomaton = field(default_factory=BlockAutomaton)
    # Параметры из модели (копируются при инициализации)
    service_time: float = 0.0
    service_mode: str = "fixed"        # "fixed" или "exponential"
    defect_prob: float = 0.0           # только для CONTROL
    threshold: float = 0.0             # только для CONTROL
    has_internal_control: bool = False  # только для PROCESS


@dataclass
class DetailRuntime:
    """Деталь в runtime: экземпляр + автомат фазы + автомат качества."""
    instance: DetailInstance
    phase: PhaseAutomaton = field(default_factory=PhaseAutomaton)
    quality: QualityAutomaton = field(default_factory=QualityAutomaton)


# ──────────────────────────────────────────────────────────────
# Симулятор
# ──────────────────────────────────────────────────────────────

class Simulator:
    """
    Главный движок DES-симуляции.

    Использование:
        from model.model import Model
        model = Model.from_dict(json_data)
        sim = Simulator(model, max_time=10000, seed=42)
        result = sim.run()
    """

    def __init__(self, model_dict: dict, max_time: float = 10000.0,
                 seed: Optional[int] = None):
        """
        model_dict — словарь из model.to_dict() (JSON-совместимый).
                     Принимаем dict, а не Model, чтобы simulation/ не зависел
                     от model/ на уровне импорта — модули лежат в разных
                     частях проекта.
        max_time   — максимальное модельное время (секунды).
        seed       — seed для генератора случайных чисел (воспроизводимость).
        """
        self._model = model_dict
        self._max_time = max_time
        self._seed = seed
        self._rng = random.Random(seed)

        # Модельное время
        self._clock: float = 0.0

        # Очередь событий
        self._queue = EventQueue()

        # Сборщик метрик
        self._metrics = MetricsCollector()

        # Runtime-объекты (заполняются в _initialize)
        self._buffers: dict[str, BufferRuntime] = {}
        self._operations: dict[str, OperationRuntime] = {}
        self._details: dict[int, DetailRuntime] = {}
        self._detail_counter: int = 0

        # Маппинг: block_id → список исходящих связей
        self._outgoing: dict[str, list[dict]] = {}
        # Маппинг: block_id → список входящих связей
        self._incoming: dict[str, list[dict]] = {}

        # SOURCE-блоки: (block_id, detail_type, capacity, interval_sec)
        self._sources: list[dict] = []

        # SINK-блоки: множество id
        self._sinks: set[str] = set()
        # sink для готовой продукции vs утиля (определяется по входящим связям)
        self._product_sinks: set[str] = set()
        self._scrap_sinks: set[str] = set()

        # detail_types из модели (для max_repair и т.п.)
        self._detail_types: dict[str, dict] = {}

        # Детали, ожидающие входа в буфер: buf_id → [(uid, type_id, source_id)]
        # Заполняется когда SOURCE пытается поместить деталь в полный буфер.
        self._pending_arrivals: dict[str, list[tuple[int, str, str]]] = {}

    # ══════════════════════════════════════════════════════════
    # Публичный API
    # ══════════════════════════════════════════════════════════

    def run(self) -> SimulationResult:
        """
        Запустить симуляцию. Возвращает SimulationResult.

        Шаги:
        1. Инициализация runtime-объектов
        2. Планирование начальных событий (детали из SOURCE)
        3. Главный цикл обработки событий
        4. Финализация метрик
        """
        self._initialize()
        self._schedule_initial_events()
        self._main_loop()
        return self._finalize()

    # ══════════════════════════════════════════════════════════
    # Инициализация
    # ══════════════════════════════════════════════════════════

    def _initialize(self) -> None:
        """Создать runtime-объекты для всех блоков модели."""
        blocks = self._model["blocks"]
        edges = self._model["edges"]
        self._detail_types = self._model.get("detail_types", {})

        # Построить маппинги связей
        for edge in edges.values():
            from_id = edge["from_block"]
            to_id = edge["to_block"]
            self._outgoing.setdefault(from_id, []).append(edge)
            self._incoming.setdefault(to_id, []).append(edge)

        # Создать runtime-объекты для каждого блока
        # ПРОХОД 1: SOURCE, BUFFER, SINK — они не зависят от других блоков
        for bid, bdata in blocks.items():
            btype = bdata["type"]
            params = bdata["params"]
            label = bdata.get("label", bid)

            if btype == "source":
                self._sources.append({
                    "block_id": bid,
                    "detail_type": params.get("detail_type", ""),
                    "capacity": int(params.get("capacity", 10)),
                    "interval_sec": float(params.get("interval_sec", 0)),
                    "arrival_mode": params.get("arrival_mode", "fixed"),
                })

            elif btype == "buffer":
                capacity = int(params.get("capacity", 100))
                buf_state = BufferState(block_id=bid, capacity=capacity)
                self._buffers[bid] = BufferRuntime(
                    block_id=bid,
                    state=buf_state,
                )
                self._metrics.register_buffer(bid, label, capacity)

            elif btype == "sink":
                self._sinks.add(bid)

        # ПРОХОД 2: PROCESS, ASSEMBLY, CONTROL, TRANSPORT —
        # им нужны ссылки на уже созданные буферы
        for bid, bdata in blocks.items():
            btype = bdata["type"]
            params = bdata["params"]
            label = bdata.get("label", bid)

            if btype in ("process", "assembly", "control", "transport"):
                # Определить время обработки
                if btype == "process":
                    stime = float(params.get("operation_time_sec",
                                  params.get("t_proc", 0)))
                elif btype == "assembly":
                    stime = float(params.get("assembly_time_sec",
                                  params.get("t_asm", 0)))
                elif btype == "control":
                    stime = float(params.get("control_time_sec",
                                  params.get("t_ctrl", 0)))
                elif btype == "transport":
                    stime = float(params.get("transport_time_sec",
                                  params.get("t_trans", 0)))
                else:
                    stime = 0

                # Найти upstream и downstream буферы
                upstream_bufs = self._find_upstream_buffers(bid)
                downstream_buf = self._find_downstream_buffer(bid)

                if downstream_buf is None:
                    # Если downstream — не буфер (ТО→ТО или ТО→SINK),
                    # создаём виртуальный буфер с бесконечной ёмкостью.
                    vbuf_id = f"_vbuf_{bid}"
                    vbuf_state = BufferState(block_id=vbuf_id, capacity=999999)
                    self._buffers[vbuf_id] = BufferRuntime(
                        block_id=vbuf_id, state=vbuf_state)
                    downstream_buf = self._buffers[vbuf_id]

                    # 1. Синтетическое ребро bid → vbuf_id:
                    #    _find_normal_target(bid) найдёт виртуальный буфер
                    #    как правомерную цель.
                    syn = {"from_block": bid, "from_port": "out",
                           "to_block": vbuf_id, "to_port": "in",
                           "is_back_edge": False}
                    self._outgoing.setdefault(bid, []).insert(0, syn)
                    self._incoming.setdefault(vbuf_id, []).append(syn)

                    # 2. Исходящие рёбра bid копируем на vbuf_id:
                    #    _try_start_downstream(vbuf_id) найдёт следующий блок,
                    #    _drain_buffer_to_sinks(vbuf_id) найдёт SINK.
                    for edge in list(self._outgoing.get(bid, []))[1:]:
                        virt = dict(edge, from_block=vbuf_id)
                        self._outgoing.setdefault(vbuf_id, []).append(virt)
                        self._incoming.setdefault(edge["to_block"], []).append(virt)

                op_state = BlockOperationState(
                    block_id=bid,
                    upstream_buffers=[b.state for b in upstream_bufs],
                    downstream_buffer=downstream_buf.state,
                    service_time=stime,
                )

                op_runtime = OperationRuntime(
                    block_id=bid,
                    block_type=btype,
                    op_state=op_state,
                    service_time=stime,
                    service_mode=params.get("service_mode", "fixed"),
                    defect_prob=float(params.get("defect_prob", 0)),
                    threshold=float(params.get("threshold", 0)),
                    has_internal_control=bool(params.get(
                        "has_internal_control", False)),
                )
                self._operations[bid] = op_runtime
                self._metrics.register_block(bid, label, btype)

        # Классифицировать SINK: product vs scrap
        self._classify_sinks()

    def _find_upstream_buffers(self, block_id: str) -> list[BufferRuntime]:
        """Найти буферы, подающие детали в данный блок."""
        result = []
        for edge in self._incoming.get(block_id, []):
            from_id = edge["from_block"]
            if from_id in self._buffers:
                result.append(self._buffers[from_id])
        return result if result else []

    def _find_downstream_buffer(self, block_id: str) -> Optional[BufferRuntime]:
        """Найти основной downstream-буфер (через out или out_good)."""
        for edge in self._outgoing.get(block_id, []):
            port = edge["from_port"]
            # Основной выход — out, out_good, out1 (не out_defect)
            if port in ("out", "out_good", "out1") or not port.startswith("out_defect"):
                to_id = edge["to_block"]
                if to_id in self._buffers:
                    return self._buffers[to_id]
        # Если ничего не нашли по основному порту, берём первый попавшийся буфер
        for edge in self._outgoing.get(block_id, []):
            to_id = edge["to_block"]
            if to_id in self._buffers:
                return self._buffers[to_id]
        return None

    def _classify_sinks(self) -> None:
        """
        Определить, какие SINK принимают готовую продукцию, а какие — брак.
        Логика: если в SINK ведёт связь из порта out_defect — это scrap_sink.
        Остальные — product_sink.
        """
        for sink_id in self._sinks:
            is_scrap = False
            for edge in self._incoming.get(sink_id, []):
                if edge["from_port"] == "out_defect":
                    is_scrap = True
                    break
            if is_scrap:
                self._scrap_sinks.add(sink_id)
            else:
                self._product_sinks.add(sink_id)

    # ══════════════════════════════════════════════════════════
    # Планирование начальных событий
    # ══════════════════════════════════════════════════════════

    def _schedule_initial_events(self) -> None:
        """Создать детали из SOURCE и запланировать их поступление."""
        for src in self._sources:
            capacity = src["capacity"]
            interval = src["interval_sec"]
            block_id = src["block_id"]
            detail_type = src["detail_type"]
            # Режим генерации: "fixed" (по умолчанию) или "exponential" (для M/M/1)
            arrival_mode = src.get("arrival_mode", "fixed")

            t = 0.0
            for i in range(capacity):
                if i > 0:
                    if interval <= 0:
                        t = 0.0  # все сразу
                    elif arrival_mode == "exponential":
                        # Экспоненциальный интервал: среднее = interval
                        t += self._rng.expovariate(1.0 / interval)
                    else:
                        t += interval  # фиксированный интервал

                if t > self._max_time:
                    break

                self._detail_counter += 1
                uid = self._detail_counter

                self._queue.schedule(
                    time=t,
                    event_type=EventType.DETAIL_CREATED,
                    block_id=block_id,
                    detail_uid=uid,
                    data={"type_id": detail_type},
                )

    # ══════════════════════════════════════════════════════════
    # Главный цикл
    # ══════════════════════════════════════════════════════════

    def _main_loop(self) -> None:
        """Обрабатывать события, пока очередь не пуста или не кончилось время."""
        while not self._queue.is_empty:
            event = self._queue.pop()

            if event.time > self._max_time:
                break

            self._clock = event.time
            self._metrics.event_processed()

            # Диспетчеризация по типу события
            if event.event_type == EventType.DETAIL_CREATED:
                self._handle_detail_created(event)
            elif event.event_type == EventType.SERVICE_STARTED:
                self._handle_service_started(event)
            elif event.event_type == EventType.SERVICE_FINISHED:
                self._handle_service_finished(event)
            elif event.event_type == EventType.DETAIL_DEPARTED:
                self._handle_detail_departed(event)
            elif event.event_type == EventType.UNBLOCK_CHECK:
                self._handle_unblock_check(event)

    # ══════════════════════════════════════════════════════════
    # Обработчики событий
    # ══════════════════════════════════════════════════════════

    def _handle_detail_created(self, event: SimEvent) -> None:
        """
        Деталь порождена из SOURCE.

        Действия:
        1. Найти первый буфер после SOURCE
        2. Если буфер полон — встать в очередь ожидания (_pending_arrivals)
        3. Иначе — создать DetailRuntime, положить в буфер, будить downstream
        """
        uid = event.detail_uid
        type_id = event.data["type_id"]
        source_id = event.block_id

        # Найти буфер после SOURCE
        target_buf = self._find_first_buffer_after(source_id)
        if target_buf is None:
            return  # некуда класть деталь (ошибка конфигурации)

        # Буфер полон — встаём в очередь; деталь войдёт когда освободится место
        if target_buf.state.is_full:
            self._pending_arrivals.setdefault(target_buf.block_id, []).append(
                (uid, type_id, source_id)
            )
            return

        self._admit_detail(uid, type_id, target_buf)

    def _admit_detail(self, uid: int, type_id: str,
                      target_buf: "BufferRuntime") -> None:
        """Создать DetailRuntime и положить деталь в буфер."""
        instance = DetailInstance(uid=uid, type_id=type_id, created_at=self._clock)
        detail_rt = DetailRuntime(instance=instance)
        self._details[uid] = detail_rt
        self._metrics.detail_created()

        self._push_to_buffer(target_buf, detail_rt, self._clock)
        self._try_start_downstream(target_buf.block_id)

    def _handle_service_started(self, event: SimEvent) -> None:
        """
        Блок техоперации начинает обработку детали.

        Действия:
        1. Забрать деталь из upstream-буфера
        2. Автомат блока: IDLE → BUSY
        3. Автомат фазы детали: WAITING → PROCESSING
        4. Запланировать SERVICE_FINISHED через service_time
        """
        block_id = event.block_id
        op = self._operations.get(block_id)
        if op is None:
            return

        # Проверить: блок должен быть IDLE и в upstream должна быть деталь
        if op.automaton.state != BlockState.IDLE:
            return
        if not op.op_state.has_upstream_detail:
            return

        # Для ASSEMBLY: нужны детали во ВСЕХ upstream-буферах
        if op.block_type == "assembly":
            if not op.op_state.all_upstream_have_details:
                return

        # Забрать деталь из upstream-буфера
        detail_rt = self._take_detail_from_upstream(op)
        if detail_rt is None:
            return

        # Автомат блока: IDLE → BUSY
        op.automaton.fire(BlockEvent.BUFFER_HAS_DETAIL, op.op_state)
        self._metrics.block_state_changed(block_id, "busy", self._clock)

        # Автомат фазы: WAITING → PROCESSING
        detail_rt.phase.fire(PhaseEvent.START_SERVICE)

        # Записать вход детали в блок
        detail_rt.instance.enter_block(block_id, self._clock)

        # Запланировать окончание обработки
        actual_service_time = op.service_time
        if op.service_mode == "exponential" and op.service_time > 0:
            actual_service_time = self._rng.expovariate(1.0 / op.service_time)
        finish_time = self._clock + actual_service_time
        self._queue.schedule(
            time=finish_time,
            event_type=EventType.SERVICE_FINISHED,
            block_id=block_id,
            detail_uid=detail_rt.instance.uid,
        )

    def _handle_service_finished(self, event: SimEvent) -> None:
        """
        Блок техоперации завершил обработку.

        Действия:
        1. Автомат фазы: PROCESSING → DONE
        2. Если блок CONTROL — определить годность (автомат качества)
        3. Определить выходной порт (out_good / out_defect)
        4. Попробовать передать деталь в downstream
        5. Если downstream полон — автомат блока → BLOCKED
        """
        block_id = event.block_id
        op = self._operations.get(block_id)
        if op is None:
            return

        uid = event.detail_uid
        detail_rt = self._details.get(uid)
        if detail_rt is None:
            return

        # Автомат фазы: PROCESSING → DONE
        detail_rt.phase.fire(PhaseEvent.SERVICE_COMPLETE)

        # Записать выход из блока
        detail_rt.instance.leave_block(self._clock)
        self._metrics.block_detail_processed(block_id)

        # Если CONTROL — проверить качество
        if op.block_type == "control":
            self._perform_quality_check(op, detail_rt)

        # Если PROCESS с внутренним контролем — тоже проверить
        if op.block_type == "process" and op.has_internal_control:
            self._perform_quality_check(op, detail_rt)

        # Определить куда отправлять деталь
        is_defective = (detail_rt.instance.quality_state ==
                        DetailQualityState.DEFECTIVE)

        if is_defective:
            # Искать путь через out_defect
            target = self._find_defect_target(block_id)
        else:
            # Основной путь: через out / out_good
            target = self._find_normal_target(block_id)

        if target is None:
            # Некуда отправить деталь — блокируемся
            self._block_operation(op)
            return

        # Попробовать передать деталь
        if target["type"] == "buffer":
            buf = self._buffers[target["id"]]
            if buf.state.is_full:
                self._block_operation(op)
            else:
                self._depart_detail(op, detail_rt, buf)
                self._try_start_downstream(buf.block_id)
                self._try_start_next_on_block(op)
        elif target["type"] == "sink":
            self._deliver_to_sink(detail_rt, target["id"])
            # Блок свободен — автомат → IDLE
            op.automaton.fire(BlockEvent.SERVICE_FINISHED, op.op_state)
            self._metrics.block_state_changed(block_id, "idle", self._clock)
            op.op_state.current_detail = None
            op.op_state.service_start_time = None
            self._try_start_next_on_block(op)
        else:
            self._block_operation(op)

    def _handle_detail_departed(self, event: SimEvent) -> None:
        """
        Деталь передана в буфер (отложенная передача после разблокировки).
        """
        # В текущей реализации используется только для цепочечного
        # пробуждения заблокированных блоков — обрабатывается через
        # UNBLOCK_CHECK
        pass

    def _handle_unblock_check(self, event: SimEvent) -> None:
        """
        Проверить: можно ли разблокировать блок (downstream освободился).

        Это событие планируется, когда из downstream-буфера забирают деталь —
        возможно, upstream-блок ждал именно этого.
        """
        block_id = event.block_id
        op = self._operations.get(block_id)
        if op is None:
            return

        if op.automaton.state != BlockState.BLOCKED:
            return

        # Проверяем: деталь ещё в блоке (не пропала по ошибке)
        detail_rt = None
        if op.op_state.current_detail is not None:
            uid = op.op_state.current_detail.uid if hasattr(
                op.op_state.current_detail, 'uid') else None
            if uid is not None:
                detail_rt = self._details.get(uid)

        if detail_rt is None:
            return

        # Определить куда отправлять
        is_defective = (detail_rt.instance.quality_state ==
                        DetailQualityState.DEFECTIVE)

        if is_defective:
            target = self._find_defect_target(block_id)
        else:
            target = self._find_normal_target(block_id)

        if target is None:
            return

        if target["type"] == "buffer":
            buf = self._buffers[target["id"]]
            if buf.state.is_full:
                return  # всё ещё полон

            # Разблокировка!
            op.automaton.fire(BlockEvent.DOWNSTREAM_FREE, op.op_state)
            self._metrics.block_state_changed(block_id, "idle", self._clock)

            self._depart_detail(op, detail_rt, buf)
            self._try_start_downstream(buf.block_id)
            self._try_start_next_on_block(op)

        elif target["type"] == "sink":
            op.automaton.fire(BlockEvent.DOWNSTREAM_FREE, op.op_state)
            self._metrics.block_state_changed(block_id, "idle", self._clock)

            self._deliver_to_sink(detail_rt, target["id"])
            op.op_state.current_detail = None
            op.op_state.service_start_time = None
            self._try_start_next_on_block(op)

    # ══════════════════════════════════════════════════════════
    # Вспомогательные методы
    # ══════════════════════════════════════════════════════════

    def _push_to_buffer(self, buf_rt: BufferRuntime, detail_rt: DetailRuntime,
                        time: float) -> None:
        """Положить деталь в буфер и обновить автомат."""
        buf_rt.automaton.fire(BufferEvent.DETAIL_IN, buf_rt.state)
        buf_rt.state.push(detail_rt.instance)
        self._metrics.buffer_count_changed(
            buf_rt.block_id, buf_rt.state.count, time)

        # Если после буфера стоит SINK — сразу сливаем
        self._drain_buffer_to_sinks(buf_rt)

    def _pop_from_buffer(self, buf_rt: BufferRuntime,
                         time: float) -> DetailInstance:
        """Забрать деталь из буфера и обновить автомат."""
        buf_rt.automaton.fire(BufferEvent.DETAIL_OUT, buf_rt.state)
        detail = buf_rt.state.pop()
        self._metrics.buffer_count_changed(
            buf_rt.block_id, buf_rt.state.count, time)

        # Если буфер освободил место — разбудить upstream-блок
        self._notify_upstream_unblock(buf_rt.block_id)

        # Впустить следующую деталь из очереди SOURCE (если есть)
        self._admit_pending(buf_rt)

        return detail

    def _admit_pending(self, buf_rt: "BufferRuntime") -> None:
        """Если есть детали, ожидающие входа в этот буфер, впустить одну."""
        pending = self._pending_arrivals.get(buf_rt.block_id)
        if not pending or buf_rt.state.is_full:
            return
        uid, type_id, _source_id = pending.pop(0)
        self._admit_detail(uid, type_id, buf_rt)

    def _drain_buffer_to_sinks(self, buf_rt: BufferRuntime) -> None:
        """
        Если после буфера стоит SINK (а не блок техоперации),
        автоматически переместить все детали из буфера в SINK.

        Это нужно потому, что SINK не имеет автомата и не «забирает»
        детали сам. Буфер перед SINK — это последняя остановка.
        """
        # Найти SINK после этого буфера
        sink_id = None
        for edge in self._outgoing.get(buf_rt.block_id, []):
            to_id = edge["to_block"]
            if to_id in self._sinks:
                sink_id = to_id
                break

        if sink_id is None:
            return  # после буфера не SINK, а блок техоперации

        # Сливаем все детали из буфера в SINK
        while not buf_rt.state.is_empty:
            instance = self._pop_from_buffer(buf_rt, self._clock)
            detail_rt = self._details.get(instance.uid)
            if detail_rt is not None:
                self._deliver_to_sink(detail_rt, sink_id)

    def _take_detail_from_upstream(self, op: OperationRuntime
                                   ) -> Optional[DetailRuntime]:
        """Забрать деталь из upstream-буфера блока техоперации."""
        for i, buf_state in enumerate(op.op_state.upstream_buffers):
            buf_rt = self._buffers.get(buf_state.block_id)
            if buf_rt is not None and not buf_rt.state.is_empty:
                instance = self._pop_from_buffer(buf_rt, self._clock)
                op.op_state.current_detail = instance
                op.op_state.service_start_time = self._clock
                return self._details.get(instance.uid)
        return None

    def _depart_detail(self, op: OperationRuntime, detail_rt: DetailRuntime,
                       target_buf: BufferRuntime) -> None:
        """Передать деталь из блока в downstream-буфер."""
        # Автомат блока: BUSY → IDLE (downstream свободен)
        if op.automaton.state == BlockState.BUSY:
            op.automaton.fire(BlockEvent.SERVICE_FINISHED, op.op_state)
            self._metrics.block_state_changed(op.block_id, "idle", self._clock)

        # Автомат фазы: DONE → WAITING
        if detail_rt.phase.state == Phase.DONE:
            detail_rt.phase.fire(PhaseEvent.DEPART)

        # Физически переместить деталь
        op.op_state.current_detail = None
        op.op_state.service_start_time = None
        self._push_to_buffer(target_buf, detail_rt, self._clock)

    def _block_operation(self, op: OperationRuntime) -> None:
        """Заблокировать блок (downstream полон)."""
        if op.automaton.state == BlockState.BUSY:
            op.automaton.fire(BlockEvent.SERVICE_FINISHED, op.op_state)
            self._metrics.block_state_changed(
                op.block_id, "blocked", self._clock)

    def _deliver_to_sink(self, detail_rt: DetailRuntime,
                         sink_id: str) -> None:
        """Доставить деталь в SINK (финиш маршрута)."""
        instance = detail_rt.instance

        # Определить тип sink
        if sink_id in self._product_sinks:
            # Автомат качества: → ACCEPTED
            if detail_rt.quality.state not in (
                    QualityState.ACCEPTED, QualityState.SCRAPPED):
                ctx = QualityCheckContext(
                    detail=instance,
                    detail_types=self._detail_types,
                )
                detail_rt.quality.fire(QualityEvent.ENTER_PRODUCT_SINK, ctx)

            final_state = "ACCEPTED"
        else:
            # Автомат качества: → SCRAPPED
            if detail_rt.quality.state not in (
                    QualityState.ACCEPTED, QualityState.SCRAPPED):
                ctx = QualityCheckContext(
                    detail=instance,
                    detail_types=self._detail_types,
                )
                detail_rt.quality.fire(QualityEvent.ENTER_SCRAP_SINK, ctx)

            final_state = "SCRAPPED"

        # Автомат фазы: DONE → WAITING (формально завершить цикл)
        if detail_rt.phase.state == Phase.DONE:
            detail_rt.phase.fire(PhaseEvent.DEPART)

        # Зафиксировать метрики
        cycle_time = instance.total_time_in_system(self._clock)
        self._metrics.detail_finished(
            uid=instance.uid,
            type_id=instance.type_id,
            final_state=final_state,
            cycle_time=cycle_time,
            repair_count=instance.repair_count,
            blocks_visited=len(instance.history),
        )

    def _perform_quality_check(self, op: OperationRuntime,
                               detail_rt: DetailRuntime) -> None:
        """
        Выполнить контроль качества.
        Генерирует случайное число и сравнивает с threshold.
        """
        r = self._rng.random()
        ctx = QualityCheckContext(
            detail=detail_rt.instance,
            detail_types=self._detail_types,
        )

        if r <= op.threshold:
            # Контроль пройден
            detail_rt.quality.fire(QualityEvent.CONTROL_PASSED, ctx)
        else:
            # Контроль не пройден — брак
            detail_rt.quality.fire(QualityEvent.CONTROL_FAILED, ctx)
            detail_rt.instance.quality_state = DetailQualityState.DEFECTIVE

    def _try_start_downstream(self, buffer_id: str) -> None:
        """
        Попробовать запустить блок, стоящий после данного буфера.
        Вызывается когда в буфер положили деталь.
        """
        for edge in self._outgoing.get(buffer_id, []):
            to_id = edge["to_block"]
            op = self._operations.get(to_id)
            if op is not None and op.automaton.state == BlockState.IDLE:
                if op.op_state.has_upstream_detail:
                    # Для ASSEMBLY: нужны все входы
                    if op.block_type == "assembly":
                        if not op.op_state.all_upstream_have_details:
                            continue
                    self._queue.schedule(
                        time=self._clock,
                        event_type=EventType.SERVICE_STARTED,
                        block_id=to_id,
                    )
                    return  # Один блок — одно пробуждение

    def _try_start_next_on_block(self, op: OperationRuntime) -> None:
        """
        Попробовать начать обработку следующей детали на этом же блоке.
        Вызывается когда блок освободился (отдал деталь).
        """
        if op.automaton.state == BlockState.IDLE and op.op_state.has_upstream_detail:
            if op.block_type == "assembly":
                if not op.op_state.all_upstream_have_details:
                    return
            self._queue.schedule(
                time=self._clock,
                event_type=EventType.SERVICE_STARTED,
                block_id=op.block_id,
            )

    def _notify_upstream_unblock(self, buffer_id: str) -> None:
        """
        Уведомить upstream-блок о том, что в буфере освободилось место.
        Если upstream-блок в состоянии BLOCKED — запланировать проверку.
        """
        for edge in self._incoming.get(buffer_id, []):
            from_id = edge["from_block"]
            op = self._operations.get(from_id)
            if op is not None and op.automaton.state == BlockState.BLOCKED:
                self._queue.schedule(
                    time=self._clock,
                    event_type=EventType.UNBLOCK_CHECK,
                    block_id=from_id,
                )

    def _find_first_buffer_after(self, source_id: str
                                 ) -> Optional[BufferRuntime]:
        """Найти первый буфер после SOURCE."""
        for edge in self._outgoing.get(source_id, []):
            to_id = edge["to_block"]
            if to_id in self._buffers:
                return self._buffers[to_id]
        return None

    def _find_normal_target(self, block_id: str
                            ) -> Optional[dict]:
        """Найти цель для нормальной (не бракованной) детали."""
        for edge in self._outgoing.get(block_id, []):
            port = edge["from_port"]
            if port == "out_defect":
                continue
            to_id = edge["to_block"]
            if to_id in self._buffers:
                return {"type": "buffer", "id": to_id}
            if to_id in self._sinks:
                return {"type": "sink", "id": to_id}
        return None

    def _find_defect_target(self, block_id: str
                            ) -> Optional[dict]:
        """Найти цель для бракованной детали (через out_defect)."""
        for edge in self._outgoing.get(block_id, []):
            port = edge["from_port"]
            if port == "out_defect":
                to_id = edge["to_block"]
                if to_id in self._buffers:
                    return {"type": "buffer", "id": to_id}
                if to_id in self._sinks:
                    return {"type": "sink", "id": to_id}
        # Если нет out_defect — бракованная деталь идёт тем же путём
        return self._find_normal_target(block_id)

    # ══════════════════════════════════════════════════════════
    # Финализация
    # ══════════════════════════════════════════════════════════

    def _finalize(self) -> SimulationResult:
        """Закрыть метрики и собрать результат."""
        self._metrics.finalize(self._clock)

        # Посчитать детали, оставшиеся в системе
        in_progress = sum(
            1 for d in self._details.values()
            if not d.instance.is_terminal()
        )

        return self._metrics.build_result(
            max_time=self._max_time,
            elapsed_time=self._clock,
            seed=self._seed,
            total_in_progress=in_progress,
        )
