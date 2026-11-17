# -*- coding: utf-8 -*-
"""
Material visual de la Academia Apex Quant — Módulo «Figuras Chartistas».

Cada figura se dibuja con velas japonesas (OHLC) construidas a medida para que
los puntos clave (cimas, valles, líneas de cuello, ruptura, reentrada, Stop Loss
y objetivo) queden exactos. No usa datos reales: son ejemplos educativos.

Uso desde bot.py:
    from chart_patterns_visuals import BUILDERS, CAPTIONS
    ACADEMY_VISUAL_BUILDERS.update(BUILDERS)
    ACADEMY_VISUAL_CAPTIONS.update(CAPTIONS)

Cada builder() devuelve una figura de matplotlib (el bot la guarda y la cierra).
"""

import matplotlib

try:
    matplotlib.use("Agg")
except Exception:  # pragma: no cover
    pass

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle

# ------------------------------------------------------------------
# Estilo Apex Quant (verde neón sobre negro)
# ------------------------------------------------------------------
BG = "#0a0d0b"
PANEL = "#0d120f"
GRID = "#16201a"
GREEN = "#00e676"
RED = "#ff4d5e"
WHITE = "#eef3ef"
GREY = "#8a978e"
YELLOW = "#ffd54a"
ORANGE = "#ff9f43"
CYAN = "#4dd0ff"
SL_COLOR = "#ff5c6c"
TP_COLOR = "#00e676"
ENTRY_COLOR = "#4dd0ff"


# ------------------------------------------------------------------
# Generación de velas
# ------------------------------------------------------------------
def _path(n, wp):
    xs = [p[0] for p in wp]
    ys = [p[1] for p in wp]
    return np.interp(np.arange(n), xs, ys)


def make_candles(n, wp, seed, noise=0.30, wick=0.28, hi_cap=None, lo_cap=None,
                 hi_piv=None, lo_piv=None, forced=None, margin=0.05):
    """Construye velas OHLC siguiendo la ruta de cierres `wp` y respetando topes."""
    rng = np.random.default_rng(seed)
    base = _path(n, wp)
    wpx = {int(p[0]) for p in wp}
    c = base.copy()
    for i in range(n):
        if i not in wpx:
            c[i] += rng.normal(0, noise)
    o = np.empty(n)
    o[0] = c[0] - abs(rng.normal(0, noise * 0.5))
    o[1:] = c[:-1] + rng.normal(0, noise * 0.12, n - 1)
    h = np.maximum(o, c) + np.abs(rng.normal(wick, wick * 0.6, n))
    l = np.minimum(o, c) - np.abs(rng.normal(wick, wick * 0.6, n))
    hi_piv = hi_piv or {}
    lo_piv = lo_piv or {}
    forced = forced or {}
    for i in range(n):
        if i in forced:
            o[i], h[i], l[i], c[i] = forced[i]
            continue
        ch = hi_cap[i] if hi_cap is not None else np.inf
        cl = lo_cap[i] if lo_cap is not None else -np.inf
        top = ch - margin
        bot = cl + margin
        o[i] = min(max(o[i], bot), top)
        c[i] = min(max(c[i], bot), top)
        h[i] = max(min(h[i], ch), o[i], c[i])
        l[i] = min(max(l[i], cl), o[i], c[i])
        if abs(c[i] - o[i]) < 0.14:
            step = 0.16 if base[min(i + 1, n - 1)] >= base[max(i - 1, 0)] else -0.16
            nc = o[i] + step
            if bot + 0.0 <= nc <= top:
                c[i] = nc
            else:
                c[i] = o[i] - step
            h[i] = max(h[i], o[i], c[i])
            l[i] = min(l[i], o[i], c[i])
        if i in hi_piv:
            h[i] = hi_piv[i]
        if i in lo_piv:
            l[i] = lo_piv[i]
    return o, h, l, c


def peak_caps(arr, piv, win=3, slope=0.30):
    n = len(arr)
    for p, v in piv.items():
        for i in range(max(0, p - win), min(n, p + win + 1)):
            arr[i] = min(arr[i], v - slope * abs(i - p))
    return arr


def trough_caps(arr, piv, win=3, slope=0.30):
    n = len(arr)
    for p, v in piv.items():
        for i in range(max(0, p - win), min(n, p + win + 1)):
            arr[i] = max(arr[i], v + slope * abs(i - p))
    return arr


def line_hi(arr, i0, i1, fn, touches, gap=0.30):
    for i in range(i0, i1 + 1):
        arr[i] = fn(i) if i in touches else fn(i) - gap
    return arr


def line_lo(arr, i0, i1, fn, touches, gap=0.30):
    for i in range(i0, i1 + 1):
        arr[i] = fn(i) if i in touches else fn(i) + gap
    return arr


def make_volume(o, c, env, seed, spikes=None):
    n = len(o)
    rng = np.random.default_rng(seed + 99)
    e = _path(n, env)
    body = np.abs(c - o)
    mb = max(body.mean(), 1e-6)
    v = e * (0.75 + 0.5 * rng.random(n)) * (0.75 + 0.45 * np.clip(body / mb, 0, 2.2))
    for i, m in (spikes or {}).items():
        v[i] = max(v[i], m)
    return v


