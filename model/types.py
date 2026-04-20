"""
model/types.py

Базовые типы данных модели: перечисления и PortSet.
"""

from enum import Enum
from dataclasses import dataclass, field


class BlockType(Enum):
    # Хранение
    SOURCE    = "source"     # только out — источник деталей
    BUFFER    = "buffer"     # in + out  — промежуточный буфер/склад
    SINK      = "sink"       # только in — конечный приёмник
    # Транспортировка
    TRANSPORT = "transport"
    # Техоперации
    PROCESS   = "process"    # обработка (один основной вход)
    ASSEMBLY  = "assembly"   # сборка (несколько входов)
    # Контроль
    CONTROL   = "control"


class EdgeType(Enum):
    NORMAL = "normal"
    RETURN = "return"


BLOCK_TYPE_LABELS = {
    BlockType.SOURCE:    "Источник (только выход)",
    BlockType.BUFFER:    "Буфер / промежуточный склад",
    BlockType.SINK:      "Приёмник (только вход)",
    BlockType.TRANSPORT: "Транспортировка",
    BlockType.PROCESS:   "Обработка (тех. операция)",
    BlockType.ASSEMBLY:  "Сборка",
    BlockType.CONTROL:   "Контроль / ОТК",
}

# Группировка для GUI — двухуровневое меню выбора типа
BLOCK_TYPE_GROUPS = {
    "Хранение":       [BlockType.SOURCE, BlockType.BUFFER, BlockType.SINK],
    "Транспортировка":[BlockType.TRANSPORT],
    "Тех. операция":  [BlockType.PROCESS, BlockType.ASSEMBLY],
    "Контроль":       [BlockType.CONTROL],
}

EDGE_TYPE_LABELS = {
    EdgeType.NORMAL: "Обычная",
    EdgeType.RETURN: "Возврат (обратная связь)",
}


@dataclass
class PortSet:
    in_ports:  list[str] = field(default_factory=list)
    out_ports: list[str] = field(default_factory=list)
    used:      set[str]  = field(default_factory=set)

    def all_ports(self):
        return self.in_ports + self.out_ports

    def is_port_used(self, port):
        return port in self.used

    def unused_ports(self):
        return [p for p in self.all_ports() if p not in self.used]
