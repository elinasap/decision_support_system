"""
Блок генерации интерпретаций (A2).

Три шага:
    A21 — сопоставление признаков с базой правил
    A22 — формулировка интерпретаций (уже встроена в Sign.message из diagnosis.py)
    A23 — приоритизация: сначала по severity (red→yellow→green),
          внутри одной группы — по влиянию на avg_cycle_time

Приоритизация по влиянию на CT:
    Признаки, напрямую влияющие на CT, ставятся выше:
    overload > downstream_jam > logistics_jam > overflow >
    blockage > long_queue > long_cycle > low_throughput >
    high_defect_rate > idle > starvation

Входные данные:
    diagnosis: DiagnosisResult — результат блока A1
    result: SimulationResult   — нужен для контекста при приоритизации

Выходные данные:
    list[Interpretation] — ранжированный список интерпретаций
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from simulation.result import SimulationResult, BlockMetrics
from recommendation.diagnosis import DiagnosisResult, Sign, SEVERITY_RED, SEVERITY_YELLOW


# ── Приоритет типов признаков по влиянию на CT ───────────────────────────────
# Меньше число = выше приоритет

_CT_IMPACT_PRIORITY: dict[str, int] = {
    "overload_and_blockage": 1,
    "flow_imbalance":        2,
    "overload":              3,
    "frequent_failure":      4,
    "downstream_jam":        5,
    "logistics_jam":         6,
    "overflow":              7,
    "blockage":              8,
    "low_availability":      9,
    "parallel_imbalance":    10,
    "long_queue":            11,
    "long_operation":        12,
    "long_cycle":            13,
    "low_throughput":        14,
    "high_defect_rate":      15,
    "early_control":         16,
    "idle":                  17,
    "starvation":            18,
}

_SEVERITY_ORDER = {
    SEVERITY_RED:    0,
    SEVERITY_YELLOW: 1,
    "green":         2,
}

# ── База рекомендаций (A21) ───────────────────────────────────────────────────
# Для каждого типа признака — текст рекомендации пользователю.

_RECOMMENDATIONS: dict[str, str] = {
    # Блоки
    "overload": (
        "Операция загружена на {utilization:.0%}. "
        "С учётом коэффициента готовности ({availability:.0%}) "
        "рекомендуется {required_machines} станк(а/ов) на данную операцию. "
        "Альтернативы: сократить норму времени или ввести дополнительную смену."
    ),
    "overload_and_blockage": (
        "Проанализируйте цепочку целиком: устраните узкое место downstream, "
        "затем оцените загрузку этого блока повторно."
    ),
    "blockage": (
        "Увеличьте производительность следующей операции "
        "или ёмкость буфера между ними."
    ),
    "idle": (
        "Рассмотрите перераспределение мощности этого блока "
        "на перегруженные участки или объединение с соседней операцией."
    ),
    # Буферы
    "overflow": (
        "Увеличьте ёмкость буфера или повысьте производительность "
        "downstream-операции, которая его разгружает."
    ),
    "long_queue": (
        "Рассмотрите ускорение downstream-операции "
        "или увеличение ёмкости буфера как временную меру."
    ),
    "starvation": (
        "Проверьте upstream-позиции: возможно, одна из них является узким местом, "
        "которое не даёт деталям доходить до этого буфера."
    ),
    # Контекстные
    "flow_imbalance": (
        "Сбалансируйте производительность входных ветвей: "
        "ускорьте подачу по голодающим входам или замедлите подачу по переполненным."
    ),
    "downstream_jam": (
        "Сосредоточьте усилия на downstream-операции: она является первопричиной "
        "проблемы. Устранение блокировки upstream само по себе не поможет."
    ),
    "logistics_jam": (
        "Увеличьте пропускную способность транспортной позиции "
        "или сократите транспортное плечо за счёт перекомпоновки участка."
    ),
    # Надёжность
    "low_availability": (
        "Коэффициент готовности: {availability:.0%}. "
        "Рекомендуется увеличить частоту планового ТО для снижения аварийных остановок "
        "или ввести резервный станок. "
        "Скорректированная потребность в оборудовании: {required_machines} ед."
    ),
    "frequent_failure": (
        "Высокая частота отказов ({failure_rate:.1f}/час) указывает на износ. "
        "Проверьте техническое состояние оборудования, "
        "снизьте интенсивность загрузки или замените оборудование."
    ),
    # Структурные
    "parallel_imbalance": (
        "Перенаправьте часть потока с перегруженной операции на простаивающую. "
        "Проверьте технологическую допустимость перераспределения "
        "с учётом возможных неявных ограничений процесса."
    ),
    "long_operation": (
        "Операция значительно длиннее средней по участку. "
        "Рассмотрите разбиение на два этапа или внедрение параллельного рабочего места."
    ),
    "early_control": (
        "Перенесите контроль качества на более ранний этап маршрута, "
        "чтобы выявлять брак до дорогостоящих операций."
    ),
    # Системные
    "long_cycle": (
        "Найдите блок с наибольшим вкладом в время ожидания "
        "(переполненные буферы или перегруженные операции) "
        "и устраните его в первую очередь."
    ),
    "low_throughput": (
        "Найдите блок с наибольшей загрузкой (utilization) — "
        "он с высокой вероятностью является ограничителем пропускной способности."
    ),
    "high_defect_rate": (
        "Проверьте наиболее загруженные техоперации: высокая загрузка коррелирует "
        "с ростом брака. Рассмотрите снижение темпа на критичных позициях."
    ),
}


@dataclass
class Interpretation:
    """
    Одна готовая интерпретация для вывода пользователю.

    Содержит всю информацию из Sign, рекомендацию
    и порядковый номер после ранжирования.
    """
    rank: int
    block_id: str | None
    label: str
    sign_type: str
    severity: str
    message: str          # интерпретация: «возможно, ...»
    recommendation: str   # рекомендация: «рассмотрите ...»
    metric_name: str
    metric_value: float
    threshold: float | None

    @classmethod
    def from_sign(cls, rank: int, sign: Sign,
                  block_metrics: Optional[BlockMetrics] = None) -> "Interpretation":
        template = _RECOMMENDATIONS.get(sign.sign_type, "")
        if template and block_metrics is not None:
            try:
                template = template.format(
                    utilization=block_metrics.utilization,
                    availability=block_metrics.availability,
                    required_machines=block_metrics.required_machines,
                    failure_rate=block_metrics.failure_rate,
                )
            except (KeyError, AttributeError, ValueError):
                pass
        return cls(
            rank=rank,
            block_id=sign.block_id,
            label=sign.label,
            sign_type=sign.sign_type,
            severity=sign.severity,
            message=sign.message,
            recommendation=template,
            metric_name=sign.metric_name,
            metric_value=sign.metric_value,
            threshold=sign.threshold,
        )


@dataclass
class InterpretationResult:
    """Итоговый результат блока A2."""
    interpretations: list[Interpretation]


# ── A21: Сопоставление с правилами ───────────────────────────────────────────

def run_a21(diagnosis: DiagnosisResult) -> list[Sign]:
    """
    A21 — принимает все признаки из DiagnosisResult,
    фильтрует дубликаты (один блок — один признак наивысшей критичности).

    Если у блока есть и overload_and_blockage, и overload — оставляем
    только overload_and_blockage, так как он включает оба условия.
    """
    all_signs = diagnosis.all_signs

    # Группируем по block_id, для каждого блока оставляем признаки
    # отсортированные по severity + ct_impact
    seen_pairs: set[tuple] = set()
    filtered: list[Sign] = []

    for sign in all_signs:
        key = (sign.block_id, sign.sign_type)
        if key not in seen_pairs:
            seen_pairs.add(key)
            filtered.append(sign)

    return filtered


# ── A22: Формулировка интерпретаций ──────────────────────────────────────────

def run_a22(signs: list[Sign]) -> list[Sign]:
    """
    A22 — интерпретации уже сформулированы в Sign.message на этапе A11/A12/A13.
    Этот шаг оставлен явным для соответствия архитектуре IDEF0
    и для возможного расширения (например, локализация сообщений).

    В текущей реализации просто возвращает знаки как есть.
    """
    return signs


# ── Фильтрация избыточных признаков ──────────────────────────────────────────

def _suppress_redundant(signs: list[Sign]) -> list[Sign]:
    """
    Убирает overflow / starvation / long_queue для буферов, которые уже
    объяснены признаком flow_imbalance на связанном блоке сборки.

    Если блок «Сборка А» получил flow_imbalance с full_inputs=[B1] и
    starved_inputs=[B2], то отдельные признаки overflow(B1) и starvation(B2)
    избыточны — пользователю не нужно видеть их дважды.
    """
    _REDUNDANT_TYPES = frozenset({"overflow", "starvation", "long_queue"})

    suppressed: set[str] = set()
    for s in signs:
        if s.sign_type == "flow_imbalance":
            suppressed.update(s.detail.get("full_inputs", []))
            suppressed.update(s.detail.get("starved_inputs", []))

    return [
        s for s in signs
        if not (s.block_id in suppressed and s.sign_type in _REDUNDANT_TYPES)
    ]


# ── A23: Приоритизация ────────────────────────────────────────────────────────

def run_a23(
    signs: list[Sign],
    result: Optional[SimulationResult] = None,
) -> list[Interpretation]:
    """
    A23 — ранжирует интерпретации:
        1. По severity: red → yellow → green
        2. Внутри одной severity — по влиянию на CT (_CT_IMPACT_PRIORITY)

    Возвращает список Interpretation с проставленными rank.
    """
    def sort_key(sign: Sign) -> tuple:
        severity_order = _SEVERITY_ORDER.get(sign.severity, 99)
        ct_order = _CT_IMPACT_PRIORITY.get(sign.sign_type, 99)
        return (severity_order, ct_order)

    sorted_signs = sorted(signs, key=sort_key)

    return [
        Interpretation.from_sign(
            rank=i + 1,
            sign=sign,
            block_metrics=(
                result.block_metrics.get(sign.block_id)
                if result and sign.block_id else None
            ),
        )
        for i, sign in enumerate(sorted_signs)
    ]


# ── Точка входа A2 ────────────────────────────────────────────────────────────

def run_interpretation(
    diagnosis: DiagnosisResult,
    result: SimulationResult,
) -> InterpretationResult:
    """
    Запускает полный блок генерации интерпретаций (A21 + A22 + A23).

    Возвращает InterpretationResult с ранжированным списком.
    """
    signs_a21 = run_a21(diagnosis)
    signs_a22 = run_a22(signs_a21)
    signs_filtered = _suppress_redundant(signs_a22)
    interpretations = run_a23(signs_filtered, result)

    return InterpretationResult(
        interpretations=interpretations,
    )