# ------------------------------------------------------------------
# Lienzo
# ------------------------------------------------------------------
class Chart:
    def __init__(self, title, subtitle, n, o, h, l, c, vol, inv=False,
                 right=17, ymargin=(3.2, 6.2)):
        self.n = n
        self.inv = inv
        base_lo = float(np.min(l))
        base_hi = float(np.max(h))
        self.M = base_lo + base_hi
        if inv:
            o, h, l, c = self.M - o, self.M - l, self.M - h, self.M - c
        self.o, self.h, self.l, self.c = o, h, l, c
        self.right = right
        self.fig = plt.figure(figsize=(10, 7.4), dpi=100)
        self.fig.patch.set_facecolor(BG)
        gs = self.fig.add_gridspec(2, 1, height_ratios=[5.2, 1.05], hspace=0.06,
                                   left=0.045, right=0.985, top=0.885, bottom=0.075)
        self.ax = self.fig.add_subplot(gs[0])
        self.axv = self.fig.add_subplot(gs[1], sharex=self.ax)
        for a in (self.ax, self.axv):
            a.set_facecolor(PANEL)
            for s in a.spines.values():
                s.set_color(GRID)
            a.tick_params(colors=GREY, labelsize=8)
            a.grid(True, color=GRID, lw=0.6, alpha=0.8)
        self.ax.set_xticklabels([])
        self.ax.set_yticks([])
        self.axv.set_yticks([])
        self.axv.set_xticks([])
        self.ax.set_xlim(-1.5, n + right)
        if inv:
            ymargin = (ymargin[1], ymargin[0])
        lo = float(np.min(self.l)) - ymargin[0]
        hi = float(np.max(self.h)) + ymargin[1]
        self.ax.set_ylim(lo, hi)
        self.ylo, self.yhi = lo, hi
        self.fig.text(0.045, 0.955, title, color=WHITE, fontsize=17,
                      fontweight="bold", ha="left", va="center")
        self.fig.text(0.045, 0.918, subtitle, color=GREEN, fontsize=10.5,
                      ha="left", va="center")
        self.fig.text(0.985, 0.955, "APEX QUANT", color=GREEN, fontsize=11,
                      fontweight="bold", ha="right", va="center")
        self.fig.text(0.985, 0.918, "ACADEMIA · Figuras chartistas", color=GREY,
                      fontsize=9, ha="right", va="center")
        self.fig.text(0.5, 0.025,
                      "Ejemplo educativo con velas ilustrativas. No es una recomendación de operación "
                      "ni garantiza resultados.",
                      color=GREY, fontsize=8, ha="center", va="center")
        self._candles()
        self._volume(vol)

    # ---- conversiones (para que las variantes espejo reutilicen coordenadas) ----
    def Y(self, v):
        return self.M - v if self.inv else v

    def up(self, d):
        return -d if self.inv else d

    def w(self, a, b):
        return b if self.inv else a

    # ---- dibujo ----
    def _candles(self):
        ax = self.ax
        for i in range(self.n):
            col = GREEN if self.c[i] >= self.o[i] else RED
            ax.vlines(i, self.l[i], self.h[i], color=col, lw=1.1, zorder=3)
            top = max(self.o[i], self.c[i])
            bot = min(self.o[i], self.c[i])
            hgt = max(top - bot, 0.06)
            ax.add_patch(Rectangle((i - 0.32, bot), 0.64, hgt, facecolor=col,
                                   edgecolor=col, lw=0.6, zorder=4))

    def _volume(self, vol):
        for i in range(self.n):
            col = GREEN if self.c[i] >= self.o[i] else RED
            self.axv.bar(i, vol[i], width=0.64, color=col, alpha=0.75, zorder=3)
        self.axv.set_ylim(0, float(np.max(vol)) * 1.25)
        self.axv.text(0.006, 0.10, "Volumen", transform=self.axv.transAxes,
                      color=GREY, fontsize=8.5, ha="left", va="center",
                      bbox=dict(boxstyle="round,pad=0.15", fc=PANEL, ec="none", alpha=0.85), zorder=10)

    def seg(self, x0, y0, x1, y1, color=YELLOW, ls="-", lw=1.8, z=5, alpha=1.0):
        self.ax.plot([x0, x1], [y0, y1], color=color, ls=ls, lw=lw, zorder=z,
                     alpha=alpha, solid_capstyle="round")

    def level(self, y, x0, text, color, ls="--", tag_dy=0.0, lw=1.4):
        xr = self.n + 0.4
        self.ax.plot([x0, xr], [y, y], color=color, ls=ls, lw=lw, zorder=4, alpha=0.95)
        self.ax.text(xr + 0.4, y + tag_dy, text, color=color, fontsize=9.2,
                     fontweight="bold", ha="left", va="center", zorder=7,
                     bbox=dict(boxstyle="round,pad=0.22", fc=BG, ec=color, lw=0.9))

    def dot(self, x, y, txt, dy=1.6, color=WHITE, size=9.5):
        """Burbuja numerada con línea hacia el punto (dy en sentido 'natural')."""
        self.ax.annotate(
            txt, xy=(x, y), xytext=(x, y + self.up(dy)), ha="center", va="center",
            color=BG, fontsize=size, fontweight="bold", zorder=8,
            bbox=dict(boxstyle="circle,pad=0.28", fc=color, ec="none"),
            arrowprops=dict(arrowstyle="-", color=color, lw=1.1, shrinkA=0, shrinkB=1))

    def note(self, x, y, text, color=WHITE, ha="left", size=9.4, bold=False,
             boxed=True, ec=None, va="center"):
        kw = dict(boxstyle="round,pad=0.3", fc=BG, ec=ec or color, lw=0.9) if boxed else None
        self.ax.text(x, y, text, color=color, fontsize=size, ha=ha, va=va,
                     fontweight="bold" if bold else "normal", zorder=8, bbox=kw,
                     linespacing=1.25)

    def pointer(self, x_txt, y_txt, x_pt, y_pt, text, color=WHITE, ha="center",
                size=9.4, bold=True):
        self.ax.annotate(
            text, xy=(x_pt, y_pt), xytext=(x_txt, y_txt), ha=ha, va="center",
            color=color, fontsize=size, fontweight="bold" if bold else "normal",
            zorder=9, linespacing=1.25,
            bbox=dict(boxstyle="round,pad=0.3", fc=BG, ec=color, lw=0.9),
            arrowprops=dict(arrowstyle="-|>", color=color, lw=1.3,
                            shrinkA=2, shrinkB=3))

    def bracket(self, x, y0, y1, text, color=YELLOW, tx=None, ha="left"):
        self.ax.annotate("", xy=(x, y1), xytext=(x, y0),
                         arrowprops=dict(arrowstyle="<->", color=color, lw=1.4,
                                         shrinkA=0, shrinkB=0), zorder=6)
        self.ax.text(x + (tx if tx is not None else 0.6), (y0 + y1) / 2, text,
                     color=color, fontsize=9.6, fontweight="bold", ha=ha,
                     va="center", zorder=8,
                     bbox=dict(boxstyle="round,pad=0.2", fc=BG, ec=color, lw=0.8))

    def vnote(self, x, text, color=WHITE, side="left", row=0.88):
        """Nota sobre el panel de volumen (side: left/right del punto señalado)."""
        ymax = self.axv.get_ylim()[1]
        dx = -4.0 if side == "left" else 4.0
        self.axv.annotate(text, xy=(x, ymax * 0.30), xytext=(x + dx, ymax * row),
                          color=color, fontsize=8.6, fontweight="bold",
                          ha="right" if side == "left" else "left",
                          va="center", zorder=9,
                          arrowprops=dict(arrowstyle="-|>", color=color, lw=1.1),
                          bbox=dict(boxstyle="round,pad=0.2", fc=BG, ec=color, lw=0.8))

    def fig_out(self):
        self.fig.apex_data = (self.o, self.h, self.l, self.c)
        return self.fig


def _mirror_pts(M, pts, inv):
    return pts


