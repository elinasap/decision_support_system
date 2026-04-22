"""
gui/tab_edges.py

Вкладка 2 — «Связи».

Таблица существующих связей + форма добавления новой.
Обратные рёбра (петли) подсвечиваются оранжевым автоматически.
Тип связи выводится из имени порта-источника (out_defect) и флага is_back_edge.
"""

import tkinter as tk
from tkinter import ttk, messagebox


_CLR_BG   = "#F8F7F5"
_CLR_HDR  = "#2F5496"
_CLR_BACK = "#FDEBD0"   # оранжевый фон для обратных связей
_FONT     = ("Arial", 10)
_FONT_BOLD= ("Arial", 10, "bold")


class TabEdges(tk.Frame):

    def __init__(self, parent: tk.Frame, app):
        super().__init__(parent, bg=_CLR_BG)
        self.app = app
        self.pack(fill="both", expand=True)
        self._editing_eid = None
        self._build_ui()

    def _build_ui(self):
        outer = tk.Frame(self, bg=_CLR_BG)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Форма добавления связи ──────────────────────────────────────────
        self._build_section_label(outer, "Добавить связь")

        form = tk.Frame(outer, bg=_CLR_BG)
        form.pack(fill="x", pady=(4, 12))

        # Откуда: блок + порт
        tk.Label(form, text="Откуда", font=_FONT, bg=_CLR_BG, width=8).grid(
            row=0, column=0, sticky="w")
        self._from_block = ttk.Combobox(form, state="readonly", width=14)
        self._from_block.grid(row=0, column=1, padx=(4, 2))
        self._from_block.bind("<<ComboboxSelected>>",
                              lambda e: self._refresh_from_ports())
        self._from_port = ttk.Combobox(form, state="readonly", width=14)
        self._from_port.grid(row=0, column=2, padx=(2, 12))

        # Куда: блок + порт
        tk.Label(form, text="Куда", font=_FONT, bg=_CLR_BG, width=6).grid(
            row=0, column=3, sticky="w")
        self._to_block = ttk.Combobox(form, state="readonly", width=14)
        self._to_block.grid(row=0, column=4, padx=(4, 2))
        self._to_block.bind("<<ComboboxSelected>>",
                            lambda e: self._refresh_to_ports())
        self._to_port = ttk.Combobox(form, state="readonly", width=14)
        self._to_port.grid(row=0, column=5, padx=(2, 12))

        # Тип детали
        tk.Label(form, text="Деталь", font=_FONT, bg=_CLR_BG).grid(
            row=0, column=6, sticky="w")
        self._detail_type = ttk.Combobox(form, state="readonly", width=20)
        self._detail_type.grid(row=0, column=7, padx=(4, 12))

        # Комментарий
        tk.Label(form, text="Комментарий", font=_FONT, bg=_CLR_BG).grid(
            row=0, column=8, sticky="w")
        self._comment_var = tk.StringVar()
        tk.Entry(form, textvariable=self._comment_var,
                 font=_FONT, width=20).grid(row=0, column=9, padx=(4, 0))

        # Кнопки управления связями
        btn_row = tk.Frame(outer, bg=_CLR_BG)
        btn_row.pack(fill="x", pady=(0, 8))
        tk.Button(
            btn_row, text="+ Добавить связь", font=_FONT, relief="flat",
            bg="#534AB7", fg="white", padx=8, pady=2, cursor="hand2",
            command=self._add_edge,
        ).pack(side="left")
        tk.Button(
            btn_row, text="Удалить выбранную", font=_FONT, relief="flat",
            bg=_CLR_BG, padx=8, pady=2, cursor="hand2",
            command=self._delete_selected,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            btn_row, text="✓ Применить изменения", font=_FONT, relief="flat",
            bg=_CLR_BG, padx=8, pady=2, cursor="hand2",
            command=self._apply_edit,
        ).pack(side="left", padx=(8, 0))
        tk.Label(btn_row,
                 text="Выберите строку в таблице — поля заполнятся для редактирования",
                 font=("Arial", 9), bg=_CLR_BG, fg="#888780").pack(side="left", padx=(8, 0))

        # ── Таблица связей ──────────────────────────────────────────────────
        self._build_section_label(outer, "Связи участка")

        cols = ("id", "from", "to", "detail", "back")
        self._tree = ttk.Treeview(
            outer, columns=cols, show="headings", height=14,
            selectmode="browse",
        )
        self._tree.heading("id",     text="ID")
        self._tree.heading("from",   text="Откуда")
        self._tree.heading("to",     text="Куда")
        self._tree.heading("detail", text="Деталь")
        self._tree.heading("back",   text="Обратная?")

        self._tree.column("id",     width=50,  anchor="center")
        self._tree.column("from",   width=200)
        self._tree.column("to",     width=200)
        self._tree.column("detail", width=180, anchor="center")
        self._tree.column("back",   width=90,  anchor="center")

        self._tree.tag_configure("back", background=_CLR_BACK,
                                 foreground="#843C0C")

        sb = ttk.Scrollbar(outer, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

    def _build_section_label(self, parent, text):
        f = tk.Frame(parent, bg=_CLR_BG)
        f.pack(fill="x", pady=(8, 4))
        tk.Label(f, text=text, font=_FONT_BOLD, bg=_CLR_BG,
                 fg=_CLR_HDR).pack(side="left")
        tk.Frame(f, bg="#D3D1C7", height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=6)

    def _refresh_from_ports(self):
        bid = self._from_block.get().split(":")[0].strip()
        if bid not in self.app.model.blocks:
            return
        ports = self.app.model.blocks[bid].ports.out_ports
        self._from_port["values"] = ports
        if ports:
            self._from_port.set(ports[0])

    def _refresh_to_ports(self):
        bid = self._to_block.get().split(":")[0].strip()
        if bid not in self.app.model.blocks:
            return
        ports = self.app.model.blocks[bid].ports.in_ports
        self._to_port["values"] = ports
        if ports:
            self._to_port.set(ports[0])

    def _refresh_combos(self):
        block_labels = [
            f"{b.id}: {b.label}"
            for b in self.app.model.blocks.values()
        ]
        self._from_block["values"] = block_labels
        self._to_block["values"]   = block_labels

        # Показываем деталь как «ID: Название»
        detail_items = [
            f"{did}: {info.get('label', did)}"
            for did, info in self.app.model.detail_types.items()
        ]
        self._detail_type["values"] = detail_items
        if detail_items:
            self._detail_type.set(detail_items[0])

    def _refresh_table(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for edge in self.app.model.edges.values():
            tags = ("back",) if edge.is_back_edge else ()
            # Показываем деталь как «ID: Название» если возможно
            det_label = self._detail_display(edge.detail_type)
            self._tree.insert(
                "", "end", iid=edge.id,
                values=(
                    edge.id,
                    f"{edge.from_block}.{edge.from_port}",
                    f"{edge.to_block}.{edge.to_port}",
                    det_label,
                    "да ↻" if edge.is_back_edge else "—",
                ),
                tags=tags,
            )

    def _detail_display(self, detail_id: str) -> str:
        """Формирует строку 'ID: Название' для отображения."""
        if not detail_id:
            return "—"
        info = self.app.model.detail_types.get(detail_id)
        if info:
            return f"{detail_id}: {info.get('label', detail_id)}"
        return detail_id

    def _detail_id_from_combo(self, combo_val: str) -> str:
        """Извлекает ID детали из строки 'ID: Название'."""
        return combo_val.split(":")[0].strip() if combo_val else ""

    def _add_edge(self):
        from_str  = self._from_block.get().split(":")[0].strip()
        to_str    = self._to_block.get().split(":")[0].strip()
        from_port = self._from_port.get().strip()
        to_port   = self._to_port.get().strip()

        if not all([from_str, to_str, from_port, to_port]):
            messagebox.showwarning("Ошибка",
                "Заполните все поля связи (блок + порт).", parent=self)
            return

        detail  = self._detail_id_from_combo(self._detail_type.get())
        comment = self._comment_var.get()

        self.app.model.add_edge(
            from_str, from_port, to_str, to_port,
            detail_type=detail,
            comment=comment,
        )
        self._refresh_table()
        self.app.refresh_model()
        self.app.set_status(f"Связь добавлена: {from_str}.{from_port} → {to_str}.{to_port}")

    def _delete_selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Выберите связь",
                "Выберите связь в таблице.", parent=self)
            return
        eid = sel[0]
        self.app.model.remove_edge(eid)
        self._refresh_table()
        self.app.refresh_model()

    def _on_select(self, event):
        """Клик по строке — заполняет форму для редактирования."""
        sel = self._tree.selection()
        if not sel:
            return
        eid = sel[0]
        edge = self.app.model.edges.get(eid)
        if not edge:
            return

        def _find_label(bid):
            for v in self._from_block["values"]:
                if v.startswith(bid + ":"):
                    return v
            return bid

        self._from_block.set(_find_label(edge.from_block))
        self._refresh_from_ports()
        self._from_port.set(edge.from_port)
        self._to_block.set(_find_label(edge.to_block))
        self._refresh_to_ports()
        self._to_port.set(edge.to_port)

        # Устанавливаем деталь в формате «ID: Название»
        det_combo = self._detail_display(edge.detail_type)
        if det_combo in self._detail_type["values"]:
            self._detail_type.set(det_combo)

        self._comment_var.set(edge.comment)
        self._editing_eid = eid

    def _apply_edit(self):
        """Удаляет старую связь и создаёт новую с обновлёнными данными."""
        eid = self._editing_eid
        if not eid or eid not in self.app.model.edges:
            return
        self.app.model.remove_edge(eid)
        self._add_edge()

    def on_activate(self):
        self._refresh_combos()
        self._refresh_table()

    def validate(self) -> bool:
        if not self.app.model.edges:
            messagebox.showwarning("Нет связей",
                "Добавьте хотя бы одну связь.", parent=self)
            return False
        return True
