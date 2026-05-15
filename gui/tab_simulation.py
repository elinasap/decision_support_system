"""
gui/tab_simulation.py

Вкладка 5 — «Симуляция и рекомендации».
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox

_SIM_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "simulation_module")
)
if _SIM_PATH not in sys.path:
    sys.path.insert(0, _SIM_PATH)

from simulation.engine import Simulator
from recommendation.engine import RecommendationEngine


_CLR_BG     = "#F8F7F5"
_CLR_HDR    = "#2F5496"
_CLR_ACTIVE = "#534AB7"
_FONT       = ("Arial", 10)
_FONT_BOLD  = ("Arial", 10, "bold")
_FONT_SMALL = ("Arial", 9)

_CLR_RED    = "#FCEBEB"
_CLR_RED_FG = "#791F1F"
_CLR_YEL    = "#FAEEDA"
_CLR_YEL_FG = "#633806"
_CLR_GRN    = "#EAF3DE"
_CLR_GRN_FG = "#27500A"

_SEVERITY_COLORS = {
    "red":    (_CLR_RED, _CLR_RED_FG),
    "yellow": (_CLR_YEL, _CLR_YEL_FG),
    "green":  (_CLR_GRN, _CLR_GRN_FG),
}
_SEVERITY_ICON = {"red": "✗", "yellow": "⚠", "green": "•"}


class TabSimulation(tk.Frame):

    def __init__(self, parent: tk.Frame, app):
        super().__init__(parent, bg=_CLR_BG)
        self.app = app
        self._base_result = None   # результат базового прогона
        self._engine = None        # RecommendationEngine с порогами
        self._last_report = None   # последний отчёт рекомендаций
        self.pack(fill="both", expand=True)
        self._build_ui()

    # ── Построение интерфейса ─────────────────────────────────────────────────

    def _build_ui(self):
        outer = tk.Frame(self, bg=_CLR_BG)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # Параметры
        self._build_section_label(outer, "Параметры симуляции")
        params = tk.Frame(outer, bg=_CLR_BG)
        params.pack(fill="x", pady=(4, 12))

        tk.Label(params, text="Макс. время:", font=_FONT, bg=_CLR_BG).pack(side="left")
        self._max_time_var = tk.StringVar(value="10000")
        tk.Entry(params, textvariable=self._max_time_var,
                 font=_FONT, width=8).pack(side="left", padx=(4, 16))

        tk.Label(params, text="Seed:", font=_FONT, bg=_CLR_BG).pack(side="left")
        self._seed_var = tk.StringVar(value="42")
        tk.Entry(params, textvariable=self._seed_var,
                 font=_FONT, width=6).pack(side="left", padx=(4, 16))

        tk.Button(
            params,
            text="▶  Запустить симуляцию",
            font=_FONT_BOLD, relief="flat",
            bg=_CLR_ACTIVE, fg="white",
            activebackground="#3C3489", activeforeground="white",
            padx=14, pady=6, cursor="hand2",
            command=self._run,
        ).pack(side="left")

        self._run_status = tk.StringVar(value="")
        tk.Label(params, textvariable=self._run_status,
                 font=_FONT_SMALL, bg=_CLR_BG, fg="#888780").pack(side="left", padx=12)

        # Итоговые показатели
        self._build_section_label(outer, "Итоговые показатели")
        self._summary_frame = tk.Frame(outer, bg=_CLR_BG)
        self._summary_frame.pack(fill="x", pady=(4, 4))
        self._fill_summary_empty()

        # Нижняя область: таблица блоков + рекомендации
        bottom = tk.Frame(outer, bg=_CLR_BG)
        bottom.pack(fill="both", expand=True, pady=(4, 0))

        left = tk.Frame(bottom, bg=_CLR_BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self._build_section_label(left, "Загрузка блоков")
        self._build_block_table(left)

        right = tk.Frame(bottom, bg=_CLR_BG)
        right.pack(side="left", fill="both", expand=True)
        self._build_section_label(right, "Рекомендации")
        self._rec_outer = tk.Frame(right, bg=_CLR_BG)
        self._rec_outer.pack(fill="both", expand=True)
        self._fill_rec_empty()

        # Сценарный анализ — скрыт до первого успешного прогона
        self._build_sensitivity_section(outer)

    def _build_section_label(self, parent, text):
        f = tk.Frame(parent, bg=_CLR_BG)
        f.pack(fill="x", pady=(8, 4))
        tk.Label(f, text=text, font=_FONT_BOLD, bg=_CLR_BG,
                 fg=_CLR_HDR).pack(side="left")
        tk.Frame(f, bg="#D3D1C7", height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=6)

    # ── Итоговые показатели ───────────────────────────────────────────────────

    def _fill_summary_empty(self):
        for w in self._summary_frame.winfo_children():
            w.destroy()
        for label in ("Пропускная способность", "Доля брака", "Среднее время цикла"):
            self._summary_card(label, "—")

    def _summary_card(self, label, value):
        card = tk.Frame(self._summary_frame, bg="white",
                        highlightbackground="#D3D1C7", highlightthickness=1)
        card.pack(side="left", padx=(0, 12), ipadx=16, ipady=8)
        tk.Label(card, text=value, font=("Arial", 18, "bold"),
                 bg="white", fg="#222").pack()
        tk.Label(card, text=label, font=_FONT_SMALL,
                 bg="white", fg="#888780").pack()

    def _update_summary(self, result):
        for w in self._summary_frame.winfo_children():
            w.destroy()
        items = [
            ("Пропускная способность (дет/с)", f"{result.throughput:.4f}"),
            ("Доля брака",                     f"{result.defect_rate:.1%}"),
            ("Среднее время цикла (с)",         f"{result.avg_cycle_time:.1f}"),
        ]
        for label, value in items:
            self._summary_card(label, value)

    # ── Таблица блоков ────────────────────────────────────────────────────────

    def _build_block_table(self, parent):
        cols = ("Блок", "Тип", "Загрузка", "Блокировка", "Простой", "Обработано")
        frame = tk.Frame(parent, bg=_CLR_BG)
        frame.pack(fill="both", expand=True)

        self._tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        widths = (130, 80, 70, 80, 70, 90)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center")
        self._tree.column("Блок", anchor="w")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

    def _update_block_table(self, result):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for bid, m in result.block_metrics.items():
            idle = max(1.0 - m.utilization - m.blocked_ratio, 0.0)
            self._tree.insert("", "end", values=(
                m.block_label or bid,
                m.block_type,
                f"{m.utilization:.0%}",
                f"{m.blocked_ratio:.0%}",
                f"{idle:.0%}",
                m.details_processed,
            ))

    # ── Рекомендации ──────────────────────────────────────────────────────────

    def _fill_rec_empty(self):
        for w in self._rec_outer.winfo_children():
            w.destroy()
        tk.Label(self._rec_outer,
                 text="Запустите симуляцию для получения рекомендаций.",
                 font=_FONT_SMALL, bg=_CLR_BG, fg="#888780",
                 wraplength=340).pack(anchor="nw", pady=8)

    def _update_recommendations(self, report):
        for w in self._rec_outer.winfo_children():
            w.destroy()

        if not report.interpretations:
            f = tk.Frame(self._rec_outer, bg=_CLR_GRN,
                         highlightbackground=_CLR_GRN_FG, highlightthickness=1)
            f.pack(fill="x", pady=2)
            tk.Label(f, text="✓  Отклонений не обнаружено.",
                     font=_FONT, bg=_CLR_GRN, fg=_CLR_GRN_FG,
                     padx=10, pady=6, anchor="w").pack(fill="x")
            return

        # Кнопка деталей дисбаланса потоков (если есть соответствующие признаки)
        fi_items = [i for i in report.interpretations if i.sign_type == "flow_imbalance"]
        if fi_items:
            fi_banner = tk.Frame(self._rec_outer, bg=_CLR_RED,
                                 highlightbackground=_CLR_RED_FG, highlightthickness=1)
            fi_banner.pack(fill="x", pady=(0, 6), padx=2)
            tk.Label(fi_banner,
                     text=f"✗  Обнаружен дисбаланс входных потоков ({len(fi_items)} блок(а))",
                     font=_FONT_BOLD, bg=_CLR_RED, fg=_CLR_RED_FG,
                     padx=10, anchor="w").pack(side="left", pady=5)
            tk.Button(fi_banner, text="Подробнее →",
                      font=_FONT_SMALL, relief="flat",
                      bg=_CLR_RED_FG, fg="white",
                      activebackground="#5a1414", activeforeground="white",
                      padx=8, pady=3, cursor="hand2",
                      command=self._show_flow_imbalance_window,
                      ).pack(side="right", padx=8, pady=5)

        canvas = tk.Canvas(self._rec_outer, bg=_CLR_BG, highlightthickness=0)
        sb = ttk.Scrollbar(self._rec_outer, orient="vertical",
                           command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=_CLR_BG)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))

        for item in report.interpretations:
            bg, fg = _SEVERITY_COLORS.get(item.severity, (_CLR_BG, "#222"))
            icon = _SEVERITY_ICON.get(item.severity, "•")
            f = tk.Frame(inner, bg=bg,
                         highlightbackground=fg, highlightthickness=1)
            f.pack(fill="x", pady=2, padx=2)
            header = f"{icon}  [{item.rank}] {item.label}"
            tk.Label(f, text=header,
                     font=_FONT_BOLD, bg=bg, fg=fg,
                     padx=8, anchor="w").pack(fill="x", pady=(5, 0))
            tk.Label(f, text=item.message,
                     font=_FONT_SMALL, bg=bg, fg=fg,
                     padx=16, anchor="w",
                     wraplength=320, justify="left").pack(fill="x", pady=2)
            if item.recommendation:
                tk.Frame(f, bg=fg, height=1).pack(fill="x", padx=8, pady=(2, 0))
                tk.Label(f, text=f"→  {item.recommendation}",
                         font=_FONT_SMALL, bg=bg, fg=fg,
                         padx=16, anchor="w",
                         wraplength=320, justify="left").pack(fill="x", pady=(2, 5))

    # ── Окно дисбаланса потоков ───────────────────────────────────────────────

    def _show_flow_imbalance_window(self):
        if self._last_report is None or self._base_result is None:
            return

        fi_signs = [s for s in self._last_report.diagnosis.context_signs
                    if s.sign_type == "flow_imbalance"]
        if not fi_signs:
            return

        win = tk.Toplevel(self)
        win.title("Дисбаланс входных потоков")
        win.configure(bg=_CLR_BG)
        win.resizable(True, True)
        win.geometry("520x420")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        # Заголовок
        hdr = tk.Frame(win, bg=_CLR_HDR)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⇄  Дисбаланс входных потоков",
                 font=_FONT_BOLD, bg=_CLR_HDR, fg="white",
                 padx=14, pady=8).pack(side="left")
        tk.Label(hdr,
                 text=(f"{len(fi_signs)} сборочн. блок(а) с рассинхронизированными входами"),
                 font=_FONT_SMALL, bg=_CLR_HDR, fg="#B0C4E8",
                 padx=6).pack(side="left")

        # Прокручиваемое содержимое
        body = tk.Frame(win, bg=_CLR_BG)
        body.pack(fill="both", expand=True)

        canvas = tk.Canvas(body, bg=_CLR_BG, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=_CLR_BG)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))

        buf_mets = self._base_result.buffer_metrics

        for sign in fi_signs:
            card = tk.Frame(inner, bg=_CLR_RED,
                            highlightbackground=_CLR_RED_FG, highlightthickness=1)
            card.pack(fill="x", padx=10, pady=6)

            tk.Label(card, text=f"✗  {sign.label}",
                     font=_FONT_BOLD, bg=_CLR_RED, fg=_CLR_RED_FG,
                     padx=10, anchor="w").pack(fill="x", pady=(7, 2))

            tk.Label(card, text=sign.message,
                     font=_FONT_SMALL, bg=_CLR_RED, fg=_CLR_RED_FG,
                     padx=14, anchor="w",
                     wraplength=460, justify="left").pack(fill="x")

            # Две колонки: переполненные / голодающие
            cols = tk.Frame(card, bg=_CLR_RED)
            cols.pack(fill="x", padx=10, pady=(6, 4))

            full_ids    = sign.detail.get("full_inputs", [])
            starved_ids = sign.detail.get("starved_inputs", [])

            lcol = tk.Frame(cols, bg=_CLR_RED)
            lcol.pack(side="left", fill="both", expand=True)
            tk.Label(lcol, text="Переполненные входы:",
                     font=("Arial", 9, "bold"), bg=_CLR_RED, fg=_CLR_RED_FG,
                     anchor="w").pack(anchor="w")
            for buf_id in full_ids:
                m = buf_mets.get(buf_id)
                lbl   = (m.block_label if m else None) or buf_id
                ratio = f"{m.full_ratio:.0%} полон" if m else "?"
                tk.Label(lcol, text=f"  • {lbl}  ({ratio})",
                         font=_FONT_SMALL, bg=_CLR_RED, fg=_CLR_RED_FG,
                         anchor="w").pack(anchor="w")

            rcol = tk.Frame(cols, bg=_CLR_RED)
            rcol.pack(side="left", fill="both", expand=True, padx=(10, 0))
            tk.Label(rcol, text="Голодающие входы:",
                     font=("Arial", 9, "bold"), bg=_CLR_RED, fg=_CLR_RED_FG,
                     anchor="w").pack(anchor="w")
            for buf_id in starved_ids:
                m = buf_mets.get(buf_id)
                lbl   = (m.block_label if m else None) or buf_id
                ratio = f"{m.empty_ratio:.0%} пуст" if m else "?"
                tk.Label(rcol, text=f"  • {lbl}  ({ratio})",
                         font=_FONT_SMALL, bg=_CLR_RED, fg=_CLR_RED_FG,
                         anchor="w").pack(anchor="w")

            tk.Frame(card, bg=_CLR_RED_FG, height=1).pack(fill="x", padx=8, pady=(6, 0))
            tk.Label(card,
                     text="→  Сбалансируйте производительность входных ветвей: "
                          "ускорьте подачу по голодающим входам или "
                          "замедлите подачу по переполненным.",
                     font=_FONT_SMALL, bg=_CLR_RED, fg=_CLR_RED_FG,
                     padx=14, anchor="w",
                     wraplength=460, justify="left").pack(fill="x", pady=(4, 8))

        # Кнопка закрытия
        tk.Button(win, text="Закрыть", font=_FONT,
                  relief="flat", bg="#D3D1C7", fg="#333",
                  activebackground="#b8b6ae",
                  padx=16, pady=4, cursor="hand2",
                  command=win.destroy).pack(pady=10)

    # ── Сценарный анализ ─────────────────────────────────────────────────────

    def _build_sensitivity_section(self, parent):
        self._sens_section = tk.Frame(parent, bg=_CLR_BG)
        # не пакуем — покажем после первого успешного прогона

        self._build_section_label(self._sens_section, "Сценарный анализ")

        # Строка с кнопкой и статусом
        btn_row = tk.Frame(self._sens_section, bg=_CLR_BG)
        btn_row.pack(fill="x", pady=(0, 4))

        self._sens_run_btn = tk.Button(
            btn_row,
            text="▶  Запустить сценарный анализ",
            font=_FONT_BOLD, relief="flat",
            bg=_CLR_HDR, fg="white",
            activebackground="#1a3a7a", activeforeground="white",
            padx=14, pady=6, cursor="hand2",
            command=self._run_sensitivity,
        )
        self._sens_run_btn.pack(side="left")

        self._sens_status = tk.StringVar(value="")
        tk.Label(btn_row, textvariable=self._sens_status,
                 font=_FONT_SMALL, bg=_CLR_BG, fg="#888780").pack(side="left", padx=12)

        # Пояснительный текст под кнопкой
        tk.Label(
            self._sens_section,
            text=(
                "Проверьте, как изменится поведение участка "
                "при росте нагрузки, снижении производительности, "
                "росте брака или отказе позиции."
            ),
            font=_FONT_SMALL, bg=_CLR_BG, fg="#888780",
            wraplength=700, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self._sens_results_outer = tk.Frame(self._sens_section, bg=_CLR_BG)
        self._sens_results_outer.pack(fill="both", expand=True)

    def _run_sensitivity(self):
        from recommendation.sensitivity import ScenarioAnalyzer

        self._sens_run_btn.configure(state="disabled")
        self._sens_status.set("Выполняется...")
        self.configure(cursor="watch")
        self.update_idletasks()

        try:
            seed_str = self._seed_var.get().strip()
            seed = int(seed_str) if seed_str.isdigit() else None
            max_time = float(self._max_time_var.get())

            analyzer = ScenarioAnalyzer(
                model_dict=self.app.model.to_dict(),
                base_result=self._base_result,
                thresholds=self._engine.thresholds,
                max_time=max_time,
                seed=seed,
            )
            sens_report = analyzer.run()
            self._update_sensitivity_results(sens_report)
            self._sens_status.set(f"Готово — {len(sens_report.scenarios)} прогонов")
            self.app.set_status("Сценарный анализ завершён")

        except Exception as e:
            messagebox.showerror("Ошибка сценарного анализа", str(e), parent=self)
            self._sens_status.set("Ошибка")
        finally:
            self._sens_run_btn.configure(state="normal")
            self.configure(cursor="")

    def _update_sensitivity_results(self, report):
        for w in self._sens_results_outer.winfo_children():
            w.destroy()

        if not report.robustness:
            tk.Label(self._sens_results_outer,
                     text="Нет сценариев для анализа (нет операций или блоков контроля).",
                     font=_FONT_SMALL, bg=_CLR_BG, fg="#888780").pack(anchor="nw")
            return

        canvas = tk.Canvas(self._sens_results_outer, bg=_CLR_BG,
                           highlightthickness=0, height=220)
        sb = ttk.Scrollbar(self._sens_results_outer, orient="vertical",
                           command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=_CLR_BG)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))

        # Индекс шагов по scenario_id для быстрого доступа к новым признакам
        steps_by_scenario: dict[str, list] = {}
        for step in report.scenarios:
            steps_by_scenario.setdefault(step.scenario_id, []).append(step)

        for rob in report.robustness:
            if rob.is_robust:
                bg, fg, icon = _CLR_GRN, _CLR_GRN_FG, "✓"
            elif rob.first_critical_step:
                bg, fg, icon = _CLR_RED, _CLR_RED_FG, "✗"
            else:
                bg, fg, icon = _CLR_YEL, _CLR_YEL_FG, "⚠"

            card = tk.Frame(inner, bg=bg,
                            highlightbackground=fg, highlightthickness=1)
            card.pack(fill="x", pady=2, padx=2)

            tk.Label(card, text=f"{icon}  {rob.scenario_name}",
                     font=_FONT_BOLD, bg=bg, fg=fg,
                     padx=8, anchor="w").pack(fill="x", pady=(5, 0))
            tk.Label(card, text=rob.summary,
                     font=_FONT_SMALL, bg=bg, fg=fg,
                     padx=16, anchor="w",
                     wraplength=680, justify="left").pack(fill="x", pady=(2, 4))

            if not rob.is_robust:
                # Показываем новые признаки из первого проблемного шага
                for step in steps_by_scenario.get(rob.scenario_id, []):
                    if not step.new_signs:
                        continue
                    tk.Frame(card, bg=fg, height=1).pack(fill="x", padx=8)
                    tk.Label(card,
                             text=f"Шаг «{step.step_label}» — новые отклонения:",
                             font=_FONT_SMALL, bg=bg, fg=fg,
                             padx=16, anchor="w").pack(fill="x", pady=(3, 1))
                    for sign in step.new_signs:
                        sicon = _SEVERITY_ICON.get(sign.severity, "•")
                        msg = sign.message[:90] + ("…" if len(sign.message) > 90 else "")
                        tk.Label(card,
                                 text=f"    {sicon}  {sign.label}: {msg}",
                                 font=_FONT_SMALL, bg=bg, fg=fg,
                                 padx=16, pady=0, anchor="w").pack(fill="x")
                    tk.Label(card, text="", bg=bg).pack()
                    break  # только первый проблемный шаг

    # ── Запуск симуляции ──────────────────────────────────────────────────────

    def _run(self):
        from validation import validate

        val = validate(self.app.model)
        if not val.ok:
            messagebox.showerror(
                "Ошибка модели",
                "Модель содержит ошибки валидации:\n\n"
                + "\n".join(f"• {e}" for e in val.errors),
            )
            return

        try:
            max_time = float(self._max_time_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Макс. время должно быть числом.",
                                 parent=self)
            return

        seed_str = self._seed_var.get().strip()
        seed = int(seed_str) if seed_str.isdigit() else None

        self._run_status.set("Выполняется...")
        self.configure(cursor="watch")
        self.update_idletasks()

        try:
            model_dict = self.app.model.to_dict()
            result = Simulator(model_dict, max_time=max_time, seed=seed).run()

            engine = RecommendationEngine(model_dict=model_dict)
            report = engine.analyze(result)

            self._update_summary(result)
            self._update_block_table(result)
            self._update_recommendations(report)

            # Сохраняем для сценарного анализа
            self._base_result = result
            self._engine = engine
            self._last_report = report

            # Передаём composite scores в схему для heatmap
            schema_tab = self.app._tabs.get("schema")
            if schema_tab is not None:
                schema_tab.set_scores(report.block_scores, report.buffer_scores)

            # Сценарный анализ доступен всегда после базового прогона
            self._sens_section.pack(fill="x", pady=(4, 0))
            self._sens_run_btn.configure(state="normal")
            self._sens_status.set("")
            for w in self._sens_results_outer.winfo_children():
                w.destroy()

            self._run_status.set(
                f"Готово — {result.total_events_processed} событий, "
                f"t = {result.elapsed_model_time:.1f}"
            )
            self.app.set_status("Симуляция завершена")

        except Exception as e:
            messagebox.showerror("Ошибка симуляции", str(e))
            self._run_status.set("Ошибка")
        finally:
            self.configure(cursor="")

    def on_activate(self):
        pass
