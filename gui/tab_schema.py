"""
gui/tab_schema.py

Вкладка 3 — «Схема».

Автоматически строит граф участка через networkx + matplotlib
и встраивает его в tkinter через FigureCanvasTkAgg.

Обратные рёбра (петли) отображаются пунктиром другого цвета.
Цвет узлов соответствует типу блока.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import networkx as nx
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from model import BlockType


_CLR_BG  = "#F8F7F5"
_CLR_HDR = "#2F5496"
_FONT    = ("Arial", 10)
_FONT_BOLD = ("Arial", 10, "bold")

# Цвета узлов по типу блока (для matplotlib — hex)
_NODE_CLR = {
    BlockType.SOURCE:    "#C0DD97",
    BlockType.TRANSPORT: "#85B7EB",
    BlockType.PROCESS:   "#AFA9EC",
    BlockType.ASSEMBLY:  "#ED93B1",
    BlockType.CONTROL:   "#FAC775",
    BlockType.BUFFER:    "#B4B2A9",
    BlockType.SINK:      "#B4B2A9",
}


class TabSchema(tk.Frame):

    def __init__(self, parent: tk.Frame, app):
        super().__init__(parent, bg=_CLR_BG)
        self.app    = app
        self._dirty = True   # нужно ли перерисовать граф
        self.pack(fill="both", expand=True)
        self._build_ui()

    def _build_ui(self):
        # Панель инструментов
        toolbar = tk.Frame(self, bg=_CLR_BG)
        toolbar.pack(side="top", fill="x", padx=20, pady=(12, 6))

        tk.Button(
            toolbar, text="↺ Перестроить", font=_FONT, relief="flat",
            bg=_CLR_BG, padx=8, pady=2, cursor="hand2",
            command=self._draw,
        ).pack(side="left")

        tk.Label(toolbar, text="Макет:", font=_FONT,
                 bg=_CLR_BG).pack(side="left", padx=(16, 4))
        self._layout_var = tk.StringVar(value="dot")
        for name in ("dot", "spring", "shell"):
            tk.Radiobutton(
                toolbar, text=name, variable=self._layout_var,
                value=name, font=_FONT, bg=_CLR_BG,
                command=self._draw,
            ).pack(side="left")

        # Легенда
        legend_frame = tk.Frame(toolbar, bg=_CLR_BG)
        legend_frame.pack(side="right")
        for btype, clr in _NODE_CLR.items():
            f = tk.Frame(legend_frame, bg=clr,
                         highlightbackground="#888780", highlightthickness=1)
            f.pack(side="left", padx=2)
            tk.Label(f, text=btype.value, font=("Arial", 8),
                     bg=clr, padx=4, pady=2).pack()

        # Область графа
        self._fig, self._ax = plt.subplots(figsize=(10, 6))
        self._fig.patch.set_facecolor(_CLR_BG)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(
            fill="both", expand=True, padx=20, pady=(0, 12))

    def _draw(self):
        """Строит и отрисовывает граф из текущей модели."""
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

        # Строим directed graph
        G = nx.DiGraph()
        for bid, block in model.blocks.items():
            G.add_node(bid, label=f"{bid}\n{block.label}",
                       btype=block.type)

        forward_edges = []
        back_edges    = []
        for edge in model.edges.values():
            if edge.is_back_edge:
                back_edges.append((edge.from_block, edge.to_block))
            else:
                forward_edges.append((edge.from_block, edge.to_block))
            G.add_edge(edge.from_block, edge.to_block,
                       is_back=edge.is_back_edge)

        # Позиции узлов
        layout = self._layout_var.get()
        try:
            if layout == "dot":
                pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
            elif layout == "spring":
                pos = nx.spring_layout(G, seed=42, k=2.5)
            else:
                pos = nx.shell_layout(G)
        except Exception:
            pos = nx.spring_layout(G, seed=42, k=2.5)

        # Цвета узлов
        node_colors = [
            _NODE_CLR.get(G.nodes[n]["btype"], "#DDDDDD")
            for n in G.nodes
        ]
        labels = {n: G.nodes[n]["label"] for n in G.nodes}

        # Рисуем узлы
        nx.draw_networkx_nodes(
            G, pos, ax=self._ax,
            node_color=node_colors,
            node_size=2200,
            node_shape="s",   # квадрат
        )
        nx.draw_networkx_labels(
            G, pos, labels=labels, ax=self._ax,
            font_size=7, font_family="Arial",
        )

        # Прямые рёбра — сплошная линия со стрелками
        nx.draw_networkx_edges(
            G, pos, edgelist=forward_edges, ax=self._ax,
            edge_color="#5F5E5A", width=1.4,
            arrows=True, arrowsize=18,
            arrowstyle="-|>",
            min_source_margin=22, min_target_margin=22,
            connectionstyle="arc3,rad=0.05",
        )
        # Обратные рёбра — пунктир оранжевый
        if back_edges:
            nx.draw_networkx_edges(
                G, pos, edgelist=back_edges, ax=self._ax,
                edge_color="#BA7517", width=1.8,
                style="dashed", arrows=True, arrowsize=20,
                arrowstyle="-|>",
                min_source_margin=22, min_target_margin=22,
                connectionstyle="arc3,rad=0.35",
            )

        self._fig.tight_layout()
        self._canvas.draw()
        self._dirty = False

    def mark_dirty(self):
        """Помечает граф устаревшим — перерисуется при следующей активации."""
        self._dirty = True

    def on_activate(self):
        if self._dirty:
            self._draw()
