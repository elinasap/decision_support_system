"""
model/__init__.py

Публичный интерфейс пакета model.
Остальные модули программы импортируют только отсюда:

    from model import Model, Block, Edge, BlockType, PortSet
"""

from .types import BlockType, PortSet, BLOCK_TYPE_LABELS, BLOCK_TYPE_GROUPS
from .block import Block, make_ports
from .edge  import Edge, is_back_edge
from .model import Model
from .route import Route, RouteStep, build_routes, build_routes_dict

__all__ = [
    "Model",
    "Block", "make_ports",
    "Edge",  "is_back_edge",
    "BlockType", "PortSet",
    "BLOCK_TYPE_LABELS", "BLOCK_TYPE_GROUPS",
    "Route", "RouteStep", "build_routes", "build_routes_dict",
]
