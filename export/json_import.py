"""
export/json_import.py

Загрузка модели из JSON-файла, созданного export_json().

Поддерживает два формата:
  - {"model": {...}, "routes": [...]}  — полный экспорт
  - {...}                               — только словарь модели
"""

import json
from pathlib import Path
from model import Model


def import_json(path: str | Path) -> Model:
    """
    Читает JSON-файл и восстанавливает объект Model.

    Параметры:
        path — путь к .json файлу

    Возвращает:
        Model
    """
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    model_data = data.get("model", data)
    return Model.from_dict(model_data)