# ------------------------------------------------------------------
# FIGURAS DE REVERSIÓN
# ------------------------------------------------------------------
def build_hch(inv=False):
    n = 72
    s = (106.0 - 105.0) / 18.0

    def neck(i):
        return 105.0 + (i - 20) * s

    hp = {14: 112.0, 29: 119.0, 46: 112.6}
    lp = {20: neck(20), 38: neck(38)}
    wp = [(0, 97.0), (5, 102.5), (10, 108.0), (14, 111.5), (17, 108.2), (20, 105.5),
          (24, 110.5), (29, 118.5), (34, 111.0), (38, 106.6), (42, 110.0), (46, 112.1),
          (50, 109.0), (53, 107.8), (54, 104.3), (55, 103.9), (57, 105.7), (58, 105.0),
          (62, 101.0), (66, 97.5), (69, 94.3), (71, 95.2)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    peak_caps(hi_cap, hp)
    for i in range(15, 54):
        lo_cap[i] = neck(i)
    trough_caps(lo_cap, lp, win=2, slope=0.25)
    for i in range(55, n):
        hi_cap[i] = min(hi_cap[i], neck(i))
    hp2 = dict(hp)
    hp2[57] = neck(57)
    lp2 = dict(lp)
    lp2[69] = 93.4
    forced = {54: (107.5, 107.7, 103.9, 104.3)}
    o, h, l, c = make_candles(n, wp, 11, noise=0.32, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp2, lo_piv=lp2, forced=forced)
    env = [(0, 0.9), (14, 1.6), (20, 0.8), (29, 1.0), (38, 0.7), (46, 0.6),
           (53, 0.7), (54, 2.2), (58, 1.1), (71, 0.9)]
    vol = make_volume(o, c, env, 11, spikes={54: 2.6})
    t = ("Hombro-Cabeza-Hombro (HCH)", "Reversión bajista · aparece tras una tendencia alcista") \
        if not inv else \
        ("Hombro-Cabeza-Hombro invertido", "Reversión alcista · aparece tras una tendencia bajista")
    ch = Chart(t[0], t[1], n, o, h, l, c, vol, inv=inv)
    Y, up, w = ch.Y, ch.up, ch.w
    height = 119.0 - neck(29)
    target = neck(54) - height
    # numeración
    ch.dot(14, Y(112.0), "1", 2.2)
    ch.dot(29, Y(119.0), "2", 2.2)
    ch.dot(46, Y(112.6), "3", 2.2)
    ch.note(14, Y(112.0) + up(4.2), "Hombro izq.", GREY, ha="center", boxed=False, size=9)
    ch.note(29, Y(119.0) + up(4.2), "Cabeza", GREY, ha="center", boxed=False, size=9)
    ch.note(46, Y(112.6) + up(4.2), "Hombro der.", GREY, ha="center", boxed=False, size=9)
    # línea de cuello
    ch.seg(20, Y(neck(20)), 38, Y(neck(38)), ORANGE, "-", 2.2)
    ch.seg(38, Y(neck(38)), 70, Y(neck(70)), ORANGE, "--", 1.6)
    ch.dot(20, Y(neck(20)), "a", -1.8, ORANGE, 8.5)
    ch.dot(38, Y(neck(38)), "b", -1.8, ORANGE, 8.5)
    ch.note(27, Y(neck(27)) + up(-3.3), "Línea de cuello (a–b)", ORANGE, ha="center", bold=True)
    # altura H
    ch.bracket(29, Y(116.6), Y(neck(29)), "H", tx=0.7)
    # ruptura y reentrada
    ch.pointer(46.0, Y(99.2), 54, Y(104.0),
               w("Ruptura: cierre\nbajo la línea de cuello", "Ruptura: cierre\nsobre la línea de cuello"),
               WHITE, ha="center")
    ch.pointer(64.5, Y(neck(58)) + up(5.6), 57, Y(neck(57)) + up(0.15),
               "Reentrada (retest)\nde la línea de cuello", CYAN, ha="center")
    # tendencia previa
    ch.pointer(5.5, Y(111.8), 8, Y(106.5),
               w("Tendencia alcista\nprevia", "Tendencia bajista\nprevia"), GREY, ha="center", size=9)
    # niveles
    ch.level(Y(113.1), 46, w("Stop Loss", "Stop Loss"), SL_COLOR)
    ch.level(Y(neck(58)), 58, "Entrada", ENTRY_COLOR)
    ch.level(Y(target), 54, "Objetivo = H", TP_COLOR)
    ch.bracket(n + 1.0, Y(neck(54)), Y(target), "H", tx=0.0, ha="center")
    ch.vnote(54, "Volumen ↑ en la ruptura", side="left")
    ch.vnote(29, "Volumen ↓ en la cabeza", side="left")
    return ch.fig_out()


def build_doble(inv=False):
    n = 57
    NECK = 102.0
    hp = {16: 110.0, 38: 109.6, 49: NECK}
    lp = {27: NECK, 55: 94.0}
    wp = [(0, 94.0), (6, 100.0), (12, 106.5), (16, 109.5), (21, 105.6), (27, 102.5),
          (32, 106.0), (38, 109.2), (42, 105.0), (44, 102.8), (45, 100.7), (47, 99.5),
          (49, 101.3), (50, 100.6), (54, 96.5), (56, 94.8)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    peak_caps(hi_cap, {16: 110.0, 38: 109.6})
    for i in range(17, 45):
        lo_cap[i] = NECK
    trough_caps(lo_cap, {27: NECK}, win=2, slope=0.25)
    for i in range(46, n):
        hi_cap[i] = NECK
    forced = {45: (102.2, 102.4, 100.4, 100.7)}
    o, h, l, c = make_candles(n, wp, 5, noise=0.30, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp, lo_piv=lp, forced=forced)
    env = [(0, 0.8), (16, 1.5), (27, 0.8), (38, 0.75), (44, 0.7), (45, 2.3),
           (50, 1.0), (56, 0.8)]
    vol = make_volume(o, c, env, 5, spikes={45: 2.5})
    t = ("Doble techo", "Reversión bajista · dos máximos similares y ruptura de la línea de cuello") \
        if not inv else \
        ("Doble suelo", "Reversión alcista · dos mínimos similares y ruptura de la línea de cuello")
    ch = Chart(t[0], t[1], n, o, h, l, c, vol, inv=inv)
    Y, up, w = ch.Y, ch.up, ch.w
    target = NECK - (110.0 - NECK)
    ch.dot(16, Y(110.0), "1", 2.2)
    ch.dot(38, Y(109.6), "2", 2.2)
    ch.note(16, Y(110.0) + up(4.2), w("Techo 1", "Suelo 1"), GREY, ha="center", boxed=False, size=9)
    ch.note(38, Y(109.6) + up(4.2), w("Techo 2", "Suelo 2"), GREY, ha="center", boxed=False, size=9)
    ch.seg(16, Y(110.0), 44, Y(109.6 - 0.1), YELLOW, "--", 1.5)
    ch.note(27.5, Y(110.0) + up(1.7), w("Zona de resistencia", "Zona de soporte"), YELLOW,
            ha="center", size=8.8)
    ch.seg(27, Y(NECK), 47, Y(NECK), ORANGE, "-", 2.2)
    ch.dot(27, Y(NECK), "N", -1.9, ORANGE, 8.5)
    ch.note(19.5, Y(NECK) + up(-3.1), "Línea de cuello (mínimo entre los dos techos)"
            if not inv else "Línea de cuello (máximo entre los dos suelos)", ORANGE,
            ha="center", bold=True, size=8.8)
    ch.bracket(16, Y(108.2), Y(NECK), "H", tx=0.7)
    ch.pointer(38.0, Y(96.4), 45, Y(100.5),
               w("Ruptura: cierre\nbajo la línea de cuello", "Ruptura: cierre\nsobre la línea de cuello"),
               WHITE, ha="center")
    ch.pointer(53.5, Y(NECK) + up(5.2), 49, Y(NECK) + up(0.15),
               "Reentrada\n(retest)", CYAN, ha="center")
    ch.pointer(5.5, Y(104.6), 8, Y(101.7),
               w("Tendencia alcista\nprevia", "Tendencia bajista\nprevia"), GREY, ha="center", size=9)
    ch.level(Y(110.8), 38, "Stop Loss", SL_COLOR)
    ch.level(Y(NECK + 0.0), 49, "Entrada", ENTRY_COLOR, tag_dy=ch.up(-0.0))
    ch.level(Y(target), 45, "Objetivo = H", TP_COLOR)
    ch.bracket(n + 1.0, Y(NECK), Y(target), "H", tx=0.0, ha="center")
    ch.vnote(45, "Volumen ↑ en la ruptura", side="left")
    return ch.fig_out()


def build_triple(inv=False):
    n = 69
    SUP = 102.8
    hp = {12: 110.0, 28: 109.7, 44: 110.2, 55: SUP}
    lp = {20: SUP, 36: SUP, 66: 95.5}
    wp = [(0, 95.0), (5, 102.0), (9, 107.0), (12, 109.5), (16, 106.0), (20, 103.4),
          (24, 106.5), (28, 109.2), (32, 105.8), (36, 103.3), (40, 107.0), (44, 109.7),
          (48, 105.5), (50, 103.7), (51, 101.4), (53, 100.5), (55, 102.3), (56, 101.5),
          (61, 98.0), (66, 95.9), (68, 96.8)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    peak_caps(hi_cap, {12: 110.0, 28: 109.7, 44: 110.2})
    for i in range(13, 51):
        lo_cap[i] = SUP
    trough_caps(lo_cap, {20: SUP, 36: SUP}, win=2, slope=0.25)
    for i in range(52, n):
        hi_cap[i] = SUP
    forced = {51: (103.0, 103.2, 101.2, 101.4)}
    o, h, l, c = make_candles(n, wp, 8, noise=0.30, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp, lo_piv=lp, forced=forced)
    env = [(0, 0.8), (12, 1.5), (20, 0.9), (28, 1.0), (36, 0.75), (44, 0.65),
           (50, 0.7), (51, 2.3), (56, 1.1), (68, 0.8)]
    vol = make_volume(o, c, env, 8, spikes={51: 2.6})
    t = ("Triple techo", "Reversión bajista · tres máximos al mismo nivel y ruptura del soporte") \
        if not inv else \
        ("Triple suelo", "Reversión alcista · tres mínimos al mismo nivel y ruptura de la resistencia")
    ch = Chart(t[0], t[1], n, o, h, l, c, vol, inv=inv)
    Y, up, w = ch.Y, ch.up, ch.w
    top = 110.0
    target = SUP - (top - SUP)
    for x, v, k in ((12, 110.0, "1"), (28, 109.7, "2"), (44, 110.2, "3")):
        ch.dot(x, Y(v), k, 2.2)
    ch.note(12, Y(110.0) + up(4.2), w("Techo 1", "Suelo 1"), GREY, ha="center", boxed=False, size=9)
    ch.note(28, Y(109.7) + up(4.2), w("Techo 2", "Suelo 2"), GREY, ha="center", boxed=False, size=9)
    ch.note(44, Y(110.2) + up(4.2), w("Techo 3", "Suelo 3"), GREY, ha="center", boxed=False, size=9)
    ch.seg(12, Y(110.0), 46, Y(110.0), YELLOW, "--", 1.5)
    ch.note(20, Y(110.0) + up(1.7), w("Zona de resistencia", "Zona de soporte"), YELLOW,
            ha="center", size=8.8)
    ch.seg(20, Y(SUP), 51, Y(SUP), ORANGE, "-", 2.2)
    ch.dot(20, Y(SUP), "a", -1.9, ORANGE, 8.5)
    ch.dot(36, Y(SUP), "b", -1.9, ORANGE, 8.5)
    ch.note(28, Y(SUP) + up(-3.1), w("Soporte (línea de cuello)", "Resistencia (línea de cuello)"),
            ORANGE, ha="center", bold=True)
    ch.bracket(12, Y(108.2), Y(SUP), "H", tx=0.7)
    ch.pointer(46.0, Y(96.6), 51, Y(101.4),
               w("Ruptura: cierre\nbajo el soporte", "Ruptura: cierre\nsobre la resistencia"),
               WHITE, ha="center")
    ch.pointer(60, Y(SUP) + up(5.2), 55, Y(SUP) + up(0.15), "Reentrada\n(retest)", CYAN, ha="center")
    ch.pointer(4.5, Y(105.8), 7, Y(104.6),
               w("Tendencia alcista\nprevia", "Tendencia bajista\nprevia"), GREY, ha="center", size=9)
    ch.level(Y(110.9), 44, "Stop Loss", SL_COLOR)
    ch.level(Y(SUP), 55, "Entrada", ENTRY_COLOR)
    ch.level(Y(target), 51, "Objetivo = H", TP_COLOR)
    ch.bracket(n + 1.0, Y(SUP), Y(target), "H", tx=0.0, ha="center")
    ch.vnote(51, "Volumen ↑ en la ruptura", side="left")
    return ch.fig_out()


# ------------------------------------------------------------------
# FIGURAS DE CONTINUACIÓN
# ------------------------------------------------------------------
def build_bandera(inv=False):
    n = 60

    def upper(i):
        return 113.8 - 0.24 * (i - 19)

    def lower(i):
        return upper(i) - 2.6

    ht = {20, 24, 28, 33}
    lt = {22, 26, 31}
    hp = {18: 114.2, **{i: upper(i) for i in ht}, 37: None, 58: 124.2}
    hp = {k: v for k, v in hp.items() if v is not None}
    lp = {**{i: lower(i) for i in lt}, 37: upper(37)}
    wp = [(0, 100.2), (4, 100.8), (7, 100.4), (8, 101.2), (10, 104.0), (12, 107.0), (14, 110.0),
          (16, 112.2), (18, 113.8), (19, 112.3), (20, 113.1), (22, 110.9), (24, 112.2),
          (26, 110.0), (28, 111.2), (31, 108.9), (33, 110.0), (34, 112.0), (35, 113.5),
          (36, 112.3), (37, 111.0), (38, 112.5), (42, 115.5), (46, 118.0), (50, 120.5),
          (54, 122.6), (58, 123.9), (59, 123.2)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    peak_caps(hi_cap, {18: 114.2}, win=2, slope=0.4)
    line_hi(hi_cap, 19, 33, upper, ht, 0.35)
    line_lo(lo_cap, 19, 33, lower, lt, 0.35)
    for i in range(35, 58):
        lo_cap[i] = upper(i) - 0.0
    peak_caps(hi_cap, {58: 124.2}, win=2, slope=0.4)
    forced = {34: (110.0, 112.3, 109.8, 112.0)}
    o, h, l, c = make_candles(n, wp, 21, noise=0.22, wick=0.25, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp, lo_piv=lp, forced=forced)
    env = [(0, 0.6), (8, 0.8), (12, 1.7), (18, 1.6), (19, 0.9), (33, 0.5), (34, 2.2),
           (38, 1.3), (59, 1.0)]
    vol = make_volume(o, c, env, 21, spikes={34: 2.6})
    t = ("Bandera alcista", "Continuación alcista · mástil fuerte + canal inclinado en contra") \
        if not inv else \
        ("Bandera bajista", "Continuación bajista · mástil fuerte + canal inclinado en contra")
    ch = Chart(t[0], t[1], n, o, h, l, c, vol, inv=inv)
    Y, up, w = ch.Y, ch.up, ch.w
    pole = 114.2 - 100.4
    brk = upper(34)
    target = brk + pole
    ch.seg(19, Y(upper(19)), 34, Y(upper(34)), YELLOW, "-", 2.0)
    ch.seg(19, Y(lower(19)), 34, Y(lower(34)), YELLOW, "-", 2.0)
    ch.seg(34, Y(upper(34)), 46, Y(upper(46)), YELLOW, "--", 1.3, alpha=0.7)
    ch.note(26, Y(upper(26)) + up(3.1), w("Bandera: canal paralelo descendente", "Bandera: canal paralelo ascendente"),
            YELLOW, ha="center", bold=True, size=9)
    ch.seg(2.5, Y(100.4), 8.0, Y(100.4), GREY, ":", 1.0)
    ch.seg(2.5, Y(114.2), 18.5, Y(114.2), GREY, ":", 1.0)
    ch.bracket(2.5, Y(100.4), Y(114.2), "Mástil (M)", tx=0.6, ha="left")
    ch.pointer(26.5, Y(105.0), 34, Y(111.8),
               "Ruptura: cierre\nfuera de la bandera",
               WHITE, ha="center")
    ch.pointer(47.5, Y(106.8), 37, Y(upper(37)) + up(0.2), "Reentrada (retest)\nde la línea rota",
               CYAN, ha="center")
    ch.level(Y(lower(31) - 0.6), 31, "Stop Loss", SL_COLOR)
    ch.level(Y(brk), 34, "Entrada", ENTRY_COLOR)
    ch.level(Y(target), 34, "Objetivo = M", TP_COLOR)
    ch.bracket(n + 1.0, Y(brk), Y(target), "M", tx=0.0, ha="center")
    ch.vnote(34, "Volumen ↑ en la ruptura", side="right")
    ch.vnote(15, "Volumen alto en el mástil", side="left")
    return ch.fig_out()


def build_banderin(inv=False):
    n = 56

    def upper(i):
        return 113.9 - 0.12 * (i - 19)

    def lower(i):
        return 109.4 + 0.14 * (i - 19)

    ht = {21, 25, 29}
    lt = {23, 27, 31}
    hp = {18: 114.2, **{i: upper(i) for i in ht}, 54: 125.7}
    lp = {**{i: lower(i) for i in lt}, 37: upper(37)}
    wp = [(0, 100.2), (4, 100.8), (7, 100.4), (8, 101.2), (10, 104.0), (12, 107.0), (14, 110.0),
          (16, 112.2), (18, 113.8), (19, 112.0), (21, 113.4), (23, 111.0), (25, 112.6),
          (27, 111.2), (29, 112.2), (31, 111.5), (32, 113.5), (33, 114.0), (35, 113.5),
          (36, 112.6), (37, 111.9), (38, 113.0), (41, 116.0), (46, 120.0), (51, 123.5),
          (54, 125.2), (55, 124.4)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    peak_caps(hi_cap, {18: 114.2}, win=2, slope=0.4)
    line_hi(hi_cap, 19, 31, upper, ht, 0.30)
    line_lo(lo_cap, 19, 31, lower, lt, 0.30)
    for i in range(33, 54):
        lo_cap[i] = upper(i)
    peak_caps(hi_cap, {54: 125.7}, win=2, slope=0.4)
    forced = {32: (112.1, 113.8, 111.9, 113.5)}
    o, h, l, c = make_candles(n, wp, 31, noise=0.2, wick=0.22, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp, lo_piv=lp, forced=forced)
    env = [(0, 0.6), (8, 0.8), (12, 1.7), (18, 1.6), (19, 0.8), (31, 0.4), (32, 2.2),
           (36, 1.2), (55, 0.9)]
    vol = make_volume(o, c, env, 31, spikes={32: 2.6})
    t = ("Banderín alcista", "Continuación alcista · mástil fuerte + pequeño triángulo que converge") \
        if not inv else \
        ("Banderín bajista", "Continuación bajista · mástil fuerte + pequeño triángulo que converge")
    ch = Chart(t[0], t[1], n, o, h, l, c, vol, inv=inv)
    Y, up, w = ch.Y, ch.up, ch.w
    pole = 114.2 - 100.4
    brk = upper(32)
    target = brk + pole
    ch.seg(19, Y(upper(19)), 33, Y(upper(33)), YELLOW, "-", 2.0)
    ch.seg(19, Y(lower(19)), 33, Y(lower(33)), YELLOW, "-", 2.0)
    ch.seg(33, Y(upper(33)), 44, Y(upper(44)), YELLOW, "--", 1.3, alpha=0.7)
    ch.note(23.5, Y(upper(23)) + up(3.3), "Banderín: triángulo pequeño\nque converge", YELLOW,
            ha="center", bold=True, size=9)
    ch.seg(2.5, Y(100.4), 8.0, Y(100.4), GREY, ":", 1.0)
    ch.seg(2.5, Y(114.2), 18.5, Y(114.2), GREY, ":", 1.0)
    ch.bracket(2.5, Y(100.4), Y(114.2), "Mástil (M)", tx=0.6, ha="left")
    ch.pointer(25.5, Y(105.2), 32, Y(113.3), "Ruptura: cierre\nfuera del banderín", WHITE,
               ha="center")
    ch.pointer(46.0, Y(107.0), 37, Y(upper(37)) + up(0.2), "Reentrada (retest)\nde la línea rota",
               CYAN, ha="center")
    ch.level(Y(lower(31) - 0.7), 31, "Stop Loss", SL_COLOR)
    ch.level(Y(brk), 32, "Entrada", ENTRY_COLOR)
    ch.level(Y(target), 32, "Objetivo = M", TP_COLOR)
    ch.bracket(n + 1.0, Y(brk), Y(target), "M", tx=0.0, ha="center")
    ch.vnote(32, "Volumen ↑ en la ruptura", side="right")
    ch.vnote(15, "Volumen alto en el mástil", side="left")
    return ch.fig_out()


def build_tri_asc(inv=False):
    n = 62
    RES = 112.0

    def lower(i):
        return 103.4 + 0.30 * (i - 18)

    ht = {14, 22, 30, 37}
    lt = {18, 27, 34}
    hp = {**{i: RES for i in ht}, 43: RES, 58: 121.8}
    lp = {i: lower(i) for i in lt}
    wp = [(0, 96.0), (3, 100.0), (7, 105.0), (11, 109.5), (14, 111.5), (16, 107.5), (18, 104.0),
          (20, 108.0), (22, 111.4), (25, 108.4), (27, 106.6), (29, 110.2), (30, 111.4),
          (32, 109.8), (34, 108.7), (36, 111.0), (37, 111.5), (38, 110.9), (39, 113.5),
          (41, 114.2), (42, 113.0), (43, 112.4), (44, 113.4), (48, 116.2), (53, 119.0),
          (58, 121.4), (60, 120.6)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    peak_caps(hi_cap, {58: 121.8}, win=2, slope=0.4)
    line_hi(hi_cap, 14, 38, lambda i: RES, ht, 0.35)
    line_lo(lo_cap, 14, 38, lower, lt, 0.35)
    for i in range(40, 58):
        lo_cap[i] = RES
    forced = {39: (111.5, 113.9, 111.3, 113.6)}
    o, h, l, c = make_candles(n, wp, 41, noise=0.25, wick=0.25, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp, lo_piv=lp, forced=forced)
    # la vela 43 hace el retest tocando la resistencia rota desde arriba
    l[43] = RES
    o[43] = min(o[43], RES + 1.2)
    env = [(0, 1.0), (14, 1.2), (22, 0.95), (30, 0.7), (38, 0.5), (39, 2.3), (44, 1.2), (61, 0.9)]
    vol = make_volume(o, c, env, 41, spikes={39: 2.6})
    t = ("Triángulo ascendente", "Continuación alcista · resistencia horizontal + mínimos cada vez más altos") \
        if not inv else \
        ("Triángulo descendente", "Continuación bajista · soporte horizontal + máximos cada vez más bajos")
    ch = Chart(t[0], t[1], n, o, h, l, c, vol, inv=inv)
    Y, up, w = ch.Y, ch.up, ch.w
    first_low = lower(14)
    height = RES - first_low
    target = RES + height
    ch.seg(14, Y(RES), 39, Y(RES), YELLOW, "-", 2.0)
    ch.seg(39, Y(RES), 46, Y(RES), YELLOW, "--", 1.3, alpha=0.7)
    ch.seg(14, Y(lower(14)), 39, Y(lower(39)), YELLOW, "-", 2.0)
    for x in (14, 22, 30, 37):
        ch.dot(x, Y(RES), str({14: 1, 22: 3, 30: 5, 37: 7}[x]), 2.0, WHITE, 8.5)
    for x in (18, 27, 34):
        ch.dot(x, Y(lower(x)), str({18: 2, 27: 4, 34: 6}[x]), -2.0, WHITE, 8.5)
    ch.note(22, Y(RES) + up(5.4), w("Resistencia horizontal (≥ 2–3 toques)", "Soporte horizontal (≥ 2–3 toques)"),
            YELLOW, ha="center", bold=True, size=8.8)
    ch.note(27.5, Y(lower(26)) + up(-3.9), w("Línea de mínimos crecientes", "Línea de máximos decrecientes"),
            YELLOW, ha="center", bold=True, size=8.8)
    ch.bracket(14.0, Y(RES - 1.4), Y(first_low), "H", tx=0.6)
    ch.pointer(35.5, Y(RES) + up(8.2), 39, Y(113.7), "Ruptura: cierre\nfuera del triángulo", WHITE,
               ha="center")
    ch.pointer(52, Y(109.0), 43, Y(RES) + up(0.25), "Reentrada (retest)\nde la línea rota",
               CYAN, ha="center")
    ch.level(Y(lower(34) - 0.6), 34, "Stop Loss", SL_COLOR)
    ch.level(Y(RES), 39, "Entrada", ENTRY_COLOR)
    ch.level(Y(target), 39, "Objetivo = H", TP_COLOR)
    ch.bracket(n + 1.0, Y(RES), Y(target), "H", tx=0.0, ha="center")
    ch.vnote(39, "Volumen ↑ en la ruptura", side="right")
    ch.vnote(30, "Volumen ↓ al comprimirse", side="left")
    return ch.fig_out()


def build_tri_sim():
    n = 56

    def upper(i):
        return 114.0 - 0.25 * (i - 10)

    def lower(i):
        return 102.0 + 0.25 * (i - 10)

    ht = {10, 16, 22}
    lt = {13, 19, 25}
    hp = {**{i: upper(i) for i in ht}, 31: None, 52: 121.5}
    hp = {k: v for k, v in hp.items() if v is not None}
    lp = {i: lower(i) for i in lt}
    lp[31] = upper(31)
    wp = [(0, 94.0), (3, 99.0), (6, 105.0), (8, 111.0), (10, 113.5), (13, 103.2), (16, 112.0),
          (19, 104.8), (22, 111.0), (25, 107.2), (26, 109.6), (27, 108.4), (28, 110.8),
          (29, 111.6), (30, 110.8), (31, 109.8), (32, 111.6), (36, 114.0), (40, 116.5),
          (44, 118.4), (48, 120.2), (52, 121.2), (54, 120.3)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    line_hi(hi_cap, 10, 27, upper, ht, 0.3)
    line_lo(lo_cap, 10, 27, lower, lt, 0.3)
    peak_caps(hi_cap, {52: 121.5}, win=2, slope=0.4)
    for i in range(30, 52):
        lo_cap[i] = upper(i)
    forced = {28: (108.9, 111.2, 108.7, 110.8)}
    # velas 29 y 30: continúan por encima de la línea superior
    o, h, l, c = make_candles(n, wp, 51, noise=0.22, wick=0.22, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp, lo_piv=lp, forced=forced)
    for i in (26, 27):
        # Evita cierres fuera del triángulo antes de la ruptura
        c[i] = min(c[i], upper(i) - 0.3)
        o[i] = min(o[i], upper(i) - 0.3)
        h[i] = min(h[i], upper(i))
    env = [(0, 1.0), (10, 1.3), (16, 0.95), (22, 0.7), (27, 0.5), (28, 2.2), (32, 1.2), (55, 0.9)]
    vol = make_volume(o, c, env, 51, spikes={28: 2.5})
    ch = Chart("Triángulo simétrico", "Bilateral · rompe a favor o en contra de la tendencia previa",
               n, o, h, l, c, vol)
    Y, up = ch.Y, ch.up
    height = 114.0 - 102.0
    brk = upper(28)
    target = brk + height
    ch.seg(10, upper(10), 29, upper(29), YELLOW, "-", 2.0)
    ch.seg(10, lower(10), 29, lower(29), YELLOW, "-", 2.0)
    ch.seg(29, upper(29), 38, upper(38), YELLOW, "--", 1.3, alpha=0.7)
    ch.seg(29, lower(29), 38, lower(38), YELLOW, "--", 1.3, alpha=0.5)
    ch.dot(10, upper(10), "1", 2.0, WHITE, 8.5)
    ch.dot(13, lower(13), "2", -2.0, WHITE, 8.5)
    ch.dot(16, upper(16), "3", 2.0, WHITE, 8.5)
    ch.dot(19, lower(19), "4", -2.0, WHITE, 8.5)
    ch.dot(22, upper(22), "5", 2.0, WHITE, 8.5)
    ch.dot(25, lower(25), "6", -2.0, WHITE, 8.5)
    ch.note(15.5, 117.6, "Máximos decrecientes (línea superior)", YELLOW, ha="left", bold=True, size=8.8)
    ch.note(16.5, 99.6, "Mínimos crecientes (línea inferior)", YELLOW, ha="left", bold=True, size=8.8)
    ch.bracket(10.0, 112.6, 102.0, "H", tx=0.6)
    ch.pointer(35.5, 102.8, 28, 110.6, "Ruptura: cierre\nfuera del triángulo", WHITE, ha="center")
    ch.pointer(47, 108.4, 31, upper(31) + 0.2, "Reentrada (retest)", CYAN, ha="center")
    ch.note(3.8, 108.6, "Tendencia\nalcista previa", GREY, ha="center", size=8.8)
    ch.level(lower(25) - 0.6, 25, "Stop Loss", SL_COLOR)
    ch.level(brk, 28, "Entrada", ENTRY_COLOR)
    ch.level(target, 28, "Objetivo = H", TP_COLOR)
    ch.bracket(n + 1.0, brk, target, "H", tx=0.0, ha="center")
    ch.note(44.0, 123.4, "Si rompe hacia abajo (cierre bajo la línea inferior),\n"
                         "el escenario es el espejo: objetivo = H hacia abajo.",
            ORANGE, ha="center", size=8.6)
    ch.vnote(28, "Volumen ↑ en la ruptura", side="right")
    ch.vnote(24, "Volumen ↓ al comprimirse", side="left")
    return ch.fig_out()


def build_rectangulo():
    n = 62
    RES, SUP = 110.0, 102.0
    hp = {10: RES, 20: RES, 30: RES, 38: RES, 44: RES, 58: 118.0}
    lp = {15: SUP, 25: SUP, 34: SUP}
    wp = [(0, 92.0), (3, 96.0), (6, 102.5), (8, 107.5), (10, 109.6), (12, 106.0), (15, 102.6),
          (18, 107.0), (20, 109.6), (23, 105.5), (25, 102.6), (28, 107.5), (30, 109.6),
          (32, 106.0), (34, 102.7), (36, 107.0), (38, 109.6), (39, 109.0), (40, 109.2),
          (41, 111.6), (42, 112.6), (43, 111.2), (44, 110.4), (45, 111.8), (49, 114.0),
          (54, 116.5), (58, 117.6), (60, 117.0)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    line_hi(hi_cap, 10, 40, lambda i: RES, {10, 20, 30, 38}, 0.35)
    line_lo(lo_cap, 10, 40, lambda i: SUP, {15, 25, 34}, 0.35)
    for i in range(42, 58):
        lo_cap[i] = RES
    peak_caps(hi_cap, {58: 118.0}, win=2, slope=0.4)
    forced = {41: (109.4, 111.9, 109.2, 111.6)}
    o, h, l, c = make_candles(n, wp, 61, noise=0.24, wick=0.25, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp, lo_piv=lp, forced=forced)
    l[44] = RES
    o[44] = min(o[44], RES + 1.0)
    env = [(0, 1.0), (10, 1.2), (20, 0.8), (30, 0.7), (40, 0.5), (41, 2.2), (45, 1.2), (61, 0.9)]
    vol = make_volume(o, c, env, 61, spikes={41: 2.6})
    ch = Chart("Rectángulo (rango lateral)",
               "Bilateral · soporte y resistencia horizontales; operar la ruptura con cierre",
               n, o, h, l, c, vol)
    height = RES - SUP
    target = RES + height
    ch.seg(10, RES, 41, RES, YELLOW, "-", 2.0)
    ch.seg(41, RES, 47, RES, YELLOW, "--", 1.3, alpha=0.7)
    ch.seg(10, SUP, 41, SUP, YELLOW, "-", 2.0)
    for x, k in ((10, "1"), (20, "3"), (30, "5"), (38, "7")):
        ch.dot(x, RES, k, 2.0, WHITE, 8.5)
    for x, k in ((15, "2"), (25, "4"), (34, "6")):
        ch.dot(x, SUP, k, -2.0, WHITE, 8.5)
    ch.note(25, RES + 3.4, "Resistencia horizontal", YELLOW, ha="center", bold=True, size=9)
    ch.note(25, SUP - 3.6, "Soporte horizontal", YELLOW, ha="center", bold=True, size=9)
    ch.bracket(7.0, RES, SUP, "H", tx=-0.5, ha="right")
    ch.pointer(34.0, 115.6, 41, 111.6, "Ruptura: cierre\nsobre la resistencia", WHITE, ha="center")
    ch.pointer(52.5, 106.8, 44, RES + 0.25, "Reentrada (retest)\nde la resistencia rota", CYAN, ha="center")
    ch.level(105.8, 34, "Stop Loss", SL_COLOR)
    ch.level(RES, 41, "Entrada", ENTRY_COLOR)
    ch.level(target, 41, "Objetivo = H", TP_COLOR)
    ch.bracket(n + 1.0, RES, target, "H", tx=0.0, ha="center")
    ch.note(3.2, 98.0, "Tendencia\nprevia", GREY, ha="center", size=8.8)
    ch.vnote(41, "Volumen ↑ en la ruptura", side="right")
    ch.vnote(32, "Volumen ↓ dentro del rango", side="left")
    return ch.fig_out()


# ------------------------------------------------------------------
# CUÑAS
# ------------------------------------------------------------------
def build_cuna(inv=False):
    n = 62

    def upper(i):
        return 106.0 + 0.30 * (i - 12)

    def lower(i):
        return 100.0 + 0.50 * (i - 12)

    ht = {14, 21, 27, 32}
    lt = {18, 24, 30}
    START = 99.0
    hp = {i: upper(i) for i in ht}
    lp = {10: START, **{i: lower(i) for i in lt}, 56: START + 0.1}
    wp = [(0, 86.0), (3, 90.0), (6, 96.0), (8, 101.6), (9, 100.6), (10, 99.5), (11, 101.2), (12, 103.2), (14, 106.2), (18, 103.5),
          (21, 108.3), (24, 106.4), (27, 110.1), (30, 109.4), (32, 111.6), (33, 111.2),
          (34, 109.8), (35, 108.7), (37, 107.8), (40, 105.4), (44, 103.0), (48, 101.4),
          (52, 100.4), (56, 99.5), (58, 100.2), (61, 101.0)]
    hi_cap = np.full(n, np.inf)
    lo_cap = np.full(n, -np.inf)
    peak_caps(hi_cap, {}, 0)
    line_hi(hi_cap, 13, 33, upper, ht, 0.28)
    line_lo(lo_cap, 13, 33, lower, lt, 0.28)
    for i in range(35, n):
        hi_cap[i] = lower(i) - 0.2
    trough_caps(lo_cap, {10: START, 56: START + 0.1}, win=2, slope=0.35)
    forced = {34: (111.0, 111.2, 109.6, 109.8)}
    o, h, l, c = make_candles(n, wp, 71, noise=0.22, wick=0.24, hi_cap=hi_cap, lo_cap=lo_cap,
                              hi_piv=hp, lo_piv=lp, forced=forced)
    env = [(0, 1.0), (12, 1.2), (21, 0.9), (27, 0.7), (33, 0.55), (34, 2.3), (38, 1.3), (61, 0.9)]
    vol = make_volume(o, c, env, 71, spikes={34: 2.6})
    t = ("Cuña ascendente", "Sesgo bajista · máximos y mínimos suben, pero el rango se estrecha") \
        if not inv else \
        ("Cuña descendente", "Sesgo alcista · máximos y mínimos bajan, pero el rango se estrecha")
    ch = Chart(t[0], t[1], n, o, h, l, c, vol, inv=inv, ymargin=(5.2, 9.0))
    Y, up, w = ch.Y, ch.up, ch.w
    ch.seg(12, Y(upper(12)), 34, Y(upper(34)), YELLOW, "-", 2.0)
    ch.seg(10, Y(lower(10)), 34, Y(lower(34)), YELLOW, "-", 2.0)
    ch.seg(34, Y(lower(34)), 40, Y(lower(40)), YELLOW, "--", 1.3, alpha=0.7)
    ch.dot(10, Y(START), "1", -2.0, WHITE, 8.5)
    ch.dot(14, Y(upper(14)), "2", 2.0, WHITE, 8.5)
    ch.dot(18, Y(lower(18)), "3", -2.0, WHITE, 8.5)
    ch.dot(21, Y(upper(21)), "4", 2.0, WHITE, 8.5)
    ch.dot(24, Y(lower(24)), "5", -2.0, WHITE, 8.5)
    ch.dot(27, Y(upper(27)), "6", 2.0, WHITE, 8.5)
    ch.dot(30, Y(lower(30)), "7", -2.0, WHITE, 8.5)
    ch.note(23.5, Y(upper(23)) + up(7.2), w("Línea superior (sube menos)", "Línea superior (baja más)"),
            YELLOW, ha="center", bold=True, size=8.8)
    ch.note(30.0, Y(lower(26)) + up(-5.6), w("Línea inferior (sube más)", "Línea inferior (baja menos)"),
            YELLOW, ha="center", bold=True, size=8.8)
    ch.pointer(44.0, Y(115.4), 34, Y(109.7),
               w("Ruptura: cierre\nbajo la línea inferior", "Ruptura: cierre\nsobre la línea superior"),
               WHITE, ha="center")
    ch.pointer(3.5, Y(103.2), 5, Y(94.6),
               w("Tendencia alcista\nprevia", "Tendencia bajista\nprevia"), GREY, ha="center", size=9)
    ch.note(49.5, Y(START) + up(9.4), w("A menudo no hay reentrada clara: la línea\ninferior sigue subiendo y el precio cae rápido",
                                       "A menudo no hay reentrada clara: la línea\nsuperior sigue bajando y el precio sube rápido"),
            GREY, ha="center", size=8.4)
    ch.level(Y(upper(32) + 0.9), 32, "Stop Loss", SL_COLOR)
    ch.level(Y(109.8), 34, "Entrada", ENTRY_COLOR)
    ch.level(Y(START + 0.0), 34, "Objetivo: inicio\nde la cuña (1)", TP_COLOR)
    ch.vnote(34, "Volumen ↑ en la ruptura", side="right")
    ch.vnote(28, "Volumen ↓ dentro de la cuña", side="left")
    return ch.fig_out()


# ------------------------------------------------------------------
# RESUMEN VISUAL (esquemas)
# ------------------------------------------------------------------
def build_resumen():
    fig = plt.figure(figsize=(10, 9.6), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.04, 0.975, "Figuras chartistas — resumen visual", color=WHITE, fontsize=17,
             fontweight="bold", ha="left", va="center")
    fig.text(0.04, 0.945, "Esquemas del precio · línea amarilla = línea clave · flecha = sesgo esperado",
             color=GREEN, fontsize=10, ha="left", va="center")
    fig.text(0.97, 0.975, "APEX QUANT", color=GREEN, fontsize=11, fontweight="bold",
             ha="right", va="center")
    # cada panel: (título, categoría, puntos del precio, líneas, sesgo)
    P = [
        ("Hombro-Cabeza-Hombro", "Reversión",
         [(0, 1), (1, 3), (2, 2), (3, 4), (4, 2), (5, 3), (6, 1.5), (7, 0.5)],
         [(1.8, 2, 4.2, 2, "o"), (4.2, 2, 7, 1.6, "o")], -1),
        ("HCH invertido", "Reversión",
         [(0, 3), (1, 1), (2, 2), (3, 0), (4, 2), (5, 1), (6, 2.5), (7, 3.5)],
         [(1.8, 2, 4.2, 2, "o"), (4.2, 2, 7, 2.4, "o")], 1),
        ("Doble techo", "Reversión",
         [(0, 0.5), (1, 2), (2, 3), (3, 2), (4, 1.4), (5, 3), (6, 2), (7, 0.8)],
         [(1.5, 3, 5.3, 3, "y"), (2.8, 1.4, 6.5, 1.4, "o")], -1),
        ("Doble suelo", "Reversión",
         [(0, 3.5), (1, 2), (2, 1), (3, 2), (4, 2.6), (5, 1), (6, 2), (7, 3.2)],
         [(1.5, 1, 5.3, 1, "y"), (2.8, 2.6, 6.5, 2.6, "o")], 1),
        ("Triple techo", "Reversión",
         [(0, 0.5), (1, 2.8), (2, 1.5), (3, 2.8), (4, 1.5), (5, 2.8), (6, 1.4), (7, 0.4)],
         [(1, 2.8, 5.4, 2.8, "y"), (1.5, 1.5, 7, 1.5, "o")], -1),
        ("Triple suelo", "Reversión",
         [(0, 3.5), (1, 1.2), (2, 2.5), (3, 1.2), (4, 2.5), (5, 1.2), (6, 2.6), (7, 3.6)],
         [(1, 1.2, 5.4, 1.2, "y"), (1.5, 2.5, 7, 2.5, "o")], 1),
        ("Bandera alcista", "Continuación",
         [(0, 0.5), (1, 3.5), (2, 3.2), (3, 3.5), (4, 3.0), (5, 3.3), (6, 4.2), (7, 5.2)],
         [(1, 3.6, 5.6, 3.2, "y"), (1, 2.9, 5.6, 2.5, "y")], 1),
        ("Bandera bajista", "Continuación",
         [(0, 5), (1, 2), (2, 2.15), (3, 2.0), (4, 2.55), (5, 2.5), (6, 1.3), (7, 0.3)],
         [(1, 1.7, 5.6, 2.3, "y"), (1, 2.45, 5.6, 3.05, "y")], -1),
        ("Banderín", "Continuación",
         [(0, 0.5), (1, 3.5), (2, 2.8), (3, 3.4), (4, 3.0), (5, 3.3), (6, 4.2), (7, 5.2)],
         [(1, 3.6, 5.6, 3.25, "y"), (1, 2.7, 5.6, 3.15, "y")], 1),
        ("Triángulo ascendente", "Continuación",
         [(0, 0.5), (1, 2.0), (2, 3.2), (3, 2.3), (4, 3.2), (5, 2.7), (6, 3.2), (7, 4.4)],
         [(1.5, 3.2, 6.3, 3.2, "y"), (1.5, 2.0, 6, 3.0, "y")], 1),
        ("Triángulo descendente", "Continuación",
         [(7, 0.5), (6, 2.0), (5, 3.2), (4, 2.3), (3, 3.2), (2, 2.7), (1, 3.2), (0, 4.4)][::-1],
         [(1.5, 2.2, 6.3, 2.2, "y"), (1.5, 3.7, 6, 2.5, "y")], -1),
        ("Triángulo simétrico", "Bilateral",
         [(0, 1), (1, 3.6), (2, 1.6), (3, 3.2), (4, 2.0), (5, 2.9), (6, 2.4), (7, 3.6)],
         [(1, 3.8, 6, 2.6, "y"), (1, 1.4, 6, 2.5, "y")], 0),
        ("Rectángulo", "Bilateral",
         [(0, 1), (1, 3.2), (2, 1.6), (3, 3.2), (4, 1.6), (5, 3.2), (6, 3.8), (7, 4.6)],
         [(1, 3.3, 5.6, 3.3, "y"), (1, 1.5, 5.6, 1.5, "y")], 0),
        ("Cuña ascendente", "Cuña · sesgo bajista",
         [(0, 0.5), (1, 1.6), (2, 1.0), (3, 2.2), (4, 1.8), (5, 2.6), (6, 2.2), (7, 0.8)],
         [(1, 1.5, 5.6, 2.7, "y"), (2, 0.9, 5.6, 2.3, "y")], -1),
        ("Cuña descendente", "Cuña · sesgo alcista",
         [(0, 3.5), (1, 2.6), (2, 3.1), (3, 1.9), (4, 2.3), (5, 1.5), (6, 1.9), (7, 3.3)],
         [(1, 2.7, 5.6, 1.5, "y"), (2, 3.2, 5.6, 1.9, "y")], 1),
    ]
    cols, rows = 4, 4
    for k, (name, cat, pts, lines, bias) in enumerate(P):
        r, cidx = divmod(k, cols)
        ax = fig.add_axes([0.04 + cidx * 0.2375, 0.722 - r * 0.2125, 0.2175, 0.16])
        ax.set_facecolor(PANEL)
        for s in ax.spines.values():
            s.set_color(GRID)
        ax.set_xticks([])
        ax.set_yticks([])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=GREEN, lw=2.0, solid_joinstyle="round", zorder=4)
        for (x0, y0, x1, y1, kind) in lines:
            ax.plot([x0, x1], [y0, y1], color=ORANGE if kind == "o" else YELLOW,
                    lw=1.5, ls="-", zorder=3)
        ax.set_xlim(-0.4, 8.4)
        ax.set_ylim(-0.4, 5.9)
        if bias != 0:
            colr = GREEN if bias > 0 else RED
            ax.annotate("", xy=(7.9, 5.2 if bias > 0 else 0.5), xytext=(7.9, 3.0 if bias > 0 else 2.7),
                        arrowprops=dict(arrowstyle="-|>", color=colr, lw=2.2))
        else:
            ax.annotate("", xy=(7.9, 5.1), xytext=(7.9, 3.4),
                        arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.6))
            ax.annotate("", xy=(7.9, 0.4), xytext=(7.9, 2.1),
                        arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.6))
        ax.text(0.02, 1.05, name, transform=ax.transAxes, color=WHITE, fontsize=9.6,
                fontweight="bold", ha="left", va="bottom")
        ax.text(0.03, 0.05, cat, transform=ax.transAxes, color=GREY, fontsize=7.8,
                ha="left", va="bottom")
    fig.text(0.5, 0.045, "Regla común: no se opera la figura al formarse; se espera la ruptura con cierre de vela "
                         "(idealmente con volumen) y se gestiona el riesgo con Stop Loss.",
             color=GREY, fontsize=8.6, ha="center", va="center", wrap=True)
    fig.text(0.5, 0.020, "Esquemas educativos. No constituyen una recomendación de operación.",
             color=GREY, fontsize=8, ha="center", va="center")
    return fig


# ------------------------------------------------------------------
# Registro para el bot
# ------------------------------------------------------------------
BUILDERS = {
    "fig_resumen": build_resumen,
    "fig_hch": lambda: build_hch(False),
    "fig_hch_inv": lambda: build_hch(True),
    "fig_doble_techo": lambda: build_doble(False),
    "fig_doble_suelo": lambda: build_doble(True),
    "fig_triple_techo": lambda: build_triple(False),
    "fig_triple_suelo": lambda: build_triple(True),
    "fig_bandera_alc": lambda: build_bandera(False),
    "fig_bandera_baj": lambda: build_bandera(True),
    "fig_banderin_alc": lambda: build_banderin(False),
    "fig_banderin_baj": lambda: build_banderin(True),
    "fig_tri_asc": lambda: build_tri_asc(False),
    "fig_tri_desc": lambda: build_tri_asc(True),
    "fig_tri_sim": build_tri_sim,
    "fig_rectangulo": build_rectangulo,
    "fig_cuna_asc": lambda: build_cuna(False),
    "fig_cuna_desc": lambda: build_cuna(True),
}

def _cap(title, legend, confirm, retest, sl, tp):
    return (
        f"📐 {title}\n\n{legend}\n\n"
        f"✅ Confirmación: {confirm}\n"
        f"🔁 Reentrada (opcional): {retest}\n"
        f"🛑 Stop Loss: {sl}\n"
        f"🎯 Objetivo: {tp}\n\n"
        "Velas ilustrativas. Contenido educativo, no es una recomendación de operación."
    )


CAPTIONS = {
    "fig_resumen": (
        "📐 Figuras chartistas — resumen visual\n\n"
        "• Reversión: HCH, doble y triple techo/suelo.\n"
        "• Continuación: banderas, banderines y triángulos ascendente/descendente.\n"
        "• Bilaterales: triángulo simétrico y rectángulo.\n"
        "• Cuñas: ascendente (sesgo bajista) y descendente (sesgo alcista).\n\n"
        "Línea naranja = línea de cuello · línea amarilla = línea de la figura · "
        "flecha = sesgo esperado.\n\n"
        "Ninguna figura se opera al formarse: se espera la ruptura con cierre de vela.\n"
        "Esquemas educativos, no una recomendación de operación."
    ),
    "fig_hch": _cap(
        "Hombro-Cabeza-Hombro (reversión bajista)",
        "1 Hombro izquierdo · 2 Cabeza (máximo más alto) · 3 Hombro derecho (máximo más bajo)\n"
        "a–b Línea de cuello: une los dos mínimos intermedios. H = altura cabeza–cuello.",
        "una vela CIERRA por debajo de la línea de cuello (una mecha no basta). "
        "Suele haber menos volumen en la cabeza y más en la ruptura.",
        "retest de la línea de cuello que el precio rechaza.",
        "sobre el hombro derecho (o sobre la cabeza, más conservador).",
        "H proyectada hacia abajo desde la ruptura."),
    "fig_hch_inv": _cap(
        "Hombro-Cabeza-Hombro invertido (reversión alcista)",
        "1 Hombro izquierdo · 2 Cabeza (mínimo más bajo) · 3 Hombro derecho (mínimo más alto)\n"
        "a–b Línea de cuello: une los dos máximos intermedios. H = altura cuello–cabeza.",
        "una vela CIERRA por encima de la línea de cuello (una mecha no basta). "
        "Más volumen en la ruptura.",
        "retest de la línea de cuello que el precio respeta como soporte.",
        "bajo el hombro derecho (o bajo la cabeza, más conservador).",
        "H proyectada hacia arriba desde la ruptura."),
    "fig_doble_techo": _cap(
        "Doble techo (reversión bajista)",
        "1 y 2 Dos máximos en una zona similar · N Línea de cuello: el mínimo entre ambos techos. "
        "H = altura techo–cuello.",
        "una vela CIERRA por debajo de la línea de cuello. Mientras no cierre por debajo, "
        "solo es un posible rango.",
        "retest de la línea de cuello rechazada desde abajo.",
        "sobre el segundo techo (o sobre el techo más alto).",
        "H proyectada hacia abajo desde la línea de cuello."),
    "fig_doble_suelo": _cap(
        "Doble suelo (reversión alcista)",
        "1 y 2 Dos mínimos en una zona similar · N Línea de cuello: el máximo entre ambos suelos. "
        "H = altura cuello–suelo.",
        "una vela CIERRA por encima de la línea de cuello. Mientras no cierre por encima, "
        "solo es un posible rango.",
        "retest de la línea de cuello respetada como soporte.",
        "bajo el segundo suelo (o bajo el suelo más bajo).",
        "H proyectada hacia arriba desde la línea de cuello."),
    "fig_triple_techo": _cap(
        "Triple techo (reversión bajista)",
        "1, 2 y 3 Tres máximos en la misma zona · a–b Soporte que une los mínimos intermedios "
        "(línea de cuello). H = altura techo–soporte.",
        "una vela CIERRA por debajo del soporte. Tres rechazos no garantizan la caída: "
        "hace falta la ruptura.",
        "retest del soporte roto, ahora resistencia.",
        "sobre el techo más alto.",
        "H proyectada hacia abajo desde el soporte roto."),
    "fig_triple_suelo": _cap(
        "Triple suelo (reversión alcista)",
        "1, 2 y 3 Tres mínimos en la misma zona · a–b Resistencia que une los máximos intermedios "
        "(línea de cuello). H = altura resistencia–suelo.",
        "una vela CIERRA por encima de la resistencia. Tres rebotes no garantizan la subida: "
        "hace falta la ruptura.",
        "retest de la resistencia rota, ahora soporte.",
        "bajo el suelo más bajo.",
        "H proyectada hacia arriba desde la resistencia rota."),
    "fig_bandera_alc": _cap(
        "Bandera alcista (continuación alcista)",
        "M Mástil: impulso fuerte con volumen alto · Bandera: canal paralelo descendente, "
        "corto y con volumen decreciente.",
        "una vela CIERRA por encima de la línea superior de la bandera, idealmente con más volumen.",
        "retest de la línea superior rota (ahora soporte).",
        "bajo el mínimo de la bandera.",
        "M (longitud del mástil) proyectada hacia arriba desde la ruptura."),
    "fig_bandera_baj": _cap(
        "Bandera bajista (continuación bajista)",
        "M Mástil: impulso bajista fuerte con volumen alto · Bandera: canal paralelo ascendente, "
        "corto y con volumen decreciente.",
        "una vela CIERRA por debajo de la línea inferior de la bandera, idealmente con más volumen.",
        "retest de la línea inferior rota (ahora resistencia).",
        "sobre el máximo de la bandera.",
        "M (longitud del mástil) proyectada hacia abajo desde la ruptura."),
    "fig_banderin_alc": _cap(
        "Banderín alcista (continuación alcista)",
        "M Mástil: impulso fuerte · Banderín: pequeño triángulo simétrico que converge, "
        "de corta duración y con volumen decreciente.",
        "una vela CIERRA por encima de la línea superior del banderín, antes de llegar al vértice.",
        "retest de la línea superior rota (ahora soporte).",
        "bajo el último mínimo del banderín.",
        "M proyectada hacia arriba desde la ruptura."),
    "fig_banderin_baj": _cap(
        "Banderín bajista (continuación bajista)",
        "M Mástil: impulso bajista fuerte · Banderín: pequeño triángulo simétrico que converge, "
        "de corta duración y con volumen decreciente.",
        "una vela CIERRA por debajo de la línea inferior del banderín, antes de llegar al vértice.",
        "retest de la línea inferior rota (ahora resistencia).",
        "sobre el último máximo del banderín.",
        "M proyectada hacia abajo desde la ruptura."),
    "fig_tri_asc": _cap(
        "Triángulo ascendente (sesgo alcista)",
        "Resistencia horizontal (1-3-5-7) + mínimos crecientes (2-4-6). "
        "H = altura de la base (parte más ancha).",
        "una vela CIERRA por encima de la resistencia, con volumen creciente y antes del vértice.",
        "retest de la resistencia rota (ahora soporte).",
        "bajo el último mínimo creciente (o bajo la línea ascendente).",
        "H proyectada hacia arriba desde la ruptura."),
    "fig_tri_desc": _cap(
        "Triángulo descendente (sesgo bajista)",
        "Soporte horizontal (1-3-5-7) + máximos decrecientes (2-4-6). "
        "H = altura de la base (parte más ancha).",
        "una vela CIERRA por debajo del soporte, con volumen creciente y antes del vértice.",
        "retest del soporte roto (ahora resistencia).",
        "sobre el último máximo decreciente (o sobre la línea descendente).",
        "H proyectada hacia abajo desde la ruptura."),
    "fig_tri_sim": _cap(
        "Triángulo simétrico (bilateral)",
        "Máximos decrecientes (1-3-5) y mínimos crecientes (2-4-6): dos líneas que convergen. "
        "H = altura de la parte más ancha.",
        "una vela CIERRA fuera de cualquiera de las dos líneas. No se anticipa la dirección.",
        "retest de la línea rota.",
        "dentro del triángulo, tras el último mínimo (ruptura alcista) o máximo (bajista).",
        "H proyectada en el sentido de la ruptura."),
    "fig_rectangulo": _cap(
        "Rectángulo (bilateral)",
        "Soporte y resistencia horizontales con al menos 2 toques cada uno (1-7). "
        "H = altura del rango.",
        "una vela CIERRA fuera del rango; así se distingue una ruptura real de un barrido de liquidez.",
        "retest del nivel roto.",
        "bajo el último mínimo interno o la mitad del rango (el otro extremo es más conservador).",
        "H proyectada en el sentido de la ruptura."),
    "fig_cuna_asc": _cap(
        "Cuña ascendente (sesgo bajista)",
        "Dos líneas ascendentes que convergen (la inferior sube más). Tras tendencia alcista "
        "suele ser reversión; en una tendencia bajista suele ser continuación bajista.",
        "una vela CIERRA por debajo de la línea inferior, con más volumen.",
        "no siempre hay reentrada clara.",
        "sobre el último máximo de la cuña.",
        "inicio de la cuña (zona donde empezó a formarse)."),
    "fig_cuna_desc": _cap(
        "Cuña descendente (sesgo alcista)",
        "Dos líneas descendentes que convergen (la superior baja más). Tras tendencia bajista "
        "suele ser reversión; en una tendencia alcista suele ser continuación alcista.",
        "una vela CIERRA por encima de la línea superior, con más volumen.",
        "no siempre hay reentrada clara.",
        "bajo el último mínimo de la cuña.",
        "inicio de la cuña (zona donde empezó a formarse)."),
}
