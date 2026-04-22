"""
validation/validator.py

Четыре уровня валидации модели.

Порядок проверок:
  1. check_ports      — все ли порты подключены?
  2. check_edges      — все ли связи допустимы?
  3. check_operations — корректны ли технологические позиции?
  4. check_control    — корректны ли контроль и брак?
"""

from model import Model, BlockType
from .result import ValidationResult


# ══════════════════════════════════════════════════════════════════
# Уровень 1 — Порты: есть ли неподключённые?
# ══════════════════════════════════════════════════════════════════

def check_ports(model: Model) -> ValidationResult:
    result = ValidationResult()

    for block in model.blocks.values():
        unused = block.ports.unused_ports()
        if not unused:
            continue

        filtered = []
        for port in unused:
            if block.type == BlockType.SOURCE and port.startswith("in"):
                continue
            if block.type == BlockType.SINK and port.startswith("out"):
                continue
            filtered.append(port)

        if filtered:
            result.add_error(
                f"Блок {block.display_name()}: незакрытые порты: {', '.join(filtered)}"
            )

    return result


# ══════════════════════════════════════════════════════════════════
# Уровень 2 — Связи: дубли, висячие, запрещённые направления
# ══════════════════════════════════════════════════════════════════

def check_edges(model: Model) -> ValidationResult:
    result = ValidationResult()
    seen_pairs: set[tuple] = set()
    in_port_count: dict[tuple, int] = {}

    for edge in model.edges.values():
        key = (edge.to_block, edge.to_port)
        in_port_count[key] = in_port_count.get(key, 0) + 1
        pair = (edge.from_block, edge.from_port, edge.to_block, edge.to_port)

        if pair in seen_pairs:
            result.add_error(f"Дублирующая связь: {edge.display_name()}")
        seen_pairs.add(pair)

        if edge.from_block == edge.to_block:
            result.add_error(
                f"Связь {edge.id}: блок не может соединяться сам с собой "
                f"({edge.from_block})"
            )

        if not edge.from_port.startswith("out"):
            result.add_error(
                f"Связь {edge.id}: источник должен быть выходным портом, "
                f"получен '{edge.from_port}'"
            )
        if not edge.to_port.startswith("in"):
            result.add_error(
                f"Связь {edge.id}: получатель должен быть входным портом, "
                f"получен '{edge.to_port}'"
            )

        if edge.from_block not in model.blocks:
            result.add_error(f"Связь {edge.id}: блок '{edge.from_block}' не существует")
        if edge.to_block not in model.blocks:
            result.add_error(f"Связь {edge.id}: блок '{edge.to_block}' не существует")

        # Проверка совместимости типа детали с блоком-получателем (формализация п.6, ограничение №4)
        if edge.detail_type and edge.to_block in model.blocks:
            to_block = model.blocks[edge.to_block]
            allowed = set()
            allowed.add(to_block.params.get("detail_type", ""))
            allowed.add(to_block.params.get("input_type", ""))
            for t in to_block.params.get("input_types", []):
                allowed.add(t)
            allowed.discard("")
            if allowed and edge.detail_type not in allowed:
                result.add_error(
                    f"Связь {edge.id}: тип детали '{edge.detail_type}' не совместим "
                    f"с блоком-получателем {to_block.display_name()} "
                    f"(ожидается один из: {', '.join(sorted(allowed))})"
                )

    # Ограничение §11.1: один входной порт — не более одной входящей связи
    for (block_id, port), count in in_port_count.items():
        if count > 1:
            result.add_error(
                f"Порт {block_id}.{port}: более одной входящей связи ({count})"
            )

    return result


# ══════════════════════════════════════════════════════════════════
# Уровень 3 — Технологические позиции
# ══════════════════════════════════════════════════════════════════

