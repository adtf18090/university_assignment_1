"""
주식 대시보드 — 다크 모드 · CustomTkinter
원본 소스입니다!!!
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import yfinance as yf
import feedparser
import threading
import time
import datetime
import pandas as pd
import numpy as np

import urllib.request
import urllib.parse
import json

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec

# ─── Palette (색상 팔레트) ──────────────────────────────────────────────────
BG         = "#0D0D0F"
SURFACE    = "#141417"
BORDER     = "#1E1E24"
MUTED      = "#2A2A33"
TEXT_PRI   = "#F0F0F5"
TEXT_SEC   = "#6B6B80"
ACCENT     = "#4F8EF7"
GREEN      = "#2ECC71"
RED        = "#E74C3C"
CHART_LINE = "#4F8EF7"
CHART_FILL = "#1A2840"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

DEFAULT_WATCHLIST = ["AAPL", "TSLA", "NVDA", "MSFT", "005930.KS"]

# ─── Helpers (도우미 함수) ──────────────────────────────────────────────────
def get_currency_symbol(sym: str) -> str:
    return "₩" if sym.endswith(".KS") or sym.endswith(".KQ") else "$"

def fmt_large(n: float, sym: str) -> str:
    try:
        n = float(n or 0)
        if n == 0: return "—"
        curr = get_currency_symbol(sym)
        if n >= 1e12: return f"{curr}{n/1e12:.2f}T"
        if n >= 1e9:  return f"{curr}{n/1e9:.2f}B"
        if n >= 1e6:  return f"{curr}{n/1e6:.2f}M"
        return f"{curr}{n:,.0f}"
    except Exception:
        return "—"

def delta_color(v: float) -> str:
    return GREEN if v >= 0 else RED

def delta_str(v: float) -> str:
    sign = "▲" if v >= 0 else "▼"
    return f"{sign} {abs(v):.2f}%"

def safe_float(v, default=0.0) -> float:
    try:
        return float(v) if v is not None else default
    except Exception:
        return default

# 스마트 검색 기능 (Yahoo Finance API 활용)
def search_yahoo_ticker(query: str):
    safe_query = urllib.parse.quote(query)
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={safe_query}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            quotes = data.get('quotes', [])
            for q in quotes:
                # 주식(EQUITY) 또는 ETF 우선 반환
                if q.get('quoteType') in ('EQUITY', 'ETF'):
                    return q.get('symbol'), q.get('shortname', q.get('longname', query))
    except Exception:
        pass
    return None, None

# ─── Main App (메인 애플리케이션) ───────────────────────────────────────────
class StockDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("주식 시장 대시보드")
        self.geometry("1440x900")
        self.minsize(1200, 720)
        self.configure(fg_color=BG)

        self.selected_ticker = ctk.StringVar(value="AAPL")
        self.watchlist       = list(DEFAULT_WATCHLIST)
        self.ticker_data: dict = {}
        
        self.ticker_names = {
            "AAPL": "Apple", "TSLA": "Tesla", "NVDA": "NVIDIA",
            "MSFT": "Microsoft", "005930.KS": "삼성전자"
        }
        
        # 차트 컨트롤 변수
        self.period_var      = ctk.StringVar(value="1mo")
        self.chart_type_var  = ctk.StringVar(value="라인 차트")
        self.show_sma        = tk.BooleanVar(value=False)
        self.show_vol        = tk.BooleanVar(value=False)
        
        self._chart_canvas   = None
        self.current_hist    = pd.DataFrame()
        
        self.click_points  = []
        self.click_artists = []
        self.ax            = None
        self.ax_vol        = None

        self.bind("<Escape>", lambda e: self._clear_chart_points())

        self._build_layout()
        self._start_data_thread()

    # ── Layout ─────────────────────────────────────────────────────────────────
    def _build_layout(self):
        self.grid_columnconfigure(0, weight=0, minsize=210)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self._build_topbar()
        self._build_sidebar()
        self._build_main()

    # ── Top bar (상단 바) ──────────────────────────────────────────────────────
    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=54)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="◈  시장 동향",
                     font=ctk.CTkFont("Malgun Gothic", 15, weight="bold"),
                     text_color=ACCENT).grid(row=0, column=0, padx=20, sticky="w")

        center = ctk.CTkFrame(bar, fg_color="transparent")
        center.grid(row=0, column=1, pady=10)

        ef = ctk.CTkFrame(center, fg_color=MUTED, corner_radius=7)
        ef.grid(row=0, column=0, padx=5)
        self.add_entry = ctk.CTkEntry(ef, placeholder_text="종목명 또는 티커 검색...",
                                      font=ctk.CTkFont("Malgun Gothic", 12),
                                      fg_color="transparent", border_width=0,
                                      text_color=TEXT_PRI, width=200, height=28)
        self.add_entry.grid(row=0, column=0, padx=(10, 4))
        self.add_entry.bind("<Return>", self._add_ticker)
        ctk.CTkButton(ef, text="＋", width=30, height=28,
                      font=ctk.CTkFont("Arial", 14),
                      fg_color=ACCENT, hover_color="#3a72d4", corner_radius=5,
                      command=lambda: self._add_ticker(None)).grid(row=0, column=1, padx=(0, 4))

        # 설정 버튼
        ctk.CTkButton(center, text="⚙️ 설정", width=60, height=28,
                      font=ctk.CTkFont("Malgun Gothic", 12),
                      fg_color=MUTED, hover_color=BORDER, text_color=TEXT_PRI,
                      command=self._open_settings).grid(row=0, column=1, padx=5)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, padx=20, sticky="e")
        self.src_badge = ctk.CTkLabel(right, text="● 연결됨",
                                      font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
                                      text_color=GREEN)
        self.src_badge.grid(row=0, column=0, padx=(0, 12))
        self.clock_lbl = ctk.CTkLabel(right, text="",
                                      font=ctk.CTkFont("Malgun Gothic", 12),
                                      text_color=TEXT_SEC)
        self.clock_lbl.grid(row=0, column=1)
        self._tick_clock()

    def _tick_clock(self):
        self.clock_lbl.configure(text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ── 설정 창 ──
    def _open_settings(self):
        top = ctk.CTkToplevel(self)
        top.title("설정")
        top.geometry("300x200")
        top.configure(fg_color=SURFACE)
        top.transient(self)
        top.grab_set()

        ctk.CTkLabel(top, text="차트 표시 설정", font=ctk.CTkFont("Malgun Gothic", 14, weight="bold"), 
                     text_color=TEXT_PRI).pack(pady=(20, 10))

        seg = ctk.CTkSegmentedButton(top, values=["라인 차트", "캔들 차트"],
                                     variable=self.chart_type_var,
                                     font=ctk.CTkFont("Malgun Gothic", 12),
                                     command=lambda v: self._refresh_chart_only())
        seg.pack(pady=10)

        ctk.CTkButton(top, text="닫기", width=100, command=top.destroy, 
                      fg_color=MUTED, hover_color=BORDER).pack(pady=20)

    # ── Sidebar (사이드바) ─────────────────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(1, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.sidebar, text="관심 종목 (WATCHLIST)",
                     font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
                     text_color=TEXT_SEC).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self.watch_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", corner_radius=0)
        self.watch_scroll.grid(row=1, column=0, sticky="nsew")
        self.watch_scroll.grid_columnconfigure(0, weight=1)
        self._refresh_sidebar()

    def _refresh_sidebar(self):
        for w in self.watch_scroll.winfo_children():
            w.destroy()
        for i, sym in enumerate(self.watchlist):
            self._sidebar_card(sym, i)

    def _sidebar_card(self, sym: str, idx: int):
        data   = self.ticker_data.get(sym, {})
        price  = data.get("price", 0.0)
        chg    = data.get("change_pct", 0.0)
        active = sym == self.selected_ticker.get()
        name   = self.ticker_names.get(sym, sym)
        curr   = get_currency_symbol(sym)

        card = ctk.CTkFrame(self.watch_scroll, fg_color=MUTED if active else "transparent", corner_radius=7, cursor="hand2")
        card.grid(row=idx, column=0, padx=10, pady=3, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        card.bind("<Button-1>", lambda e, s=sym: self._select_ticker(s))

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, padx=10, pady=(8, 2), sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        sym_lbl = ctk.CTkLabel(top, text=name, font=ctk.CTkFont("Malgun Gothic", 13, weight="bold"),
                               text_color=ACCENT if active else TEXT_PRI, cursor="hand2")
        sym_lbl.grid(row=0, column=0, sticky="w")
        sym_lbl.bind("<Button-1>", lambda e, s=sym: self._select_ticker(s))

        rm = ctk.CTkLabel(top, text="×", font=ctk.CTkFont("Arial", 16), text_color=TEXT_SEC, cursor="hand2")
        rm.grid(row=0, column=1, sticky="e")
        rm.bind("<Button-1>", lambda e, s=sym: self._remove_ticker(s))

        bot = ctk.CTkFrame(card, fg_color="transparent")
        bot.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(bot, text=f"{curr}{price:,.2f}" if price else "—", font=ctk.CTkFont("Courier", 13, weight="bold"), text_color=TEXT_PRI).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(bot, text=delta_str(chg) if price else "", font=ctk.CTkFont("Courier", 11), text_color=delta_color(chg)).grid(row=0, column=1, padx=(8, 0), sticky="w")

    # ── Main panel (메인 패널) ─────────────────────────────────────────────────
    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main.grid(row=1, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=3)
        self.main.grid_rowconfigure(2, weight=2)
        self._build_hero_stats()
        self._build_chart_panel()
        self._build_bottom_row()

    def _build_hero_stats(self):
        self.hero = ctk.CTkFrame(self.main, fg_color="transparent")
        self.hero.grid(row=0, column=0, padx=20, pady=(16, 0), sticky="ew")
        self.hero.grid_columnconfigure(tuple(range(6)), weight=1)

        self.ticker_header = ctk.CTkLabel(self.hero, text="Apple", font=ctk.CTkFont("Malgun Gothic", 28, weight="bold"), text_color=TEXT_PRI)
        self.ticker_header.grid(row=0, column=0, columnspan=6, padx=5, pady=(0, 10), sticky="w")

        self.stat_lbls = {}
        for i, key in enumerate(["현재가", "변동률", "거래량", "시가총액", "52주 최고가", "52주 최저가"]):
            card = ctk.CTkFrame(self.hero, fg_color=SURFACE, corner_radius=8)
            card.grid(row=1, column=i, padx=5, sticky="ew", ipady=8)
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=key, font=ctk.CTkFont("Malgun Gothic", 10, weight="bold"), text_color=TEXT_SEC).grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")
            val = ctk.CTkLabel(card, text="—", font=ctk.CTkFont("Courier", 16, weight="bold"), text_color=TEXT_PRI)
            val.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
            self.stat_lbls[key] = val

    # ── Chart (차트 설정 및 오버레이 옵션) ───────────────────────────────────────
    def _build_chart_panel(self):
        self.chart_frame = ctk.CTkFrame(self.main, fg_color=SURFACE, corner_radius=10)
        self.chart_frame.grid(row=1, column=0, padx=20, pady=12, sticky="nsew")
        self.chart_frame.grid_columnconfigure(0, weight=1)
        self.chart_frame.grid_rowconfigure(1, weight=1)

        ctrl = ctk.CTkFrame(self.chart_frame, fg_color="transparent")
        ctrl.grid(row=0, column=0, padx=16, pady=(12, 0), sticky="ew")
        ctrl.grid_columnconfigure(2, weight=1)

        # 기간 버튼
        btn_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="w")
        self.period_btns = {}
        for j, (label, val) in enumerate([("1시간","1h"), ("1일","1d"), ("1주일","5d"), ("1개월","1mo"), ("3개월","3mo"), ("1년","1y"), ("3년","3y"), ("5년","5y")]):
            btn = ctk.CTkButton(btn_frame, text=label, width=46, height=26, font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
                                fg_color=ACCENT if val == "1mo" else MUTED, hover_color="#3a72d4", corner_radius=5, command=lambda v=val: self._change_period(v))
            btn.grid(row=0, column=j, padx=2)
            self.period_btns[val] = btn

        # 오버레이 체크박스 (SMA, 거래량)
        cb_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        cb_frame.grid(row=0, column=1, padx=15, sticky="w")
        ctk.CTkCheckBox(cb_frame, text="SMA (5,20,60)", variable=self.show_sma, font=ctk.CTkFont("Malgun Gothic", 11), 
                        text_color=TEXT_SEC, command=self._refresh_chart_only).grid(row=0, column=0, padx=5)
        ctk.CTkCheckBox(cb_frame, text="거래량", variable=self.show_vol, font=ctk.CTkFont("Malgun Gothic", 11), 
                        text_color=TEXT_SEC, command=self._refresh_chart_only).grid(row=0, column=1, padx=5)

        self.clear_btn = ctk.CTkButton(ctrl, text="초기화 (ESC)", width=80, height=26, font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"),
                                       fg_color=RED, hover_color="#c0392b", corner_radius=5, command=self._clear_chart_points)
        self.clear_btn.grid(row=0, column=3, sticky="e")
        self.clear_btn.grid_remove()

        self.chart_container = ctk.CTkFrame(self.chart_frame, fg_color="transparent", corner_radius=0)
        self.chart_container.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.chart_container.grid_propagate(False)

        self.loading_lbl = ctk.CTkLabel(self.chart_container, text="차트 불러오는 중…", font=ctk.CTkFont("Malgun Gothic", 12), text_color=TEXT_SEC)
        self.loading_lbl.pack(expand=True)

    def _refresh_chart_only(self):
        """데이터를 다시 다운받지 않고 차트 형태(라인/캔들, 보조지표)만 다시 그림"""
        if not self.current_hist.empty:
            self._draw_chart(self.current_hist)

    def _draw_chart(self, hist):
        self._clear_chart_points()
        self.current_hist = hist

        if self._chart_canvas:
            self._chart_canvas.get_tk_widget().destroy()
            self._chart_canvas = None
        for w in self.chart_container.winfo_children():
            w.destroy()

        if hist is None or hist.empty:
            ctk.CTkLabel(self.chart_container, text="차트 데이터가 없습니다.", font=ctk.CTkFont("Malgun Gothic", 12), text_color=TEXT_SEC).pack(expand=True)
            return

        fig = Figure(figsize=(6, 3.5), dpi=100) 
        fig.patch.set_facecolor(SURFACE)

        # 거래량 체크 여부에 따른 분할 레이아웃
        gs = gridspec.GridSpec(4, 1, hspace=0.1)
        if self.show_vol.get():
            self.ax = fig.add_subplot(gs[0:3, 0])
            self.ax_vol = fig.add_subplot(gs[3, 0], sharex=self.ax)
            self.ax_vol.set_facecolor(SURFACE)
            # 메인 차트의 X축 라벨 숨김 (하단 거래량 차트에만 표시)
            matplotlib.pyplot.setp(self.ax.get_xticklabels(), visible=False)
        else:
            self.ax = fig.add_subplot(gs[:, 0])
            self.ax_vol = None

        self.ax.set_facecolor(SURFACE)

        df = hist.copy()
        dates  = df.index.to_pydatetime()
        df['DateNum'] = mdates.date2num(dates)
        closes = df['Close'].values

        # 1. 메인 차트 (라인 or 캔들)
        is_candle = (self.chart_type_var.get() == "캔들 차트")
        
        if is_candle:
            dx = np.median(np.diff(df['DateNum'])) * 0.7 # 캔들 두께 비율
            if np.isnan(dx) or dx == 0: dx = 0.5
            up = df[df.Close >= df.Open]
            down = df[df.Close < df.Open]
            # Wicks
            self.ax.vlines(up['DateNum'], up.Low, up.High, color=GREEN, linewidth=1, zorder=3)
            self.ax.vlines(down['DateNum'], down.Low, down.High, color=RED, linewidth=1, zorder=3)
            # Bodies
            self.ax.bar(up['DateNum'], up.Close - up.Open, width=dx, bottom=up.Open, color=GREEN, zorder=3)
            self.ax.bar(down['DateNum'], down.Open - down.Close, width=dx, bottom=down.Close, color=RED, zorder=3)
        else:
            self.ax.fill_between(dates, closes, closes.min() * 0.998, color=CHART_FILL, alpha=0.7, zorder=1)
            self.ax.plot(dates, closes, color=CHART_LINE, linewidth=1.6, zorder=3)

        # 2. 이동평균선 (SMA)
        if self.show_sma.get():
            for w, c in [(5, '#f1c40f'), (20, '#9b59b6'), (60, '#e67e22')]:
                sma = df['Close'].rolling(window=w).mean()
                self.ax.plot(dates, sma, color=c, linewidth=1.2, label=f'SMA {w}', zorder=2)
            self.ax.legend(loc="upper left", fontsize=7, framealpha=0.5, facecolor=SURFACE, edgecolor=BORDER, labelcolor=TEXT_PRI)

        # 3. 최고/최저가 표시
        curr = get_currency_symbol(self.selected_ticker.get())
        i_max = closes.argmax(); i_min = closes.argmin()
        self.ax.annotate(f"{curr}{closes[i_max]:,.2f}", xy=(dates[i_max], closes[i_max]), xytext=(0, 8), textcoords="offset points", color=GREEN, fontsize=8, ha="center")
        self.ax.annotate(f"{curr}{closes[i_min]:,.2f}", xy=(dates[i_min], closes[i_min]), xytext=(0, -14), textcoords="offset points", color=RED, fontsize=8, ha="center")

        # 4. 축 설정 (메인)
        self.ax.tick_params(colors=TEXT_SEC, labelsize=8)
        for spine in self.ax.spines.values(): spine.set_edgecolor(BORDER)
        self.ax.set_xlim(dates[0], dates[-1])
        self.ax.yaxis.set_label_position("right")
        self.ax.yaxis.tick_right()
        self.ax.grid(axis="y", color=BORDER, linewidth=0.5, alpha=0.6)
        self.ax.grid(axis="x", color="none")

        # 5. 하단 거래량 표시
        if self.ax_vol:
            dx_vol = np.median(np.diff(df['DateNum'])) * 0.8
            if np.isnan(dx_vol) or dx_vol == 0: dx_vol = 0.5
            colors = [GREEN if c >= o else RED for c, o in zip(df['Close'], df['Open'])]
            self.ax_vol.bar(df['DateNum'], df['Volume'], width=dx_vol, color=colors, alpha=0.8)
            
            self.ax_vol.tick_params(colors=TEXT_SEC, labelsize=7)
            for spine in self.ax_vol.spines.values(): spine.set_edgecolor(BORDER)
            self.ax_vol.yaxis.set_label_position("right")
            self.ax_vol.yaxis.tick_right()
            self.ax_vol.grid(axis="y", color=BORDER, linewidth=0.5, alpha=0.6)
            self.ax_vol.grid(axis="x", color="none")
            
            # 거래량 Y축 큰 수 포맷
            def vol_fmt(x, pos):
                if x >= 1e6: return f'{x*1e-6:.1f}M'
                elif x >= 1e3: return f'{x*1e-3:.0f}K'
                return f'{x:.0f}'
            from matplotlib.ticker import FuncFormatter
            self.ax_vol.yaxis.set_major_formatter(FuncFormatter(vol_fmt))

        # 6. X축 시간 포맷 (가장 아래에 있는 축에 적용)
        bottom_ax = self.ax_vol if self.ax_vol else self.ax
        period = self.period_var.get()
        if period in ("1h", "1d", "5d"):
            bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        elif period in ("1mo", "3mo"):
            bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter("%m월 %d일"))
        else:
            bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter("%y년 %m월"))

        fig.autofmt_xdate(rotation=0, ha="center")
        if not self.show_vol.get():
            fig.tight_layout(pad=1.2)

        self._chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_container)
        self._chart_canvas.mpl_connect('button_press_event', self._on_chart_click)
        self._chart_canvas.draw()
        w = self._chart_canvas.get_tk_widget()
        w.configure(bg=SURFACE, highlightthickness=0)
        w.pack(fill=tk.BOTH, expand=True)

    def _on_chart_click(self, event):
        if not event.inaxes or self.current_hist.empty: return
        # 클릭이 메인 차트(ax)에서 발생했는지 확인
        if event.inaxes != self.ax: return
        if event.button != 1: return

        if len(self.click_points) == 2:
            self._clear_chart_points()

        dates_num = mdates.date2num(self.current_hist.index.to_pydatetime())
        idx = np.argmin(np.abs(dates_num - event.xdata))
        
        px = dates_num[idx]
        py = self.current_hist['Close'].iloc[idx]
        p_date = self.current_hist.index[idx]
        curr = get_currency_symbol(self.selected_ticker.get())
        
        period = self.period_var.get()
        fmt_str = "%m-%d %H:%M" if period in ("1h", "1d", "5d") else "%y-%m-%d"
        date_str = p_date.strftime(fmt_str)

        self.click_points.append((px, py, p_date))

        dot, = self.ax.plot(px, py, marker='o', color='white', markersize=6, zorder=6)
        self.click_artists.append(dot)

        if len(self.click_points) == 1:
            txt = f"{curr}{py:,.2f}\n{date_str}"
            ann = self.ax.annotate(txt, xy=(px, py), xytext=(0, 15), textcoords="offset points",
                                   ha="center", va="bottom", color=TEXT_PRI, fontsize=9, weight="bold",
                                   bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=BORDER, alpha=0.85), zorder=6)
            self.click_artists.append(ann)
            self.clear_btn.grid()
        
        elif len(self.click_points) == 2:
            p1_x, p1_y, _ = self.click_points[0]
            p2_x, p2_y, _ = self.click_points[1]

            line, = self.ax.plot([p1_x, p2_x], [p1_y, p2_y], color='white', linestyle='--', linewidth=1.5, zorder=5)
            self.click_artists.append(line)

            diff = p2_y - p1_y
            pct_change = (diff / p1_y) * 100 if p1_y != 0 else 0
            sign = "+" if diff >= 0 else ""
            color = GREEN if diff >= 0 else RED

            txt = f"{sign}{curr}{diff:,.2f} ({sign}{pct_change:.2f}%)"
            ann = self.ax.annotate(txt, xy=(p2_x, p2_y), xytext=(0, -20), textcoords="offset points",
                                   ha="center", va="top", color=color, fontsize=10, weight="bold",
                                   bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=BORDER, alpha=0.9), zorder=6)
            self.click_artists.append(ann)

        self._chart_canvas.draw()

    def _clear_chart_points(self):
        if not self.click_artists: return
        for artist in self.click_artists:
            artist.remove()
        self.click_artists.clear()
        self.click_points.clear()
        if self._chart_canvas:
            self._chart_canvas.draw()
        self.clear_btn.grid_remove()

    # ── Bottom row (하단 패널) ─────────────────────────────────────────────────
    def _build_bottom_row(self):
        row = ctk.CTkFrame(self.main, fg_color="transparent")
        row.grid(row=2, column=0, padx=20, pady=(0, 16), sticky="nsew")
        row.grid_columnconfigure((0, 1), weight=1)
        row.grid_rowconfigure(0, weight=1)
        self._build_fundamentals(row)
        self._build_news_panel(row)

    def _build_fundamentals(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10)
        frame.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="기본 지표 (FUNDAMENTALS)", font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"), text_color=TEXT_SEC).grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")
        sf = ctk.CTkScrollableFrame(frame, fg_color="transparent", corner_radius=0)
        sf.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        sf.grid_columnconfigure((0, 1), weight=1)
        self.fund_scroll = sf

        self.fund_rows = []
        for i, key in enumerate(["PER", "선행 PER", "EPS (TTM)", "매출", "이익률", "배당수익률", "베타 (Beta)", "평균 거래량", "유동 주식수"]):
            ctk.CTkLabel(sf, text=key, font=ctk.CTkFont("Malgun Gothic", 12), text_color=TEXT_SEC).grid(row=i, column=0, padx=12, pady=4, sticky="w")
            val = ctk.CTkLabel(sf, text="—", font=ctk.CTkFont("Courier", 12), text_color=TEXT_PRI)
            val.grid(row=i, column=1, padx=12, pady=4, sticky="e")
            sep = ctk.CTkFrame(sf, fg_color=BORDER, height=1)
            sep.grid(row=i, column=0, columnspan=2, padx=8, pady=(0, 0), sticky="ew")
            self.fund_rows.append((key, val))

    def _build_news_panel(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10)
        frame.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="최신 뉴스 (LATEST NEWS)", font=ctk.CTkFont("Malgun Gothic", 11, weight="bold"), text_color=TEXT_SEC).grid(row=0, column=0, sticky="w")
        self.news_status = ctk.CTkLabel(hdr, text="● 대기중", font=ctk.CTkFont("Malgun Gothic", 10, weight="bold"), text_color=TEXT_SEC)
        self.news_status.grid(row=0, column=1, sticky="e")

        sf = ctk.CTkScrollableFrame(frame, fg_color="transparent", corner_radius=0)
        sf.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        sf.grid_columnconfigure(0, weight=1)
        self.news_scroll = sf
        self._populate_news([])

    def _populate_news(self, items: list):
        for w in self.news_scroll.winfo_children(): w.destroy()
        if not items:
            ctk.CTkLabel(self.news_scroll, text="뉴스 불러오는 중…", font=ctk.CTkFont("Malgun Gothic", 12), text_color=TEXT_SEC, wraplength=340).grid(row=0, column=0, padx=12, pady=12)
            return
        for i, item in enumerate(items[:14]):
            card = ctk.CTkFrame(self.news_scroll, fg_color=MUTED if i % 2 == 0 else "transparent", corner_radius=6)
            card.grid(row=i, column=0, padx=6, pady=2, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=item.get("title", ""), font=ctk.CTkFont("Malgun Gothic", 12), text_color=TEXT_PRI, wraplength=360, justify="left", anchor="w").grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")
            meta = "  ·  ".join(filter(None, [item.get("source"), item.get("published")]))
            ctk.CTkLabel(card, text=meta, font=ctk.CTkFont("Malgun Gothic", 10), text_color=TEXT_SEC, anchor="w").grid(row=1, column=0, padx=10, pady=(0, 6), sticky="w")

    # ── Data fetching ────────────────────────────────────────────────────────────
    def _start_data_thread(self):
        threading.Thread(target=self._data_loop, daemon=True).start()

    def _data_loop(self):
        while True:
            self._fetch_all_tickers()
            sym = self.selected_ticker.get()
            self._fetch_detail(sym)
            self._fetch_news(sym)
            time.sleep(60)

    def _fetch_all_tickers(self):
        failed_any = False
        for sym in list(self.watchlist):
            try:
                hist = yf.Ticker(sym).history(period="5d")
                if hist.empty: raise ValueError("No data")
                price = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else price
                chg = ((price - prev) / prev * 100) if prev else 0
                self.ticker_data[sym] = {"price": price, "change_pct": chg}
            except Exception:
                failed_any = True
                self.ticker_data[sym] = {"price": 0.0, "change_pct": 0.0}
        self.after(0, self._refresh_sidebar)
        badge = "● 실시간" if not failed_any else "○ 일부 연결 실패"
        col   = GREEN if not failed_any else RED
        self.after(0, lambda: self.src_badge.configure(text=badge, text_color=col))

    def _fetch_detail(self, sym: str):
        try:
            tk_obj = yf.Ticker(sym)
            info = tk_obj.info
            period = self.period_var.get()
            
            if period == "1h":
                hist = tk_obj.history(period="1d", interval="1m")
                if not hist.empty: hist = hist.tail(60)
            elif period == "1d":
                hist = tk_obj.history(period="1d", interval="5m")
            elif period == "5d":
                hist = tk_obj.history(period="5d", interval="15m")
            elif period == "3y":
                hist = tk_obj.history(period="5y", interval="1d")
                if not hist.empty:
                    cutoff = hist.index[-1] - pd.DateOffset(years=3)
                    hist = hist[hist.index >= cutoff]
            else:
                hist = tk_obj.history(period=period, auto_adjust=True)

            if hist.empty: raise ValueError("No history")
            
            price = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else price
            chg = ((price - prev) / prev * 100) if prev else 0

            hist_52w = tk_obj.history(period="1y")
            high_52w = hist_52w['High'].max() if not hist_52w.empty else 0
            low_52w = hist_52w['Low'].min() if not hist_52w.empty else 0

            curr = get_currency_symbol(sym)
            stats = {
                "현재가":     f"{curr}{price:,.2f}", "변동률":     delta_str(chg),
                "거래량":     fmt_large(info.get("volume") or hist['Volume'].iloc[-1], sym),
                "시가총액":   fmt_large(info.get("marketCap", 0), sym),
                "52주 최고가": f"{curr}{high_52w:,.2f}" if high_52w else "—",
                "52주 최저가":  f"{curr}{low_52w:,.2f}"  if low_52w  else "—",
            }
            fund = {
                "PER":           str(round(safe_float(info.get("trailingPE")), 1)) if info.get("trailingPE") else "—",
                "선행 PER":        str(round(safe_float(info.get("forwardPE")), 1)) if info.get("forwardPE") else "—",
                "EPS (TTM)":     str(round(safe_float(info.get("trailingEps")), 2)) if info.get("trailingEps") else "—",
                "매출":           fmt_large(info.get("totalRevenue", 0), sym),
                "이익률":          f"{round(safe_float(info.get('profitMargins'))*100, 1)}%" if info.get("profitMargins") else "—",
                "배당수익률":        f"{round(safe_float(info.get('dividendYield'))*100, 2)}%" if info.get("dividendYield") else "—",
                "베타 (Beta)":   str(round(safe_float(info.get("beta")), 2)) if info.get("beta") else "—",
                "평균 거래량":       fmt_large(info.get("averageVolume", 0), sym),
                "유동 주식수":       fmt_large(info.get("floatShares", 0), sym),
            }
            chg_col = delta_color(chg)
            self.after(0, lambda: self._update_detail_ui(sym, stats, fund, hist, chg_col))

        except Exception:
            empty_stats = {k: "—" for k in ["현재가", "변동률", "거래량", "시가총액", "52주 최고가", "52주 최저가"]}
            empty_fund  = {k: "—" for k in ["PER", "선행 PER", "EPS (TTM)", "매출", "이익률", "배당수익률", "베타 (Beta)", "평균 거래량", "유동 주식수"]}
            self.after(0, lambda: self._update_detail_ui(sym, empty_stats, empty_fund, pd.DataFrame(), TEXT_PRI))

    def _update_detail_ui(self, sym, stats, fund, hist, chg_col):
        name = self.ticker_names.get(sym, sym)
        self.ticker_header.configure(text=name)
        for key, lbl in self.stat_lbls.items():
            col = chg_col if key == "변동률" else TEXT_PRI
            lbl.configure(text=stats.get(key, "—"), text_color=col)
        for key, val_lbl in self.fund_rows:
            val_lbl.configure(text=fund.get(key, "—"))
        self._draw_chart(hist)

    def _fetch_news(self, sym: str):
        try:
            url = f"https://news.google.com/rss/search?q={sym}+stock&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            if not feed.entries: raise ValueError("No entries found")
            items = []
            for e in feed.entries[:15]:
                try:
                    dt  = datetime.datetime(*e.published_parsed[:6])
                    pub = dt.strftime("%Y-%m-%d %H:%M")
                except Exception: pub = ""
                src = e.source.get("title", "") if hasattr(e, "source") else ""
                title = e.get("title", "").rsplit(" - ", 1)[0] if " - " in e.get("title", "") else e.get("title", "")
                items.append({"title": title, "source": src, "published": pub})
            self.after(0, lambda: self._populate_news(items))
            self.after(0, lambda: self.news_status.configure(text="● 실시간", text_color=GREEN))
        except Exception:
            self.after(0, lambda: self._show_news_error())

    def _show_news_error(self):
        for w in self.news_scroll.winfo_children(): w.destroy()
        ctk.CTkLabel(self.news_scroll, text="뉴스를 불러올 수 없습니다.", font=ctk.CTkFont("Malgun Gothic", 12), text_color=RED).grid(row=0, column=0, padx=12, pady=12)
        self.news_status.configure(text="○ 오류", text_color=RED)

    # ── 상호작용 (종목 검색 및 추가) ──────────────────────────────────────────
    def _select_ticker(self, sym: str):
        if self.selected_ticker.get() == sym: return
        self.selected_ticker.set(sym)
        self._refresh_sidebar()
        
        if self._chart_canvas:
            self._chart_canvas.get_tk_widget().destroy()
            self._chart_canvas = None
        for w in self.chart_container.winfo_children(): w.destroy()
        ctk.CTkLabel(self.chart_container, text="차트 불러오는 중…", font=ctk.CTkFont("Malgun Gothic", 12), text_color=TEXT_SEC).pack(expand=True)
                     
        threading.Thread(target=self._fetch_detail, args=(sym,), daemon=True).start()
        threading.Thread(target=self._fetch_news,   args=(sym,), daemon=True).start()

    def _change_period(self, period: str):
        self.period_var.set(period)
        for p, btn in self.period_btns.items():
            btn.configure(fg_color=ACCENT if p == period else MUTED)
        sym = self.selected_ticker.get()
        threading.Thread(target=self._fetch_detail, args=(sym,), daemon=True).start()

    def _add_ticker(self, event):
        query = self.add_entry.get().strip()
        if not query: return
            
        self.add_entry.delete(0, "end")
        self.add_entry.configure(placeholder_text="검색 중...")

        def validate_and_add():
            try:
                # 1. 영문 소문자/한글 등 직접 티커가 아닌 것 같은 경우 야후 검색 API 호출
                # (또는 검색어로 들어온 것을 먼저 티커로 취급해보고 실패하면 검색하는 방식)
                test_hist = yf.Ticker(query.upper()).history(period="1d")
                if not test_hist.empty:
                    sym = query.upper()
                    name = yf.Ticker(sym).info.get('shortName', sym)
                else:
                    # 스마트 검색 실행
                    sym, name = search_yahoo_ticker(query)
                    if not sym: raise ValueError("검색 결과 없음")
                    
                    # 검색한 심볼 검증
                    if yf.Ticker(sym).history(period="1d").empty:
                        raise ValueError("유효하지 않은 검색 심볼")

                if sym in self.watchlist:
                    self.after(0, lambda: self.add_entry.configure(placeholder_text="이미 추가된 종목입니다"))
                    time.sleep(1)
                    self.after(0, lambda: self.add_entry.configure(placeholder_text="종목명 또는 티커 검색..."))
                    return

                self.ticker_names[sym] = name
                self.watchlist.append(sym)
                self._fetch_all_tickers()
                self.after(0, self._refresh_sidebar)
                self.after(0, lambda: self.add_entry.configure(placeholder_text="종목명 또는 티커 검색..."))
            except Exception:
                self.after(0, lambda: messagebox.showerror("종목 검색 실패", f"'{query}'에 대한 종목을 찾을 수 없습니다.\n정확한 기업명이나 티커를 입력해주세요."))
                self.after(0, lambda: self.add_entry.configure(placeholder_text="종목명 또는 티커 검색..."))

        threading.Thread(target=validate_and_add, daemon=True).start()

    def _remove_ticker(self, sym: str):
        if sym in self.watchlist:
            self.watchlist.remove(sym)
            if self.selected_ticker.get() == sym and self.watchlist:
                self._select_ticker(self.watchlist[0])
            else:
                self._refresh_sidebar()


if __name__ == "__main__":
    app = StockDashboard()
    app.mainloop()