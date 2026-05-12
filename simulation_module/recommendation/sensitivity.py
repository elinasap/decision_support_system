"""
Блок сценарного анализа (A3).

Запускается только по явному запросу пользователя.
Прогоняет пять фиксированных сценариев с изменёнными параметрами,
для каждого запускает диагностику (A1) и сравнивает с базовым прогоном.

Три подблока:
    A31 — формирование вариантов параметров (патч model_dict)
    A32 — прогон симуляции + диагностика для каждого варианта
    A33 — сравнение с базовым прогоном, оценка устойчивости

Сценарии:
    1. Рост входного потока:         интенсивность source × (1.1, 1.2, 1.3)
    2. Рост брака:                   defect_prob × (1.5, 2.0)
    3. Снижение производительности:  operation_time самого загруженного блока × (1.2, 1.4)
    4. Уменьшение ёмкости буферов:   capacity всех буферов × (0.75, 0.5)
    5. Отказ позиции:                operation_time каждого блока → очень большое число

Использование:
    from recommendation.sensitivity import ScenarioAnalyzer

    analyzer = ScenarioAnalyzer(
        model_dict=model_dict,
        base_result=base_result,
        thresholds=thresholds,
        max_time=500,
        seed=42,
    )
    report = analyzer.run()

    for scenario in report.scenarios:
        print(scenario.scenario_name, scenario.step_label)
        for sign in scenario.new_signs:
            print(" ", sign.label, sign.sign_type)
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from simulation.engine import Simulator
from simulation.result import SimulationResult
from recommendation.thresholds import Thresholds
from recommendation.diagnosis import run_diagnosis, Sign


# ── Результат одного шага сценария ───────────────────────────────────────────

@dataclass
class ScenarioStepResult:
    """Результат одного шага одного сценария."""
    scenario_id: str          # например "input_flow"
    scenario_name: str        # читаемое название сценария
    step_label: str           # например "+20% к входному потоку"
    modified_param: str       # что именно изменили
    new_signs: list[Sign]     # признаки которых не было в базовом прогоне
    all_signs: list[Sign]     # все признаки после изменения
    result: SimulationResult  # результат прогона для этого шага


@dataclass
class RobustnessEstimate:
    """
    Оценка устойчивости системы по одному сценарию.

    first_critical_step — шаг при котором впервые появился красный признак
    first_warning_step  — шаг при котором впервые появился жёлтый признак
    is_robust           — True если ни при каком шаге не появилось новых признаков
    summary             — текстовое резюме
    """
    scenario_id: str
    scenario_name: str
    first_critical_step: Optional[str] = None   # red
    first_warning_step: Optional[str] = None    # yellow
    is_robust: bool = True
    summary: str = ""


@dataclass
class SensitivityReport:
    """Итоговый отчёт сценарного анализа."""
    scenarios: list[ScenarioStepResult] = field(default_factory=list)
    robustness: list[RobustnessEstimate] = field(default_factory=list)


# ── A31: Формирование вариантов параметров ────────────────────────────────────

def _find_source_blocks(model_dict: dict) -> list[str]:
    """Найти все блоки типа source."""
    return [
        bid for bid, b in model_dict.get("blocks", {}).items()
        if b.get("type") == "source"
    ]


def _find_process_blocks(model_dict: dict) -> list[str]:
    """Найти все блоки типа process и transport."""
    return [
        bid for bid, b in model_dict.get("blocks", {}).items()
        if b.get("type") in ("process", "transport")
    ]


def _find_control_blocks(model_dict: dict) -> list[str]:
    """Найти все блоки типа control (контроль качества, есть defect_prob)."""
    return [
        bid for bid, b in model_dict.get("blocks", {}).items()
        if b.get("type") == "control"
        and "defect_prob" in b.get("params", {})
    ]


def _find_buffer_blocks(model_dict: dict) -> list[str]:
    """Найти все блоки типа buffer."""
    return [
        bid for bid, b in model_dict.get("blocks", {}).items()
        if b.get("type") == "buffer"
    ]


def _find_most_loaded_block(
    base_result: SimulationResult,
    model_dict: dict,
) -> Optional[str]:
    """Найти блок с наибольшей загрузкой среди process/transport."""
    process_ids = set(_find_process_blocks(model_dict))
    best_id = None
    best_u = 0.0
    for bid, m in base_result.block_metrics.items():
        if bid in process_ids and m.utilization > best_u:
            best_u = m.utilization
            best_id = bid
    return best_id


def build_variants_a31(
    model_dict: dict,
    base_result: SimulationResult,
) -> list[tuple[str, str, str, dict]]:
    """
    A31 — формирует список вариантов параметров для прогона.

    Возвращает список кортежей:
        (scenario_id, step_label, modified_param, patched_model_dict)
    """
    variants: list[tuple[str, str, str, dict]] = []

    # ── Сценарий 1: рост входного потока ──
    # Уменьшаем inter_arrival_time (время между деталями) → поток растёт
    # Или увеличиваем initial_count у source если inter_arrival нет
    source_ids = _find_source_blocks(model_dict)
    if source_ids:
        for factor, label in [(1.1, "+10%"), (1.2, "+20%"), (1.3, "+30%")]:
            patched = copy.deepcopy(model_dict)
            for sid in source_ids:
                params = patched["blocks"][sid]["params"]
                # Уменьшаем inter_arrival_time если есть (больше деталей)
                if "inter_arrival_time" in params and params["inter_arrival_time"]:
                    params["inter_arrival_time"] = params["inter_arrival_time"] / factor
                # Или увеличиваем начальный запас
                elif "initial_count" in params:
                    params["initial_count"] = int(params["initial_count"] * factor)
            variants.append((
                "input_flow",
                f"Входной поток {label}",
                "inter_arrival_time / initial_count",
                patched,
            ))

    # ── Сценарий 2: рост брака ──
    control_ids = _find_control_blocks(model_dict)
    if control_ids:
        for factor, label in [(1.5, "+50%"), (2.0, "+100%")]:
            patched = copy.deepcopy(model_dict)
            for cid in control_ids:
                params = patched["blocks"][cid]["params"]
                new_prob = min(params["defect_prob"] * factor, 1.0)
                params["defect_prob"] = new_prob
            variants.append((
                "defect_rate",
                f"Вероятность брака {label}",
                "defect_prob",
                patched,
            ))

    # ── Сценарий 3: снижение производительности самого загруженного блока ──
    most_loaded = _find_most_loaded_block(base_result, model_dict)
    if most_loaded:
        block_label = (
            base_result.block_metrics[most_loaded].block_label
            or most_loaded
        )
        for factor, label in [(1.2, "+20% к времени операции"), (1.4, "+40% к времени операции")]:
            patched = copy.deepcopy(model_dict)
            params = patched["blocks"][most_loaded]["params"]
            if "operation_time_sec" in params:
                params["operation_time_sec"] = params["operation_time_sec"] * factor
            elif "control_time_sec" in params:
                params["control_time_sec"] = params["control_time_sec"] * factor
            variants.append((
                "performance_drop",
                f"Снижение производительности «{block_label}» {label}",
                f"{most_loaded}.operation_time_sec",
                patched,
            ))

    # ── Сценарий 4: уменьшение ёмкости буферов ──
    buffer_ids = _find_buffer_blocks(model_dict)
    if buffer_ids:
        for factor, label in [(0.75, "−25%"), (0.5, "−50%")]:
            patched = copy.deepcopy(model_dict)
            for bid in buffer_ids:
                params = patched["blocks"][bid]["params"]
                if "capacity" in params:
                    new_cap = max(1, int(params["capacity"] * factor))
                    params["capacity"] = new_cap
            variants.append((
                "buffer_capacity",
                f"Ёмкость буферов {label}",
                "buffer.capacity",
                patched,
            ))

    # ── Сценарий 5: отказ позиции ──
    # Поочерёдно «выключаем» каждый блок (время операции → очень большое)
    process_ids = _find_process_blocks(model_dict)
    for pid in process_ids:
        block_label = (
            base_result.block_metrics.get(pid, type("", (), {"block_label": pid})()).block_label
            or pid
        )
        patched = copy.deepcopy(model_dict)
        params = patched["blocks"][pid]["params"]
        if "operation_time_sec" in params:
            params["operation_time_sec"] = 999_999.0
        elif "control_time_sec" in params:
            params["control_time_sec"] = 999_999.0
        variants.append((
            "block_failure",
            f"Отказ блока «{block_label}»",
            f"{pid}.operation_time_sec",
            patched,
        ))

    return variants


# ── A32: Прогон симуляции по сценариям ───────────────────────────────────────

def run_scenario_a32(
    variant: tuple[str, str, str, dict],
    thresholds: Thresholds,
    max_time: float,
    seed: Optional[int],
) -> tuple[str, str, str, SimulationResult, list[Sign]]:
    """
    A32 — запускает один вариант симуляции и диагностику.

    Возвращает:
        (scenario_id, step_label, modified_param, result, all_signs)
    """
    scenario_id, step_label, modified_param, patched_dict = variant

    result = Simulator(patched_dict, max_time=max_time, seed=seed).run()
    diagnosis = run_diagnosis(result, patched_dict, thresholds)

    return scenario_id, step_label, modified_param, result, diagnosis.all_signs


# ── A33: Сравнение с базовым прогоном ────────────────────────────────────────

def compare_with_base_a33(
    scenario_id: str,
    scenario_name: str,
    step_label: str,
    modified_param: str,
    scenario_signs: list[Sign],
    base_signs: list[Sign],
    scenario_result: SimulationResult,
) -> ScenarioStepResult:
    """
    A33 — сравнивает признаки сценария с базовым прогоном.

    Новые признаки = те, которых не было в базовом прогоне
    (сравниваем по block_id + sign_type).
    """
    base_keys = {(s.block_id, s.sign_type) for s in base_signs}
    new_signs = [
        s for s in scenario_signs
        if (s.block_id, s.sign_type) not in base_keys
    ]

    return ScenarioStepResult(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        step_label=step_label,
        modified_param=modified_param,
        new_signs=new_signs,
        all_signs=scenario_signs,
        result=scenario_result,
    )


def estimate_robustness(
    scenario_id: str,
    scenario_name: str,
    steps: list[ScenarioStepResult],
) -> RobustnessEstimate:
    """
    Оценивает устойчивость системы по результатам всех шагов сценария.

    Ищет первый шаг где появились новые красные/жёлтые признаки.
    """
    first_red = None
    first_yellow = None

    for step in steps:
        for sign in step.new_signs:
            if sign.severity == "red" and first_red is None:
                first_red = step.step_label
            if sign.severity == "yellow" and first_yellow is None:
                first_yellow = step.step_label

    is_robust = first_red is None and first_yellow is None

    if is_robust:
        summary = f"При сценарии «{scenario_name}» новых признаков не обнаружено — система устойчива."
    elif first_red:
        summary = (
            f"При сценарии «{scenario_name}» критические признаки появляются "
            f"начиная с шага «{first_red}»."
        )
    else:
        summary = (
            f"При сценарии «{scenario_name}» предупреждения появляются "
            f"начиная с шага «{first_yellow}»."
        )

    return RobustnessEstimate(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        first_critical_step=first_red,
        first_warning_step=first_yellow,
        is_robust=is_robust,
        summary=summary,
    )


# ── Точка входа A3 ────────────────────────────────────────────────────────────

# Читаемые названия сценариев
_SCENARIO_NAMES = {
    "input_flow":       "Рост входного потока",
    "defect_rate":      "Рост вероятности брака",
    "performance_drop": "Снижение производительности",
    "buffer_capacity":  "Уменьшение ёмкости буферов",
    "block_failure":    "Отказ позиции",
}


class ScenarioAnalyzer:
    """
    Блок сценарного анализа (A3).

    Запускается только по явному запросу пользователя.

    Параметры:
        model_dict   — исходное описание модели (не изменяется)
        base_result  — результат базового прогона симуляции
        thresholds   — пороговые значения (те же что в RecommendationEngine)
        max_time     — время прогона для каждого сценария
        seed         — seed для воспроизводимости
    """

    def __init__(
        self,
        model_dict: dict,
        base_result: SimulationResult,
        thresholds: Optional[Thresholds] = None,
        max_time: float = 500.0,
        seed: Optional[int] = None,
    ):
        self.model_dict = model_dict
        self.base_result = base_result
        self.thresholds = thresholds or Thresholds()
        self.max_time = max_time
        self.seed = seed

    def run(self) -> SensitivityReport:
        """
        Запускает полный сценарный анализ (A31 + A32 + A33).

        Возвращает SensitivityReport со всеми сценариями
        и оценками устойчивости.
        """
        # A31: формируем варианты
        variants = build_variants_a31(self.model_dict, self.base_result)

        # Базовые признаки для сравнения
        base_diagnosis = run_diagnosis(
            self.base_result, self.model_dict, self.thresholds
        )
        base_signs = base_diagnosis.all_signs

        # A32 + A33: прогоняем каждый вариант и сравниваем
        step_results: list[ScenarioStepResult] = []
        for variant in variants:
            scenario_id, step_label, modified_param, scenario_result, scenario_signs = \
                run_scenario_a32(variant, self.thresholds, self.max_time, self.seed)

            scenario_name = _SCENARIO_NAMES.get(scenario_id, scenario_id)
            step = compare_with_base_a33(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                step_label=step_label,
                modified_param=modified_param,
                scenario_signs=scenario_signs,
                base_signs=base_signs,
                scenario_result=scenario_result,
            )
            step_results.append(step)

        # Оценка устойчивости по каждому сценарию
        robustness: list[RobustnessEstimate] = []
        seen_scenarios: dict[str, list[ScenarioStepResult]] = {}
        for step in step_results:
            seen_scenarios.setdefault(step.scenario_id, []).append(step)

        for scenario_id, steps in seen_scenarios.items():
            scenario_name = _SCENARIO_NAMES.get(scenario_id, scenario_id)
            robustness.append(
                estimate_robustness(scenario_id, scenario_name, steps)
            )

        return SensitivityReport(
            scenarios=step_results,
            robustness=robustness,
        )
