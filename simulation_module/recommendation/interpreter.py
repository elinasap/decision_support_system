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
from simulation.result import SimulationResult
from recommendation.diagnosis import DiagnosisResult, Sign, SEVERITY_RED, SEVERITY_YELLOW


# ── Приоритет типов признаков по влиянию на CT ───────────────────────────────
# Меньше число = выше приоритет

_CT_IMPACT_PRIORITY: dict[str, int] = {
    "overload_and_blockage": 1,
    "overload":              2,
    "downstream_jam":        3,
    "logistics_jam":         4,
    "overflow":              5,
    "blockage":              6,
    "long_queue":            7,
    "long_cycle":            8,
    "low_throughput":        9,
    "high_defect_rate":      10,
    "idle":                  11,
    "starvation":            12,
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
        "Рассмотрите увеличение числа рабочих мест на этой операции, "
        "сокращение времени цикла или перераспределение маршрутов деталей."
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
    "downstream_jam": (
        "Сосредоточьте усилия на downstream-операции: она является первопричиной "
        "проблемы. Устранение блокировки upstream само по себе не поможет."
    ),
    "logistics_jam": (
        "Увеличьте пропускную способность транспортной позиции "
        "или сократите транспортное плечо за счёт перекомпоновки участка."
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
    def from_sign(cls, rank: int, sign: Sign) -> "Interpretation":
        return cls(
            rank=rank,
            block_id=sign.block_id,
            label=sign.label,
            sign_type=sign.sign_type,
            severity=sign.severity,
            message=sign.message,
            recommendation=_RECOMMENDATIONS.get(sign.sign_type, ""),
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


# ── A23: Приоритизация ────────────────────────────────────────────────────────

def run_a23(signs: list[Sign]) -> list[Interpretation]:
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
        Interpretation.from_sign(rank=i + 1, sign=sign)
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
    interpretations = run_a23(signs_a22)

    return InterpretationResult(
        interpretations=interpretations,
    )
