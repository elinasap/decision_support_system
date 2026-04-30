"""
gui/tab_export.py

Вкладка 4 — «Экспорт».

Показывает результат валидации и предоставляет кнопки
сохранения в Excel и JSON.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from validation import validate
from export import export_excel, export_json, import_excel, import_json


_CLR_BG    = "#F8F7F5"
_CLR_HDR   = "#2F5496"
_CLR_OK    = "#EAF3DE"
_CLR_OK_FG = "#27500A"
_CLR_ERR   = "#FCEBEB"
_CLR_ERR_FG= "#791F1F"
_CLR_WARN  = "#FAEEDA"
_CLR_WARN_FG="#633806"
_FONT      = ("Arial", 10)
_FONT_BOLD = ("Arial", 10, "bold")


class TabExport(tk.Frame):

    def __init__(self, parent: tk.Frame, app):
        super().__init__(parent, bg=_CLR_BG)
        self.app = app
        self.pack(fill="both", expand=True)
        self._build_ui()

    def _build_ui(self):
        outer = tk.Frame(self, bg=_CLR_BG)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Секция: имя файла ───────────────────────────────────────────────
        self._build_section_label(outer, "Имя файла")
        name_row = tk.Frame(outer, bg=_CLR_BG)
        name_row.pack(fill="x", pady=(4, 12))

        self._filename_var = tk.StringVar(value="production_unit")
        tk.Entry(name_row, textvariable=self._filename_var,
                 font=_FONT, width=32).pack(side="left")
        tk.Label(name_row, text=".xlsx / .json",
                 font=_FONT, bg=_CLR_BG,
                 fg="#888780").pack(side="left", padx=8)

        # ── Секция: результат валидации ────────────────────────────────────
        self._build_section_label(outer, "Результат валидации")

        self._validation_frame = tk.Frame(outer, bg=_CLR_BG)
        self._validation_frame.pack(fill="x", pady=(4, 12))

        # (заполняется в on_activate)

        # ── Секция: кнопки экспорта ─────────────────────────────────────────
        self._build_section_label(outer, "Сохранить")

        btn_area = tk.Frame(outer, bg=_CLR_BG)
        btn_area.pack(fill="x", pady=(8, 0))

        tk.Button(
            btn_area,
            text="↓  Сохранить Excel (.xlsx)",
            font=_FONT_BOLD, relief="flat",
            bg="#534AB7", fg="white",
            activebackground="#3C3489", activeforeground="white",
            padx=16, pady=8, cursor="hand2",
            command=self._save_excel,
        ).pack(side="left")

        tk.Button(
            btn_area,
            text="↓  Сохранить JSON (.json)",
            font=_FONT, relief="flat",
            bg=_CLR_BG, padx=16, pady=8, cursor="hand2",
            command=self._save_json,
        ).pack(side="left", padx=(12, 0))

        # Статус последнего сохранения
        self._save_status = tk.StringVar(value="")
        tk.Label(
            outer, textvariable=self._save_status,
            font=("Arial", 9), bg=_CLR_BG, fg="#3B6D11",
        ).pack(anchor="w", pady=(8, 0))

        # ── Секция: загрузка ────────────────────────────────────────────────
        self._build_section_label(outer, "Загрузить")

        load_area = tk.Frame(outer, bg=_CLR_BG)
        load_area.pack(fill="x", pady=(8, 0))

        tk.Button(
            load_area,
            text="↑  Загрузить Excel (.xlsx)",
            font=_FONT_BOLD, relief="flat",
            bg="#1E6B3B", fg="white",
            activebackground="#155130", activeforeground="white",
            padx=16, pady=8, cursor="hand2",
            command=self._load_excel,
        ).pack(side="left")

        tk.Button(
            load_area,
            text="↑  Загрузить JSON (.json)",
            font=_FONT, relief="flat",
            bg=_CLR_BG, padx=16, pady=8, cursor="hand2",
            command=self._load_json,
        ).pack(side="left", padx=(12, 0))

        self._load_status = tk.StringVar(value="")
        tk.Label(
            outer, textvariable=self._load_status,
            font=("Arial", 9), bg=_CLR_BG, fg="#3B6D11",
        ).pack(anchor="w", pady=(8, 0))

    def _build_section_label(self, parent, text):
        f = tk.Frame(parent, bg=_CLR_BG)
        f.pack(fill="x", pady=(8, 4))
        tk.Label(f, text=text, font=_FONT_BOLD, bg=_CLR_BG,
                 fg=_CLR_HDR).pack(side="left")
        tk.Frame(f, bg="#D3D1C7", height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=6)

    def _run_validation(self):
        """Запускает валидацию и отображает результаты."""
        for w in self._validation_frame.winfo_children():
            w.destroy()

        result = validate(self.app.model)

        if result.ok and not result.warnings:
            self._add_badge(
                self._validation_frame,
                "✓  Схема корректна — можно сохранять",
                _CLR_OK, _CLR_OK_FG,
            )
        else:
            for err in result.errors:
                self._add_badge(
                    self._validation_frame,
                    f"✗  {err}", _CLR_ERR, _CLR_ERR_FG)
            for warn in result.warnings:
                self._add_badge(
                    self._validation_frame,
                    f"⚠  {warn}", _CLR_WARN, _CLR_WARN_FG)

        return result

    def _add_badge(self, parent, text, bg, fg):
        f = tk.Frame(parent, bg=bg,
                     highlightbackground=fg, highlightthickness=1)
        f.pack(fill="x", pady=3)
        tk.Label(f, text=text, font=("Arial", 9),
                 bg=bg, fg=fg, padx=10, pady=4,
                 anchor="w", wraplength=680).pack(fill="x")

    def _save_excel(self):
        result = self._run_validation()
        if not result.ok:
            if not messagebox.askyesno(
                "Есть ошибки",
                "Модель содержит ошибки валидации.\n"
                "Всё равно сохранить Excel?",
                parent=self,
            ):
                return

        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=self._filename_var.get(),
            parent=self,
        )
        if not path:
            return
        try:
            export_excel(self.app.model, path)
            self._save_status.set(f"✓ Excel сохранён: {path}")
            self.app.set_status(f"Excel: {path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}",
                                 parent=self)

    def _save_json(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=self._filename_var.get(),
            parent=self,
        )
        if not path:
            return
        try:
            export_json(self.app.model, path)
            self._save_status.set(f"✓ JSON сохранён: {path}")
            self.app.set_status(f"JSON: {path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}",
                                 parent=self)

    def _load_excel(self):
        path = filedialog.askopenfilename(
            filetypes=[("Excel files", "*.xlsx")],
            title="Открыть Excel-файл модели",
            parent=self,
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Загрузить файл",
            "Текущая модель будет заменена данными из файла.\nПродолжить?",
            parent=self,
        ):
            return
        try:
            model = import_excel(path)
            self.app.replace_model(model)
            self._load_status.set(f"✓ Загружено из Excel: {path}")
            self.app.set_status(f"Импорт Excel: {path}")
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", f"Не удалось загрузить файл:\n{e}",
                                 parent=self)

    def _load_json(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")],
            title="Открыть JSON-файл модели",
            parent=self,
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Загрузить файл",
            "Текущая модель будет заменена данными из файла.\nПродолжить?",
            parent=self,
        ):
            return
        try:
            model = import_json(path)
            self.app.replace_model(model)
            self._load_status.set(f"✓ Загружено из JSON: {path}")
            self.app.set_status(f"Импорт JSON: {path}")
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", f"Не удалось загрузить файл:\n{e}",
                                 parent=self)

    def on_activate(self):
        self._run_validation()
