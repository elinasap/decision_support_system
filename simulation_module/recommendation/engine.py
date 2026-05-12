"""
Точка входа алгоритма формирования рекомендаций.

Использование:

    from recommendation.engine import RecommendationEngine
    from recommendation.thresholds import Thresholds

    engine = RecommendationEngine(model_dict=model_dict)
    report = engine.analyze(result)

    for item in report.interpretations:
        print(f"[{item.severity}] {item.label}: {item.message}")

    if not report.interpretations:
        print("Отклонений не обнаружено.")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from simulation.result import SimulationResult
from recommendation.thresholds import Thresholds
from recommendation.diagnosis import run_diagnosis, DiagnosisResult
from recommendation.interpreter import run_interpretation, InterpretationResult, Interpretation


@dataclass
class RecommendationReport:
    """
    Итоговый отчёт алгоритма рекомендаций.

    Содержит:
        interpretations — ранжированный список интерпретаций (A2)
        diagnosis       — детальный результат диагностики (A1), для отладки/GUI

    Если interpretations пуст — отклонений не обнаружено.
    """
    interpretations: list[Interpretation]
    diagnosis: DiagnosisResult


class RecommendationEngine:
    """
    Основной класс алгоритма рекомендаций.

    Принимает model_dict и thresholds при инициализации,
    затем может анализировать любое количество SimulationResult.

    Параметры:
        model_dict  — описание модели (используется для топологии в A12)
        thresholds  — пороговые значения (если не передать — используются defaults)
    """

    def __init__(
        self,
        model_dict: dict,
        thresholds: Optional[Thresholds] = None,
    ):
        self.model_dict = model_dict
        self.thresholds = thresholds or Thresholds()

    def analyze(self, result: SimulationResult) -> RecommendationReport:
        """
        Запускает полный анализ: A1 (диагностика) + A2 (интерпретации).

        Возвращает RecommendationReport с ранжированным списком интерпретаций.
        """
        # A1: диагностика (A11 + A12 + A13)
        diagnosis = run_diagnosis(
            result=result,
            model_dict=self.model_dict,
            thresholds=self.thresholds,
        )

        # A2: генерация интерпретаций (A21 + A22 + A23)
        interpretation = run_interpretation(
            diagnosis=diagnosis,
            result=result,
        )

        return RecommendationReport(
            interpretations=interpretation.interpretations,
            diagnosis=diagnosis,
        )
