"""V6 雙欄 UI：左側四分頁，右上世界版圖，右下排名／即時事件 LOG。"""

from __future__ import annotations

import random
import math
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
from scipy import ndimage
from PIL import ImageTk

import map_config as cfg
from map_generator import MapSettings, SAVES_DIR, generate_world, load_world, save_world
from map_renderer import render_environment
from terrain_rules import terrain_name
from climate_rules import biome_name
from war_engine import WarEngine
from country_generator import BARRACKS, PORT


# ==============================================================================
# 【UI 全域參數】常用介面尺寸、比例與字體集中在這裡調整
# ==============================================================================
WINDOW_SIZE = "1900x1000"

# 左／右主框初始比例。0.46 代表左側 46%、右側 54%；啟動後仍可拖曳中間分隔線。
UI_LEFT_PANEL_RATIO = 0.46

# 右側「世界版圖」高度比例。0.70 代表地圖約占右側 70%；可拖曳水平分隔線。
UI_MAP_HEIGHT_RATIO = 0.70

# 主介面字體（整體加大）。
UI_FONT_FAMILY = "Microsoft JhengHei UI"
UI_FONT_SIZE = 12
UI_FONT_SIZE_HEADER = 12
UI_FONT_SIZE_TAB = 12
UI_FONT_SIZE_DETAIL = 12
UI_FONT_SIZE_LOG = 12
UI_FONT_SIZE_RANK = 12
UI_RANK_FONT_FAMILY = "Consolas"
UI_RANK_LINE_SPACING = 2
UI_COUNTRY_NAME_FONT_SIZE = 14
UI_TREE_ROW_HEIGHT = 30

# 地圖顯示。FIT_WORLD_MARGIN < 1 會保留一圈邊界；最小值避免 Canvas 尚未完成排版時縮成小點。
MAP_FIT_MARGIN = 0.96
MAP_MIN_ZOOM = 0.10
MAP_MAX_ZOOM = 15.0
MAP_WHEEL_ZOOM_IN = 1.25
MAP_WHEEL_ZOOM_OUT = 0.80

# 主框初始最小像素，避免拖曳時整區消失。
UI_LEFT_MIN_PIXELS = 520
UI_RIGHT_MIN_PIXELS = 620
UI_MAP_MIN_PIXELS = 360
UI_BOTTOM_MIN_PIXELS = 180

# ===== 自動存檔／國家定位／綜合國力排名 =====
AUTO_SAVE_ENABLED = True
AUTO_SAVE_EVERY_YEARS = 100
AUTO_LOAD_LAST_SAVE = True

COUNTRY_FOCUS_MARGIN = 0.82
COUNTRY_FOCUS_MIN_ZOOM = 0.35
COUNTRY_FOCUS_MAX_ZOOM = 8.0

# 綜合國力 = 士兵×1 + 艦隊×50 + 領土×2
RANK_SOLDIER_WEIGHT = 1.0
RANK_FLEET_WEIGHT = 1.0
RANK_LAND_WEIGHT = 3.0

# ==============================================================================
# 【模擬時鐘 V2】模擬速度與 UI / 地圖刷新完全分離
# ==============================================================================
SECONDS_PER_YEAR = float(cfg.SECONDS_PER_YEAR)  # 從 map_config.py 讀取每年實際節奏。
SIM_CLOCK_POLL_MS = 10           # 主時鐘檢查頻率
SIM_MAX_BATCH_YEARS = 1          # 每批只推進 1 年；完成後立即回報並更新介面
SIM_MAX_BACKLOG_YEARS = 250      # 最大追趕積欠，避免視窗卡頓後暴衝
UI_REFRESH_EVERY_YEARS = 1       # 國家數值與表格每年刷新
MAP_REFRESH_SECONDS = 0.50       # 地圖每 0.5 秒重繪
AUTO_SAVE_EVERY_YEARS = 100      # 高速模式避免每年寫硬碟


STYLE_LABELS = {
    "RANDOM": "隨機風格", "BALANCED": "均衡世界", "SUPERCONTINENT": "超級大陸",
    "ARCHIPELAGO": "群島世界", "FRACTURED": "破碎大陸", "INLAND_SEAS": "內海世界",
    "TWIN_CONTINENTS": "雙大陸世界", "EARTH_MAP": "地球地圖",
}


def _capital_landmass_mask(territory, continent, country_id, capital):
    """Keep only this country's territory on the geographic landmass of its capital."""
    owned = territory == int(country_id)
    cx, cy = map(int, capital)
    height, width = territory.shape
    if not (0 <= cy < height and 0 <= cx < width):
        return owned
    landmass_id = int(continent[cy, cx])
    if landmass_id > 0:
        return owned & (continent == landmass_id)
    labels, _ = ndimage.label(
        owned, structure=np.array([[0,1,0],[1,1,1],[0,1,0]], dtype=np.uint8)
    )
    capital_label = int(labels[cy, cx])
    return (labels == capital_label) if capital_label > 0 else owned
STYLE_CODES = {v: k for k, v in STYLE_LABELS.items()}


class MapViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("亂世演算_征佔紀元 V22_3｜全島共用人口加成版")
        self.root.geometry(WINDOW_SIZE)
        self.root.configure(bg="#161616")
        self.world = self.war = self.full_image = self.tk_image = None
        self.zoom = 0.55
        self.center_x = cfg.MAP_WIDTH / 2
        self.center_y = cfg.MAP_HEIGHT / 2
        self.drag_start = None
        self.view_box = None
        self.war_busy = False
        self.running = bool(cfg.AUTO_RUN_ON_START)
        self.show_geographic_names = False
        self.selected_country_id = 1
        self.country_sort_column = "land"
        self.country_sort_reverse = True
        self.alliance_sort_column = "land"
        self.alliance_sort_reverse = True
        self._initial_sashes_applied = False
        self._map_has_been_fitted = False
        self._last_auto_save_year = None
        self._sim_last_clock = time.perf_counter()
        self._sim_year_credit = 0.0
        self._sim_years_completed_window = 0
        self._sim_speed_window_start = time.perf_counter()
        self._actual_years_per_second = 0.0
        self._last_ui_refresh = 0.0
        self._last_map_refresh = 0.0
        self._last_visual_revision = -1
        self._setup_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self.load_or_generate)
        self.root.after(SIM_CLOCK_POLL_MS, self._sim_clock_tick)

    def _setup_style(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("Dark.TFrame", background="#1d1d1d")
        style.configure("TButton", font=(UI_FONT_FAMILY, UI_FONT_SIZE))
        style.configure("TEntry", font=(UI_FONT_FAMILY, UI_FONT_SIZE))
        style.configure("TCombobox", font=(UI_FONT_FAMILY, UI_FONT_SIZE))
        style.configure("Panel.TLabelframe", background="#202020", foreground="#00bfff", bordercolor="#777")
        style.configure("Panel.TLabelframe.Label", background="#1d1d1d", foreground="#00bfff", font=(UI_FONT_FAMILY, UI_FONT_SIZE_HEADER, "bold"))
        style.configure("Dark.TLabel", background="#1d1d1d", foreground="#eeeeee", font=(UI_FONT_FAMILY, UI_FONT_SIZE))
        style.configure("Accent.TLabel", background="#1d1d1d", foreground="#ffd84a", font=(UI_FONT_FAMILY, UI_FONT_SIZE_HEADER, "bold"))
        style.configure("Dark.Treeview", background="#222", fieldbackground="#222", foreground="#eee", rowheight=UI_TREE_ROW_HEIGHT, font=(UI_FONT_FAMILY, UI_FONT_SIZE))
        style.configure("Dark.Treeview.Heading", background="#333", foreground="#fff", font=(UI_FONT_FAMILY, UI_FONT_SIZE_HEADER, "bold"))
        style.map("Dark.Treeview", background=[("selected", "#075b83")])
        style.configure("TNotebook.Tab", font=(UI_FONT_FAMILY, UI_FONT_SIZE_TAB, "bold"), padding=(9, 6))

    def _build_ui(self):
        top = ttk.Frame(self.root, style="Dark.TFrame", padding=6)
        top.pack(fill="x")
        self.year_var = tk.StringVar(value="世界準備中")
        ttk.Label(top, textvariable=self.year_var, style="Accent.TLabel").pack(side="left", padx=8)
        self.seed_var = tk.StringVar(value=str(cfg.MAP_SEED))
        self.style_var = tk.StringVar(value=STYLE_LABELS.get(cfg.WORLD_STYLE, "均衡世界"))
        ttk.Label(top, text="Seed", style="Dark.TLabel").pack(side="left", padx=(20, 3))
        ttk.Entry(top, textvariable=self.seed_var, width=12).pack(side="left")
        style_picker = ttk.Combobox(top, textvariable=self.style_var, values=list(STYLE_CODES), state="readonly", width=11)
        style_picker.pack(side="left", padx=5)
        style_picker.bind("<<ComboboxSelected>>", self._terrain_style_changed)
        self.width_var = tk.StringVar(value=str(cfg.MAP_WIDTH))
        self.height_var = tk.StringVar(value=str(cfg.MAP_HEIGHT))
        ttk.Label(top, text="寬×高", style="Dark.TLabel").pack(side="left", padx=(5, 2))
        ttk.Spinbox(top, from_=128, to=8000, increment=100, textvariable=self.width_var, width=6).pack(side="left")
        ttk.Label(top, text="×", style="Dark.TLabel").pack(side="left")
        ttk.Spinbox(top, from_=128, to=8000, increment=100, textvariable=self.height_var, width=6).pack(side="left", padx=(0, 4))
        ttk.Button(top, text="新世界", command=self.generate_clicked).pack(side="left", padx=3)
        ttk.Button(top, text="隨機Seed", command=lambda: self.seed_var.set(str(random.SystemRandom().randint(1, 2**31-1)))).pack(side="left")
        self.run_button = ttk.Button(top, text="暫停", command=self.toggle_run)
        self.run_button.pack(side="left", padx=(20, 3))
        ttk.Button(top, text="推進1年", command=lambda: self.advance_war(1)).pack(side="left", padx=3)
        ttk.Button(top, text="推進10年", command=lambda: self.advance_war(10)).pack(side="left")
        ttk.Button(top, text="儲存戰局", command=self.save_war).pack(side="right", padx=3)
        ttk.Button(top, text="讀取戰局", command=self.load_war).pack(side="right")

        # 主體固定左右各半；左側沿用上代四分頁，右側上地圖、下雙分頁。
        body = ttk.Panedwindow(self.root, orient="horizontal")
        self.body_panes = body
        body.pack(fill="both", expand=True, padx=5, pady=3)
        left = ttk.Frame(body, style="Dark.TFrame")
        right = ttk.Frame(body, style="Dark.TFrame")
        body.add(left, weight=1)
        body.add(right, weight=1)

        # ===== 左半：四個標籤 =====
        self.left_notebook = ttk.Notebook(left)
        self.left_notebook.pack(fill="both", expand=True)

        self.tab_country_overview = ttk.Frame(self.left_notebook, style="Dark.TFrame")
        self.tab_alliance_overview = ttk.Frame(self.left_notebook, style="Dark.TFrame")
        self.tab_country_query = ttk.Frame(self.left_notebook, style="Dark.TFrame")
        self.tab_alliance_query = ttk.Frame(self.left_notebook, style="Dark.TFrame")
        self.left_notebook.add(self.tab_country_overview, text=" 🌐 國家總攬 ")
        self.left_notebook.add(self.tab_alliance_overview, text=" 🤝 聯盟總攬 ")
        self.left_notebook.add(self.tab_country_query, text=" 🔎 國家查詢 ")
        self.left_notebook.add(self.tab_alliance_query, text=" 📜 歷史事件 ")

        # 國家總攬
        country_box = ttk.LabelFrame(self.tab_country_overview, text="🌐 世界各國", style="Panel.TLabelframe", padding=4)
        country_box.pack(fill="both", expand=True, padx=5, pady=5)
        self.ranking = ttk.Treeview(country_box, columns=("land", "pop", "army", "fleet", "alliance", "record"), show="tree headings", style="Dark.Treeview")
        for col, title in (("#0","國家"),("land","領土"),("pop","人口"),("army","士兵"),("fleet","艦隊"),("alliance","聯盟"),("record","戰績")):
            self.ranking.heading(col, text=title, command=lambda c=col: self._sort_country_overview(c))
        self.ranking.column("#0", width=160); self.ranking.column("land", width=65, anchor="e")
        self.ranking.column("pop", width=90, anchor="e"); self.ranking.column("army", width=80, anchor="e")
        self.ranking.column("fleet", width=55, anchor="e"); self.ranking.column("alliance", width=75, anchor="center"); self.ranking.column("record", width=85, anchor="center")
        self.ranking.pack(fill="both", expand=True)
        self.ranking.bind("<<TreeviewSelect>>", self._ranking_changed)

        # 聯盟總攬
        alliance_box = ttk.LabelFrame(self.tab_alliance_overview, text="🤝 世界聯盟", style="Panel.TLabelframe", padding=4)
        alliance_box.pack(fill="both", expand=True, padx=5, pady=5)
        self.alliance_tree = ttk.Treeview(alliance_box, columns=("members", "land", "pop", "army", "record"), show="tree headings", style="Dark.Treeview")
        for col, title in (("#0","聯盟"),("members","成員"),("land","領土"),("pop","人口"),("army","士兵"),("record","戰績")):
            self.alliance_tree.heading(col, text=title, command=lambda c=col: self._sort_alliance_overview(c))
        self.alliance_tree.column("#0", width=150); self.alliance_tree.column("members", width=55, anchor="center")
        self.alliance_tree.column("land", width=70, anchor="e"); self.alliance_tree.column("pop", width=95, anchor="e")
        self.alliance_tree.column("army", width=85, anchor="e"); self.alliance_tree.column("record", width=90, anchor="center")
        self.alliance_tree.pack(fill="both", expand=True)
        self.alliance_tree.bind("<<TreeviewSelect>>", self._alliance_tree_changed)

        # 國家查詢：V8風格資訊儀表板
        query_head = ttk.Frame(self.tab_country_query, style="Dark.TFrame", padding=5)
        query_head.pack(fill="x")
        ttk.Label(query_head, text="選擇國家：", style="Dark.TLabel").pack(side="left")
        self.country_var = tk.StringVar()
        self.country_combo = ttk.Combobox(query_head, textvariable=self.country_var, state="readonly")
        self.country_combo.pack(side="left", fill="x", expand=True, padx=5)
        self.country_combo.bind("<<ComboboxSelected>>", self._country_combo_changed)
        self.map_link = tk.Label(
            query_head, text="🗺 前往地圖／定位國家", bg="#1d1d1d", fg="#38bdf8",
            activeforeground="#7dd3fc", cursor="hand2",
            font=(UI_FONT_FAMILY, UI_FONT_SIZE, "underline"), padx=8,
        )
        self.map_link.pack(side="right")
        self.map_link.bind("<Button-1>", self._country_query_go_to_map)

        dashboard = ttk.Frame(self.tab_country_query, style="Dark.TFrame")
        dashboard.pack(fill="both", expand=True, padx=5, pady=(0,5))
        # uniform 會忽略兩張 Treeview 的請求寬度差異，確保左右完全等寬。
        dashboard.columnconfigure(0, weight=1, uniform="country_summary")
        dashboard.columnconfigure(1, weight=1, uniform="country_summary")
        dashboard.rowconfigure(3, weight=1)

        basic_box = ttk.LabelFrame(dashboard, text="🏛 基本狀態", style="Panel.TLabelframe", padding=5)
        basic_box.grid(row=0, column=0, sticky="nsew", padx=(0,4), pady=(0,4))
        basic_upper = ttk.Frame(basic_box, style="Dark.TFrame")
        basic_upper.pack(fill="x")
        self.country_basic = self._field_table(
            basic_upper, ("項目", "內容"), height=9, widths=(160, 220)
        )
        economy_box = ttk.LabelFrame(dashboard, text="👥 人口・建築・資源", style="Panel.TLabelframe", padding=5)
        economy_box.grid(row=0, column=1, sticky="nsew", padx=(4,0), pady=(0,4))
        self.country_economy = self._field_table(
            economy_box, ("項目", "內容"), height=9, widths=(130, 250)
        )

        # 領地清單置於上方兩張資訊表下方，橫跨整個左側欄；維持參考圖中的矮版資訊列。
        colony_box = ttk.LabelFrame(
            dashboard, text="⚓ 領地資料（含本島；點擊地名定位）",
            style="Panel.TLabelframe", padding=4,
        )
        colony_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0,4))
        self.colony_links = tk.Text(
            colony_box, height=4, bg="#222", fg="#eee", relief="flat",
            font=(UI_FONT_FAMILY, UI_FONT_SIZE), wrap="word", cursor="arrow"
        )
        colony_scroll = ttk.Scrollbar(colony_box, orient="vertical", command=self.colony_links.yview)
        self.colony_links.configure(yscrollcommand=colony_scroll.set)
        colony_scroll.pack(side="right", fill="y")
        self.colony_links.pack(side="left", fill="both", expand=True)

        war_box = ttk.LabelFrame(dashboard, text="⚔ 當前戰爭", style="Panel.TLabelframe", padding=5)
        war_box.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=4)
        self.country_war = self._field_table(
            war_box, ("戰爭", "立場", "交戰對象", "抵達", "狀態"), height=2,
            widths=(80, 90, 300, 80, 100),
        )

        dip_box = ttk.LabelFrame(dashboard, text="🏆 外交・戰績", style="Panel.TLabelframe", padding=5)
        dip_box.grid(row=3, column=0, sticky="nsew", padx=(0,4), pady=4)
        self.country_diplomacy = self._field_table(dip_box, ("項目", "內容"), height=7)

        own_box = ttk.LabelFrame(dashboard, text="📜 近期國家／戰爭事件", style="Panel.TLabelframe", padding=4)
        own_box.grid(row=3, column=1, sticky="nsew", padx=(4,0), pady=4)
        self.country_log = self._log_widget(own_box)

        self.detail = None

        history_box = ttk.LabelFrame(self.tab_alliance_query, text="📜 世界政權重大歷史", style="Panel.TLabelframe", padding=5)
        history_box.pack(fill="both", expand=True, padx=5, pady=5)
        self.history_log = self._log_widget(history_box)

        # ===== 右半：上地圖，下方兩標籤 =====
        # 使用垂直 Panedwindow：使用者可直接拖曳分隔線調整地圖／排名區高度。
        self.right_panes = ttk.Panedwindow(right, orient="vertical")
        self.right_panes.pack(fill="both", expand=True)
        map_group = ttk.LabelFrame(self.right_panes, text="🗺 世界版圖情況", style="Panel.TLabelframe", padding=3)
        self.right_bottom_host = ttk.Frame(self.right_panes, style="Dark.TFrame")
        self.right_panes.add(map_group, weight=3)
        self.right_panes.add(self.right_bottom_host, weight=1)
        map_head = ttk.Frame(map_group, style="Dark.TFrame")
        map_head.pack(fill="x")
        self.layer_var = tk.StringVar(value="國家與領土")
        self.layer_var.trace_add("write", self._layer_changed)
        layers = ("國家與領土", "純領土歸屬", "生態環境", "基礎地形", "農業價值", "木材價值", "礦產價值", "淡水供應", "建城價值", "防禦價值", "移動成本")
        ttk.Combobox(map_head, textvariable=self.layer_var, values=layers, state="readonly", width=12).pack(side="left", padx=3)
        ttk.Button(map_head, text="全圖", command=self.fit_world).pack(side="left", padx=3)
        self.place_name_button = ttk.Button(map_head, text="隱藏地名", command=self.toggle_place_names)
        self.place_name_button.pack(side="left", padx=(0,3))
        ttk.Label(map_head, text=f"國名字級 {UI_COUNTRY_NAME_FONT_SIZE}", style="Dark.TLabel").pack(side="right", padx=6)
        self.canvas = tk.Canvas(map_group, bg="#0b1725", highlightbackground="#777", highlightthickness=1)
        self.canvas.pack(fill="both", expand=True)

        self.right_bottom_notebook = ttk.Notebook(self.right_bottom_host)
        self.right_bottom_notebook.pack(fill="both", expand=True, padx=3, pady=(3,0))
        self.tab_world_rank = ttk.Frame(self.right_bottom_notebook, style="Dark.TFrame")
        self.tab_world_log = ttk.Frame(self.right_bottom_notebook, style="Dark.TFrame")
        self.right_bottom_notebook.add(self.tab_world_rank, text=" 🏆 世界即時排名 ")
        self.right_bottom_notebook.add(self.tab_world_log, text=" ⚔ 即時事件LOG ")

        world_rank_box = ttk.LabelFrame(self.tab_world_rank, text="🏆 世界即時排名", style="Panel.TLabelframe", padding=4)
        world_rank_box.pack(fill="both", expand=True, padx=4, pady=4)
        # V8_7 風格：世界排名改用 rank_text，而不是表格。
        # 國家名稱＝藍色超連結；聯盟名稱＝黃色超連結，點擊直接跳詳細查詢。
        self.rank_text = tk.Text(
            world_rank_box, bg="#171717", fg="#dcdcdc", insertbackground="white",
            wrap="none", relief="flat", font=(UI_RANK_FONT_FAMILY, UI_FONT_SIZE_RANK),
            spacing1=UI_RANK_LINE_SPACING, spacing3=UI_RANK_LINE_SPACING,
        )
        rank_scroll_y = ttk.Scrollbar(world_rank_box, orient="vertical", command=self.rank_text.yview)
        rank_scroll_x = ttk.Scrollbar(world_rank_box, orient="horizontal", command=self.rank_text.xview)
        self.rank_text.configure(yscrollcommand=rank_scroll_y.set, xscrollcommand=rank_scroll_x.set)
        rank_scroll_y.pack(side="right", fill="y")
        rank_scroll_x.pack(side="bottom", fill="x")
        self.rank_text.pack(fill="both", expand=True)
        self.setup_entity_link_widget(self.rank_text)

        event_box = ttk.LabelFrame(self.tab_world_log, text="⚔ 世界即時戰鬥與事件", style="Panel.TLabelframe", padding=4)
        event_box.pack(fill="both", expand=True, padx=4, pady=4)
        self.battle_log = self._log_widget(event_box)
        for _w in (self.country_log, self.history_log, self.battle_log):
            self.setup_entity_link_widget(_w)

        self.status = ttk.Label(self.root, text="滾輪縮放｜左鍵拖曳｜點擊領土查詢", style="Dark.TLabel", padding=5)
        self.status.pack(fill="x")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.after_idle(self._apply_initial_sashes)

    def _log_widget(self, parent):
        text = tk.Text(parent, bg="#171717", fg="#e9e9e9", insertbackground="white", wrap="word", relief="flat", font=(UI_FONT_FAMILY, UI_FONT_SIZE_LOG))
        scroll = ttk.Scrollbar(parent, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y"); text.pack(fill="both", expand=True)
        return text

    def _field_table(self, parent, headings, height=7, widths=None):
        columns = tuple(f"field_{i}" for i in range(len(headings)))
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height, style="Dark.Treeview")
        widths = widths or tuple(125 if i == 0 else 330 for i in range(len(headings)))
        for index, (column, heading) in enumerate(zip(columns, headings)):
            tree.heading(column, text=heading)
            tree.column(column, width=widths[index], anchor="w", stretch=True)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    @staticmethod
    def _set_field_rows(tree, rows):
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=row)

    def _country_query_go_to_map(self, _event=None):
        self.focus_country_on_map(self.selected_country_id)
        self.canvas.focus_set()
        self.status.configure(text=f"已從國家查詢定位：{self.war.country(self.selected_country_id)['name']}")
        return "break"

    def _refresh_colony_links(self, country):
        """列出本島與海外領地的面積、建立年份、人口和士兵。"""
        widget = self.colony_links
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        for tag in widget.tag_names():
            if tag.startswith("site_"):
                widget.tag_delete(tag)
        sites = list(country.get("overseas_capitals", []))
        if not sites and country.get("overseas_capital"):
            sites = [country["overseas_capital"]]
        cx, cy = map(int, country.get("capital", self.world.countries[int(country["id"]) - 1]["capital"]))
        home_id = int(self.world.continent[cy, cx]) if 0 <= cy < self.world.settings.height and 0 <= cx < self.world.settings.width else 0
        rows = []
        owned = self.world.territory == int(country["id"])
        for continent_id in sorted(int(v) for v in np.unique(self.world.continent[owned]) if int(v) > 0):
            continent_mask = (self.world.continent == continent_id) & owned
            area = int(continent_mask.sum())
            population = int(self.war.local_population[continent_mask].sum())
            soldiers = int(self.war.local_soldiers[continent_mask].sum())
            site = next((s for s in sites if int(s.get("continent_id", -1)) == continent_id), None)
            if continent_id == home_id:
                anchor = (cx, cy)
                kind = str(country.get("capital_type", "本島首都"))
                founded = int(site.get("founded_year", self.war.year)) if site else 0
            elif site:
                anchor = tuple(map(int, site.get("anchor", (-1, -1))))
                kind, founded = str(site.get("type", "海外征戰首都")), int(site.get("founded_year", self.war.year))
            else:
                continue
            ax, ay = anchor
            if not (0 <= ay < self.world.settings.height and 0 <= ax < self.world.settings.width):
                continue
            name = self.war.geographic_name_at(ay, ax)
            rows.append((kind, name, area, founded, population, soldiers, ax, ay))
        if not rows:
            widget.insert("end", "尚無有效領地")
        else:
            for index, (kind, name, area, founded, population, soldiers, ax, ay) in enumerate(rows):
                tag = f"site_{index}"
                if index:
                    widget.insert("end", "\n")
                founded_text = "開局" if kind in ("本島", "本島首都") else f"第 {founded} 年建立"
                widget.insert("end", f"{kind}｜{name}", tag)
                widget.insert("end", f"｜{area:,} 格｜{founded_text}｜人口 {population:,}｜駐軍 {soldiers:,}")
                widget.tag_config(tag, foreground="#38bdf8", underline=True)
                widget.tag_bind(tag, "<Enter>", lambda _e, w=widget: w.configure(cursor="hand2"))
                widget.tag_bind(tag, "<Leave>", lambda _e, w=widget: w.configure(cursor="arrow"))
                if kind not in ("本島", "本島首都", "後撤基地"):
                    widget.tag_bind(tag, "<Button-1>", lambda _e, x=ax, y=ay, n=name: self.focus_colony_on_map(x, y, n))
        voyage = country.get("colonization_voyage")
        if voyage:
            ax, ay = map(int, voyage["anchor"])
            destination = self.war.geographic_name_at(ay, ax)
            distance_left = max(0.0, float(voyage["route_distance_km"]) - float(voyage["travelled_km"]))
            speed = float(voyage.get("speed_km_per_year", cfg.COLONY_SHIP_SPEED_KM_PER_YEAR))
            eta = int(np.ceil(distance_left / max(0.1, speed)))
            if sites:
                widget.insert("end", "\n")
            widget.insert("end", f"⛵ 航行中：{destination}｜剩餘 {distance_left:,.0f} 公里，約 {eta} 年")
        reinforcement = country.get("reinforcement_voyage")
        if reinforcement:
            anchor = tuple(map(int, reinforcement.get("anchor", (0, 0))))
            destination = self.war.geographic_name_at(anchor[1], anchor[0])
            if sites or voyage:
                widget.insert("end", "\n")
            widget.insert("end", f"⚓ 海外增援：前往{destination}｜{int(reinforcement.get('soldiers', 0)):,}人｜約 {int(reinforcement.get('years_left', 0))} 年抵達")
        widget.configure(state="disabled")

    def focus_colony_on_map(self, x, y, name):
        self.center_x, self.center_y = float(x), float(y)
        self.zoom = max(self.zoom, 3.0)
        self.redraw()
        self.status.configure(text=f"已定位海外首都／據點：{name}｜座標({x},{y})")
        return "break"

    def load_or_generate(self):
        try: self.set_world(load_world())
        except Exception: self.generate_clicked()

    def generate_clicked(self):
        if self.war_busy: return
        try:
            settings = MapSettings(
                int(self.width_var.get()), int(self.height_var.get()), int(self.seed_var.get()),
                STYLE_CODES.get(self.style_var.get(), "BALANCED"),
            ).validated()
            self.width_var.set(str(settings.width)); self.height_var.set(str(settings.height))
        except ValueError:
            messagebox.showerror("參數錯誤", "Seed、地圖寬度與高度必須是整數。"); return
        self.war_busy = True; self.status.configure(text="正在生成拓荒世界…")
        threading.Thread(target=self._generate_worker, args=(settings,), daemon=True).start()

    def _terrain_style_changed(self, _event=None):
        if STYLE_CODES.get(self.style_var.get()) == "EARTH_MAP":
            for variable in (self.width_var, self.height_var):
                try:
                    value = int(variable.get())
                except ValueError:
                    value = 1200
                variable.set(str(max(1200, min(2000, value))))

    def _generate_worker(self, settings):
        try:
            world = generate_world(settings)
            save_world(world)
            self.root.after(0, self.set_world, world)
        except Exception as exc: self.root.after(0, messagebox.showerror, "生成失敗", str(exc))
        finally: self.root.after(0, setattr, self, "war_busy", False)

    def set_world(self, world):
        self.world = world
        self.war = WarEngine(world, SAVES_DIR / "war_state")
        if AUTO_LOAD_LAST_SAVE:
            try:
                self.war = WarEngine.load(self.world, SAVES_DIR / "war_state")
            except Exception:
                pass
        self.full_image = render_environment(world, self.layer_var.get())
        self._last_visual_revision = int(getattr(self.war, "visual_revision", 0))
        self.seed_var.set(str(world.settings.seed))
        self.width_var.set(str(world.settings.width)); self.height_var.set(str(world.settings.height))
        self.style_var.set(STYLE_LABELS.get(world.world_style, "均衡世界"))
        self.selected_country_id = 1
        self.refresh_panels(); self._map_has_been_fitted = False; self.root.after_idle(self.fit_world)

    def toggle_run(self):
        self.running = not self.running
        self._sim_last_clock = time.perf_counter()
        if not self.running:
            self._sim_year_credit = 0.0
        self.run_button.configure(text="暫停" if self.running else "繼續")

    def _sim_clock_tick(self):
        """真實時間驅動：累積應推進年份，與 UI / 地圖刷新頻率解耦。"""
        now = time.perf_counter()
        elapsed = max(0.0, now - self._sim_last_clock)
        self._sim_last_clock = now

        if self.running and self.war:
            self._sim_year_credit += elapsed / max(0.0001, float(SECONDS_PER_YEAR))
            self._sim_year_credit = min(self._sim_year_credit, float(SIM_MAX_BACKLOG_YEARS))

            # 累積滿一個模擬年便派送，避免長批次令介面久候無回報。
            batch_years = max(1, int(SIM_MAX_BATCH_YEARS))
            if not self.war_busy and self._sim_year_credit >= batch_years:
                years = min(int(self._sim_year_credit), batch_years)
                self._sim_year_credit -= years
                self.advance_war(years)

        # 每約 1 秒更新一次實際速度數值。
        speed_elapsed = now - self._sim_speed_window_start
        if speed_elapsed >= 1.0:
            self._actual_years_per_second = self._sim_years_completed_window / speed_elapsed
            self._sim_years_completed_window = 0
            self._sim_speed_window_start = now
            if self.war:
                try:
                    s = self.war.summary()
                    self.year_var.set(
                        f"🌍 世界第 {s['year']} 年｜存活 {s['alive']} 國｜"
                        f"設定 {1.0/SECONDS_PER_YEAR:.1f} 年/秒｜實際 {self._actual_years_per_second:.1f} 年/秒"
                    )
                except Exception:
                    pass

        self.root.after(SIM_CLOCK_POLL_MS, self._sim_clock_tick)

    def advance_war(self, years):
        if not self.war or self.war_busy: return
        self.war_busy = True
        threading.Thread(target=self._advance_worker, args=(years,), daemon=True).start()

    def _advance_worker(self, years):
        try:
            summary = self.war.step(years)
            self.root.after(0, self._finish_advance, summary, int(years))
        except Exception as exc:
            self.root.after(0, messagebox.showerror, "推進失敗", str(exc))
            self.root.after(0, setattr, self, "war_busy", False)

    def _finish_advance(self, summary, years_completed):
        """模擬完成後只按各自頻率刷新 UI / 地圖，不再每年重畫整張世界。"""
        now = time.perf_counter()
        self._sim_years_completed_window += int(years_completed)

        # 每批只推進一年；完成後立即刷新查詢欄位與排名。
        self.refresh_panels()
        self._last_ui_refresh = now

        revision = int(getattr(self.war, "visual_revision", 0))
        if now - self._last_map_refresh >= MAP_REFRESH_SECONDS and revision != self._last_visual_revision:
            self.full_image = render_environment(self.world, self.layer_var.get())
            self.redraw()
            self._last_map_refresh = now
            self._last_visual_revision = revision

        self._maybe_auto_save()
        self.war_busy = False

    def _alliance_display_name(self, aid):
        if int(aid or 0) <= 0:
            return "無"
        if not self.war:
            return f"第 {aid} 聯盟"
        return getattr(self.war, "alliance_names", {}).get(int(aid), f"【=第{aid}聯盟=】")

    def refresh_panels(self):
        if not self.war: return
        summary = self.war.summary()
        self.year_var.set(f"🌍 世界第 {summary['year']} 年｜存活 {summary['alive']} 國｜行軍 {summary['campaigns']} 支｜殖民船 {summary.get('colonizing_voyages',0)} 艘｜戰役 {summary['battles']} 場")
        names = [c["name"] for c in self.war.countries]
        self.country_combo.configure(values=names)
        cid = min(max(1, self.selected_country_id), len(names)); self.selected_country_id = cid
        self.country_var.set(names[cid - 1])

        overview_rows = self._sorted_countries()
        world_ranked = sorted(self.war.countries, key=lambda x: (bool(x.get("alive", True)), self._country_power_score(x)), reverse=True)
        for item in self.ranking.get_children(): self.ranking.delete(item)
        for c in overview_rows:
            self.ranking.insert("", "end", iid=str(c["id"]), text=c["name"], values=(c["territory_cells"], f"{c['population']:,}", f"{c['soldiers']:,}", c['fleet'], self._alliance_display_name(c["alliance"]), f"{c['wars_won']}勝/{c['wars_lost']}敗"))
        self._refresh_rank_text(world_ranked, summary)

        c = self.war.country(cid)
        rank_pos = 1 + next((i for i, x in enumerate(world_ranked) if int(x["id"]) == cid), 0)
        power = self._country_power_score(c)
        alliance_name = self._alliance_display_name(c.get("alliance", 0))
        active = [x for x in self.war.campaigns if x.status == "marching" and (x.attacker == cid or x.defender == cid)]
        frontier_empty, frontier_blocked = self.war.expansion_status(cid)
        basic_rows = (
            ("國家狀態", f"{'◉ 存活' if c['alive'] else '✖ 滅亡'}｜{c['name']}"),
            ("目前排名", f"第 {rank_pos} 名／存活 {summary['alive']} 國"),
            ("綜合戰力", f"{power:,}"),
            ("世界年份", (f"已滅亡｜滅亡於第 {c.get('extinction_year', summary['year'])} 年"
                       if not c['alive'] else f"第 {summary['year']} 年")),
            ("現任國王", (f"第 {c.get('king_number',1)} 任｜{c.get('king_name','未記錄')}"
                       if c['alive'] else f"末代第 {c.get('king_number',1)} 任｜{c.get('king_name','未記錄')}")),
            ("領土規模", f"{c['territory_cells']:,} 格"),
            ("本島無主土地", f"可拓荒 {frontier_empty:,}／不可通行 {frontier_blocked:,} 格"),
            ("戰略狀態", "休養生息" if self.war.year < int(c.get("recovery_until_year", 0)) else ("交戰中" if active else "和平")),
            # ("終極戰爭目標", "統一世界" if c.get("war_goal", "UNIFY_WORLD") == "UNIFY_WORLD" else c.get("war_goal", "統一世界")),
            ("已用出海遠征", f"{self.war._overseas_expeditions_used(c):,}／{cfg.OVERSEAS_EXPEDITION_LIMIT}（含失敗）"),
            ("海外首都／出海名額", f"{self.war._overseas_site_count(c):,} 處／{self.war._overseas_expansion_capacity(c):,} 格"),
            ("本島出海資格", ("危局：僅准緊急後撤" if self.war._homeland_is_critical(c) and not self.war._homeland_is_unified(c)
                              else "已達標（>80%、唯一政權）" if self.war._homeland_is_unified(c)
                              else "未達標：一般出海禁止")),
            # ("殖民地數", f"{len(c.get('colonies', [])):,}／{cfg.COLONY_MAX_PER_COUNTRY}"),
        )
        economy_rows = (
            ("人口", f"{c['population']:,} 人｜人口成長加成 +{float(c.get('food_capacity',0))/100000:.0%}"),
            ("士兵", f"{c['soldiers']:,} 人｜徵兵比例加成 +{float(c.get('food_capacity',0))/100000:.0%}"),
            ("艦隊", f"{c['fleet']:,}"),
            ("殖民船航行", (f"前往{self.war.geographic_name_at(*reversed(c['colonization_voyage']['anchor']))}｜{max(0.0, float(c['colonization_voyage']['route_distance_km'])-float(c['colonization_voyage']['travelled_km'])):,.0f}公里" if c.get("colonization_voyage") else "無")),
            ("城市／兵營", f"{c['cities']}／{c['barracks']}"),
            ("拓荒等級／港口", f"{c.get('frontier_level', 0)} 級／{c['ports']}"),
            ("糧食／承載", f"{c['food']:,.0f}／{c.get('food_capacity',0):,} 人"),
            # ("年度產糧／消耗", f"{c.get('last_food_production',0):,.1f}／{c.get('last_food_consumption',0):,.1f}"),
            # ("糧食淨額／承載", f"{c.get('last_food_balance',0):+,.1f}／{c.get('food_capacity',0):,} 人"),
            ("木材／礦產", f"{c['timber']:,.0f}／{c['minerals']:,.0f}"),
            ("戰爭疲乏／士氣", f"{float(c.get('war_exhaustion', 0.0)):.0%}／{float(c.get('morale', 1.0)):.0%}"),
        )
        war_rows = []
        for camp in active[:12]:
            role = "進攻" if camp.attacker == cid else "防守"
            other = camp.defender if camp.attacker == cid else camp.attacker
            other_name = self.war.country(other)["name"]
            war_rows.append((f"W{camp.id}", role, other_name, f"{camp.years_left} 年", "行軍中"))
        diplomacy_rows = (
            ("普通聯盟", alliance_name),
            ("歷史參戰", f"{c['wars_won'] + c['wars_lost']} 場"),
            ("戰績", f"勝 {c['wars_won']}／敗 {c['wars_lost']}"),
            ("勝率", f"{(100*c['wars_won']/max(1,c['wars_won']+c['wars_lost'])):.1f}%"),
            # ("目前行軍", f"{sum(1 for x in self.war.campaigns if x.attacker == cid and x.status == 'marching')} 支"),
        )
        self._set_field_rows(self.country_basic, basic_rows)
        self._refresh_colony_links(c)
        self._set_field_rows(self.country_economy, economy_rows)
        self._set_field_rows(self.country_war, war_rows or [("—", "和平", "無", "—", "無戰事")])
        self._set_field_rows(self.country_diplomacy, diplomacy_rows)
        self._set_text(self.country_log, "\n".join(self.war.country_events.get(cid, [])[-120:]) or "尚無國家事件。")
        self._set_text(self.battle_log, "\n".join(self.war.events[-180:]) or "目前尚無世界事件。")

        groups = self._alliance_groups()
        current_aid = getattr(self, "selected_alliance_id", c["alliance"])
        if current_aid not in groups and groups: current_aid = next(iter(groups))
        self.selected_alliance_id = current_aid

        for item in self.alliance_tree.get_children(): self.alliance_tree.delete(item)
        alliance_rows = []
        for aid, members in groups.items():
            land=sum(x['territory_cells'] for x in members); pop=sum(x['population'] for x in members); army=sum(x['soldiers'] for x in members)
            won=sum(x['wars_won'] for x in members); lost=sum(x['wars_lost'] for x in members)
            alliance_rows.append({"aid": aid, "members": len(members), "land": land, "pop": pop, "army": army, "won": won, "lost": lost})
        alliance_rows = self._sorted_alliances(alliance_rows)
        for row in alliance_rows:
            aid=row["aid"]
            self.alliance_tree.insert("", "end", iid=f"a{aid}", text=self._alliance_display_name(aid), values=(row["members"], f"{row['land']:,}", f"{row['pop']:,}", f"{row['army']:,}", f"{row['won']}勝/{row['lost']}敗"))
        self._set_text(
            self.history_log,
            "\n".join(self.war.history_events[-500:]) or "尚未發生國家分裂、獨立、滅亡或統一事件。",
            see_end=True,
        )

    def _country_sort_value(self, country, column):
        if column == "#0": return str(country.get("name", ""))
        if column == "land": return int(country.get("territory_cells", 0))
        if column == "pop": return int(country.get("population", 0))
        if column == "army": return int(country.get("soldiers", 0))
        if column == "fleet": return int(country.get("fleet", 0))
        if column == "alliance": return int(country.get("alliance", 0))
        if column == "record": return (int(country.get("wars_won", 0)), -int(country.get("wars_lost", 0)))
        return 0

    def _sorted_countries(self):
        if not self.war: return []
        return sorted(self.war.countries, key=lambda c: self._country_sort_value(c, self.country_sort_column), reverse=self.country_sort_reverse)

    def _sort_country_overview(self, column):
        if self.country_sort_column == column:
            self.country_sort_reverse = not self.country_sort_reverse
        else:
            self.country_sort_column = column
            self.country_sort_reverse = False if column == "#0" else True
        self.refresh_panels()

    def _alliance_sort_value(self, row, column):
        if column == "#0": return int(row["aid"])
        if column == "members": return int(row["members"])
        if column in ("land", "pop", "army"): return int(row[column])
        if column == "record": return (int(row["won"]), -int(row["lost"]))
        return 0

    def _sorted_alliances(self, rows):
        return sorted(rows, key=lambda r: self._alliance_sort_value(r, self.alliance_sort_column), reverse=self.alliance_sort_reverse)

    def _sort_alliance_overview(self, column):
        if self.alliance_sort_column == column:
            self.alliance_sort_reverse = not self.alliance_sort_reverse
        else:
            self.alliance_sort_column = column
            self.alliance_sort_reverse = False if column == "#0" else True
        self.refresh_panels()

    def _alliance_groups(self):
        groups = {}
        if not self.war: return groups
        for c in self.war.countries:
            aid = int(c.get("alliance", 0))
            if aid > 0:
                groups.setdefault(aid, []).append(c)
        return dict(sorted(groups.items()))

    def _refresh_alliance_detail(self):
        groups = self._alliance_groups()
        aid = getattr(self, "selected_alliance_id", 0)
        members = groups.get(aid, [])
        if not members:
            self._set_text(self.alliance_detail, "尚無聯盟資料。")
            self._set_text(self.alliance_log, "尚無聯盟事件。")
            return
        alive=sum(1 for x in members if x['alive']); land=sum(x['territory_cells'] for x in members)
        pop=sum(x['population'] for x in members); army=sum(x['soldiers'] for x in members); fleet=sum(x['fleet'] for x in members)
        won=sum(x['wars_won'] for x in members); lost=sum(x['wars_lost'] for x in members)
        member_names="、".join(x['name'] for x in members)
        text=(f"聯盟　　 {self._alliance_display_name(aid)}\n成員　　 {len(members)} 國（存活 {alive} 國）\n"
              f"總領土　 {land:,} 格\n總人口　 {pop:,}\n總士兵　 {army:,}\n總艦隊　 {fleet:,}\n"
              f"總戰績　 勝 {won}｜敗 {lost}\n\n成員：\n{member_names}")
        self._set_text(self.alliance_detail, text)
        events=[]
        for x in members: events.extend(self.war.country_events.get(int(x['id']), [])[-40:])
        self._set_text(self.alliance_log, "\n".join(events[-120:]) or "尚無聯盟成員相關事件。")

    def _alliance_tree_changed(self, _event=None):
        selected=self.alliance_tree.selection()
        if selected:
            self.selected_alliance_id=int(selected[0][1:])

    def _alliance_combo_changed(self, _event=None):
        selected = self.alliance_var.get()
        for aid in self._alliance_groups():
            if self._alliance_display_name(aid) == selected:
                self.selected_alliance_id = aid
                self._refresh_alliance_detail()
                return

    def _country_power_score(self, country):
        return int(round(
            int(country.get("soldiers", 0)) * RANK_SOLDIER_WEIGHT
            + int(country.get("fleet", 0)) * RANK_FLEET_WEIGHT
            + int(country.get("territory_cells", 0)) * RANK_LAND_WEIGHT
        ))

    def _refresh_rank_text(self, world_ranked, summary):
        total_pop = sum(int(c.get("population", 0)) for c in self.war.countries if c.get("alive", True))
        total_land = sum(int(c.get("territory_cells", 0)) for c in self.war.countries if c.get("alive", True))
        lines = [
            f"亂世演算｜世界第 {summary['year']} 年｜全世界人口 = {total_pop:,}｜已控制領土 = {total_land:,} 格",
            f"排名公式：士兵×{RANK_SOLDIER_WEIGHT:g} + 艦隊×{RANK_FLEET_WEIGHT:g} + 領土×{RANK_LAND_WEIGHT:g}",
        ]
        for pos, c in enumerate(world_ranked, 1):
            status = "" if c.get("alive", True) else " [滅亡]"
            alliance = self._alliance_display_name(int(c.get("alliance", 0)))
            record = f"{int(c.get('wars_won', 0))}勝/{int(c.get('wars_lost', 0))}敗"
            power = self._country_power_score(c)
            lines.append(
                f"{pos:02d}. {power:>9,}｜{c['name']}｜士兵 {int(c.get('soldiers',0)):,}"
                f"｜艦隊 {int(c.get('fleet',0)):,}｜領土 {int(c.get('territory_cells',0)):,}"
                f"｜{alliance}｜{record}{status}"
            )
        rank_value = "\n".join(lines)
        self._set_text(self.rank_text, rank_value, see_end=False)
        try:
            SAVES_DIR.mkdir(parents=True, exist_ok=True)
            (SAVES_DIR / "Live_Ranking.txt").write_text(rank_value, encoding="utf-8")
        except Exception:
            pass

    def setup_entity_link_widget(self, widget):
        """國家藍色、聯盟黃色、地理名稱綠色，點擊可直接定位。"""
        widget.tag_config("country_link", foreground="#4FC1FF", underline=True)
        widget.tag_config("alliance_link", foreground="#FFE066", underline=True)
        widget.tag_config("place_link", foreground="#4ADE80", underline=True)
        widget.bind("<ButtonRelease-1>", self._on_entity_text_click, add="+")
        widget.bind("<Double-Button-1>", self._on_entity_text_click, add="+")
        widget.bind("<Motion>", self._on_entity_text_motion, add="+")
        widget.bind("<Leave>", lambda e, w=widget: w.configure(cursor="xterm"), add="+")

    def _entity_aliases(self, include_places=False):
        aliases = []
        if not self.war:
            return aliases
        for c in self.war.countries:
            name = str(c.get("name", "")).strip()
            if name: aliases.append((name, "country", int(c["id"])))
        for aid in self._alliance_groups():
            for alias in (f"第{aid}盟", f"第 {aid} 聯盟"):
                aliases.append((alias, "alliance", int(aid)))
        if include_places:
            for region in self.war.geographic_regions:
                name = str(region.get("name", "")).strip()
                if name:
                    x, y = map(int, region["center"])
                    aliases.append((name, "place", (x, y, name)))
        # 長名稱優先，避免短名稱搶先命中。
        return sorted(aliases, key=lambda x: len(x[0]), reverse=True)

    def _entity_at_pointer(self, widget, event):
        try:
            index = widget.index(f"@{event.x},{event.y}")
            line_no, col_no = map(int, index.split("."))
            line_text = widget.get(f"{line_no}.0", f"{line_no}.end")
        except Exception:
            return None
        include_places = widget is getattr(self, "history_log", None)
        for alias, entity_type, entity_id in self._entity_aliases(include_places=include_places):
            if alias not in line_text:
                continue
            start = 0
            while True:
                pos = line_text.find(alias, start)
                if pos < 0: break
                end = pos + len(alias)
                if pos <= col_no < end:
                    return entity_type, entity_id
                start = pos + max(1, len(alias))
        return None

    def _on_entity_text_click(self, event):
        entity = self._entity_at_pointer(event.widget, event)
        if not entity: return
        kind, entity_id = entity
        if kind == "country":
            self.selected_country_id = entity_id
            self.refresh_panels()
            self.left_notebook.select(self.tab_country_query)
            self.root.after_idle(lambda cid=entity_id: self.focus_country_on_map(cid))
        elif kind == "alliance":
            self.selected_alliance_id = entity_id
            self.left_notebook.select(self.tab_alliance_overview)
        else:
            x, y, name = entity_id
            self.focus_colony_on_map(x, y, name)
        return "break"

    def _on_entity_text_motion(self, event):
        try: event.widget.configure(cursor="hand2" if self._entity_at_pointer(event.widget, event) else "xterm")
        except Exception: pass

    def _apply_entity_link_tags(self, widget):
        try:
            widget.tag_remove("country_link", "1.0", tk.END)
            widget.tag_remove("alliance_link", "1.0", tk.END)
            widget.tag_remove("place_link", "1.0", tk.END)
            content = widget.get("1.0", tk.END)
            include_places = widget is getattr(self, "history_log", None)
            for alias, kind, _entity_id in self._entity_aliases(include_places=include_places):
                if alias not in content:
                    continue
                start = "1.0"
                tag = "alliance_link" if kind == "alliance" else ("place_link" if kind == "place" else "country_link")
                while True:
                    pos = widget.search(alias, start, stopindex=tk.END)
                    if not pos: break
                    end = f"{pos}+{len(alias)}c"
                    widget.tag_add(tag, pos, end)
                    start = end
        except tk.TclError:
            pass

    def _set_text(self, widget, value, see_end=True):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", value)
        self._apply_entity_link_tags(widget)
        if see_end: widget.see("end")
        else: widget.see("1.0")
        widget.configure(state="disabled")

    def _country_combo_changed(self, _event=None):
        selected = next((c for c in self.war.countries if c["name"] == self.country_var.get()), None)
        if not selected: return
        self.selected_country_id = int(selected["id"])
        self.refresh_panels()
        self.root.after_idle(lambda: self.focus_country_on_map(self.selected_country_id))

    def _ranking_changed(self, _event=None):
        selected = self.ranking.selection()
        if selected: self.selected_country_id = int(selected[0]); self.refresh_panels(); self.left_notebook.select(self.tab_country_query)

    def focus_country_on_map(self, country_id):
        """以首都所在主島取景；海外殖民地由個別地名連結定位。"""
        if not self.world or not self.war:
            return
        try:
            country = self.war.country(int(country_id))
            owned = self.world.territory == int(country_id)
            capital = country.get("capital", self.world.countries[int(country_id)-1].get(
                "capital", (0, 0)
            ))
            focus_mask = _capital_landmass_mask(
                self.world.territory, self.world.continent, country_id, capital
            )
            ys, xs = np.where(focus_mask)
            if len(xs) == 0:
                cx, cy = country.get("capital", self.world.countries[int(country_id)-1].get(
                    "capital", (self.world.settings.width // 2, self.world.settings.height // 2)
                ))
                self.center_x, self.center_y = float(cx), float(cy)
                self.redraw()
                self.status.configure(text=f"{country['name']}已滅亡；定位至最後首都({cx},{cy})。")
                return
            # 世界地圖左右相接：排除最大空白經度，避免跨接縫國家被定位到地圖中央。
            width = self.world.settings.width
            unique_x = np.unique(xs)
            if len(unique_x) > 1:
                gaps = np.diff(np.r_[unique_x, unique_x[0] + width])
                cut = int(np.argmax(gaps))
                start_x = int(unique_x[(cut + 1) % len(unique_x)])
                unwrapped_x = np.where(xs < start_x, xs + width, xs)
                min_x, max_x = int(unwrapped_x.min()), int(unwrapped_x.max())
                self.center_x = ((min_x + max_x) / 2.0) % width
            else:
                min_x = max_x = int(unique_x[0])
                self.center_x = float(min_x)
            min_y, max_y = int(ys.min()), int(ys.max())
            self.center_y = (min_y + max_y) / 2.0
            self.root.update_idletasks()
            cw, ch = max(80, self.canvas.winfo_width()), max(80, self.canvas.winfo_height())
            span_x, span_y = max(8, max_x-min_x+1), max(8, max_y-min_y+1)
            fit_zoom = min(cw/span_x, ch/span_y) * COUNTRY_FOCUS_MARGIN
            self.zoom = max(COUNTRY_FOCUS_MIN_ZOOM, min(COUNTRY_FOCUS_MAX_ZOOM, fit_zoom))
            self.redraw()
            self.status.configure(text=f"已定位首都主島：{country['name']}｜主島領土 {len(xs):,} 格")
        except Exception as exc:
            self.status.configure(text=f"國家定位失敗：{exc}")

    def _maybe_auto_save(self, force=False):
        """按遊戲年份自動儲存世界與戰局。"""
        if not AUTO_SAVE_ENABLED or not self.war or not self.world:
            return
        try:
            year = int(self.war.summary().get("year", 0))
            due = force or self._last_auto_save_year is None or (
                year - int(self._last_auto_save_year) >= max(1, int(AUTO_SAVE_EVERY_YEARS))
            )
            if not due:
                return
            SAVES_DIR.mkdir(parents=True, exist_ok=True)
            save_world(self.world)
            self.war.save(SAVES_DIR / "war_state")
            self._last_auto_save_year = year
            self.status.configure(text=f"已自動存檔｜世界第 {year} 年｜saves/war_state")
        except Exception as exc:
            self.status.configure(text=f"自動存檔失敗：{exc}")

    def _on_close(self):
        try:
            self._maybe_auto_save(force=True)
        finally:
            self.root.destroy()

    def save_war(self):
        try: self.war.save(SAVES_DIR / "war_state"); messagebox.showinfo("完成", "戰局已存入saves資料夾。")
        except Exception as exc: messagebox.showerror("儲存失敗", str(exc))

    def load_war(self):
        try:
            self.war = WarEngine.load(self.world, SAVES_DIR / "war_state")
            self.full_image = render_environment(self.world, self.layer_var.get()); self.redraw(); self.refresh_panels()
        except Exception as exc: messagebox.showerror("讀取失敗", str(exc))

    def fit_world(self):
        """依目前 Canvas 真實尺寸把全世界放到最大；避免啟動時 1x1 尺寸造成地圖縮成小點。"""
        if not self.world: return
        self.root.update_idletasks()
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 80 or ch < 80:
            self.root.after(80, self.fit_world)
            return
        fit_zoom = min(cw / self.world.settings.width, ch / self.world.settings.height) * MAP_FIT_MARGIN
        self.zoom = max(MAP_MIN_ZOOM, min(MAP_MAX_ZOOM, fit_zoom))
        self.center_x = self.world.settings.width / 2
        self.center_y = self.world.settings.height / 2
        self._map_has_been_fitted = True
        self.redraw()

    def toggle_place_names(self):
        """切換地理區域名稱；國名維持顯示，避免玩家失去國家辨識。"""
        self.show_geographic_names = not self.show_geographic_names
        self.place_name_button.configure(text="隱藏地名" if self.show_geographic_names else "顯示地名")
        self.redraw()

    def _on_canvas_configure(self, _event=None):
        # 第一次取得有效尺寸時自動全圖；之後改框大小只重畫，不強迫改掉使用者的縮放。
        if self.world and not self._map_has_been_fitted:
            self.root.after_idle(self.fit_world)
        else:
            self.redraw()

    def _apply_initial_sashes(self):
        """套用上方全域比例；之後使用者可直接拖曳兩條分隔線。"""
        if self._initial_sashes_applied:
            return
        self.root.update_idletasks()
        try:
            total_w = self.body_panes.winfo_width()
            total_h = self.right_panes.winfo_height()

            # 啟動初期 PanedWindow 常暫時只有 1px。若此時設定 sash，
            # 會把左側與地圖上半部直接壓成 0，畫面只剩右下排名。
            # 必須等兩個 PanedWindow 都真正完成 geometry 後才套比例。
            if (total_w < UI_LEFT_MIN_PIXELS + UI_RIGHT_MIN_PIXELS + 50 or
                    total_h < UI_MAP_MIN_PIXELS + UI_BOTTOM_MIN_PIXELS + 50):
                self.root.after(100, self._apply_initial_sashes)
                return

            x_low = UI_LEFT_MIN_PIXELS
            x_high = total_w - UI_RIGHT_MIN_PIXELS
            x = min(x_high, max(x_low, round(total_w * UI_LEFT_PANEL_RATIO)))
            self.body_panes.sashpos(0, x)

            y_low = UI_MAP_MIN_PIXELS
            y_high = total_h - UI_BOTTOM_MIN_PIXELS
            y = min(y_high, max(y_low, round(total_h * UI_MAP_HEIGHT_RATIO)))
            self.right_panes.sashpos(0, y)

            self._initial_sashes_applied = True

            # sash 套好後 Canvas 才有可靠尺寸，再做一次全圖適配。
            if self.world:
                self._map_has_been_fitted = False
                self.root.after(120, self.fit_world)
        except (tk.TclError, AttributeError):
            self.root.after(100, self._apply_initial_sashes)

    def _layer_changed(self, *_args):
        if not self.world:
            return
        self.full_image = render_environment(self.world, self.layer_var.get())
        self.redraw()

    def redraw(self):
        if not self.world or self.full_image is None: return
        cw, ch = max(2, self.canvas.winfo_width()), max(2, self.canvas.winfo_height())
        half_w, half_h = cw / (2*self.zoom), ch / (2*self.zoom)
        left, top = max(0, int(self.center_x-half_w)), max(0, int(self.center_y-half_h))
        right, bottom = min(self.world.settings.width, int(self.center_x+half_w)+1), min(self.world.settings.height, int(self.center_y+half_h)+1)
        if right <= left or bottom <= top: return
        crop = self.full_image.crop((left, top, right, bottom))
        tw, th = max(1, int((right-left)*self.zoom)), max(1, int((bottom-top)*self.zoom))
        crop = crop.resize((tw, th), resample=0 if self.zoom >= 2 else 2)
        self.tk_image = ImageTk.PhotoImage(crop); self.canvas.delete("all")
        self.canvas.create_image(cw//2, ch//2, image=self.tk_image, anchor="center")
        self.view_box = (left, top, right, bottom, tw, th)
        self._draw_overlays(left, top, cw, ch, tw, th)

    def _draw_overlays(self, left, top, cw, ch, tw, th):
        ox, oy = (cw-tw)/2, (ch-th)/2
        if self.war:
            # 大型地理區域以低對比文字標示；縮得太遠時限制數量避免遮住國名。
            visible_regions = [
                region for region in self.war.geographic_regions
                if region["size"] >= cfg.GEOGRAPHIC_LABEL_MIN_CELLS
            ] if self.show_geographic_names else []
            visible_regions.sort(key=lambda region: region["size"], reverse=True)
            for region in visible_regions[:cfg.GEOGRAPHIC_MAX_VISIBLE_LABELS]:
                rx, ry = region["center"]
                sx, sy = ox + (rx-left)*self.zoom, oy + (ry-top)*self.zoom
                if -100 <= sx <= cw+100 and -20 <= sy <= ch+20:
                    self.canvas.create_text(
                        sx, sy, text=region["name"],
                        font=(UI_FONT_FAMILY, 9, "normal"), fill="#d1d8df"
                    )
            for campaign in self.war.campaigns:
                if campaign.status != "marching": continue
                y0,x0=campaign.origin; y1,x1=campaign.objective
                color="#59e6f2" if campaign.mode=="naval" else "#ff5c57"
                self.canvas.create_line(ox+(x0-left)*self.zoom, oy+(y0-top)*self.zoom, ox+(x1-left)*self.zoom, oy+(y1-top)*self.zoom, fill=color, width=2, arrow="last", dash=(5,3))
            for country in self.war.countries:
                voyage = country.get("colonization_voyage")
                if not voyage:
                    continue
                route = voyage.get("route", [])
                world_width = self.world.settings.width
                for first, second in zip(route, route[1:]):
                    x0, y0 = map(float, first); x1, y1 = map(float, second)
                    if abs(x1 - x0) > world_width / 2:
                        continue  # 地圖左右相接處不畫跨整張圖的長線。
                    sx0, sy0 = ox+(x0-left)*self.zoom, oy+(y0-top)*self.zoom
                    sx1, sy1 = ox+(x1-left)*self.zoom, oy+(y1-top)*self.zoom
                    if (-12 <= sx0 <= cw+12 and -12 <= sx1 <= cw+12
                            and -12 <= sy0 <= ch+12 and -12 <= sy1 <= ch+12):
                        self.canvas.create_line(sx0, sy0, sx1, sy1, fill="#f4c95d",
                                                width=max(2, min(4, self.zoom*1.4)), dash=(6, 4))
                position = voyage.get("position") or route[0]
                px, py = map(float, position)
                sx, sy = ox+(px-left)*self.zoom, oy+(py-top)*self.zoom
                if not (-28 <= sx <= cw+28 and -30 <= sy <= ch+30):
                    continue
                # A large, map-native sailboat marker remains legible at ordinary zoom levels.
                self.canvas.create_oval(sx-13, sy-13, sx+13, sy+13,
                                        fill="#ffe082", outline="#172b4d", width=2)
                self.canvas.create_line(sx, sy-8, sx, sy+4, fill="#172b4d", width=2)
                self.canvas.create_polygon(sx+1, sy-7, sx+8, sy+1, sx+1, sy+1,
                                           fill="#f05b45", outline="#172b4d")
                self.canvas.create_polygon(sx-1, sy-5, sx-7, sy+1, sx-1, sy+1,
                                           fill="#ffffff", outline="#172b4d")
                self.canvas.create_polygon(sx-8, sy+5, sx+9, sy+5, sx+5, sy+9,
                                           sx-5, sy+9, fill="#172b4d", outline="#172b4d")
                label = str(country["name"])
                label_x, label_y = sx+17, sy-17
                label_width = max(54, len(label)*12+16)
                if label_x+label_width > cw-3:
                    label_x = sx-label_width-17
                self.canvas.create_rectangle(label_x, label_y, label_x+label_width,
                                             label_y+25, fill="#10253b",
                                             outline="#f4c95d", width=1)
                self.canvas.create_text(label_x+label_width/2, label_y+12,
                                        text=label, fill="white",
                                        font=(UI_FONT_FAMILY, 10, "bold"))
        
        # # 殖民地只標示為殖民據點；海外首都僅由海外征服地建立。
        # if self.war:
        #     for country in self.war.countries:
        #         if not country.get("alive", True):
        #             continue
        #         for colony in country.get("colonies", []):
        #             ax, ay = map(int, colony.get("anchor", (0, 0)))
        #             if not (0 <= ay < self.world.settings.height and 0 <= ax < self.world.settings.width):
        #                 continue
        #             if int(self.world.territory[ay, ax]) != int(country["id"]):
        #                 continue
        #             sx, sy = ox + (ax-left)*self.zoom, oy + (ay-top)*self.zoom
        #             if not (-100 <= sx <= cw+100 and -35 <= sy <= ch+35):
        #                 continue
        #             radius = max(4, min(7, int(4*self.zoom)))
        #             self.canvas.create_oval(sx-radius, sy-radius, sx+radius, sy+radius,
        #                                     fill="#65d6a6", outline="#073b32", width=2)
        #             label = f"{country['name']}・殖民地"
        #             self.canvas.create_text(
        #                 sx + radius + 4, sy - 10, text=label, font=(UI_FONT_FAMILY, 9, "bold"),
        #                 fill="#d9ffec", anchor="w",
        #             )

        # 建築圖示以原生幾何圖形繪製，並置於地名、航線等圖層上方。
        icon_size = max(12, min(30, int(cfg.MAP_BUILDING_ICON_SIZE * max(0.75, self.zoom))))
        half = icon_size / 2
        if self.war:
            crop_right = min(self.world.settings.width, left + int(math.ceil(tw / self.zoom)))
            crop_bottom = min(self.world.settings.height, top + int(math.ceil(th / self.zoom)))
            buildings = self.world.settlement[top:crop_bottom, left:crop_right]
            # for code, color in ((PORT, "#25c9e8"), (BARRACKS, "#ef765e")):
            #     yy, xx = np.where(buildings == code)
            #     if len(xx) > 2500:
            #         pick = np.linspace(0, len(xx) - 1, 2500, dtype=int)
            #         yy, xx = yy[pick], xx[pick]
            #     for by, bx in zip(yy, xx):
            #         sx, sy = ox + int(bx)*self.zoom, oy + int(by)*self.zoom
            #         if code == PORT:
            #             self.canvas.create_oval(sx-half, sy-half, sx+half, sy+half,
            #                                     fill="#083b66", outline="#b8f5ff", width=2)
            #             self.canvas.create_line(sx-half*0.55, sy+half*0.15, sx+half*0.55, sy+half*0.15,
            #                                     fill=color, width=2)
            #             self.canvas.create_line(sx-half*0.4, sy+half*0.45, sx+half*0.4, sy+half*0.45,
            #                                     fill="#b8f5ff", width=1)
            #             self.canvas.create_polygon(sx, sy-half*0.65, sx+half*0.42, sy+half*0.1,
            #                                        sx-half*0.42, sy+half*0.1,
            #                                        fill=color, outline="white", width=1)
            #         else:
            #             self.canvas.create_rectangle(sx-half, sy-half, sx+half, sy+half,
            #                                          fill="#762f32", outline="#ffe0c2", width=2)
            #             self.canvas.create_line(sx-half*0.4, sy+half*0.4, sx+half*0.4, sy-half*0.4,
            #                                     fill="#fff0d6", width=3)
            #             self.canvas.create_line(sx-half*0.4, sy-half*0.4, sx+half*0.4, sy+half*0.4,
            #                                     fill="#fff0d6", width=3)

            # 殖民或征服取得的每一處海外領地，都須有海外首都標記。
            for country in self.war.countries:
                if not country.get("alive", True):
                    continue
                sites = list(country.get("overseas_capitals", []))
                if not sites and country.get("overseas_capital"):
                    sites = [country["overseas_capital"]]
                for overseas in sites:
                    ax, ay = map(int, overseas.get("anchor", (0, 0)))
                    if not (0 <= ay < self.world.settings.height and 0 <= ax < self.world.settings.width):
                        continue
                    if int(self.world.territory[ay, ax]) != int(country["id"]):
                        continue
                    sx, sy = ox + (ax-left)*self.zoom, oy + (ay-top)*self.zoom
                    if -half <= sx <= cw+half and -half <= sy <= ch+half:
                        self.canvas.create_oval(sx-half, sy-half, sx+half, sy+half,
                                                fill="#10555d", outline="#b7f9ff", width=3)
                        self.canvas.create_text(sx, sy, text="★", fill="#ffffff",
                                                font=(UI_FONT_FAMILY, max(10, icon_size-4), "bold"))
                        kind = overseas.get("type", "海外")
                        # self.canvas.create_text(sx+half+4, sy-half, text=f"{country['name']}・{kind}首都",
                        #                         fill="white", anchor="w", font=(UI_FONT_FAMILY, 9, "bold"))

                        self.canvas.create_text(sx+half+4, sy-half, text=f"{country['name']}",
                                                                        fill="white", anchor="w", font=(UI_FONT_FAMILY, 12, "bold"))

        # 本土首都圖示最後繪製，確保港口、兵營、地名與航線都不能遮住它。
        for country in self.world.countries:
            cid = int(country["id"])
            cx, cy = map(int, country["capital"])
            if not (0 <= cy < self.world.settings.height and 0 <= cx < self.world.settings.width):
                continue
            if int(self.world.territory[cy, cx]) != cid:
                continue
            sx, sy = ox + (cx-left)*self.zoom, oy + (cy-top)*self.zoom
            if -half <= sx <= cw+half and -half <= sy <= ch+half:
                self.canvas.create_oval(sx-half, sy-half, sx+half, sy+half,
                                        fill="#533c0b", outline="#fff1a8", width=3)
                self.canvas.create_text(sx, sy, text="★", fill="#ffd54f",
                                        font=(UI_FONT_FAMILY, max(11, icon_size-3), "bold"))

        font = (UI_FONT_FAMILY, UI_COUNTRY_NAME_FONT_SIZE, "bold" if cfg.COUNTRY_NAME_FONT_BOLD else "normal")
        for country in self.world.countries:
            cid=int(country["id"]); cx,cy=country["capital"]
            if self.world.territory[cy,cx] != cid: continue
            sx,sy=ox+(cx-left)*self.zoom,oy+(cy-top)*self.zoom
            if -100 <= sx <= cw+100 and -30 <= sy <= ch+30:
                # Tkinter Canvas.create_text 不支援 stroke_width/stroke_fill。
                # 以偏移文字模擬黑色外框，再於中央畫白色國名。
                outline = max(0, int(cfg.COUNTRY_NAME_OUTLINE_WIDTH))
                if outline:
                    for dx in range(-outline, outline + 1):
                        for dy in range(-outline, outline + 1):
                            if dx == 0 and dy == 0:
                                continue
                            if max(abs(dx), abs(dy)) != outline:
                                continue
                            self.canvas.create_text(
                                sx + dx, sy - 12 + dy, text=country["name"],
                                font=font, fill="#111"
                            )
                self.canvas.create_text(
                    sx, sy - 12, text=country["name"], font=font, fill="white"
                )

    def on_wheel(self, event): self.zoom=max(MAP_MIN_ZOOM,min(MAP_MAX_ZOOM,self.zoom*(MAP_WHEEL_ZOOM_IN if event.delta>0 else MAP_WHEEL_ZOOM_OUT))); self.redraw()
    def on_press(self,event): self.drag_start=(event.x,event.y,self.center_x,self.center_y)
    def on_drag(self,event):
        if not self.drag_start:return
        sx,sy,cx,cy=self.drag_start; self.center_x=cx-(event.x-sx)/self.zoom; self.center_y=cy-(event.y-sy)/self.zoom; self.redraw()
    def on_release(self,event):
        if not self.drag_start or not self.view_box:return
        sx,sy,*_=self.drag_start; self.drag_start=None
        if abs(event.x-sx)+abs(event.y-sy)>5:return
        left,top,_r,_b,tw,th=self.view_box; cw,ch=self.canvas.winfo_width(),self.canvas.winfo_height()
        x=int(left+(event.x-(cw-tw)/2)/self.zoom); y=int(top+(event.y-(ch-th)/2)/self.zoom)
        if not(0<=x<self.world.settings.width and 0<=y<self.world.settings.height):return
        cid=int(self.world.territory[y,x])
        if cid>0: self.selected_country_id=cid; self.refresh_panels(); self.left_notebook.select(self.tab_country_query)
        region = self.war.geographic_name_at(y, x)
        self.status.configure(text=f"座標({x},{y})｜{region}｜{terrain_name(self.world.terrain[y,x])}｜{biome_name(self.world.biome[y,x])}｜{'無主地' if cid==0 else self.war.country(cid)['name']}")


def main():
    root=tk.Tk(); MapViewer(root); root.mainloop()


if __name__=="__main__": main()
