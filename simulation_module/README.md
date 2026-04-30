# Модуль имитационного моделирования (simulation/)

Реализация четырех конечных автоматов для дискретно-событийной симуляции
производственного процесса.

## Куда положить файлы

Из корня твоего проекта (`project_v2/project/`):

```
project_v2/project/
├── model/              (уже существует)
├── gui/                (уже существует)
├── validation/         (уже существует)
├── export/             (уже существует)
├── simulation/         ← скопировать содержимое папки simulation/ из архива
└── tests/              ← скопировать содержимое папки tests/ из архива
```

То есть содержимое архива переносится напрямую в корень проекта — папки
`simulation/` и `tests/` встают рядом с уже существующими.

## Структура

```
simulation/
├── __init__.py
├── detail_instance.py         — DetailInstance, VisitRecord, DetailQualityState
├── buffer_state.py            — runtime для BUFFER (count, capacity, очередь)
├── block_operation_state.py   — runtime для блока техоперации
└── automata/
    ├── __init__.py
    ├── base.py                — StateMachine, Transition, исключения
    ├── phase.py               — A_phase  (фаза детали в блоке)
    ├── buffer.py              — A_buffer (хранилище)
    ├── block.py               — A_op    (блок техоперации)
    └── quality.py             — A_qual  (качество детали)

tests/
├── __init__.py
├── conftest.py                — настройка путей для pytest
└── simulation/
    ├── __init__.py
    ├── test_phase.py
    ├── test_buffer.py
    ├── test_block.py
    └── test_quality.py
```

## Зависимости

Только для тестов:
```
pip install pytest
```

Сам модуль использует только стандартную библиотеку Python (dataclasses, enum,
collections, typing).

## Запуск тестов

Из корня проекта:
```
pytest tests/
```

Или для конкретного автомата:
```
pytest tests/simulation/test_phase.py
pytest tests/simulation/test_buffer.py
pytest tests/simulation/test_block.py
pytest tests/simulation/test_quality.py
```

## Что нужно поправить в существующем коде

Чтобы автомат качества работал, в словаре `model.detail_types` должно быть
поле `max_repair`:

```python
detail_types = {
    "d_blank": {"label": "Заготовка", "unit": "шт", "max_repair": 2},
    "d_shaft": {"label": "Вал",       "unit": "шт", "max_repair": 0},
}
```

`max_repair = 0` означает «деталь не подлежит ремонту» (любой брак сразу
в утиль). Существующий код, обращающийся к detail_types без ключа max_repair,
продолжит работать благодаря использованию `.get("max_repair", 0)`.

Места для правки:
- gui/tab_blocks.py — добавить поле «Максимум ремонтов» в форму типа детали
- export/excel_export.py — добавить колонку max_repair в лист типов деталей
- export/json_export.py — изменений не требуется (max_repair уйдет автоматом)

## Краткое описание автоматов

- **A_phase**  — фаза детали в блоке: WAITING → PROCESSING → DONE
- **A_buffer** — состояние хранилища: EMPTY → HAS_ITEMS → FULL
- **A_op**     — состояние блока техоперации: IDLE / BUSY / BLOCKED
- **A_qual**   — качество детали: UNCHECKED / DEFECTIVE / REPAIRED / ACCEPTED / SCRAPPED

Все четыре автомата работают параллельно и синхронизируются через события.
Подробное описание — в документе «итог_диалога.docx».
