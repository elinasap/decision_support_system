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

def run_a11(result: SimulationResult, thresholds: Thresholds) -> list[Sign]:
    """
    A11 — локальная диагностика.

    Проверяет каждый блок (техоперация, транспорт) и каждый буфер
    независимо, сравнивая метрики с пороговыми значениями.

    Возвращает список локальных признаков.
    """
    signs: list[Sign] = []

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
    for edge in model_dict.get("edges", []):
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

    return signs


# ── Точка входа A1 ────────────────────────────────────────────────────────────

def run_diagnosis(
    result: SimulationResult,
    model_dict: dict,
    thresholds: Thresholds,
) -> DiagnosisResult:
    """
    Запускает полную диагностику (A11 + A12 + A13).

    Возвращает DiagnosisResult со всеми найденными признаками.
    """
    local   = run_a11(result, thresholds)
    context = run_a12(result, model_dict, thresholds, local)
    system  = run_a13(result, thresholds)

    return DiagnosisResult(
        local_signs=local,
        context_signs=context,
        system_signs=system,
    )
