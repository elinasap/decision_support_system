"""
export/json_export.py

Сохранение модели и маршрутов в JSON-файл.

Формат файла:
  {
    "model":  { ... },   — полная модель (blocks, edges, detail_types)
    "routes": [ ... ]    — список маршрутов, построенных из модели
  }

Этот файл используется:
  - для повторной загрузки модели (Model.from_dict)
  - как входные данные симулятора
"""

import json
from pathlib import Path
from model import Model, build_routes


def export_json(model: Model, path: str | Path) -> None:
    """
    Сериализует модель и маршруты в JSON и сохраняет в файл.

    Параметры:
        model — объект Model
        path  — путь к файлу (.json)
    """
    path = Path(path)
    data = _build_export_dict(model)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_json_string(model: Model) -> str:
    """Возвращает JSON как строку (для отображения в GUI)."""
    return json.dumps(_build_export_dict(model), ensure_ascii=False, indent=2)


def _build_export_dict(model: Model) -> dict:
    """Собирает словарь для сериализации."""
    routes = build_routes(model)

    return {
        "model": model.to_dict(),
        "routes": [
            {
                "route_id":      r.route_id,
                "source_block":  r.source_block,
                "detail_family": r.detail_family,
                "steps": [
                    {
                        "position":    s.position,
                        "block_id":    s.block_id,
                        "block_label": s.block_label,
                        "block_type":  s.block_type.value,
                        "input_type":  s.input_type,
                        "output_type": s.output_type,
                        "can_repeat":  s.can_repeat,
                    }
                    for s in r.steps
                ],
            }
            for r in routes
        ],
    }
