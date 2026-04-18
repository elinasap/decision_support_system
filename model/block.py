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
      SOURCE  — только out1
      BUFFER  — in1 + out1  (промежуточный буфер)
      SINK    — только in1

    Транспортировка:
      TRANSPORT — in1 + out1

    Тех. операции:
      PROCESS  — in1..inN + out_good [+ out_defect]
                 N задаётся params["inputs_count"], по умолчанию 1
      ASSEMBLY — in1..inN + out_good
                 N задаётся params["inputs_count"], по умолчанию 2

    Контроль:
      CONTROL — in1 + out_good + out_defect
    """
    if block_type == BlockType.SOURCE:
        return PortSet(in_ports=[], out_ports=["out1"])

    if block_type == BlockType.BUFFER:
        return PortSet(in_ports=["in1"], out_ports=["out1"])

    if block_type == BlockType.SINK:
        return PortSet(in_ports=["in1"], out_ports=[])

    if block_type == BlockType.TRANSPORT:
        return PortSet(in_ports=["in1"], out_ports=["out1"])

    if block_type == BlockType.PROCESS:
        # inputs_count >= 1, по умолчанию 1
        n = max(1, int(params.get("inputs_count", 1)))
        in_ports = [f"in{i+1}" for i in range(n)]
        out_ports = ["out_good"]
        if params.get("has_defect_output", False):
            out_ports.append("out_defect")
        return PortSet(in_ports=in_ports, out_ports=out_ports)

    if block_type == BlockType.ASSEMBLY:
        n = max(2, int(params.get("inputs_count", 2)))
        return PortSet(
            in_ports=[f"in{i+1}" for i in range(n)],
            out_ports=["out_good"],
        )

    if block_type == BlockType.CONTROL:
        return PortSet(in_ports=["in1"], out_ports=["out_good", "out_defect"])

    return PortSet()
