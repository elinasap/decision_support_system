"""
gui/tab_blocks.py

Вкладка 1 — «Детали и блоки».

Две секции:
  - Типы деталей: добавить ID + название + ед. изм. (combobox), удалить
  - Блоки участка: таблица, кнопки добавить / редактировать / удалить

Диалог добавления/редактирования блока открывается в отдельном окне.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from model import BlockType, BLOCK_TYPE_LABELS, BLOCK_TYPE_GROUPS


_TYPE_CLR = {
    BlockType.SOURCE:    "#E2EFDA",
    BlockType.BUFFER:    "#D5F0E8",
    BlockType.SINK:      "#F1EFE8",
    BlockType.TRANSPORT: "#EBF3FB",
    BlockType.PROCESS:   "#DCE6F1",
    BlockType.ASSEMBLY:  "#E8D5F5",
    BlockType.CONTROL:   "#FFF2CC",
}

_CLR_BG     = "#F8F7F5"
_CLR_HDR    = "#2F5496"
_FONT       = ("Arial", 10)
_FONT_BOLD  = ("Arial", 10, "bold")
_FONT_SMALL = ("Arial", 9)

_UNIT_OPTIONS = ["шт", "кг", "г", "м", "м²", "м³", "л", "мл", "компл."]


class TabBlocks(tk.Frame):
    """Содержимое вкладки 1."""

    def __init__(self, parent: tk.Frame, app):
        super().__init__(parent, bg=_CLR_BG)
        self.app = app
        self.pack(fill="both", expand=True)
        self._build_ui()

    # ── Построение интерфейса ─────────────────────────────────────────────────

    def _build_ui(self):
        outer = tk.Frame(self, bg=_CLR_BG)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Секция 1: Типы деталей ──────────────────────────────────────────
        self._build_section_label(outer, "Типы деталей")

        det_area = tk.Frame(outer, bg=_CLR_BG)
        det_area.pack(fill="x", pady=(4, 12))

        row_in = tk.Frame(det_area, bg=_CLR_BG)
        row_in.pack(fill="x")

        tk.Label(row_in, text="ID", font=_FONT, bg=_CLR_BG, width=4).pack(side="left")
        self._det_id = tk.Entry(row_in, font=_FONT, width=14)
        self._det_id.pack(side="left", padx=(4, 10))

        tk.Label(row_in, text="Название", font=_FONT, bg=_CLR_BG).pack(side="left")
        self._det_label = tk.Entry(row_in, font=_FONT, width=28)
        self._det_label.pack(side="left", padx=(4, 10))

        tk.Label(row_in, text="Ед. изм.", font=_FONT, bg=_CLR_BG).pack(side="left")
        self._det_unit = ttk.Combobox(
            row_in, font=_FONT, width=8,
            values=_UNIT_OPTIONS, state="readonly",
        )
        self._det_unit.set("шт")
        self._det_unit.pack(side="left", padx=(4, 10))

        tk.Label(row_in, text="Макс. ремонтов", font=_FONT, bg=_CLR_BG).pack(side="left")
        self._det_max_repair = tk.Spinbox(
            row_in, from_=0, to=99, font=_FONT, width=5,
        )
        self._det_max_repair.delete(0, "end")
        self._det_max_repair.insert(0, "0")
        self._det_max_repair.pack(side="left", padx=(4, 10))

        tk.Button(
            row_in, text="+ Добавить", font=_FONT, relief="flat",
            bg="#534AB7", fg="white", padx=8, pady=2, cursor="hand2",
            command=self._add_detail,
        ).pack(side="left")

        self._det_tags_frame = tk.Frame(det_area, bg=_CLR_BG)
        self._det_tags_frame.pack(fill="x", pady=(8, 0))

        # ── Секция 2: Блоки ─────────────────────────────────────────────────
        self._build_section_label(outer, "Блоки участка")

        btn_row = tk.Frame(outer, bg=_CLR_BG)
        btn_row.pack(fill="x", pady=(4, 6))

        tk.Button(
            btn_row, text="+ Добавить блок", font=_FONT, relief="flat",
            bg="#534AB7", fg="white", padx=8, pady=2, cursor="hand2",
            command=self._open_block_dialog,
        ).pack(side="left")

        tk.Button(
            btn_row, text="Редактировать", font=_FONT, relief="flat",
            bg=_CLR_BG, padx=8, pady=2, cursor="hand2",
            command=self._edit_selected_block,
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            btn_row, text="Удалить", font=_FONT, relief="flat",
            bg=_CLR_BG, padx=8, pady=2, cursor="hand2",
            command=self._delete_selected_block,
        ).pack(side="left", padx=(8, 0))

        cols = ("id", "type", "label", "in_type", "out_type")
        self._tree = ttk.Treeview(
            outer, columns=cols, show="headings", height=12,
            selectmode="browse",
        )
        self._tree.heading("id",      text="ID")
        self._tree.heading("type",    text="Тип")
        self._tree.heading("label",   text="Наименование")
        self._tree.heading("in_type", text="Вх. деталь")
        self._tree.heading("out_type",text="Вых. деталь")

        self._tree.column("id",      width=60,  anchor="center")
        self._tree.column("type",    width=130, anchor="center")
        self._tree.column("label",   width=260)
        self._tree.column("in_type", width=160, anchor="center")
        self._tree.column("out_type",width=160, anchor="center")

        style = ttk.Style()
        for btype, clr in _TYPE_CLR.items():
            style.configure(f"{btype.value}.Treeview", background=clr)
        for btype, clr in _TYPE_CLR.items():
            self._tree.tag_configure(btype.value, background=clr)

        sb = ttk.Scrollbar(outer, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)

        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self._tree.bind("<Double-1>", lambda e: self._edit_selected_block())

    def _build_section_label(self, parent, text):
        f = tk.Frame(parent, bg=_CLR_BG)
        f.pack(fill="x", pady=(8, 4))
        tk.Label(f, text=text, font=_FONT_BOLD, bg=_CLR_BG,
                 fg=_CLR_HDR).pack(side="left")
        tk.Frame(f, bg="#D3D1C7", height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=6)

    # ── Типы деталей ─────────────────────────────────────────────────────────

    def _add_detail(self):
        det_id    = self._det_id.get().strip()
        det_label = self._det_label.get().strip()
        det_unit  = self._det_unit.get().strip() or "шт"
        try:
            det_max_repair = int(self._det_max_repair.get())
        except (ValueError, TypeError):
            det_max_repair = 0

        if not det_id:
            messagebox.showwarning("Ошибка", "Введите ID детали", parent=self)
            return
        if det_id in self.app.model.detail_types:
            messagebox.showwarning("Ошибка",
                f"Тип '{det_id}' уже существует", parent=self)
            return

        self.app.model.detail_types[det_id] = {
            "label": det_label, "unit": det_unit, "max_repair": det_max_repair,
        }
        self._det_id.delete(0, "end")
        self._det_label.delete(0, "end")
        self._refresh_tags()
        self.app.set_status(f"Добавлен тип детали: {det_id}")

    def _refresh_tags(self):
        for w in self._det_tags_frame.winfo_children():
            w.destroy()
        for det_id, info in self.app.model.detail_types.items():
            label = info.get("label", det_id)
            tag_frame = tk.Frame(
                self._det_tags_frame,
                bg="#EAF3DE", highlightbackground="#3B6D11",
                highlightthickness=1,
            )
            tag_frame.pack(side="left", padx=(0, 6), pady=2)
            tk.Label(
                tag_frame, text=f"{det_id}: {label}",
                font=_FONT_SMALL, bg="#EAF3DE", fg="#27500A",
                padx=8, pady=2,
            ).pack(side="left")
            tk.Label(
                tag_frame, text="×",
                font=_FONT_SMALL, bg="#EAF3DE", fg="#27500A",
                cursor="hand2", padx=4,
            ).pack(side="left")
            tag_frame.bind("<Button-1>",
                lambda e, d=det_id: self._remove_detail(d))
            for child in tag_frame.winfo_children():
                child.bind("<Button-1>",
                    lambda e, d=det_id: self._remove_detail(d))

    def _remove_detail(self, det_id: str):
        in_use = any(
            b.params.get("input_type") == det_id or
            b.params.get("output_type") == det_id or
            b.params.get("detail_type") == det_id
            for b in self.app.model.blocks.values()
        )
        if in_use:
            messagebox.showwarning(
                "Нельзя удалить",
                f"Тип '{det_id}' используется в блоках участка.",
                parent=self,
            )
            return
        self.app.model.detail_types.pop(det_id, None)
        self._refresh_tags()

    # ── Таблица блоков ───────────────────────────────────────────────────────

    def _detail_display(self, det_id: str) -> str:
        """Формирует строку 'ID: Название' или прочерк."""
        if not det_id:
            return "—"
        info = self.app.model.detail_types.get(det_id)
        if info:
            return f"{det_id}: {info.get('label', det_id)}"
        return det_id

    def _refresh_blocks_table(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for block in self.app.model.blocks.values():
            # Логика колонок Вх./Вых. деталь зависит от типа блока
            if block.type == BlockType.SOURCE:
                in_det  = "—"
                out_det = self._detail_display(block.params.get("detail_type", ""))
            elif block.type == BlockType.SINK:
                in_det  = self._detail_display(block.params.get("detail_type", ""))
                out_det = "—"
            else:
                in_det  = self._detail_display(block.params.get("input_type", ""))
                out_det = self._detail_display(block.params.get("output_type", ""))

            self._tree.insert(
                "", "end",
                iid=block.id,
                values=(
                    block.id,
                    block.type.value,
                    block.label,
                    in_det,
                    out_det,
                ),
                tags=(block.type.value,),
            )

    def _get_selected_block_id(self) -> str | None:
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _delete_selected_block(self):
        bid = self._get_selected_block_id()
        if not bid:
            messagebox.showinfo("Выберите блок", "Выберите блок в таблице.", parent=self)
            return
        block = self.app.model.blocks[bid]
        linked = [e for e in self.app.model.edges.values()
                  if e.from_block == bid or e.to_block == bid]
        if linked:
            if not messagebox.askyesno(
                "Удаление блока",
                f"Блок '{block.label}' используется в {len(linked)} связях.\n"
                "Удалить блок и все его связи?",
                parent=self,
            ):
                return
        self.app.model.remove_block(bid)
        self._refresh_blocks_table()
        self.app.refresh_model()
        self.app.set_status(f"Блок {bid} удалён")

    def _edit_selected_block(self):
        bid = self._get_selected_block_id()
        if not bid:
            messagebox.showinfo("Выберите блок", "Выберите блок в таблице.", parent=self)
            return
        block = self.app.model.blocks[bid]
        BlockDialog(self, self.app, edit_block=block)

    def _open_block_dialog(self):
        if not self.app.model.detail_types:
            messagebox.showwarning(
                "Сначала добавьте типы деталей",
                "Добавьте хотя бы один тип детали, прежде чем создавать блоки.",
                parent=self,
            )
            return
        BlockDialog(self, self.app)

    # ── Публичные методы (вызываются из App) ─────────────────────────────────

    def on_activate(self):
        self._refresh_tags()
        self._refresh_blocks_table()

    def validate(self) -> bool:
        if not self.app.model.detail_types:
            messagebox.showwarning(
                "Нет типов деталей",
                "Добавьте хотя бы один тип детали.", parent=self)
            return False
        if not self.app.model.blocks:
            messagebox.showwarning(
                "Нет блоков",
                "Добавьте хотя бы один блок участка.", parent=self)
            return False
        return True


# ══════════════════════════════════════════════════════════════════════════════
# Диалог добавления / редактирования блока
# ══════════════════════════════════════════════════════════════════════════════

# Поля для каждого типа блока: (ключ, метка, тип виджета, дефолт)
_BLOCK_FIELDS = {
    BlockType.SOURCE: [
        ("detail_type", "Тип детали",                    "combo_detail", ""),
        ("capacity",    "Ёмкость / начальный запас (шт)", "spinbox",      50),
    ],
    BlockType.BUFFER: [
        ("detail_type",  "Тип детали",              "combo_detail", ""),
        ("capacity",     "Ёмкость (шт)",            "spinbox",      50),
        ("time_sec",     "Задержка (сек)",           "spinbox",      0),
    ],
    BlockType.SINK: [
        ("detail_type",  "Тип детали",              "combo_detail", ""),
        ("capacity",     "Ёмкость (шт)",            "spinbox",      100),
    ],
    BlockType.TRANSPORT: [
        ("detail_type", "Тип детали",                   "combo_detail", ""),
        ("time_sec",    "Время транспортировки (сек)",   "spinbox",      180),
    ],
    BlockType.PROCESS: [
        ("input_type",               "Тип входной детали",              "combo_detail", ""),
        ("output_type",              "Тип выходной детали",             "combo_detail", ""),
        ("operation_time_sec",       "Время операции (сек)",            "spinbox",      900),
        ("num_machines",             "Кол-во станков на операцию",      "spinbox",      1),
        ("has_internal_control",     "Встроенный контроль",             "check",        False),
        ("defect_rate",              "Доля брака (0.0–0.99)",           "entry_defect", "0.05"),
        ("maintenance_interval_sec", "Интервал ТО (сек, 0 = не задан)","entry",        ""),
        ("mttr_sec",                 "Длительность ТО (сек)",           "entry",        ""),
    ],
    BlockType.ASSEMBLY: [
        ("inputs_count",             "Количество входов",               "spinbox",      2),
        ("output_type",              "Тип выходной детали",             "combo_detail", ""),
        ("operation_time_sec",       "Время сборки (сек)",              "spinbox",      600),
        ("num_machines",             "Кол-во станков на операцию",      "spinbox",      1),
        ("maintenance_interval_sec", "Интервал ТО (сек, 0 = не задан)","entry",        ""),
        ("mttr_sec",                 "Длительность ТО (сек)",           "entry",        ""),
    ],
    BlockType.CONTROL: [
        ("input_type",               "Тип детали",                      "combo_detail", ""),
        ("defect_prob",              "Доля брака (0.0–0.99)",           "entry",        "0.10"),
        ("threshold",                "Порог контроля (0.0–1.0)",        "entry",        "0.10"),
        ("control_time_sec",         "Время контроля (сек)",            "spinbox",      300),
        ("num_machines",             "Кол-во станков на операцию",      "spinbox",      1),
        ("maintenance_interval_sec", "Интервал ТО (сек, 0 = не задан)","entry",        ""),
        ("mttr_sec",                 "Длительность ТО (сек)",           "entry",        ""),
    ],
}


class BlockDialog(tk.Toplevel):
    """Диалог создания / редактирования блока."""

    def __init__(self, parent, app, edit_block=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.app        = app
        self.edit_block = edit_block

        self.title("Редактировать блок" if edit_block else "Добавить блок")
        self.geometry("520x580")
        self.resizable(False, False)
        self.configure(bg=_CLR_BG)
        self.grab_set()

        self._field_widgets: dict[str, tk.Widget] = {}
        self._build_ui()
        if edit_block:
            self._populate(edit_block)

    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}

        # ID блока
        id_row = tk.Frame(self, bg=_CLR_BG)
        id_row.pack(fill="x", padx=20, pady=(12, 0))
        tk.Label(id_row, text="ID блока", font=_FONT_BOLD,
                 bg=_CLR_BG, width=14, anchor="w").pack(side="left")
        self._id_var = tk.StringVar(
            value=self.edit_block.id if self.edit_block else "")
        self._id_entry = tk.Entry(id_row, textvariable=self._id_var,
                                  font=_FONT, width=10)
        self._id_entry.pack(side="left", padx=(4, 0))
        if not self.edit_block:
            tk.Label(id_row, text="(оставьте пустым — назначится автоматически)",
                     font=("Arial", 8), bg=_CLR_BG, fg="#888780").pack(side="left", padx=6)

        # Название
        tk.Label(self, text="Наименование блока", font=_FONT_BOLD,
                 bg=_CLR_BG, anchor="w").pack(fill="x", **pad)
        self._label_var = tk.StringVar()
        tk.Entry(self, textvariable=self._label_var,
                 font=_FONT, width=44).pack(fill="x", padx=20)

        # Группа типа
        tk.Label(self, text="Категория", font=_FONT_BOLD,
                 bg=_CLR_BG, anchor="w").pack(fill="x", **pad)
        self._group_var = tk.StringVar(value="Тех. операция")
        group_combo = ttk.Combobox(
            self, textvariable=self._group_var,
            values=list(BLOCK_TYPE_GROUPS.keys()),
            state="readonly" if not self.edit_block else "disabled",
            width=26,
        )
        group_combo.pack(anchor="w", padx=20)
        group_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_type_combo())

        # Тип блока
        tk.Label(self, text="Тип блока", font=_FONT_BOLD,
                 bg=_CLR_BG, anchor="w").pack(fill="x", **pad)
        self._type_var = tk.StringVar(
            value=self.edit_block.type.value if self.edit_block
            else BlockType.PROCESS.value)
        self._type_combo = ttk.Combobox(
            self, textvariable=self._type_var,
            state="readonly" if not self.edit_block else "disabled",
            width=30,
        )
        self._type_combo.pack(anchor="w", padx=20)
        self._type_combo.bind("<<ComboboxSelected>>",
                              lambda e: self._refresh_fields())

        # Кнопки
        btn_row = tk.Frame(self, bg=_CLR_BG)
        btn_row.pack(side="bottom", fill="x", padx=20, pady=10)
        tk.Button(
            btn_row, text="Сохранить", font=_FONT_BOLD, relief="flat",
            bg="#534AB7", fg="white", padx=12, pady=4, cursor="hand2",
            command=self._save,
        ).pack(side="right")
        tk.Button(
            btn_row, text="Отмена", font=_FONT, relief="flat",
            bg=_CLR_BG, padx=12, pady=4, cursor="hand2",
            command=self.destroy,
        ).pack(side="right", padx=(0, 8))

        # Динамические поля
        self._fields_frame = tk.Frame(self, bg=_CLR_BG)
        self._fields_frame.pack(fill="both", expand=True, padx=20, pady=4)

        if self.edit_block:
            for grp, types in BLOCK_TYPE_GROUPS.items():
                if self.edit_block.type in types:
                    self._group_var.set(grp)
                    break
        self._refresh_type_combo()

    def _refresh_type_combo(self):
        grp = self._group_var.get()
        types = BLOCK_TYPE_GROUPS.get(grp, [])
        self._type_combo["values"] = [t.value for t in types]
        if types:
            self._type_var.set(types[0].value)
        self._refresh_fields()

    def _refresh_fields(self):
        for w in self._fields_frame.winfo_children():
            w.destroy()
        self._field_widgets.clear()

        block_type = BlockType(self._type_var.get())
        detail_ids = list(self.app.model.detail_types.keys())
        # Комбобокс деталей показывает «ID: Название»
        detail_items = [
            f"{did}: {self.app.model.detail_types[did].get('label', did)}"
            for did in detail_ids
        ]
        fields = _BLOCK_FIELDS.get(block_type, [])

        self._defect_rate_row = None  # строка defect_rate, управляется чекбоксом

        for key, label, wtype, default in fields:
            if wtype == "entry_defect":
                # Поле defect_rate — показывается только при has_internal_control=True
                row = tk.Frame(self._fields_frame, bg=_CLR_BG)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=label, font=_FONT, bg=_CLR_BG,
                         width=30, anchor="w").pack(side="left")
                var = tk.StringVar(value=str(default))
                w = tk.Entry(row, textvariable=var, font=_FONT, width=12)
                w.pack(side="left")
                self._field_widgets[key] = var
                self._defect_rate_row = row
                row.pack_forget()  # скрываем по умолчанию
                continue

            row = tk.Frame(self._fields_frame, bg=_CLR_BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=_FONT, bg=_CLR_BG,
                     width=30, anchor="w").pack(side="left")

            if wtype == "spinbox":
                var = tk.IntVar(value=int(default))
                w = tk.Spinbox(row, from_=0, to=99999, textvariable=var,
                               font=_FONT, width=10)
                w.pack(side="left")
                self._field_widgets[key] = var

            elif wtype == "entry":
                var = tk.StringVar(value=str(default))
                w = tk.Entry(row, textvariable=var, font=_FONT, width=12)
                w.pack(side="left")
                self._field_widgets[key] = var

            elif wtype == "combo_detail":
                var = tk.StringVar(value=detail_items[0] if detail_items else "")
                w = ttk.Combobox(row, textvariable=var,
                                 values=detail_items, state="readonly", width=24)
                w.pack(side="left")
                self._field_widgets[key] = var

            elif wtype == "check":
                var = tk.BooleanVar(value=bool(default))
                w = tk.Checkbutton(row, variable=var, bg=_CLR_BG,
                                   command=self._toggle_defect_rate)
                w.pack(side="left")
                self._field_widgets[key] = var

        # ASSEMBLY — отдельные поля per-input
        if block_type == BlockType.ASSEMBLY:
            self._assembly_input_vars: list[tk.StringVar] = []
            tk.Label(self._fields_frame, text="Типы входных деталей:",
                     font=_FONT_BOLD, bg=_CLR_BG).pack(anchor="w", pady=(6, 2))
            n_var = self._field_widgets.get("inputs_count")
            n = int(n_var.get()) if n_var else 2
            self._render_assembly_inputs(n, detail_items, detail_ids)
            if n_var:
                n_var.trace_add("write",
                    lambda *a: self._render_assembly_inputs(
                        int(n_var.get()), detail_items, detail_ids))

        # Показываем defect_rate если has_internal_control уже включён
        self._toggle_defect_rate()

    def _toggle_defect_rate(self):
        """Показывает/скрывает строку defect_rate в зависимости от has_internal_control."""
        if self._defect_rate_row is None:
            return
        ctrl_var = self._field_widgets.get("has_internal_control")
        if ctrl_var and ctrl_var.get():
            self._defect_rate_row.pack(fill="x", pady=2)
        else:
            self._defect_rate_row.pack_forget()

    def _render_assembly_inputs(self, n: int, detail_items: list, detail_ids: list):
        children = self._fields_frame.winfo_children()
        for w in children:
            if getattr(w, "_is_assembly_input", False):
                w.destroy()
        self._assembly_input_vars = []
        for i in range(n):
            row = tk.Frame(self._fields_frame, bg=_CLR_BG)
            row._is_assembly_input = True
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"  Вход {i+1} (in{i+1})",
                     font=_FONT, bg=_CLR_BG, width=30, anchor="w").pack(side="left")
            var = tk.StringVar(value=detail_items[0] if detail_items else "")
            ttk.Combobox(row, textvariable=var,
                         values=detail_items, state="readonly",
                         width=24).pack(side="left")
            self._assembly_input_vars.append(var)

    def _populate(self, block):
        self._label_var.set(block.label)
        detail_items = {
            did: f"{did}: {info.get('label', did)}"
            for did, info in self.app.model.detail_types.items()
        }
        for key, widget_var in self._field_widgets.items():
            val = block.params.get(key)
            if val is None:
                continue
            if isinstance(widget_var, tk.BooleanVar):
                widget_var.set(bool(val))
            elif isinstance(widget_var, tk.IntVar):
                try:
                    widget_var.set(int(val))
                except (ValueError, TypeError):
                    pass
            else:
                # combo_detail — нужно отобразить как «ID: Название»
                str_val = str(val)
                if str_val in detail_items:
                    widget_var.set(detail_items[str_val])
                else:
                    widget_var.set(str_val)
        self._toggle_defect_rate()

    def _detail_id_from_var(self, var: tk.StringVar) -> str:
        """Извлекает ID детали из строки 'ID: Название'."""
        val = var.get()
        return val.split(":")[0].strip() if val else ""

    def _save(self):
        label = self._label_var.get().strip()
        if not label:
            messagebox.showwarning("Ошибка", "Введите наименование.", parent=self)
            return

        block_type = BlockType(self._type_var.get())
        params: dict = {}
        detail_keys = {
            key for key, _, wtype, _ in _BLOCK_FIELDS.get(block_type, [])
            if wtype in ("combo_detail",)
        }

        for key, widget_var in self._field_widgets.items():
            val = widget_var.get()
            if isinstance(widget_var, tk.BooleanVar):
                params[key] = bool(val)
            elif isinstance(widget_var, tk.IntVar):
                params[key] = int(val)
            elif key in detail_keys:
                # combo_detail — сохраняем только ID
                params[key] = str(val).split(":")[0].strip()
            else:
                try:
                    params[key] = float(val) if "." in str(val) else int(val)
                except (ValueError, TypeError):
                    params[key] = val

        # ASSEMBLY — сохраняем типы входов (только ID)
        if block_type == BlockType.ASSEMBLY and hasattr(self, "_assembly_input_vars"):
            params["input_types"] = [
                v.get().split(":")[0].strip() for v in self._assembly_input_vars
            ]

        if self.edit_block:
            new_id = self._id_var.get().strip()
            if new_id and new_id != self.edit_block.id:
                ok = self.app.model.renumber_block(self.edit_block.id, new_id)
                if not ok:
                    messagebox.showwarning("Ошибка",
                        f"ID '{new_id}' уже занят.", parent=self)
                    return
            self.app.model.update_block(
                new_id if new_id else self.edit_block.id, label, params)
        else:
            custom_id = self._id_var.get().strip()
            if custom_id:
                if custom_id in self.app.model.blocks:
                    messagebox.showwarning("Ошибка",
                        f"ID '{custom_id}' уже занят.", parent=self)
                    return
                from model import make_ports
                from model.block import Block
                ports = make_ports(block_type, params)
                block = Block(id=custom_id, type=block_type,
                              label=label, params=params, ports=ports)
                self.app.model.blocks[custom_id] = block
            else:
                self.app.model.add_block(block_type, label, params)

        self.parent_tab._refresh_blocks_table()
        self.app.refresh_model()
        self.destroy()
