"""
model/edge.py

Класс Edge и функция is_back_edge().
"""

from dataclasses import dataclass
from .types import EdgeType


@dataclass
class Edge:
    id:              str
    from_block:      str
    from_port:       str
    to_block:        str
    to_port:         str
    is_back_edge:    bool     = False
    edge_type:       EdgeType = EdgeType.NORMAL
    detail_type:     str      = ""
    defect_type:     str      = "repairable"
    repair_time_min: float    = 0.0
    comment:         str      = ""

    def display_name(self) -> str:
        return f"{self.from_block}.{self.from_port} -> {self.to_block}.{self.to_port}"


def is_back_edge(from_id: str, to_id: str, existing_edges: dict) -> bool:
    """DFS: True если из to_id можно дойти до from_id по прямым рёбрам."""
    visited = set()
    stack = [to_id]
    while stack:
        current = stack.pop()
        if current == from_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        for edge in existing_edges.values():
            if edge.from_block == current and not edge.is_back_edge:
                stack.append(edge.to_block)
    return False
