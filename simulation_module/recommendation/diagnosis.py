"""
Блок диагностики (A1).

Три уровня диагностики:
    A11 — локальная: проверяет каждый блок и буфер по порогам
    A12 — контекстная: анализирует пары связанных позиций по топологии
    A13 — системная: проверяет агрегированные метрики CT, TP, DR

Входные данные:
    result: SimulationResult — результат прогона симуляции
    model_dict: dict — описание модели (нужны "edges" для топологии)
    thresholds: Thresholds — пороговые значения

Выходные данные:
    DiagnosisResult — содержит локальные, контекстные и системные признаки
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from simulation.result import SimulationResult
from recommendation.thresholds import Thresholds


# ── Типы признаков ────────────────────────────────────────────────────────────

SEVERITY_RED    = "red"     # критический
SEVERITY_YELLOW = "yellow"  # предупреждение
SEVERITY_GREEN  = "green"   # норма / информация


@dataclass
class Sign:
    """
    Один диагностический признак.

    block_id  — идентификатор блока или буфера (или None для системных)
    label     — читаемое название блока
    sign_type — тип признака (например "overload", "blockage", "overflow")
    severity  — критичность: red / yellow / green
    message   — текстовая интерпретация («возможно...», «вероятно...»)
    metric_name  — название метрики, которая сработала
    metric_value — фактическое значение метрики
    threshold    — пороговое значение, которое было превышено
    """
    block_id: Optional[str]
    label: str
    sign_type: str
    severity: str
    message: str
    metric_name: str
    metric_value: float
    threshold: Optional[float] = None
    detail: dict = field(default_factory=dict)


@dataclass
class DiagnosisResult:
    """Результат диагностики одного прогона симуляции."""
    local_signs: list[Sign] = field(default_factory=list)
    context_signs: list[Sign] = field(default_factory=list)
    system_signs: list[Sign] = field(default_factory=list)
    @property
    def all_signs(self) -> list[Sign]:
        """Все признаки в порядке: локальные → контекстные → системные."""
        return self.local_signs + self.context_signs + self.system_signs


# ── A11: Локальная диагностика ────────────────────────────────────────────────

def run_a11(
    result: SimulationResult,
    thresholds: Thresholds,
    model_dict: dict | None = None,
) -> list[Sign]:
    """
    A11 — локальная диагностика.

    Проверяет каждый блок (техоперация, транспорт) и каждый буфер
    независимо, сравнивая метрики с пороговыми значениями.

    Возвращает список локальных признаков.
    """
    signs: list[Sign] = []

    # Среднее время операции по участку (для long_operation)
    _avg_op_time: float = 0.0
    if model_dict:
        op_times = [
            float(b["params"].get("operation_time_sec", 0))
            for b in model_dict.get("blocks", {}).values()
            if b.get("type") in ("process", "assembly", "control")
            and b["params"].get("operation_time_sec", 0) > 0
        ]
        _avg_op_time = sum(op_times) / len(op_times) if op_times else 0.0

    # ── Проверка блоков ──
    for block_id, m in result.block_metrics.items():
        label = m.block_label or block_id
        idle = 1.0 - m.utilization - m.blocked_ratio

        # Перегрузка: U_i > θ_U
        if m.utilization > thresholds.utilization:
            # Если одновременно заблокирован — двойная нагрузка
            if m.blocked_ratio > thresholds.blocked_ratio:
                signs.append(Sign(
                    block_id=block_id,
                    label=label,
                    sign_type="overload_and_blockage",
                    severity=SEVERITY_RED,
                    message=(
                        f"Блок «{label}» одновременно перегружен "
                        f"(загрузка {m.utilization:.0%}) и заблокирован "
                        f"({m.blocked_ratio:.0%} времени) — возможно, "
                        f"проблема есть и до, и после него."
                    ),
                    metric_name="utilization + blocked_ratio",
                    metric_value=m.utilization,
                    threshold=thresholds.utilization,
                ))
            else:
                signs.append(Sign(
                    block_id=block_id,
                    label=label,
                    sign_type="overload",
                    severity=SEVERITY_RED,
                    message=(
                        f"Блок «{label}» занят {m.utilization:.0%} времени — "
                        f"возможно, он не справляется с входящим потоком "
                        f"и является узким местом."
                    ),
                    metric_name="utilization",
                    metric_value=m.utilization,
                    threshold=thresholds.utilization,
                ))

        # Блокировка без перегрузки: B_i > θ_B
        elif m.blocked_ratio > thresholds.blocked_ratio:
            signs.append(Sign(
                block_id=block_id,
                label=label,
                sign_type="blockage",
                severity=SEVERITY_YELLOW,
                message=(
                    f"Блок «{label}» заблокирован {m.blocked_ratio:.0%} времени — "
                    f"вероятно, downstream перегружен или буфер после него заполнен."
                ),
                metric_name="blocked_ratio",
                metric_value=m.blocked_ratio,
                threshold=thresholds.blocked_ratio,
            ))

        # Длинная операция: перегружена И время в N раз больше среднего
        if (model_dict and _avg_op_time > 0
                and m.utilization > thresholds.utilization):
            bdata = model_dict.get("blocks", {}).get(block_id, {})
            op_time = float(bdata.get("params", {}).get("operation_time_sec", 0))
            if op_time > 0:
                ratio = op_time / _avg_op_time
                if ratio > thresholds.op_time_ratio:
                    signs.append(Sign(
                        block_id=block_id,
                        label=label,
                        sign_type="long_operation",
                        severity=SEVERITY_YELLOW,
                        message=(
                            f"Операция «{label}» является узким местом и имеет "
                            f"норму времени {op_time:.0f} сек — "
                            f"в {ratio:.1f}x раз больше средней по участку. "
                            f"Рассмотрите разбиение на два этапа."
                        ),
                        metric_name="op_time_ratio",
                        metric_value=ratio,
                        threshold=thresholds.op_time_ratio,
                    ))

        # Простой: I_i > θ_I
        if idle > thresholds.idle_ratio:
            signs.append(Sign(
                block_id=block_id,
                label=label,
                sign_type="idle",
                severity=SEVERITY_GREEN,
                message=(
                    f"Блок «{label}» простаивает {idle:.0%} времени — "
                    f"возможно, upstream не успевает его загружать, "
                    f"либо он избыточен по мощности."
                ),
                metric_name="idle_ratio",
                metric_value=idle,
                threshold=thresholds.idle_ratio,
            ))

        # Низкая готовность: A_i < θ_A
        if m.availability < thresholds.availability:
            signs.append(Sign(
                block_id=block_id,
                label=label,
                sign_type="low_availability",
                severity=SEVERITY_YELLOW,
                message=(
                    f"Коэффициент готовности «{label}»: {m.availability:.0%} — "
                    f"ниже порога {thresholds.availability:.0%}. "
                    f"Оборудование часто недоступно из-за ТО или ремонта."
                ),
                metric_name="availability",
                metric_value=m.availability,
                threshold=thresholds.availability,
            ))

        # Частые отказы: failure_rate > θ_fail
        if m.failure_rate > thresholds.failure_rate:
            signs.append(Sign(
                block_id=block_id,
                label=label,
                sign_type="frequent_failure",
                severity=SEVERITY_RED,
                message=(
                    f"Операция «{label}» имеет {m.failure_rate:.1f} отказов/час — "
                    f"выше нормы ({thresholds.failure_rate:.1f}). "
                    f"Возможен износ оборудования."
                ),
                metric_name="failure_rate",
                metric_value=m.failure_rate,
                threshold=thresholds.failure_rate,
            ))

    # ── Проверка буферов ──
    for buf_id, m in result.buffer_metrics.items():
        label = m.block_label or buf_id
        # Средняя заполненность: avg_count / capacity
        fill_ratio = (m.avg_count / m.capacity) if m.capacity > 0 else 0.0

        # Переполнение: full_ratio > θ_F
        if m.full_ratio > thresholds.full_ratio:
            signs.append(Sign(
                block_id=buf_id,
                label=label,
                sign_type="overflow",
                severity=SEVERITY_RED,
                message=(
                    f"Буфер «{label}» регулярно достигает максимума "
                    f"({m.full_ratio:.0%} времени полон) — детали либо "
                    f"теряются, либо блокируют предыдущий блок."
                ),
                metric_name="full_ratio",
                metric_value=m.full_ratio,
                threshold=thresholds.full_ratio,
            ))

        # Длинная очередь: avg заполненность > θ_L
        elif fill_ratio > thresholds.avg_fill_ratio:
            signs.append(Sign(
                block_id=buf_id,
                label=label,
                sign_type="long_queue",
                severity=SEVERITY_YELLOW,
                message=(
                    f"В буфере «{label}» в среднем накапливается много деталей "
                    f"(заполненность {fill_ratio:.0%}) — возможно, "
                    f"downstream не успевает их забирать."
                ),
                metric_name="avg_fill_ratio",
                metric_value=fill_ratio,
                threshold=thresholds.avg_fill_ratio,
            ))

        # Голодание: буфер почти всегда пуст
        # Проверяем: time_empty занимает почти всё наблюдаемое время
        total_observed = m._total_observed_time
        if total_observed > 0:
            empty_ratio = m.time_empty / total_observed
            if empty_ratio > 0.80 and fill_ratio < 0.05:
                signs.append(Sign(
                    block_id=buf_id,
                    label=label,
                    sign_type="starvation",
                    severity=SEVERITY_GREEN,
                    message=(
                        f"Буфер «{label}» почти всегда пуст "
                        f"({empty_ratio:.0%} времени) — возможно, "
                        f"поток деталей недостаточен или прерывается раньше."
                    ),
                    metric_name="empty_ratio",
                    metric_value=empty_ratio,
                    threshold=None,
                ))

    return signs


# ── A12: Контекстная диагностика ──────────────────────────────────────────────

def _build_topology(model_dict: dict) -> dict[str, list[str]]:
    """
    Строит маппинг: block_id → список downstream block_id.
    Использует model_dict["edges"] так же, как engine.py.
    """
    downstream: dict[str, list[str]] = {}
    edges = model_dict.get("edges", {})
    edge_iter = edges.values() if isinstance(edges, dict) else edges
    for edge in edge_iter:
        src = edge.get("from_block")
        dst = edge.get("to_block")
        if src and dst:
            downstream.setdefault(src, []).append(dst)
    return downstream


def run_a12(
    result: SimulationResult,
    model_dict: dict,
    thresholds: Thresholds,
    local_signs: list[Sign],
    multi_input_blocks: list[str] | None = None,
    upstream_map: dict[str, list[str]] | None = None,
) -> list[Sign]:
    """
    A12 — контекстная диагностика.

    Анализирует пары связанных позиций, используя топологию модели.
    Выявляет составные признаки которые нельзя увидеть по одному блоку.

    Использует local_signs из A11 чтобы не дублировать пороговые проверки.
    """
    signs: list[Sign] = []

    # Множества block_id с известными признаками для быстрого поиска
    overloaded = {s.block_id for s in local_signs if s.sign_type in ("overload", "overload_and_blockage")}
    blocked    = {s.block_id for s in local_signs if s.sign_type in ("blockage", "overload_and_blockage")}
    overflowed = {s.block_id for s in local_signs if s.sign_type == "overflow"}

    downstream = _build_topology(model_dict)

    # ── Затор downstream: блок i заблокирован, следующий перегружен ──
    for block_id in blocked:
        label_i = result.block_metrics[block_id].block_label or block_id
        for next_id in downstream.get(block_id, []):
            if next_id in overloaded:
                label_next = (
                    result.block_metrics[next_id].block_label
                    if next_id in result.block_metrics
                    else next_id
                )
                signs.append(Sign(
                    block_id=block_id,
                    label=label_i,
                    sign_type="downstream_jam",
                    severity=SEVERITY_RED,
                    message=(
                        f"Блок «{label_i}» заблокирован, а следующий за ним "
                        f"«{label_next}» перегружен — причина блокировки, "
                        f"вероятно, именно в нём."
                    ),
                    metric_name="blockage + downstream_overload",
                    metric_value=result.block_metrics[block_id].blocked_ratio,
                    threshold=thresholds.blocked_ratio,
                ))

    # ── Логистический затор: буфер перед транспортным блоком переполнен,
    #    и сам транспортный блок перегружен ──
    for block_id, m in result.block_metrics.items():
        if m.block_type != "transport":
            continue
        label_k = m.block_label or block_id
        if block_id not in overloaded:
            continue

        # Ищем буферы которые ведут в этот транспортный блок
        for buf_id in overflowed:
            if block_id in downstream.get(buf_id, []):
                label_buf = result.buffer_metrics[buf_id].block_label or buf_id
                signs.append(Sign(
                    block_id=block_id,
                    label=label_k,
                    sign_type="logistics_jam",
                    severity=SEVERITY_RED,
                    message=(
                        f"Буфер «{label_buf}» переполнен, а транспортный блок "
                        f"«{label_k}» перегружен — детали накапливаются "
                        f"быстрее, чем вывозятся. Вероятный логистический затор."
                    ),
                    metric_name="overflow + transport_overload",
                    metric_value=m.utilization,
                    threshold=thresholds.utilization,
                ))

    # ── Дисбаланс параллельных операций ──
    # Находим пары PROCESS-блоков с одинаковым input_type,
    # между которыми нет пути в графе; один перегружен, другой простаивает.
    blocks_dict = model_dict.get("blocks", {})
    process_by_type: dict[str, list[str]] = {}
    for bid, bdata in blocks_dict.items():
        if bdata.get("type") in ("process", "assembly"):
            itype = bdata.get("params", {}).get("input_type", "")
            if itype:
                process_by_type.setdefault(itype, []).append(bid)

    # Строим граф достижимости (только обычные рёбра, без back-edge)
    reachable: dict[str, set[str]] = {}

    def _get_reachable(start: str) -> set[str]:
        if start in reachable:
            return reachable[start]
        visited: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            raw_edges = model_dict.get("edges", {})
            edge_list = raw_edges.values() if isinstance(raw_edges, dict) else raw_edges
            for edge in edge_list:
                if edge.get("from_block") == cur and not edge.get("is_back_edge"):
                    nxt = edge["to_block"]
                    if nxt not in visited:
                        visited.add(nxt)
                        stack.append(nxt)
        reachable[start] = visited
        return visited

    overloaded_ids = {s.block_id for s in local_signs if s.sign_type in ("overload", "overload_and_blockage")}
    idle_ids = {s.block_id for s in local_signs if s.sign_type == "idle"}

    for itype, bids in process_by_type.items():
        if len(bids) < 2:
            continue
        for i, bid_a in enumerate(bids):
            for bid_b in bids[i + 1:]:
                if bid_a not in overloaded_ids or bid_b not in idle_ids:
                    if bid_b not in overloaded_ids or bid_a not in idle_ids:
                        continue
                # Определяем перегруженный и простаивающий
                if bid_a in overloaded_ids and bid_b in idle_ids:
                    overl_id, idle_id = bid_a, bid_b
                else:
                    overl_id, idle_id = bid_b, bid_a

                # Проверяем: нет пути между ними (параллельные)
                if (idle_id in _get_reachable(overl_id)
                        or overl_id in _get_reachable(idle_id)):
                    continue

                if overl_id not in result.block_metrics:
                    continue
                m_overl = result.block_metrics[overl_id]
                m_idle = result.block_metrics.get(idle_id)
                label_overl = m_overl.block_label or overl_id
                label_idle = (m_idle.block_label if m_idle else idle_id) or idle_id
                idle_ratio = 1.0 - m_idle.utilization - m_idle.blocked_ratio if m_idle else 0.0
                share = (m_overl.utilization - thresholds.utilization) / (m_overl.utilization + idle_ratio + 1e-9)

                signs.append(Sign(
                    block_id=overl_id,
                    label=f"{label_overl} / {label_idle}",
                    sign_type="parallel_imbalance",
                    severity=SEVERITY_YELLOW,
                    message=(
                        f"Операция «{label_overl}» перегружена "
                        f"({m_overl.utilization:.0%}), операция «{label_idle}» "
                        f"простаивает ({idle_ratio:.0%}). "
                        f"Обе принимают тип деталей «{itype}» и независимы в маршруте."
                    ),
                    metric_name="utilization / idle",
                    metric_value=m_overl.utilization,
                    threshold=thresholds.utilization,
                ))

    # ── Дисбаланс потоков на многовходовой сборке ──
    for block_id in (multi_input_blocks or []):
        upstream_bufs = (upstream_map or {}).get(block_id, [])
        buf_mets = result.buffer_metrics
        blk_mets = result.block_metrics

        known_bufs = [b for b in upstream_bufs if b in buf_mets]
        if len(known_bufs) < 2:
            continue

        full_bufs  = [b for b in known_bufs if buf_mets[b].full_ratio  > thresholds.full_ratio]
        empty_bufs = [b for b in known_bufs if buf_mets[b].empty_ratio > thresholds.theta_empty]

        if not full_bufs or not empty_bufs:
            continue

        blk = blk_mets.get(block_id)
        if blk is None:
            continue
        idle_ratio_blk = 1.0 - blk.utilization - blk.blocked_ratio
        if idle_ratio_blk <= thresholds.idle_ratio:
            continue

        label = blk.block_label or block_id
        max_empty = max(buf_mets[b].empty_ratio for b in empty_bufs)
        signs.append(Sign(
            block_id=block_id,
            label=label,
            sign_type="flow_imbalance",
            severity=SEVERITY_RED,
            message=(
                f"Блок «{label}» простаивает ({idle_ratio_blk:.0%}): "
                f"{len(full_bufs)} вход(а) переполнен(ы), "
                f"{len(empty_bufs)} вход(а) голодает — "
                f"потоки на входах рассинхронизированы."
            ),
            metric_name="flow_imbalance",
            metric_value=max_empty,
            threshold=thresholds.theta_empty,
            detail={"full_inputs": full_bufs, "starved_inputs": empty_bufs},
        ))

    return signs


# ── A13: Системная диагностика ────────────────────────────────────────────────

def run_a13(result: SimulationResult, thresholds: Thresholds) -> list[Sign]:
    """
    A13 — системная диагностика.

    Проверяет агрегированные метрики системы: CT, TP, DR.
    Запускается всегда, независимо от A11 и A12.
    """
    signs: list[Sign] = []

    # Длинный цикл: CT > θ_CT (если порог задан)
    if thresholds.avg_cycle_time is not None:
        if result.avg_cycle_time > thresholds.avg_cycle_time:
            signs.append(Sign(
                block_id=None,
                label="Система",
                sign_type="long_cycle",
                severity=SEVERITY_YELLOW,
                message=(
                    f"Среднее время цикла ({result.avg_cycle_time:.1f}) превышает "
                    f"норму ({thresholds.avg_cycle_time:.1f}) — возможно, "
                    f"значительная доля времени приходится на ожидание "
                    f"в буферах или транспортировку."
                ),
                metric_name="avg_cycle_time",
                metric_value=result.avg_cycle_time,
                threshold=thresholds.avg_cycle_time,
            ))

    # Низкая пропускная способность: TP < θ_TP (если порог задан)
    if thresholds.throughput is not None:
        if result.throughput < thresholds.throughput:
            signs.append(Sign(
                block_id=None,
                label="Система",
                sign_type="low_throughput",
                severity=SEVERITY_YELLOW,
                message=(
                    f"Пропускная способность ({result.throughput:.3f} дет/ед.вр.) "
                    f"ниже нормы ({thresholds.throughput:.3f}) — вероятно, "
                    f"где-то есть позиция, ограничивающая общий поток."
                ),
                metric_name="throughput",
                metric_value=result.throughput,
                threshold=thresholds.throughput,
            ))

    # Высокий брак: DR > θ_DR
    if result.defect_rate > thresholds.defect_rate:
        signs.append(Sign(
            block_id=None,
            label="Система",
            sign_type="high_defect_rate",
            severity=SEVERITY_RED,
            message=(
                f"Доля брака ({result.defect_rate:.1%}) выше нормы "
                f"({thresholds.defect_rate:.1%}) — возможно, это связано "
                f"с перегруженными техопераций или нарушением ритма подачи."
            ),
            metric_name="defect_rate",
            metric_value=result.defect_rate,
            threshold=thresholds.defect_rate,
        ))

    # Ранний вынос контроля качества
    if result.defect_rate > thresholds.defect_rate:
        scrapped = [d for d in result.detail_results if d.final_state == "SCRAPPED"]
        if scrapped:
            avg_ops = sum(d.blocks_visited for d in scrapped) / len(scrapped)
            if avg_ops > 1.5:
                signs.append(Sign(
                    block_id=None,
                    label="Контроль качества",
                    sign_type="early_control",
                    severity=SEVERITY_YELLOW,
                    message=(
                        f"Бракованные детали в среднем проходят "
                        f"{avg_ops:.1f} операций до обнаружения брака. "
                        f"Более ранний вынос контроля сократит потери."
                    ),
                    metric_name="avg_ops_before_control",
                    metric_value=avg_ops,
                    threshold=None,
                ))

    return signs


# ── Точка входа A1 ────────────────────────────────────────────────────────────

def run_diagnosis(
    result: SimulationResult,
    model_dict: dict,
    thresholds: Thresholds,
    multi_input_blocks: list[str] | None = None,
    upstream_map: dict[str, list[str]] | None = None,
) -> DiagnosisResult:
    """
    Запускает полную диагностику (A11 + A12 + A13).

    Возвращает DiagnosisResult со всеми найденными признаками.
    """
    local   = run_a11(result, thresholds, model_dict)
    context = run_a12(result, model_dict, thresholds, local,
                      multi_input_blocks=multi_input_blocks,
                      upstream_map=upstream_map)
    system  = run_a13(result, thresholds)

    return DiagnosisResult(
        local_signs=local,
        context_signs=context,
        system_signs=system,
    )