def check_operations(model: Model) -> ValidationResult:
    result = ValidationResult()

    has_source = any(b.type == BlockType.SOURCE for b in model.blocks.values())
    has_sink   = any(b.type == BlockType.SINK   for b in model.blocks.values())
    if not has_source:
        result.add_error("В модели нет ни одного блока SOURCE (источника деталей)")
    if not has_sink:
        result.add_error("В модели нет ни одного блока SINK (приёмника деталей)")

    for block in model.blocks.values():

        if block.type == BlockType.PROCESS:
            if len(block.ports.in_ports) != 1:
                result.add_error(
                    f"Блок {block.display_name()}: операция должна иметь ровно 1 вход"
                )
            if "operation_time_sec" not in block.params:
                result.add_error(
                    f"Блок {block.display_name()}: не задано время операции "
                    f"(operation_time_sec)"
                )
            elif block.params["operation_time_sec"] <= 0:
                result.add_error(
                    f"Блок {block.display_name()}: время операции должно быть > 0"
                )
            if not block.ports.out_ports:
                result.add_error(
                    f"Блок {block.display_name()}: нет ни одного выходного порта"
                )
            # out_defect требует has_internal_control=True и defect_rate
            if "out_defect" in block.ports.out_ports:
                if not block.params.get("has_internal_control", False):
                    result.add_error(
                        f"Блок {block.display_name()}: порт out_defect есть, но "
                        f"has_internal_control не установлен"
                    )
                if "defect_rate" not in block.params:
                    result.add_error(
                        f"Блок {block.display_name()}: has_internal_control=True, "
                        f"но не задан defect_rate"
                    )

        if block.type == BlockType.ASSEMBLY:
            if len(block.ports.in_ports) < 2:
                result.add_error(
                    f"Блок {block.display_name()}: сборка должна иметь >= 2 входов, "
                    f"задано {len(block.ports.in_ports)}"
                )
            if "operation_time_sec" not in block.params:
                result.add_error(
                    f"Блок {block.display_name()}: не задано время сборки "
                    f"(operation_time_sec)"
                )

        if block.type == BlockType.TRANSPORT:
            if "time_sec" not in block.params:
                result.add_error(
                    f"Блок {block.display_name()}: не задано время транспортировки "
                    f"(time_sec)"
                )
            elif block.params["time_sec"] < 0:
                result.add_error(
                    f"Блок {block.display_name()}: время транспортировки не может "
                    f"быть отрицательным"
                )

        if block.type == BlockType.SOURCE:
            if "capacity" not in block.params:
                result.add_warning(
                    f"Блок {block.display_name()}: не задана ёмкость склада (capacity)"
                )

    return result


# ══════════════════════════════════════════════════════════════════
# Уровень 4 — Контроль и брак
# ══════════════════════════════════════════════════════════════════

def check_control(model: Model) -> ValidationResult:
    result = ValidationResult()

    connected_out: set[tuple] = set()
    for edge in model.edges.values():
        connected_out.add((edge.from_block, edge.from_port))

    for block in model.blocks.values():
        if block.type != BlockType.CONTROL:
            continue

        if "out_defect" in block.ports.out_ports:
            if (block.id, "out_defect") not in connected_out:
                result.add_error(
                    f"Блок {block.display_name()}: порт out_defect не подключён — "
                    f"маршрут бракованной продукции не задан"
                )

        defect_prob = block.params.get("defect_prob")
        if defect_prob is None:
            result.add_error(
                f"Блок {block.display_name()}: не задана доля брака (defect_prob)"
            )
        elif not (0.0 <= defect_prob < 1.0):
            result.add_error(
                f"Блок {block.display_name()}: defect_prob должен быть в диапазоне "
                f"[0, 1), получено {defect_prob}"
            )

        threshold = block.params.get("threshold")
        if threshold is None:
            result.add_error(
                f"Блок {block.display_name()}: не задан порог контроля (threshold)"
            )
        elif not (0.0 <= threshold <= 1.0):
            result.add_error(
                f"Блок {block.display_name()}: threshold должен быть в диапазоне "
                f"[0, 1], получено {threshold}"
            )

    return result


# ══════════════════════════════════════════════════════════════════
# Главная функция
# ══════════════════════════════════════════════════════════════════

def validate(model: Model) -> ValidationResult:
    final = ValidationResult()
    final.merge(check_ports(model))
    final.merge(check_edges(model))
    final.merge(check_operations(model))
    final.merge(check_control(model))
    return final
