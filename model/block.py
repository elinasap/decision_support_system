"""
model/block.py

Класс Block и фабрика портов make_ports().
"""

from dataclasses import dataclass, field
from .types import BlockType, PortSet


@dataclass
class Block:
    id:     str
    type:   BlockType
    label:  str
    params: dict
    ports:  PortSet = field(default_factory=PortSet)

    def __post_init__(self):
        if not self.ports.in_ports and not self.ports.out_ports:
            self.ports = make_ports(self.type, self.params)

    def display_name(self):
        return f"{self.id}: {self.label}"


def make_ports(block_type: BlockType, params: dict) -> PortSet:
    """
    Создаёт порты для каждого типа блока.

    Хранение:
      SOURCE    — только out
      BUFFER    — in + out  (может иметь несколько входов через in1..inN)
      SINK      — только in

    Транспортировка:
      TRANSPORT — in + out

    Тех. операции:
      PROCESS   — in + out  [+ out_defect если has_internal_control=True]
      ASSEMBLY  — in1..inN + out_good
                  N задаётся params["inputs_count"], по умолчанию 2

    Контроль:
      CONTROL   — in + out_good + out_defect
    """
    if block_type == BlockType.SOURCE:
        return PortSet(in_ports=[], out_ports=["out"])

    if block_type == BlockType.BUFFER:
        n = max(1, int(params.get("inputs_count", 1)))
        in_ports = [f"in{i+1}" for i in range(n)] if n > 1 else ["in"]
        return PortSet(in_ports=in_ports, out_ports=["out"])

    if block_type == BlockType.SINK:
        return PortSet(in_ports=["in"], out_ports=[])

    if block_type == BlockType.TRANSPORT:
        return PortSet(in_ports=["in"], out_ports=["out"])

    if block_type == BlockType.PROCESS:
        out_ports = ["out"]
        if params.get("has_internal_control", False):
            out_ports.append("out_defect")
        return PortSet(in_ports=["in"], out_ports=out_ports)

    if block_type == BlockType.ASSEMBLY:
        n = max(2, int(params.get("inputs_count", 2)))
        return PortSet(
            in_ports=[f"in{i+1}" for i in range(n)],
            out_ports=["out_good"],
        )

    if block_type == BlockType.CONTROL:
        return PortSet(in_ports=["in"], out_ports=["out_good", "out_defect"])

    return PortSet()
