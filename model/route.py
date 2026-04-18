"""
model/route.py

Маршрутная карта производственного участка.

Маршрут строится АВТОМАТИЧЕСКИ из графа модели —
технолог его не вводит вручную.

Ключевые решения:
  - Один source = один маршрут
  - Нумерация позиций: 005, 010, 015... (шаг 5, как в ГОСТ)
  - Блоки transport не получают позиций — они вспомогательные
  - Сборка входит в маршруты ВСЕХ своих входных потоков
  - Петля брака не создаёт новую позицию — фиксируется как
    атрибут существующей позиции (can_repeat=True)
"""

from dataclasses import dataclass, field
from .types import BlockType
from .block import Block
from .model import Model


# ══════════════════════════════════════════════════════════════════
# Структуры данных
# ══════════════════════════════════════════════════════════════════

@dataclass
class RouteStep:
    """Одна позиция в маршрутной карте."""
    position:    str        # "005", "010", "015"...
    block_id:    str        # ссылка на Block в модели
    block_label: str        # название для отображения
    block_type:  BlockType
    input_type:  str        # тип детали на входе
    output_type: str        # тип детали на выходе (= input если не меняется)
    can_repeat:  bool = False  # True если на эту позицию возможен возврат брака

    def __str__(self):
        repeat_mark = " [повтор возможен]" if self.can_repeat else ""
        return (f"{self.position}  {self.block_label}"
                f"  ({self.input_type} → {self.output_type}){repeat_mark}")


@dataclass
class Route:
    """
    Маршрутная карта для одного потока деталей.
    Строится от одного source-блока до конечного storage.
    """
    route_id:      str              # "R1", "R2"...
    source_block:  str              # ID source-блока
    detail_family: str              # базовый тип детали ("d_blank")
    steps:         list[RouteStep] = field(default_factory=list)

    def step_by_position(self, position: str) -> RouteStep | None:
        return next((s for s in self.steps if s.position == position), None)

    def step_by_block(self, block_id: str) -> RouteStep | None:
        """Возвращает первое вхождение блока в маршруте."""
        return next((s for s in self.steps if s.block_id == block_id), None)

    def __str__(self):
        lines = [f"Маршрут {self.route_id} [{self.detail_family}]"]
        for step in self.steps:
            lines.append(f"  {step}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# Алгоритм построения маршрутов
# ══════════════════════════════════════════════════════════════════

# Типы блоков, которые получают позицию в маршруте
POSITIONAL_TYPES = {BlockType.PROCESS, BlockType.ASSEMBLY, BlockType.CONTROL}

# Типы блоков, которые пропускаются (вспомогательные)
SKIP_TYPES = {BlockType.SOURCE, BlockType.BUFFER, BlockType.SINK, BlockType.TRANSPORT}


def build_routes(model: Model) -> list[Route]:
    """
    Строит маршрутную карту для каждого source-блока в модели.

    Алгоритм:
      1. Найти все блоки типа SOURCE
      2. Для каждого source — обойти граф в глубину по ПРЯМЫМ рёбрам
      3. Каждый блок из POSITIONAL_TYPES получает позицию (005, 010...)
      4. Если на блок ведёт обратное ребро — пометить can_repeat=True
      5. Нумерация сквозная по всему маршруту (не по отдельным веткам)

    Возвращает список маршрутов, по одному на каждый source.
    """
    # Определяем какие блоки являются целями обратных рёбер
    back_edge_targets: set[str] = {
        e.to_block for e in model.edges.values() if e.is_back_edge
    }

    routes: list[Route] = []
    route_counter = 0

    for block_id, block in model.blocks.items():
        if block.type != BlockType.SOURCE:
            continue

        route_counter += 1
        route = Route(
            route_id=f"R{route_counter}",
            source_block=block_id,
            detail_family=block.params.get("detail_type", ""),
        )

        # Обход графа от source по прямым рёбрам (DFS)
        visited:  set[str] = set()
        position_counter = 5

        def _dfs(current_id: str, incoming_detail_type: str = ""):
            nonlocal position_counter
            if current_id in visited:
                return
            visited.add(current_id)

            current = model.blocks[current_id]

            if current.type in POSITIONAL_TYPES:
                # Тип входа: сначала из входящей связи, потом из params блока
                in_type  = incoming_detail_type or current.params.get("input_type", "")
                out_type = current.params.get("output_type", in_type)

                step = RouteStep(
                    position=f"{position_counter:03d}",
                    block_id=current_id,
                    block_label=current.label,
                    block_type=current.type,
                    input_type=in_type,
                    output_type=out_type,
                    can_repeat=(current_id in back_edge_targets),
                )
                route.steps.append(step)
                position_counter += 5

            # Идём по прямым рёбрам дальше, передавая тип детали
            for edge in model.edges.values():
                if edge.from_block == current_id and not edge.is_back_edge:
                    _dfs(edge.to_block, edge.detail_type)

        _dfs(block_id)
        routes.append(route)

    return routes


def build_routes_dict(model: Model) -> dict[str, Route]:
    """Возвращает маршруты как словарь {route_id: Route}."""
    return {r.route_id: r for r in build_routes(model)}
