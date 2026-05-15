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

from dataclasses import dataclass, field
from typing import Optional

from simulation.result import SimulationResult
from recommendation.thresholds import Thresholds
from recommendation.diagnosis import run_diagnosis, DiagnosisResult
from recommendation.interpreter import run_interpretation, InterpretationResult, Interpretation
from recommendation.scoring import compute_block_score, compute_buffer_score
from recommendation.chain import find_chains


@dataclass
class RecommendationReport:
    """
    Итоговый отчёт алгоритма рекомендаций.

    Содержит:
        interpretations — ранжированный список интерпретаций (A2)
        diagnosis       — детальный результат диагностики (A1), для отладки/GUI
        system_state    — агрегированная оценка: "stable" / "overloaded" / "unstable"
        block_scores    — composite score для каждого блока {block_id: float}
        buffer_scores   — composite score для каждого буфера {buf_id: float}
        chains          — цепочки голодания/блокировки [[block_id, ...], ...]
    """
    interpretations: list[Interpretation]
    diagnosis: DiagnosisResult
    system_state: str = "stable"
    block_scores: dict[str, float] = field(default_factory=dict)
    buffer_scores: dict[str, float] = field(default_factory=dict)
    chains: list[list[str]] = field(default_factory=list)


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
        (
            self._multi_input_blocks,
            self._upstream_map,
            self._downstream_map,
        ) = self._build_upstream_map()

    def _build_upstream_map(
        self,
    ) -> tuple[list[str], dict[str, list[str]], dict[str, list[str]]]:
        """
        Строит два маппинга:

        upstream_map   — {block_id: [buf_id, ...]}
            Для каждого операционного блока — буферы, которые подают в него.

        downstream_map — {buf_id: [block_id, ...]}
            Для каждого буфера — операционные блоки, которые выходят в него.
            Используется для обхода цепочек голодания.
        """
        blocks = self.model_dict.get("blocks", {})
        edges = self.model_dict.get("edges", {})
        edge_iter = edges.values() if isinstance(edges, dict) else edges

        upstream_map: dict[str, list[str]] = {}
        downstream_map: dict[str, list[str]] = {}

        for edge in edge_iter:
            src = edge.get("from_block")
            dst = edge.get("to_block")
            if not src or not dst:
                continue

            src_type = blocks.get(src, {}).get("type", "")
            dst_type = blocks.get(dst, {}).get("type", "")

            # upstream_map: буфер → следующий операционный блок
            if src_type == "buffer":
                upstream_map.setdefault(dst, []).append(src)

            # downstream_map: кто подаёт в буфер
            if dst_type == "buffer":
                downstream_map.setdefault(dst, []).append(src)

        multi_input_blocks = [
            bid for bid, bufs in upstream_map.items()
            if len(bufs) >= 2
            and blocks.get(bid, {}).get("type") == "assembly"
        ]
        return multi_input_blocks, upstream_map, downstream_map

    def _assess_system_state(
        self,
        signs: list,
        result: SimulationResult,
    ) -> str:
        """
        Агрегированная оценка состояния участка.

        stable     — нет красных признаков
        overloaded — до 2 красных, брак в норме (< 10 %)
        unstable   — более 2 красных или высокий брак
        """
        red_count = sum(1 for s in signs if s.severity == "red")

        if red_count == 0:
            return "stable"
        if red_count <= 2 and result.defect_rate < 0.10:
            return "overloaded"
        return "unstable"

    def analyze(self, result: SimulationResult) -> RecommendationReport:
        """
        Запускает полный анализ:
            A1 (диагностика) + A2 (интерпретации) + scoring + chains + system_state.

        Возвращает RecommendationReport.
        """
        # A1: диагностика (A11 + A12 + A13)
        diagnosis = run_diagnosis(
            result=result,
            model_dict=self.model_dict,
            thresholds=self.thresholds,
            multi_input_blocks=self._multi_input_blocks,
            upstream_map=self._upstream_map,
        )

        # A2: генерация интерпретаций (A21 + A22 + A23 + suppress_redundant)
        interpretation = run_interpretation(
            diagnosis=diagnosis,
            result=result,
        )

        # Composite scores
        block_scores  = compute_block_score(result, self.thresholds)
        buffer_scores = compute_buffer_score(result, self.thresholds)

        # Цепочки голодания / блокировки
        chains = find_chains(
            signs=diagnosis.all_signs,
            upstream_map=self._upstream_map,
            downstream_map=self._downstream_map,
            block_metrics=result.block_metrics,
            buf_metrics=result.buffer_metrics,
        )

        # Агрегированная оценка состояния
        system_state = self._assess_system_state(diagnosis.all_signs, result)

        return RecommendationReport(
            interpretations=interpretation.interpretations,
            diagnosis=diagnosis,
            system_state=system_state,
            block_scores=block_scores,
            buffer_scores=buffer_scores,
            chains=chains,
        )
