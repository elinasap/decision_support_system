"""
gui/tab_schema.py

Вкладка 3 — «Схема».

Строит граф участка через networkx + matplotlib, встраивает в tkinter.
Фиксированный иерархический макет (сверху вниз).
Узлы — скруглённые прямоугольники с белым текстом.
Обратные рёбра — пунктир оранжевого цвета.
"""

import tkinter as tk
from collections import defaultdict, deque

import networkx as nx
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

from model import BlockType


_CLR_BG    = "#F8F7F5"
_FONT      = ("Arial", 10)

# Тёмные цвета узлов — белый текст читается нормально
_NODE_CLR = {
    BlockType.SOURCE:    "#4B5563",
    BlockType.TRANSPORT: "#1D4ED8",
    BlockType.PROCESS:   "#065F46",
    BlockType.ASSEMBLY:  "#1E40AF",
    BlockType.CONTROL:   "#92400E",
    BlockType.BUFFER:    "#6B7280",
    BlockType.SINK:      "#166534",
}

_NODE_W  = 1.7   # ширина узла в единицах данных
_NODE_H  = 0.50  # высота узла
_LEVEL_H = 1.5   # вертикальное расстояние между уровнями
_NODE_DX = 2.2   # горизонтальное расстояние между центрами узлов

# Цвета heatmap по composite score
_SCORE_GREEN  = "#388E3C"   # score < 0.4
_SCORE_YELLOW = "#F57C00"   # score < 0.7
_SCORE_RED    = "#C62828"   # score >= 0.7


