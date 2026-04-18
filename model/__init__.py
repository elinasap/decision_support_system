"""
model/__init__.py

Публичный интерфейс пакета model.
Остальные модули программы импортируют только отсюда:

    from model import Model, Block, Edge, BlockType, EdgeType, PortSet
"""

from .types import BlockType, EdgeType, PortSet, BLOCK_TYPE_LABELS, BLOCK_TYPE_GROUPS, EDGE_TYPE_LABELS
from .block import Block, make_ports
from .edge  import Edge, is_back_edge
from .model import Model
from .route import Route, RouteStep, build_routes, build_routes_dict

__all__ = [
    "Model",
    "Block", "make_ports",
    "Edge",  "is_back_edge",
    "BlockType", "EdgeType", "PortSet",
    "BLOCK_TYPE_LABELS", "BLOCK_TYPE_GROUPS", "EDGE_TYPE_LABELS",
    "Route", "RouteStep", "build_routes", "build_routes_dict",
]
