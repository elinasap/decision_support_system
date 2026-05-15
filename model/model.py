"""
model/model.py

Класс Model — центральный объект всей программы.

Хранит блоки и связи, предоставляет методы для:
  - добавления блоков и связей (с автоопределением петель)
  - топологической сортировки (для симулятора)
  - сериализации в dict (для JSON/Excel экспорта)
"""

from dataclasses import dataclass, field
from .types import BlockType
from .block import Block, make_ports
from .edge import Edge, is_back_edge as _detect_back_edge


@dataclass
class Model:
    name:         str
    detail_types: dict[str, dict]        # {"d_blank": {"label": "...", "unit": "шт"}}
    blocks:       dict[str, Block]       = field(default_factory=dict)
    edges:        dict[str, Edge]        = field(default_factory=dict)
    _block_counter: int                  = field(default=0, repr=False)
    _edge_counter:  int                  = field(default=0, repr=False)

    # ──────────────────────────────────────────────────────────────
    # Добавление блока
    # ──────────────────────────────────────────────────────────────

    def add_block(self, block_type: BlockType, label: str, params: dict) -> Block:
        """
        Создаёт блок, автоматически генерирует ID и порты.
        Возвращает созданный блок.
        """
        self._block_counter += 1
        bid = f"B{self._block_counter}"
        while bid in self.blocks:
            self._block_counter += 1
            bid = f"B{self._block_counter}"
        ports = make_ports(block_type, params)
        block = Block(id=bid, type=block_type, label=label,
                      params=params, ports=ports)
        self.blocks[bid] = block
        return block

    def remove_block(self, block_id: str) -> None:
        """Удаляет блок и все связанные с ним рёбра."""
        self.blocks.pop(block_id, None)
        to_remove = [eid for eid, e in self.edges.items()
                     if e.from_block == block_id or e.to_block == block_id]
        for eid in to_remove:
            self.edges.pop(eid)
    def update_block(self, block_id: str, label: str, params: dict) -> None:
        """
        Обновляет параметры существующего блока.
        Тип блока не меняется — смена типа ломает порты и связи.
        """
        block = self.blocks.get(block_id)
        if block is None:
            return
        block.label  = label
        block.params = params

    def renumber_block(self, old_id: str, new_id: str) -> bool:
        """
        Переименовывает блок и обновляет все ссылки на него в связях.
        Возвращает False если new_id уже занят.
        """
        if new_id in self.blocks or old_id not in self.blocks:
            return False
        # Переносим блок под новым ключом
        block = self.blocks.pop(old_id)
        block.id = new_id
        self.blocks[new_id] = block
        # Обновляем все рёбра
        for edge in self.edges.values():
            if edge.from_block == old_id:
                edge.from_block = new_id
            if edge.to_block == old_id:
                edge.to_block = new_id
        return True

    # ──────────────────────────────────────────────────────────────
    # Добавление связи
    # ──────────────────────────────────────────────────────────────

    def add_edge(self,
                 from_block:      str,
                 from_port:       str,
                 to_block:        str,
                 to_port:         str,
                 detail_type:     str   = "",
                 defect_type:     str   = "repairable",
                 repair_time_sec: float = 0.0,
                 comment:         str   = "") -> Edge:
        """
        Создаёт связь между портами двух блоков.

        Автоматически определяет is_back_edge:
        если связь замыкает цикл — помечает её как обратную.
        Помечает порты как использованные.
        """
        self._edge_counter += 1
        eid = f"E{self._edge_counter}"

        back = _detect_back_edge(from_block, to_block, self.edges)

        edge = Edge(
            id=eid,
            from_block=from_block, from_port=from_port,
            to_block=to_block,     to_port=to_port,
            is_back_edge=back,
            detail_type=detail_type,
            defect_type=defect_type,
            repair_time_sec=repair_time_sec,
            comment=comment,
        )
        self.edges[eid] = edge

        # Помечаем порты как занятые
        if from_block in self.blocks:
            self.blocks[from_block].ports.used.add(from_port)
        if to_block in self.blocks:
            self.blocks[to_block].ports.used.add(to_port)

        return edge

    def remove_edge(self, edge_id: str) -> None:
        """Удаляет связь и освобождает порты."""
        edge = self.edges.pop(edge_id, None)
        if edge is None:
            return
        if edge.from_block in self.blocks:
            self.blocks[edge.from_block].ports.used.discard(edge.from_port)
        if edge.to_block in self.blocks:
            self.blocks[edge.to_block].ports.used.discard(edge.to_port)

    # ──────────────────────────────────────────────────────────────
    # Топологическая сортировка (для симулятора)
    # ──────────────────────────────────────────────────────────────

    def topological_order(self) -> list[str]:
        """
        Возвращает список ID блоков в порядке обработки.

        Обратные рёбра (петли) игнорируются при сортировке —
        симулятор обрабатывает их отдельно как повторный вход.

        Использует алгоритм Кана (обход по in-degree).
        """
        in_degree = {bid: 0 for bid in self.blocks}
        for e in self.edges.values():
            if not e.is_back_edge:
                in_degree[e.to_block] += 1

        queue = [bid for bid, deg in in_degree.items() if deg == 0]
        order = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for e in self.edges.values():
                if e.from_block == node and not e.is_back_edge:
                    in_degree[e.to_block] -= 1
                    if in_degree[e.to_block] == 0:
                        queue.append(e.to_block)

        return order

    # ──────────────────────────────────────────────────────────────
    # Сериализация
    # ──────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Сериализует модель в JSON-совместимый словарь."""
        return {
            "name": self.name,
            "detail_types": self.detail_types,
            "blocks": {
                bid: {
                    "id":     b.id,
                    "type":   b.type.value,
                    "label":  b.label,
                    "params": b.params,
                    "ports": {
                        "in":   b.ports.in_ports,
                        "out":  b.ports.out_ports,
                        "used": list(b.ports.used),
                    },
                } for bid, b in self.blocks.items()
            },
            "edges": {
                eid: {
                    "id":              e.id,
                    "from_block":      e.from_block,
                    "from_port":       e.from_port,
                    "to_block":        e.to_block,
                    "to_port":         e.to_port,
                    "is_back_edge":    e.is_back_edge,
                    "detail_type":     e.detail_type,
                    "defect_type":     e.defect_type,
                    "repair_time_sec": e.repair_time_sec,
                    "comment":         e.comment,
                } for eid, e in self.edges.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Model":
        """Восстанавливает модель из словаря (загрузка из JSON)."""
        model = cls(name=data["name"], detail_types=data["detail_types"])
        for b in data["blocks"].values():
            block = Block(
                id=b["id"],
                type=BlockType(b["type"]),
                label=b["label"],
                params=b["params"],
            )
            block.ports.in_ports  = b["ports"]["in"]
            block.ports.out_ports = b["ports"]["out"]
            block.ports.used      = set(b["ports"]["used"])
            model.blocks[b["id"]] = block
            try:
                num = int(b["id"][1:])
                if num > model._block_counter:
                    model._block_counter = num
            except ValueError:
                pass
        for e in data["edges"].values():
            edge = Edge(
                id=e["id"],
                from_block=e["from_block"], from_port=e["from_port"],
                to_block=e["to_block"],     to_port=e["to_port"],
                is_back_edge=e["is_back_edge"],
                detail_type=e.get("detail_type", ""),
                defect_type=e.get("defect_type", "repairable"),
                repair_time_sec=e.get("repair_time_sec", e.get("repair_time_min", 0.0)),
                comment=e.get("comment", ""),
            )
            model.edges[e["id"]] = edge
            try:
                num = int(e["id"][1:])
                if num > model._edge_counter:
                    model._edge_counter = num
            except ValueError:
                pass
        return model