class TabSchema(tk.Frame):

    def __init__(self, parent: tk.Frame, app):
        super().__init__(parent, bg=_CLR_BG)
        self.app    = app
        self._dirty = True
        self._block_scores:  dict[str, float] = {}
        self._buffer_scores: dict[str, float] = {}
        self.pack(fill="both", expand=True)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        toolbar = tk.Frame(self, bg=_CLR_BG)
        toolbar.pack(side="top", fill="x", padx=20, pady=(12, 6))

        tk.Button(
            toolbar, text="↺ Перестроить", font=_FONT, relief="flat",
            bg=_CLR_BG, padx=8, pady=2, cursor="hand2",
            command=self._draw,
        ).pack(side="left")

        tk.Frame(toolbar, bg="#D3D1C7", width=1).pack(
            side="left", fill="y", padx=(12, 8), pady=4)

        self._heatmap_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            toolbar, text="По загрузке", variable=self._heatmap_var,
            font=_FONT, bg=_CLR_BG, activebackground=_CLR_BG,
            command=self._draw,
        ).pack(side="left")

        # Легенда
        legend = tk.Frame(toolbar, bg=_CLR_BG)
        legend.pack(side="right")
        for btype, clr in _NODE_CLR.items():
            f = tk.Frame(legend, bg=clr,
                         highlightbackground="#888780", highlightthickness=1)
            f.pack(side="left", padx=2)
            tk.Label(f, text=btype.value, font=("Arial", 8),
                     bg=clr, fg="white", padx=4, pady=2).pack()

        # Область графа
        self._fig, self._ax = plt.subplots(figsize=(10, 6))
        self._fig.patch.set_facecolor(_CLR_BG)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(
            fill="both", expand=True, padx=20, pady=(0, 12))

    # ------------------------------------------------------------------
    def set_scores(
        self,
        block_scores:  dict[str, float],
        buffer_scores: dict[str, float],
    ) -> None:
        """Принимает composite scores после симуляции и перерисовывает граф."""
        self._block_scores  = block_scores
        self._buffer_scores = buffer_scores
        if self._heatmap_var.get():
            self._draw()

    @staticmethod
    def _score_to_color(score: float) -> str:
        if score < 0.4:
            return _SCORE_GREEN
        if score < 0.7:
            return _SCORE_YELLOW
        return _SCORE_RED

    # ------------------------------------------------------------------
    def _hierarchical_pos(self, G: nx.DiGraph) -> dict:
        """Иерархическое расположение узлов (longest-path layering)."""
        back = {(u, v) for u, v, d in G.edges(data=True) if d.get("is_back")}

        # DAG без обратных рёбер
        G_dag = nx.DiGraph()
        G_dag.add_nodes_from(G.nodes)
        G_dag.add_edges_from((u, v) for u, v in G.edges() if (u, v) not in back)

        # Уровни — самый длинный путь от истока
        level: dict = {}
        roots = [n for n in G_dag.nodes if G_dag.in_degree(n) == 0]
        queue: deque = deque(roots)
        for n in roots:
            level[n] = 0

        while queue:
            u = queue.popleft()
            for v in G_dag.successors(u):
                new_lv = level[u] + 1
                if v not in level or level[v] < new_lv:
                    level[v] = new_lv
                    queue.append(v)

        for n in G.nodes:
            if n not in level:
                level[n] = 0

        by_level: dict = defaultdict(list)
        for n, lv in level.items():
            by_level[lv].append(n)

        pos: dict = {}
        for lv, nodes in by_level.items():
            y = -lv * _LEVEL_H
            span = (len(nodes) - 1) * _NODE_DX
            for i, n in enumerate(nodes):
                pos[n] = (i * _NODE_DX - span / 2, y)

        return pos

    def _boundary_pts(self, pos: dict, u: str, v: str):
        """Возвращает (начало, конец) ребра u→v на границах прямоугольных узлов."""
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        dx, dy = x2 - x1, y2 - y1
        length = (dx ** 2 + dy ** 2) ** 0.5
        if length < 1e-9:
            return (x1, y1), (x2, y2)
        nx_, ny_ = dx / length, dy / length

        hw, hh = _NODE_W / 2, _NODE_H / 2
        t_src = min(hw / abs(nx_) if abs(nx_) > 1e-9 else 1e9,
                    hh / abs(ny_) if abs(ny_) > 1e-9 else 1e9)
        t_dst = t_src

        start = (x1 + nx_ * t_src, y1 + ny_ * t_src)
        end   = (x2 - nx_ * t_dst, y2 - ny_ * t_dst)
        return start, end

    # ------------------------------------------------------------------
    def _draw(self):
        model = self.app.model
        self._ax.clear()
        self._ax.set_facecolor(_CLR_BG)
        self._ax.axis("off")

        if not model.blocks:
            self._ax.text(0.5, 0.5, "Добавьте блоки на вкладке 1",
                          ha="center", va="center", fontsize=12,
                          color="#888780", transform=self._ax.transAxes)
            self._canvas.draw()
            self._dirty = False
            return

        # Строим граф
        G = nx.DiGraph()
        for bid, block in model.blocks.items():
            G.add_node(bid, label=f"{bid}\n{block.label}", btype=block.type)

        forward_edges, back_edges = [], []
        for edge in model.edges.values():
            if edge.is_back_edge:
                back_edges.append((edge.from_block, edge.to_block))
            else:
                forward_edges.append((edge.from_block, edge.to_block))
            G.add_edge(edge.from_block, edge.to_block, is_back=edge.is_back_edge)

        pos = self._hierarchical_pos(G)

        # Прямые рёбра
        for u, v in forward_edges:
            start, end = self._boundary_pts(pos, u, v)
            self._ax.add_patch(FancyArrowPatch(
                start, end,
                arrowstyle="-|>",
                color="#5F5E5A", lw=1.4,
                mutation_scale=14,
                connectionstyle="arc3,rad=0.04",
                zorder=1,
            ))

        # Обратные рёбра — пунктир оранжевый
        for u, v in back_edges:
            start, end = self._boundary_pts(pos, u, v)
            self._ax.add_patch(FancyArrowPatch(
                start, end,
                arrowstyle="-|>",
                color="#BA7517", lw=1.8,
                linestyle="dashed",
                mutation_scale=16,
                connectionstyle="arc3,rad=0.45",
                zorder=1,
            ))

        # Узлы поверх рёбер
        heatmap = self._heatmap_var.get()
        for nid, (x, y) in pos.items():
            btype = G.nodes[nid]["btype"]
            if heatmap:
                all_scores = {**self._block_scores, **self._buffer_scores}
                color = self._score_to_color(all_scores.get(nid, 0.0))
            else:
                color = _NODE_CLR.get(btype, "#6B7280")

            self._ax.add_patch(FancyBboxPatch(
                (x - _NODE_W / 2, y - _NODE_H / 2), _NODE_W, _NODE_H,
                boxstyle="round,pad=0.06",
                facecolor=color, edgecolor="white", linewidth=1.5,
                zorder=2,
            ))
            self._ax.text(
                x, y, G.nodes[nid]["label"],
                ha="center", va="center",
                fontsize=7, color="white", fontfamily="Arial",
                multialignment="center", linespacing=1.3,
                zorder=3,
            )

        # Подгоняем границы осей
        xs = [x for x, _ in pos.values()]
        ys = [y for _, y in pos.values()]
        self._ax.set_xlim(min(xs) - _NODE_W * 1.2, max(xs) + _NODE_W * 1.2)
        self._ax.set_ylim(min(ys) - _NODE_H * 3,   max(ys) + _NODE_H * 3)

        self._fig.tight_layout()
        self._canvas.draw()
        self._dirty = False

    # ------------------------------------------------------------------
    def mark_dirty(self):
        self._dirty = True

    def on_activate(self):
        if self._dirty:
            self._draw()
