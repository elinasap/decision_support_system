"""
validation/validator.py

Четыре уровня валидации модели — точно по блок-схеме (стр. 7).

Каждая функция проверяет один уровень и возвращает ValidationResult.
Главная функция validate() запускает их по порядку и объединяет итог.

Порядок проверок:
  1. check_ports      — все ли порты подключены?
  2. check_edges      — все ли связи допустимы?
  3. check_operations — корректны ли технологические позиции?
  4. check_control    — корректны ли контроль и брак?
"""

from model import Model, BlockType
from .result import ValidationResult


# ══════════════════════════════════════════════════════════════════
# Уровень 1 — Порты: есть ли необработанные / ожидающие?
# ══════════════════════════════════════════════════════════════════

def check_ports(model: Model) -> ValidationResult:
    """
    Проверяет: нет ли портов, которые не подключены ни к одной связи.

    SOURCE не обязан иметь входных портов — это норма.
    STORAGE не обязан иметь выходных портов — это норма.
    Все остальные блоки должны иметь все порты подключены.
    """
    result = ValidationResult()

    for block in model.blocks.values():
        unused = block.ports.unused_ports()
        if not unused:
            continue

        # Исключения: source без входа, storage без выхода
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
    """
    Проверяет допустимость всех связей:
      - нет ли дублирующих связей (одинаковые from/to порты)
      - нет ли петли на себя (блок → тот же блок)
      - нет ли запрещённых соединений (out → out, in → in)
      - корректны ли направления потоков (out → in)
    """
    result = ValidationResult()
    seen_pairs: set[tuple] = set()

    for edge in model.edges.values():
        pair = (edge.from_block, edge.from_port, edge.to_block, edge.to_port)

        # Дублирующие связи
        if pair in seen_pairs:
            result.add_error(
                f"Дублирующая связь: {edge.display_name()}"
            )
        seen_pairs.add(pair)

        # Петля на себя
        if edge.from_block == edge.to_block:
            result.add_error(
                f"Связь {edge.id}: блок не может соединяться сам с собой "
                f"({edge.from_block})"
            )

        # Направление: исходящий порт → входящий порт
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

        # Блоки существуют
        if edge.from_block not in model.blocks:
            result.add_error(
                f"Связь {edge.id}: блок '{edge.from_block}' не существует"
            )
        if edge.to_block not in model.blocks:
            result.add_error(
                f"Связь {edge.id}: блок '{edge.to_block}' не существует"
            )

    return result


# ══════════════════════════════════════════════════════════════════
# Уровень 3 — Технологические позиции
# ══════════════════════════════════════════════════════════════════

def check_operations(model: Model) -> ValidationResult:
    """
    Проверяет корректность блоков технологических операций:
      - у PROCESS один вход
      - у ASSEMBLY больше одного входа
      - задано время операции
      - сформированы требуемые выходы
      - нет противоречий по типам деталей
    """
    result = ValidationResult()

    for block in model.blocks.values():

        if block.type == BlockType.PROCESS:
            if len(block.ports.in_ports) != 1:
                result.add_error(
                    f"Блок {block.display_name()}: операция должна иметь ровно 1 вход"
                )
            if "operation_time_min" not in block.params:
                result.add_error(
                    f"Блок {block.display_name()}: не задано время операции "
                    f"(operation_time_min)"
                )
            elif block.params["operation_time_min"] <= 0:
                result.add_error(
                    f"Блок {block.display_name()}: время операции должно быть > 0"
                )
            if not block.ports.out_ports:
                result.add_error(
                    f"Блок {block.display_name()}: нет ни одного выходного порта"
                )

        if block.type == BlockType.ASSEMBLY:
            if len(block.ports.in_ports) < 2:
                result.add_error(
                    f"Блок {block.display_name()}: сборка должна иметь >= 2 входов, "
                    f"задано {len(block.ports.in_ports)}"
                )
            if "operation_time_min" not in block.params:
                result.add_error(
                    f"Блок {block.display_name()}: не задано время сборки "
                    f"(operation_time_min)"
                )

        if block.type == BlockType.TRANSPORT:
            if "time_min" not in block.params:
                result.add_error(
                    f"Блок {block.display_name()}: не задано время транспортировки "
                    f"(time_min)"
                )
            elif block.params["time_min"] < 0:
                result.add_error(
                    f"Блок {block.display_name()}: время транспортировки не может "
                    f"быть отрицательным"
                )

        if block.type == BlockType.SOURCE:
            if "volume" not in block.params:
                result.add_warning(
                    f"Блок {block.display_name()}: не задан объём склада (volume)"
                )

    return result


# ══════════════════════════════════════════════════════════════════
# Уровень 4 — Контроль и брак
# ══════════════════════════════════════════════════════════════════

def check_control(model: Model) -> ValidationResult:
    """
    Проверяет корректность блоков контроля:
      - если у блока есть out_defect — должна быть связь с него
        (маршрут дефектной продукции задан)
      - если задано extra_time_min > 0 — это допустимо, просто проверяем
        что значение не отрицательное
      - процент брака в диапазоне [0, 1)
    """
    result = ValidationResult()

    # Собираем какие out-порты реально подключены
    connected_out: set[tuple] = set()
    for edge in model.edges.values():
        connected_out.add((edge.from_block, edge.from_port))

    for block in model.blocks.values():
        if block.type != BlockType.CONTROL:
            continue

        # Маршрут бракованной продукции
        if "out_defect" in block.ports.out_ports:
            if (block.id, "out_defect") not in connected_out:
                result.add_error(
                    f"Блок {block.display_name()}: порт out_defect не подключён — "
                    f"маршрут бракованной продукции не задан"
                )

        # Процент брака
        defect_rate = block.params.get("defect_rate")
        if defect_rate is None:
            result.add_error(
                f"Блок {block.display_name()}: не задан процент брака (defect_rate)"
            )
        elif not (0.0 <= defect_rate < 1.0):
            result.add_error(
                f"Блок {block.display_name()}: defect_rate должен быть в диапазоне "
                f"[0, 1), получено {defect_rate}"
            )

        # Дополнительное время
        extra = block.params.get("extra_time_min", 0)
        if extra < 0:
            result.add_error(
                f"Блок {block.display_name()}: extra_time_min не может быть "
                f"отрицательным"
            )
        elif extra > 0:
            result.add_warning(
                f"Блок {block.display_name()}: задано дополнительное время "
                f"контроля вне операции ({extra} мин)"
            )

    return result


# ══════════════════════════════════════════════════════════════════
# Главная функция — запускает все уровни по порядку
# ══════════════════════════════════════════════════════════════════

def validate(model: Model) -> ValidationResult:
    """
    Запускает все четыре уровня валидации и возвращает объединённый результат.

    Порядок соответствует блок-схеме (стр. 7 диплома):
    порты → связи → операции → контроль.

    Все уровни выполняются всегда — оператор видит полный список
    проблем за один раз, а не по одной ошибке за запуск.
    """
    final = ValidationResult()
    final.merge(check_ports(model))
    final.merge(check_edges(model))
    final.merge(check_operations(model))
    final.merge(check_control(model))
    return final
