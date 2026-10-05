#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apex Quant · Generador de imágenes para la Academia
===================================================
Genera una imagen por módulo (1280x720 px) con matplotlib.

IDEA CLAVE: las velas se definen a mano (o con un generador de swings que
garantiza el extremo exacto de cada swing) y TODAS las zonas se calculan a
partir de esas velas:
  * FVG alcista  = máximo(vela 1) < mínimo(vela 3)  -> zona [max1, min3]
  * Order Block  = cuerpo de la última vela bajista antes del desplazamiento
  * BOS / CHOCH  = línea en el nivel del swing roto, hasta la primera vela
                   que CIERRA más allá de ese nivel
  * RSI 14       = RSI de Wilder calculado sobre los cierres
Así es imposible que una zona quede "fuera de lugar".

Uso:
    pip install matplotlib numpy
    python academy_visuals.py            # crea ./academy_visuals/*.png
    python academy_visuals.py salida/    # carpeta personalizada

Claves (compatibles con callback "academy_visual_<clave>" del bot):
    candles       -> Módulo 2
    institutional -> Módulo 4
    structure     -> Módulo 5
    liquidity     -> Módulo 6
    fvg_ob        -> Módulo 7
    flow          -> Módulo 11
    mtf           -> Módulo 12
"""
import os
import sys
import textwrap

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.patches import Rectangle, FancyBboxPatch, Circle, ConnectionPatch

# ------------------------------------------------------------------
# Tema
# ------------------------------------------------------------------
W, H, DPI = 1280, 720, 100
BG = "#0c0f16"
PANEL = "#10141d"
GRID = "#202636"
TXT = "#e2e6f0"
MUTED = "#8b94a8"
UP = "#2dd28c"
DN = "#eb5a64"
BLUE = "#58b4ff"
ORANGE = "#ffa94d"
PURPLE = "#b48cff"
YELLOW = "#ffd166"
TEAL = "#2ec4b6"
INDIGO = "#7b93ff"
CW = 0.62  # ancho de vela

plt.rcParams["font.family"] = "DejaVu Sans"


# ------------------------------------------------------------------
# Utilidades de velas
# ------------------------------------------------------------------
def seq(start, moves):
    """Construye velas (o, h, l, c) con apertura = cierre anterior.
    moves: lista de (delta_cuerpo, mecha_superior, mecha_inferior)."""
    out, prev = [], float(start)
    for d, wu, wd in moves:
        o, c = prev, prev + d
        out.append((o, max(o, c) + wu, min(o, c) - wd, c))
        prev = c
    return out


def zigzag(points, counts, seed=3, noise=0.10, wick_frac=None):
    """Genera velas que recorren los swings `points` (precio de cada swing).
    counts[j] = nº de velas del tramo j. El extremo de cada swing es EXACTO
    y ninguna vela vecina lo supera. Devuelve (velas, índices_de_swing)."""
    rng = np.random.default_rng(seed)
    wick_frac = wick_frac or {}
    p = list(points)
    n = len(p)
    is_high = [(p[k] > p[k + 1]) if k < n - 1 else (p[k] > p[k - 1]) for k in range(n)]

    step0 = abs(p[1] - p[0]) / counts[0]
    if is_high[0]:
        o, c = p[0] - 0.25 * step0, p[0] - 0.55 * step0
        cand = [[o, p[0], c - rng.uniform(.05, .3) * step0, c]]
    else:
        o, c = p[0] + 0.25 * step0, p[0] + 0.55 * step0
        cand = [[o, c + rng.uniform(.05, .3) * step0, p[0], c]]
    prev, idx, sw = c, 0, [0]

    for j, cnt in enumerate(counts):
        a, b = p[j], p[j + 1]
        step = abs(b - a) / cnt
        up = b > a
        for t in range(1, cnt + 1):
            idx += 1
            o = prev
            if t < cnt:
                c = a + (b - a) * t / cnt + rng.normal(0, noise * step)
                h = max(o, c) + rng.uniform(.05, .3) * step
                l = min(o, c) - rng.uniform(.05, .3) * step
            else:
                wf = wick_frac.get(j + 1, 0.25)
                if up:
                    c = b - wf * step
                    h, l = b, min(o, c) - rng.uniform(.05, .3) * step
                else:
                    c = b + wf * step
                    l, h = b, max(o, c) + rng.uniform(.05, .3) * step
            cand.append([o, h, l, c])
            prev = c
        sw.append(idx)

    # Ninguna vela vecina puede superar el extremo del swing
    for k in range(n):
        lo_i = sw[k - 1] + 1 if k > 0 else 0
        hi_i = sw[k + 1] - 1 if k < n - 1 else len(cand) - 1
        ref = abs(p[k] - (p[k + 1] if k < n - 1 else p[k - 1]))
        m = 0.03 * ref
        for i in range(lo_i, hi_i + 1):
            if i == sw[k]:
                continue
            o, h, l, c = cand[i]
            if is_high[k]:
                lim = p[k] - m
                o, c = min(o, lim - m), min(c, lim - m)
                h = max(min(h, lim), o, c)
            else:
                lim = p[k] + m
                o, c = max(o, lim + m), max(c, lim + m)
                l = min(max(l, lim), o, c)
            cand[i] = [o, h, l, c]

    # Validación: el swing es realmente el extremo de su entorno
    for k in range(n):
        lo_i = sw[k - 1] if k > 0 else 0
        hi_i = sw[k + 1] if k < n - 1 else len(cand) - 1
        seg = cand[lo_i:hi_i + 1]
        if is_high[k]:
            assert abs(max(x[1] for x in seg) - p[k]) < 1e-9, f"swing {k} (high) mal formado"
        else:
            assert abs(min(x[2] for x in seg) - p[k]) < 1e-9, f"swing {k} (low) mal formado"
    return [tuple(x) for x in cand], sw


def find_fvg(cs, i, bullish=True):
    """FVG de 3 velas centrado en la vela i. Devuelve (y_bajo, y_alto) o None."""
    a, c = cs[i - 1], cs[i + 1]
    if bullish and a[1] < c[2]:
        return (a[1], c[2])
    if not bullish and a[2] > c[1]:
        return (c[1], a[2])
    return None


def first_close_beyond(cs, start, level, above=True):
    for i in range(start + 1, len(cs)):
        if (cs[i][3] > level) if above else (cs[i][3] < level):
            return i
    raise ValueError("No hay ruptura con cierre")


def rsi14(closes, n=14):
    closes = np.asarray(closes, float)
    d = np.diff(closes)
    g, l = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    ag, al = g[:n].mean(), l[:n].mean()
    out = [np.nan] * n
    out.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
        out.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    return np.array(out)


# ------------------------------------------------------------------
# Utilidades de dibujo
# ------------------------------------------------------------------
def make_fig(title, subtitle=""):
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=BG)
    fig.text(0.022, 0.952, title, color=TXT, fontsize=18, fontweight="bold", va="center")
    if subtitle:
        fig.text(0.022, 0.908, subtitle, color=MUTED, fontsize=11, va="center")
    return fig


def style_ax(ax, xlim, ylim, grid=True):
    ax.set_facecolor(PANEL)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(GRID)
    if grid:
        for y in np.linspace(ylim[0], ylim[1], 9)[1:-1]:
            ax.axhline(y, color=GRID, lw=0.6, zorder=0)
        for x in range(0, int(xlim[1]), 5):
            ax.axvline(x, color=GRID, lw=0.6, zorder=0)


def draw_candles(ax, cs, width=CW):
    for i, (o, h, l, c) in enumerate(cs):
        col = UP if c >= o else DN
        ax.plot([i, i], [l, h], color=col, lw=1.5, solid_capstyle="butt", zorder=3)
        body = max(abs(c - o), 1e-6)
        ax.add_patch(Rectangle((i - width / 2, min(o, c)), width, body,
                               fc=col, ec=col, lw=0.5, zorder=4))


def zone(ax, x0, x1, y0, y1, color, label=None, alpha=0.20, label_x=None,
         ha="right", fs=10, z=1):
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=to_rgba(color, alpha),
                           ec=to_rgba(color, 0.95), lw=1.2, zorder=z))
    if label:
        ax.text(label_x if label_x is not None else x1 - 0.2, (y0 + y1) / 2, label,
                color=color, ha=ha, va="center", fontsize=fs, fontweight="bold", zorder=7)


def hline(ax, y, x0, x1, color, ls="--", lw=1.3, z=2):
    ax.plot([x0, x1], [y, y], color=color, ls=ls, lw=lw, zorder=z)


def tag(ax, x, y, text, color, ha="center", va="center", fs=10):
    ax.text(x, y, text, color=color, ha=ha, va=va, fontsize=fs, fontweight="bold", zorder=8,
            bbox=dict(boxstyle="round,pad=0.28", fc=BG, ec=color, lw=1.0, alpha=0.95))


def note(ax, text, xy, xytext, color, fs=10, ha="center", va="center"):
    ax.annotate(text, xy=xy, xytext=xytext, color=color, fontsize=fs, fontweight="bold",
                ha=ha, va=va, zorder=8,
                bbox=dict(boxstyle="round,pad=0.28", fc=BG, ec=color, lw=1.0, alpha=0.95),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.6,
                                shrinkA=0, shrinkB=2, mutation_scale=14))


def num_badge(ax, x, y, n, color=TXT):
    ax.text(x, y, str(n), color=BG, ha="center", va="center", fontsize=10, fontweight="bold",
            zorder=9, bbox=dict(boxstyle="circle,pad=0.25", fc=color, ec="none"))


def dot(ax, x, y, color):
    ax.plot([x], [y], marker="o", ms=5, color=color, zorder=6, ls="")


def break_line(ax, cs, i_from, level, above, color, label):
    """Línea de ruptura (BOS/CHOCH) desde el swing hasta la vela que cierra más allá."""
    i_b = first_close_beyond(cs, i_from, level, above)
    hline(ax, level, i_from, i_b, color, ls="--", lw=1.6, z=5)
    dot(ax, i_b, level, color)
    tag(ax, (i_from + i_b) / 2, level, label, color, va="bottom" if above else "top")
    return i_b


# ------------------------------------------------------------------
# MÓDULO 2 · Análisis técnico
# ------------------------------------------------------------------
def m2_tecnico():
    pts = [100, 110, 100.3, 109.7, 103, 117, 110.4, 123, 117, 127]
    cnt = [5, 5, 5, 4, 5, 3, 5, 3, 4]
    cs, sw = zigzag(pts, cnt, seed=11, wick_frac={3: 2.0})
    n = len(cs)

    fig = make_fig("Módulo 2 · Análisis Técnico",
                   "Velas · soporte y resistencia · rango y tendencia · máximos/mínimos · volumen · RSI 14")
    fig.text(0.978, 0.952, "Temporalidad: H1", color=MUTED, fontsize=11, ha="right", va="center")
    axp = fig.add_axes([0.02, 0.34, 0.96, 0.55])
    axv = fig.add_axes([0.02, 0.205, 0.96, 0.12], sharex=axp)
    axr = fig.add_axes([0.02, 0.04, 0.96, 0.15], sharex=axp)
    xlim = (-1, n + 1.5)
    style_ax(axp, xlim, (96, 130))
    style_ax(axv, xlim, (0, 1), grid=False)
    style_ax(axr, xlim, (0, 100), grid=False)
    draw_candles(axp, cs)

    # Soporte y resistencia como ZONAS (no líneas exactas)
    i_s6 = sw[6]
    zone(axp, -0.5, sw[4] + 0.5, 99.5, 100.9, BLUE)
    tag(axp, sw[4] + 1.0, 100.2, "Soporte", BLUE, ha="left")
    zone(axp, -0.5, i_s6 + 1.5, 109.3, 110.5, ORANGE)
    tag(axp, i_s6 + 2.0, 109.9, "Resistencia", ORANGE, ha="left")

    # Máximos y mínimos relevantes
    for k, i in enumerate(sw):
        hi = pts[k] > (pts[k + 1] if k < len(pts) - 1 else pts[k - 1])
        if hi:
            axp.plot([i], [cs[i][1] + 1.0], marker="v", ms=6, color=MUTED, ls="", zorder=6)
        else:
            axp.plot([i], [cs[i][2] - 1.0], marker="^", ms=6, color=MUTED, ls="", zorder=6)

    # Rango
    axp.annotate("", xy=(0, 112.2), xytext=(sw[3], 112.2),
                 arrowprops=dict(arrowstyle="<->", color=YELLOW, lw=1.5))
    tag(axp, sw[3] / 2, 113.6, "Rango", YELLOW)
    # Mecha de rechazo (vela del swing 3, mecha larga)
    note(axp, "Rechazo (mecha)", (sw[3] + 0.1, cs[sw[3]][1]), (sw[3] + 4.2, 115.2), PURPLE)
    # Tendencia: línea que une los mínimos crecientes S4, S6, S8
    xs = [sw[4], sw[6], sw[8]]
    ys = [pts[4], pts[6], pts[8]]
    # Los mínimos crecientes forman la tendencia alcista
    axp.plot(xs, [y - 1.2 for y in ys], color=UP, ls="--", lw=1.6, zorder=5)
    tag(axp, 31.0, 104.5, "Tendencia alcista", UP)

    # Volumen: más actividad en velas de mayor cuerpo
    rng = np.random.default_rng(5)
    vol = np.array([abs(c - o) + 0.7 + rng.uniform(0, 0.9) for o, h, l, c in cs])
    vol = vol / vol.max()
    for i, (o, h, l, c) in enumerate(cs):
        axv.bar(i, vol[i], width=CW, color=to_rgba(UP if c >= o else DN, 0.6), zorder=3)
    axv.set_ylim(0, 1.25)
    axv.text(-0.6, 1.12, "Volumen", color=MUTED, fontsize=10, fontweight="bold", va="center")

    # RSI 14 calculado de verdad
    r = rsi14([c[3] for c in cs])
    axr.axhspan(30, 70, color=to_rgba(MUTED, 0.08), zorder=1)
    axr.axhline(70, color=MUTED, lw=1, ls="--", zorder=2)
    axr.axhline(30, color=MUTED, lw=1, ls="--", zorder=2)
    axr.plot(range(n), r, color=PURPLE, lw=2, zorder=4)
    axr.text(-0.6, 88, "RSI 14", color=MUTED, fontsize=10, fontweight="bold", va="center")
    axr.text(n + 1.3, 70, "70", color=MUTED, fontsize=9, ha="right", va="bottom")
    axr.text(n + 1.3, 30, "30", color=MUTED, fontsize=9, ha="right", va="top")
    return fig


# ------------------------------------------------------------------
# MÓDULO 4 · Análisis institucional
# ------------------------------------------------------------------
def m4_institucional():
    moves = [(1.6, .4, .3), (-2.0, .3, .4), (-1.2, .3, .3), (0.8, .3, .3), (-2.6, .3, .3),
             (-1.6, .3, .4), (0.9, .3, .3), (-2.4, .3, .3), (-2.2, .3, .3), (0.8, .3, .3),
             (-2.5, .3, .3), (-2.3, .3, .3), (0.5, .3, 1.3),          # 12 = mínimo visible 102.0
             (1.2, .3, .3), (0.9, .4, .3), (-1.1, .4, .3), (-1.0, .3, .3),
             (-0.9, .3, 2.7),                                          # 17 = OB + barrido
             (3.6, .3, .3), (3.4, .3, .2), (0.9, .4, .5),             # 18-20 = desplazamiento + FVG
             (1.6, .3, .3), (1.2, .3, .3), (-1.4, .3, .3), (-1.5, .3, .3), (-1.6, .3, .3),
             (-0.9, .2, .7), (1.5, .3, .3), (2.0, .3, .3), (2.2, .3, .3), (1.5, .4, .3)]
    cs = seq(116.0, moves)
    n = len(cs)
    i_low, i_ob, i_fvg = 12, 17, 19
    r_lo, r_hi = cs[i_low][2], cs[0][1]           # rango de referencia 102 - 118
    eq = (r_lo + r_hi) / 2
    fvg = find_fvg(cs, i_fvg)
    assert fvg and cs[i_ob][3] < cs[i_ob][0], "FVG/OB mal definidos"
    assert cs[i_ob][2] < r_lo < cs[i_ob][3], "la vela OB debe barrer el mínimo y cerrar encima"
    ob_lo, ob_hi = cs[i_ob][3], cs[i_ob][0]

    fig = make_fig("Módulo 4 · Análisis Institucional",
                   "Liquidez · barrido · desplazamiento · desequilibrio (FVG) · Order Block · Premium / Discount")
    ax = fig.add_axes([0.02, 0.04, 0.96, 0.84])
    xr = n + 7
    style_ax(ax, (-1, xr), (98.4, 121), grid=False)
    # Premium / Discount
    ax.add_patch(Rectangle((-1, eq), xr + 1, r_hi - eq, fc=to_rgba(DN, 0.09), ec="none", zorder=0))
    ax.add_patch(Rectangle((-1, r_lo), xr + 1, eq - r_lo, fc=to_rgba(UP, 0.09), ec="none", zorder=0))
    hline(ax, eq, -1, xr, MUTED, ls="--", lw=1.2)
    ax.text(xr - 0.4, r_hi - 0.8, "PREMIUM", color=DN, ha="right", va="center", fontsize=12, fontweight="bold")
    ax.text(-0.5, r_lo + 1.0, "DISCOUNT", color=UP, ha="left", va="center", fontsize=12, fontweight="bold")
    ax.text(xr - 0.4, eq + 0.55, "Equilibrio 50 %", color=MUTED, ha="right", va="bottom", fontsize=9.5, fontweight="bold")

    draw_candles(ax, cs)
    # Zonas calculadas
    zone(ax, i_ob - 0.5, xr - 0.2, ob_lo, ob_hi, INDIGO, "Order Block", alpha=0.28, z=2)
    zone(ax, i_fvg - 1.5, xr - 0.2, fvg[0], fvg[1], TEAL, "Fair Value Gap", alpha=0.22, z=2)
    # Liquidez: mínimo visible + barrido
    hline(ax, r_lo, i_low, i_ob + 0.6, YELLOW, ls=":", lw=1.6, z=5)
    tag(ax, 9.3, 100.6, "Liquidez (mínimo visible)", YELLOW)
    note(ax, "Barrido", (i_ob, cs[i_ob][2]), (i_ob, 99.35), YELLOW)
    note(ax, "Desplazamiento", (i_fvg - 0.55, 107.7), (14.3, 112.6), ORANGE)
    return fig


# ------------------------------------------------------------------
# MÓDULO 5 · Estructura de mercado
# ------------------------------------------------------------------
def m5_estructura():
    pts = [100, 112, 105, 120, 113, 128, 121, 126, 111]
    cnt = [5, 3, 5, 3, 5, 3, 3, 5]
    cs, sw = zigzag(pts, cnt, seed=4)
    n = len(cs)
    S = {k: (sw[k], pts[k]) for k in range(len(pts))}

    fig = make_fig("Módulo 5 · Estructura de Mercado", "HH / HL  →  BOS  →  CHOCH")
    ax = fig.add_axes([0.02, 0.04, 0.96, 0.84])
    style_ax(ax, (-1, n + 3), (95, 133))
    draw_candles(ax, cs)
    # Camino de swings
    ax.plot([S[k][0] for k in S], [S[k][1] for k in S], color=TXT, lw=1.1, ls=(0, (2, 3)),
            alpha=0.45, zorder=2)
    labels = {2: "HL", 3: "HH", 4: "HL", 5: "HH", 6: "HL", 7: "LH", 8: "LL"}
    for k, t in labels.items():
        i, p = S[k]
        col = UP if t in ("HH", "HL") else DN
        dot(ax, i, p, col)
        high = t in ("HH", "LH")
        ax.text(i, p + (1.6 if high else -1.6), t, color=col, fontsize=12, fontweight="bold",
                ha="center", va="bottom" if high else "top", zorder=8)
    # BOS alcistas: rompen el máximo anterior (cierre por encima)
    break_line(ax, cs, S[1][0], S[1][1], True, BLUE, "BOS")
    break_line(ax, cs, S[3][0], S[3][1], True, BLUE, "BOS")
    # CHOCH: rompe el último HL (S6) con cierre por debajo
    break_line(ax, cs, S[6][0], S[6][1], False, ORANGE, "CHOCH")
    return fig


# ------------------------------------------------------------------
# MÓDULO 6 · Liquidez y flujo del precio
# ------------------------------------------------------------------
def m6_liquidez():
    pts = [102, 110, 101, 110.1, 101.1]
    cs, sw = zigzag([*pts], [4, 4, 4, 4], seed=8)
    tail = seq(cs[-1][3], [(2.2, .2, .2), (2.0, .2, .2), (1.8, .2, .2), (1.5, .3, .2),
                           (0.4, 2.2, .2),                      # barrido de EQH (mecha) y cierre debajo
                           (-2.6, .2, .2), (-2.2, .2, .2), (-1.0, .2, .3)])  # desplazamiento
    cs = cs + tail
    n = len(cs)
    i_eqh1, i_eql1, i_eqh2, i_eql2 = sw[1], sw[2], sw[3], sw[4]
    eqh = max(cs[i_eqh1][1], cs[i_eqh2][1])
    eql = min(cs[i_eql1][2], cs[i_eql2][2])
    i_sw = i_eql2 + 5
    assert cs[i_sw][1] > eqh and cs[i_sw][3] < eqh, "el barrido debe superar EQH y cerrar debajo"

    fig = make_fig("Módulo 6 · Liquidez y Flujo del Precio",
                   "EQH / EQL · Buy-side y Sell-side liquidity · barrido · desplazamiento posterior")
    ax = fig.add_axes([0.02, 0.04, 0.96, 0.84])
    xr = n + 6
    style_ax(ax, (-1, xr), (97.5, 114))
    draw_candles(ax, cs)
    # Zonas de liquidez (por encima de EQH y por debajo de EQL)
    zone(ax, i_eqh1 - 0.5, xr - 0.2, eqh, eqh + 2.0, ORANGE,
         "Buy-side liquidity (BSL)", alpha=0.16, fs=10.5, z=1)
    zone(ax, i_eql1 - 0.5, xr - 0.2, eql - 1.8, eql, BLUE,
         "Sell-side liquidity (SSL)", alpha=0.16, fs=10.5, z=1)
    # Equal highs / equal lows
    hline(ax, eqh, i_eqh1, i_eqh2, ORANGE, ls=":", lw=1.8, z=5)
    hline(ax, eql, i_eql1, i_eql2, BLUE, ls=":", lw=1.8, z=5)
    for i in (i_eqh1, i_eqh2):
        dot(ax, i, cs[i][1], ORANGE)
    for i in (i_eql1, i_eql2):
        dot(ax, i, cs[i][2], BLUE)
    tag(ax, (i_eqh1 + i_eqh2) / 2, eqh + 1.05, "EQH", ORANGE)
    tag(ax, (i_eql1 + i_eql2) / 2, eql - 1.05, "EQL", BLUE)
    note(ax, "Barrido (sweep)", (i_sw, cs[i_sw][1]), (i_sw - 4.2, cs[i_sw][1] + 1.0), YELLOW)
    note(ax, "Desplazamiento", (i_sw + 2.6, 105.6), (i_sw + 6.4, 108.9), UP)
    return fig


# ------------------------------------------------------------------
# MÓDULO 7 · Order Block + Fair Value Gap
# ------------------------------------------------------------------
def m7_fvg_ob():
    moves = [(-1.5, .5, .5), (-1.2, .4, .4), (0.8, .4, .3), (-1.4, .3, .3),
             (-1.0, .3, .4),                                         # 4 = OB (última bajista)
             (1.2, .2, .2), (3.8, .3, .2), (0.9, .3, .3),            # 5,6,7 = FVG (vela 1,2,3)
             (0.8, .3, .2), (-1.8, .2, .3), (-2.3, .2, .4), (-0.9, .2, .9),
             (1.6, .2, .2), (2.0, .2, .2), (1.5, .3, .2), (1.2, .3, .2)]
    cs = seq(105.0, moves)
    n = len(cs)
    i_ob, i1, i2, i3 = 4, 5, 6, 7
    fvg = find_fvg(cs, i2)
    assert fvg, "no hay FVG: max(vela1) debe ser < min(vela3)"
    assert cs[i_ob][3] < cs[i_ob][0], "el OB debe ser una vela bajista"
    ob_lo, ob_hi = cs[i_ob][3], cs[i_ob][0]

    fig = make_fig("Módulo 7 · Order Block + Fair Value Gap",
                   "FVG: máximo de la vela 1 < mínimo de la vela 3   ·   OB: última vela bajista antes del desplazamiento")
    ax = fig.add_axes([0.02, 0.04, 0.96, 0.84])
    xr = n + 6.5
    style_ax(ax, (-1, xr), (98.4, 110.6))
    draw_candles(ax, cs)
    zone(ax, i_ob - 0.5, xr - 0.2, ob_lo, ob_hi, INDIGO, "Order Block", alpha=0.30, z=2, fs=11)
    zone(ax, i1 - 0.5, xr - 0.2, fvg[0], fvg[1], TEAL, "Fair Value Gap", alpha=0.20, z=2, fs=11)
    num_badge(ax, i1, cs[i1][1] + 0.38, 1, TEAL)
    num_badge(ax, i2, cs[i2][1] + 0.38, 2, TEAL)
    num_badge(ax, i3, cs[i3][1] + 0.38, 3, TEAL)
    note(ax, "Desplazamiento", (i2 - 0.45, 104.3), (2.6, 107.2), ORANGE)
    note(ax, "Reacción en OB + FVG", (11, cs[11][2]), (13.6, 99.5), YELLOW)
    return fig


# ------------------------------------------------------------------
# MÓDULO 11 · Construcción de un análisis (diagrama de flujo)
# ------------------------------------------------------------------
def m11_flujo():
    fig = make_fig("Módulo 11 · Construcción de un Análisis",
                   "Del contexto a la ejecución… o a la espera")
    ax = fig.add_axes([0.02, 0.04, 0.96, 0.84])
    PW, PH = 0.96 * W, 0.84 * H
    ax.set_xlim(-6, PW + 6)
    ax.set_ylim(0, PH)
    ax.axis("off")

    steps = [("Contexto\nde mercado", BLUE), ("Temporalidad\nsuperior", BLUE),
             ("Dirección\ny estructura", BLUE), ("Identificación\nde liquidez", PURPLE),
             ("Búsqueda de\nBOS o CHOCH", PURPLE), ("Identificación\nde OB / FVG", PURPLE),
             ("Confirmación\nen temporalidad\ninferior", ORANGE), ("Definición de\ninvalidación", ORANGE),
             ("Cálculo\ndel riesgo", ORANGE), ("Ejecución\no espera", UP)]
    bw, bh = 212, 170
    gap = (PW - 5 * bw) / 4
    ys = [PH - 30 - bh, PH - 30 - bh - 215]          # y inferior de cada fila
    boxes = []
    for i, (txt, col) in enumerate(steps):
        r, c = divmod(i, 5)
        x0, y0 = c * (bw + gap), ys[r]
        boxes.append((x0, y0))
        ax.add_patch(FancyBboxPatch((x0, y0), bw, bh, boxstyle="round,pad=0,rounding_size=14",
                                    fc=PANEL, ec=col, lw=2.0 if i == 9 else 1.4))
        ax.add_patch(Circle((x0 + 30, y0 + bh - 30), 17, fc=col, ec="none"))
        ax.text(x0 + 30, y0 + bh - 30, str(i + 1), color=BG, ha="center", va="center",
                fontsize=13, fontweight="bold")
        ax.text(x0 + bw / 2, y0 + bh / 2 - 14, txt, color=TXT, ha="center", va="center",
                fontsize=14, fontweight="bold", linespacing=1.35)
    # Flechas dentro de cada fila
    for i in range(10):
        if i % 5 == 4:
            continue
        x0, y0 = boxes[i]
        ax.annotate("", xy=(x0 + bw + gap - 4, y0 + bh / 2), xytext=(x0 + bw + 4, y0 + bh / 2),
                    arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.6, mutation_scale=16))
    # Conector paso 5 -> paso 6 (baja, vuelve a la izquierda y entra)
    x5, y5 = boxes[4]
    x6, y6 = boxes[5]
    ym = (y5 + y6 + bh) / 2
    ax.plot([x5 + bw / 2, x5 + bw / 2, x6 + bw / 2], [y5 - 2, ym, ym], color=MUTED, lw=1.6)
    ax.annotate("", xy=(x6 + bw / 2, y6 + bh + 3), xytext=(x6 + bw / 2, ym),
                arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.6, mutation_scale=16))
    # Complementos
    ax.add_patch(FancyBboxPatch((0, 14), PW, 70, boxstyle="round,pad=0,rounding_size=12",
                                fc="none", ec=GRID, lw=1.2, ls="--"))
    ax.text(PW / 2, 49, "Se complementa con:   volumen   ·   calendario económico   ·   sesiones de mercado",
            color=MUTED, ha="center", va="center", fontsize=13)
    return fig


# ------------------------------------------------------------------
# MÓDULO 12 · Aplicación avanzada (Multi-Timeframe)
# ------------------------------------------------------------------
def m12_mtf():
    # --- H4: contexto alcista, pullback hacia un FVG ---
    h4 = seq(100.0, [(1.5, .3, .3), (2.0, .3, .2), (-1.0, .4, .3), (1.5, .3, .3), (1.0, .6, .3),
                     (-1.2, .3, .2), (-1.4, .2, .4),                  # 6 = mínimo (HL)
                     (2.0, .2, .2), (3.8, .3, .2), (1.0, .4, .6),      # 7,8,9 = FVG H4
                     (1.4, .5, .3), (0.8, .4, .3), (-1.2, .3, .3), (1.3, .3, .3), (0.9, .6, .3),
                     (-1.5, .3, .2), (-1.8, .3, .2), (-1.9, .3, .3), (-1.2, .2, .6)])
    n4 = len(h4)
    fvg4 = find_fvg(h4, 8)
    assert fvg4
    i_hl, i_s1 = 6, 4
    i_hh = max(range(10, n4), key=lambda i: h4[i][1])
    bsl = h4[i_hh][1]

    # --- M5: dentro de la zona H4, barrido -> CHOCH -> OB/FVG -> entrada ---
    m5 = seq(107.60, [(-0.35, .08, .06), (-0.35, .06, .08), (0.20, .10, .06), (-0.40, .06, .08),
                      (-0.35, .05, .07), (0.27, .10, .05),            # 5 = último LH (106.72)
                      (-0.12, .05, .20),                              # 6 = segundo mínimo (EQL)
                      (-0.14, .05, .62),                              # 7 = barrido + OB
                      (0.69, .06, .05), (0.35, .10, .07),             # 8,9 = desplazamiento (FVG 7-8-9)
                      (-0.25, .10, .10), (-0.30, .05, .10),           # 10,11 = retroceso al OB/FVG
                      (0.45, .08, .05), (0.45, .08, .05), (0.40, .08, .05)])
    n5 = len(m5)
    i_lh, i_eql_a, i_sweep = 5, 4, 7
    lh = m5[i_lh][1]
    fvg5 = find_fvg(m5, 8)
    assert fvg5 and m5[i_sweep][2] < min(m5[4][2], m5[6][2]) and m5[i_sweep][3] > min(m5[4][2], m5[6][2])
    ob5 = (m5[i_sweep][3], m5[i_sweep][0])

    fig = make_fig("Módulo 12 · Aplicación Avanzada: Multi-Timeframe",
                   "H4 aporta contexto, estructura y liquidez   →   M5 aporta la confirmación dentro de la zona")
    axL = fig.add_axes([0.02, 0.05, 0.45, 0.80])
    axR = fig.add_axes([0.53, 0.05, 0.45, 0.80])
    xl4 = (-1, n4 + 4.5)
    yl4 = (98.5, 114.8)
    xl5 = (-1, n5 + 4.8)
    yl5 = (104.4, 108.9)
    style_ax(axL, xl4, yl4)
    style_ax(axR, xl5, yl5)
    axL.set_title("H4 · Contexto", color=TXT, fontsize=13, fontweight="bold", loc="left", pad=8)
    axR.set_title("M5 · Confirmación", color=TXT, fontsize=13, fontweight="bold", loc="left", pad=8)

    # ---- Panel H4 ----
    draw_candles(axL, h4)
    zone(axL, 7 - 0.5, xl4[1] - 0.2, fvg4[0], fvg4[1], PURPLE, "Zona H4", alpha=0.20, z=1, fs=10.5)
    # BOS (rompe el máximo del swing 4 con cierre)
    i_b = first_close_beyond(h4, i_s1, h4[i_s1][1], True)
    hline(axL, h4[i_s1][1], i_s1, i_b, BLUE, lw=1.6, z=5)
    dot(axL, i_b, h4[i_s1][1], BLUE)
    tag(axL, (i_s1 + i_b) / 2 - 0.3, h4[i_s1][1] + 0.35, "BOS", BLUE, va="bottom")
    # HL / HH
    dot(axL, i_hl, h4[i_hl][2], UP)
    axL.text(i_hl, h4[i_hl][2] - 0.55, "HL", color=UP, fontsize=11, fontweight="bold", ha="center", va="top")
    dot(axL, i_hh, bsl, UP)
    axL.text(i_hh, bsl + 0.45, "HH", color=UP, fontsize=11, fontweight="bold", ha="center", va="bottom")
    # Liquidez objetivo
    hline(axL, bsl, i_hh, xl4[1] - 0.2, ORANGE, ls=":", lw=1.6, z=5)
    tag(axL, xl4[1] - 0.8, bsl + 0.7, "BSL (objetivo)", ORANGE, ha="right")

    # ---- Panel M5 ----
    draw_candles(axR, m5)
    # Zona H4 como fondo (mismos precios que el panel izquierdo)
    axR.add_patch(Rectangle((xl5[0], fvg4[0]), xl5[1] - xl5[0], fvg4[1] - fvg4[0],
                            fc=to_rgba(PURPLE, 0.10), ec=to_rgba(PURPLE, 0.8), lw=1.1, zorder=0))
    axR.text(xl5[0] + 0.35, fvg4[0] + 0.22, "Zona H4", color=PURPLE, fontsize=10, fontweight="bold",
             va="bottom", ha="left")
    # OB y FVG de M5
    zone(axR, i_sweep - 0.5, xl5[1] - 0.2, ob5[0], ob5[1], INDIGO, "OB M5", alpha=0.35, z=2, fs=9.5)
    zone(axR, i_sweep - 0.5, xl5[1] - 0.2, fvg5[0], fvg5[1], TEAL, "FVG M5", alpha=0.22, z=2, fs=9.5)
    # CHOCH: rompe el último LH con cierre por encima
    i_c = first_close_beyond(m5, i_lh, lh, True)
    hline(axR, lh, i_lh, i_c, ORANGE, lw=1.6, z=5)
    dot(axR, i_c, lh, ORANGE)
    tag(axR, (i_lh + i_c) / 2 - 0.1, lh + 0.07, "CHOCH", ORANGE, va="bottom", fs=9.5)
    # Barrido, entrada, invalidación, objetivo
    note(axR, "Barrido de EQL", (i_sweep - 0.05, m5[i_sweep][2]), (2.4, 105.35), YELLOW, fs=9.5)
    inv = m5[i_sweep][2] - 0.28
    hline(axR, inv, i_sweep + 0.6, n5 - 0.4, DN, ls="--", lw=1.5, z=5)
    tag(axR, n5 - 0.2, inv, "Invalidación", DN, ha="left", fs=9.5)
    note(axR, "Entrada", (11, m5[11][2] - 0.01), (11, 106.1), UP, fs=9.5)
    tag(axR, xl5[1] - 0.4, 108.62, "Objetivo: BSL H4  →", ORANGE, ha="right", fs=9.5)

    # Conectores "zoom" entre la zona H4 y el panel M5
    for y in fvg4:
        fig.add_artist(ConnectionPatch(xyA=(xl4[1], y), coordsA=axL.transData,
                                       xyB=(xl5[0], y), coordsB=axR.transData,
                                       color=PURPLE, lw=1.0, ls=":", alpha=0.8))
    return fig


# ------------------------------------------------------------------
# Registro y ejecución
# ------------------------------------------------------------------
BUILDERS = {
    "candles": m2_tecnico,
    "institutional": m4_institucional,
    "structure": m5_estructura,
    "liquidity": m6_liquidez,
    "fvg_ob": m7_fvg_ob,
    "flow": m11_flujo,
    "mtf": m12_mtf,
}

CAPTIONS = {
    "candles": "🖼️ Módulo 2: velas, soporte/resistencia, rango y tendencia, volumen y RSI 14.",
    "institutional": "🖼️ Módulo 4: liquidez, barrido, desplazamiento, FVG, Order Block y Premium/Discount.",
    "structure": "🖼️ Módulo 5: HH/HL, BOS y CHOCH sobre una estructura alcista.",
    "liquidity": "🖼️ Módulo 6: EQH/EQL, BSL/SSL, barrido y desplazamiento posterior.",
    "fvg_ob": "🖼️ Módulo 7: Fair Value Gap (3 velas) y Order Block con su desplazamiento.",
    "flow": "🖼️ Módulo 11: flujo de análisis de 10 pasos.",
    "mtf": "🖼️ Módulo 12: contexto en H4 y confirmación en M5.",
}


def build_all(outdir="academy_visuals"):
    os.makedirs(outdir, exist_ok=True)
    paths = {}
    for key, fn in BUILDERS.items():
        fig = fn()
        path = os.path.join(outdir, f"{key}.png")
        fig.savefig(path, dpi=DPI, facecolor=BG)
        plt.close(fig)
        paths[key] = path
        print("OK ->", path)
    return paths


if __name__ == "__main__":
    build_all(sys.argv[1] if len(sys.argv) > 1 else "academy_visuals")
