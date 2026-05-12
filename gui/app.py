"""
gui/app.py

Главное окно приложения.

Отвечает за:
  - создание окна и навигацию по 4 вкладкам
  - хранение общего состояния (объект Model)
  - передачу модели между вкладками
  - кнопки «Далее» / «Назад» внизу окна

Вкладки создаются как отдельные фреймы и монтируются
в центральную область через grid. Переключение — show/hide,
а не пересоздание, чтобы не терять введённые данные.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from model import Model, BlockType
from gui.tab_blocks      import TabBlocks
from gui.tab_edges       import TabEdges
from gui.tab_schema      import TabSchema
from gui.tab_export      import TabExport
from gui.tab_simulation  import TabSimulation


# Порядок вкладок
_TABS = [
    ("1. Детали и блоки",        "blocks"),
    ("2. Связи",                 "edges"),
    ("3. Схема",                 "schema"),
    ("4. Экспорт",               "export"),
    ("5. Симуляция",             "simulation"),
]

# Цвета
_CLR_ACTIVE   = "#534AB7"   # фиолетовый — активная вкладка
_CLR_INACTIVE = "#888780"   # серый — неактивная
_CLR_BG       = "#F8F7F5"   # фон окна
_CLR_BAR      = "#FFFFFF"   # фон панели вкладок


class App(tk.Tk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        self.title("Моделирование производственного участка")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(bg=_CLR_BG)

        # Общая модель — передаётся во все вкладки по ссылке
        self.model = Model(name="Новый участок", detail_types={})

        self._current_tab = 0   # индекс активной вкладки
        self._build_ui()
        self._show_tab(0)

    # ── Построение интерфейса ─────────────────────────────────────────────────

    def _build_ui(self):
        # Верхняя панель вкладок
        self._tab_bar = tk.Frame(self, bg=_CLR_BAR, height=40)
        self._tab_bar.pack(side="top", fill="x")
        self._tab_bar.pack_propagate(False)

        # Разделитель под панелью вкладок
        tk.Frame(self, bg="#D3D1C7", height=1).pack(side="top", fill="x")

        # Нижняя панель кнопок навигации
        nav = tk.Frame(self, bg=_CLR_BG, height=48)
        nav.pack(side="bottom", fill="x")
        nav.pack_propagate(False)
        tk.Frame(nav, bg="#D3D1C7", height=1).pack(side="top", fill="x")
        self._build_nav_buttons(nav)

        # Центральная область — здесь живут вкладки
        self._content = tk.Frame(self, bg=_CLR_BG)
        self._content.pack(side="top", fill="both", expand=True)

        # Создаём все вкладки заранее (они скрыты до переключения)
        self._tab_buttons: list[tk.Label] = []
        self._tab_frames:  dict[str, tk.Frame] = {}

        for i, (title, key) in enumerate(_TABS):
            # Кнопка-вкладка в верхней панели
            btn = tk.Label(
                self._tab_bar, text=title,
                font=("Arial", 10), bg=_CLR_BAR,
                padx=18, pady=10, cursor="hand2",
            )
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, idx=i: self._show_tab(idx))
            self._tab_buttons.append(btn)

            # Фрейм-контейнер вкладки
            frame = tk.Frame(self._content, bg=_CLR_BG)
            self._tab_frames[key] = frame

        # Создаём содержимое каждой вкладки
        self._tabs: dict[str, object] = {
            "blocks":     TabBlocks(    self._tab_frames["blocks"],     self),
            "edges":      TabEdges(     self._tab_frames["edges"],      self),
            "schema":     TabSchema(    self._tab_frames["schema"],     self),
            "export":     TabExport(    self._tab_frames["export"],     self),
            "simulation": TabSimulation(self._tab_frames["simulation"], self),
        }

    def _build_nav_buttons(self, nav: tk.Frame):
        inner = tk.Frame(nav, bg=_CLR_BG)
        inner.pack(side="right", padx=16, pady=8)

        self._btn_back = tk.Button(
            inner, text="← Назад",
            font=("Arial", 10), relief="flat",
            bg=_CLR_BG, activebackground="#E8E6E0",
            padx=12, pady=4, cursor="hand2",
            command=self._go_back,
        )
        self._btn_back.pack(side="left", padx=(0, 8))

        self._btn_next = tk.Button(
            inner, text="Далее →",
            font=("Arial", 10, "bold"), relief="flat",
            bg=_CLR_ACTIVE, fg="white",
            activebackground="#3C3489", activeforeground="white",
            padx=12, pady=4, cursor="hand2",
            command=self._go_next,
        )
        self._btn_next.pack(side="left")

        # Статусная строка слева
        self._status_var = tk.StringVar(value="")
        tk.Label(
            nav, textvariable=self._status_var,
            font=("Arial", 9), bg=_CLR_BG, fg=_CLR_INACTIVE,
        ).pack(side="left", padx=16)

    # ── Навигация ─────────────────────────────────────────────────────────────

    def _show_tab(self, index: int):
        """Переключает на вкладку с заданным индексом."""
        # Скрываем все фреймы
        for frame in self._tab_frames.values():
            frame.place_forget()

        # Показываем нужный
        key = _TABS[index][1]
        self._tab_frames[key].place(relx=0, rely=0, relwidth=1, relheight=1)

        # Обновляем стили кнопок-вкладок
        for i, btn in enumerate(self._tab_buttons):
            if i == index:
                btn.configure(
                    fg=_CLR_ACTIVE,
                    font=("Arial", 10, "bold"),
                )
                # Подчёркивание активной вкладки
                btn.configure(relief="flat",
                               highlightbackground=_CLR_ACTIVE,
                               highlightthickness=2)
            else:
                btn.configure(
                    fg=_CLR_INACTIVE,
                    font=("Arial", 10),
                    relief="flat",
                    highlightthickness=0,
                )

        self._current_tab = index

        # Обновляем кнопки навигации
        self._btn_back.configure(
            state="normal" if index > 0 else "disabled"
        )
        is_last = (index == len(_TABS) - 1)
        self._btn_next.configure(
            text="Готово" if is_last else "Далее →",
            state="disabled" if is_last else "normal",
        )

        # Уведомляем вкладку что она стала активной
        tab = self._tabs.get(key)
        if tab and hasattr(tab, "on_activate"):
            tab.on_activate()

    def _go_next(self):
        """Переход вперёд — с проверкой текущей вкладки."""
        key = _TABS[self._current_tab][1]
        tab = self._tabs.get(key)

        # Каждая вкладка может определить validate() → True/False
        if tab and hasattr(tab, "validate"):
            if not tab.validate():
                return  # вкладка сама показывает ошибку

        if self._current_tab < len(_TABS) - 1:
            self._show_tab(self._current_tab + 1)

    def _go_back(self):
        if self._current_tab > 0:
            self._show_tab(self._current_tab - 1)

    # ── Публичные методы (вызываются из вкладок) ─────────────────────────────

    def set_status(self, text: str, ok: bool = True):
        """Обновляет текст статусной строки внизу окна."""
        self._status_var.set(text)

    def refresh_model(self):
        """
        Вызывается вкладками после изменения модели.
        Уведомляет схему о необходимости перерисовки.
        """
        schema_tab = self._tabs.get("schema")
        if schema_tab and hasattr(schema_tab, "mark_dirty"):
            schema_tab.mark_dirty()

    def replace_model(self, new_model) -> None:
        """
        Заменяет текущую модель и обновляет все вкладки.
        Вызывается после импорта из файла.
        """
        self.model = new_model
        for tab in self._tabs.values():
            if hasattr(tab, "on_activate"):
                tab.on_activate()
        self.refresh_model()
