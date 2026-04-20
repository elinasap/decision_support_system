# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the application

```bash
cd project_v2/project
python main.py
```

Dependencies: `tkinter` (built-in), `openpyxl` (install via `pip install openpyxl`).

## Architecture

This is a Tkinter desktop application for building production unit (ПУ) models as directed graphs, targeted at small-batch manufacturing decision support.

### Layer overview

```
gui/          → Tkinter UI (4 tabs)
model/        → Pure-Python data model (no UI dependency)
validation/   → 4-level validator operating on Model
export/       → JSON and Excel writers
main.py       → Entry point: instantiates App and calls mainloop()
```

### Model layer (`model/`)

`Model` is the central object. It owns two dicts: `blocks: dict[str, Block]` and `edges: dict[str, Edge]`. IDs are auto-incremented strings (`B1`, `B2`, `E1`, `E2`…).

- **Block types** (`BlockType` enum): `SOURCE`, `BUFFER`, `SINK`, `TRANSPORT`, `PROCESS`, `ASSEMBLY`, `CONTROL`
- **Edge types** (`EdgeType` enum): `NORMAL`, `RETURN`. Дефектный маршрут не является отдельным типом — он определяется по имени исходящего порта (`out_defect`). Обратное ребро определяется автоматически (`is_back_edge = True`) и соответствует типу `RETURN`.
- `make_ports(block_type, params)` in `block.py` auto-generates named port lists from block type and params (e.g., ASSEMBLY gets one `in_` port per `num_inputs` param).
- `is_back_edge()` in `edge.py` uses DFS over existing edges to detect whether a new edge closes a cycle (used for defect-return loops).
- `Model.topological_order()` runs Kahn's algorithm ignoring back-edges, producing the simulation processing order.
- `Model.to_dict()` / `Model.from_dict()` serialize the entire model to/from JSON-compatible dicts. This JSON is the interface consumed by the Step 2 optimizer.

### GUI layer (`gui/`)

`App` (in `app.py`) is a `ttk.Notebook` with four tabs; each tab is a separate class:

| Tab | Class | File | Purpose |
|-----|-------|------|---------|
| 1 | `BlocksTab` | `tab_blocks.py` | Manage detail types + blocks; dynamic forms via `_BLOCK_FIELDS` |
| 2 | `EdgesTab` | `tab_edges.py` | Create/delete edges; shows block/port selectors |
| 3 | `SchemaTab` | `tab_schema.py` | Draws the graph on a `tk.Canvas` |
| 4 | `ExportTab` | `tab_export.py` | Triggers validation then JSON/Excel export |

`_BLOCK_FIELDS` in `tab_blocks.py` is the single source of truth for which params each block type exposes in the UI. Field widget types: `"entry"`, `"spinbox"`, `"combo_detail"` (populated from `model.detail_types`).

### Validation layer (`validation/`)

`validate(model)` runs four checks in sequence and merges results into one `ValidationResult`:

1. `check_ports` — no unconnected ports (SOURCE input and SINK output are exempted)
2. `check_edges` — no duplicates, no self-loops, correct port directions, fan-in ≤ 1 per input port
3. `check_operations` — PROCESS/ASSEMBLY/TRANSPORT param presence; model must have ≥1 SOURCE and ≥1 SINK
4. `check_control` — `defect_prob ∈ [0,1)`, `threshold ∈ [0,1]`, `out_defect` port must be connected

### Export layer (`export/`)

- `json_export.py` — calls `model.to_dict()` and writes JSON; this file is the Step 2 interface
- `excel_export.py` — writes 4 sheets: detail types, blocks, edges, auto-generated route cards

Route cards are built by `model/route.py` (`build_routes()`): DFS from each SOURCE block, skipping back-edges, producing ordered `RouteStep` lists.

## Key constraints from the formal specification

- Each input port accepts **at most one** incoming edge (enforced in `check_edges`).
- Every valid model must contain at least one SOURCE and one SINK block.
- CONTROL block params: `defect_prob` (technologist estimate, float in `[0,1)`) and `threshold` (strictness, float in `[0,1]`).
- SOURCE block param: `capacity` (initial stock, int). No `volume` or `replenishment_time`.
- The JSON export format is the stable interface between Step 1 (this project) and Step 2 (optimizer). Do not rename top-level keys or edge fields without updating the optimizer.
