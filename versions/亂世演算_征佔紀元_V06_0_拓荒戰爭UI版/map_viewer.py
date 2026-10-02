"""V6舊版風格三欄UI：左國情、中地圖、右國家與戰鬥LOG。"""

from __future__ import annotations

import random
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import ImageTk

import map_config as cfg
from map_generator import MapSettings, SAVES_DIR, generate_world, load_world, save_world
from map_renderer import render_environment
from terrain_rules import terrain_name
from climate_rules import biome_name
from war_engine import WarEngine


STYLE_LABELS = {
    "RANDOM": "隨機風格", "BALANCED": "均衡世界", "SUPERCONTINENT": "超級大陸",
    "ARCHIPELAGO": "群島世界", "FRACTURED": "破碎大陸", "INLAND_SEAS": "內海世界",
    "TWIN_CONTINENTS": "雙大陸世界",
}
STYLE_CODES = {v: k for k, v in STYLE_LABELS.items()}


class MapViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("亂世演算_征佔紀元 V6｜拓荒戰爭UI版")
        self.root.geometry("1900x1000")
        self.root.configure(bg="#161616")
        self.world = self.war = self.full_image = self.tk_image = None
        self.zoom = 0.55
        self.center_x = cfg.MAP_WIDTH / 2
        self.center_y = cfg.MAP_HEIGHT / 2
        self.drag_start = None
        self.view_box = None
        self.war_busy = False
        self.running = bool(cfg.AUTO_RUN_ON_START)
        self.selected_country_id = 1
        self._setup_style()
        self._build_ui()
        self.root.after(100, self.load_or_generate)
        self.root.after(int(cfg.SECONDS_PER_YEAR * 1000), self._auto_tick)

    def _setup_style(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("Dark.TFrame", background="#1d1d1d")
        style.configure("Panel.TLabelframe", background="#202020", foreground="#00bfff", bordercolor="#777")
        style.configure("Panel.TLabelframe.Label", background="#1d1d1d", foreground="#00bfff", font=("Microsoft JhengHei UI", 11, "bold"))
        style.configure("Dark.TLabel", background="#1d1d1d", foreground="#eeeeee", font=("Microsoft JhengHei UI", 10))
        style.configure("Accent.TLabel", background="#1d1d1d", foreground="#ffd84a", font=("Microsoft JhengHei UI", 11, "bold"))
        style.configure("Dark.Treeview", background="#222", fieldbackground="#222", foreground="#eee", rowheight=25)
        style.configure("Dark.Treeview.Heading", background="#333", foreground="#fff", font=("Microsoft JhengHei UI", 10, "bold"))
        style.map("Dark.Treeview", background=[("selected", "#075b83")])

    def _build_ui(self):
        top = ttk.Frame(self.root, style="Dark.TFrame", padding=6)
        top.pack(fill="x")
        self.year_var = tk.StringVar(value="世界準備中")
        ttk.Label(top, textvariable=self.year_var, style="Accent.TLabel").pack(side="left", padx=8)
        self.seed_var = tk.StringVar(value=str(cfg.MAP_SEED))
        self.style_var = tk.StringVar(value=STYLE_LABELS.get(cfg.WORLD_STYLE, "均衡世界"))
        ttk.Label(top, text="Seed", style="Dark.TLabel").pack(side="left", padx=(20, 3))
        ttk.Entry(top, textvariable=self.seed_var, width=12).pack(side="left")
        ttk.Combobox(top, textvariable=self.style_var, values=list(STYLE_CODES), state="readonly", width=11).pack(side="left", padx=5)
        ttk.Button(top, text="新世界", command=self.generate_clicked).pack(side="left", padx=3)
        ttk.Button(top, text="隨機Seed", command=lambda: self.seed_var.set(str(random.SystemRandom().randint(1, 2**31-1)))).pack(side="left")
        self.run_button = ttk.Button(top, text="暫停", command=self.toggle_run)
        self.run_button.pack(side="left", padx=(20, 3))
        ttk.Button(top, text="推進1年", command=lambda: self.advance_war(1)).pack(side="left", padx=3)
        ttk.Button(top, text="推進10年", command=lambda: self.advance_war(10)).pack(side="left")
        ttk.Button(top, text="儲存戰局", command=self.save_war).pack(side="right", padx=3)
        ttk.Button(top, text="讀取戰局", command=self.load_war).pack(side="right")

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=5, pady=3)
        left = ttk.Frame(panes, width=cfg.LEFT_PANEL_WIDTH, style="Dark.TFrame")
        center = ttk.Frame(panes, style="Dark.TFrame")
        right = ttk.Frame(panes, width=cfg.RIGHT_PANEL_WIDTH, style="Dark.TFrame")
        panes.add(left, weight=0); panes.add(center, weight=1); panes.add(right, weight=0)

        country_box = ttk.LabelFrame(left, text="🏛 國家基本資訊", style="Panel.TLabelframe", padding=5)
        country_box.pack(fill="x", padx=3, pady=3)
        self.country_var = tk.StringVar()
        self.country_combo = ttk.Combobox(country_box, textvariable=self.country_var, state="readonly")
        self.country_combo.pack(fill="x", pady=3)
        self.country_combo.bind("<<ComboboxSelected>>", self._country_combo_changed)
        self.detail = tk.Text(country_box, height=13, bg="#222", fg="#eee", relief="flat", font=("Microsoft JhengHei UI", 11))
        self.detail.pack(fill="x")

        rank_box = ttk.LabelFrame(left, text="🏆 國家一覽", style="Panel.TLabelframe", padding=4)
        rank_box.pack(fill="both", expand=True, padx=3, pady=3)
        self.ranking = ttk.Treeview(rank_box, columns=("land", "pop", "army"), show="tree headings", style="Dark.Treeview")
        self.ranking.heading("#0", text="國家"); self.ranking.heading("land", text="領土")
        self.ranking.heading("pop", text="人口"); self.ranking.heading("army", text="士兵")
        self.ranking.column("#0", width=125); self.ranking.column("land", width=55, anchor="e")
        self.ranking.column("pop", width=75, anchor="e"); self.ranking.column("army", width=70, anchor="e")
        self.ranking.pack(fill="both", expand=True)
        self.ranking.bind("<<TreeviewSelect>>", self._ranking_changed)

        map_head = ttk.Frame(center, style="Dark.TFrame")
        map_head.pack(fill="x")
        self.layer_var = tk.StringVar(value="國家與領土")
        self.layer_var.trace_add("write", self._layer_changed)
        layers = ("國家與領土", "生態環境", "基礎地形", "農業價值", "木材價值", "礦產價值", "淡水供應", "建城價值", "防禦價值", "移動成本")
        ttk.Combobox(map_head, textvariable=self.layer_var, values=layers, state="readonly", width=12).pack(side="left", padx=3)
        ttk.Button(map_head, text="全圖", command=self.fit_world).pack(side="left", padx=3)
        ttk.Label(map_head, text=f"國名字級：map_config.COUNTRY_NAME_FONT_SIZE={cfg.COUNTRY_NAME_FONT_SIZE}", style="Dark.TLabel").pack(side="right", padx=6)
        self.canvas = tk.Canvas(center, bg="#0b1725", highlightbackground="#777", highlightthickness=1)
        self.canvas.pack(fill="both", expand=True)

        own_box = ttk.LabelFrame(right, text="📜 選定國家專屬LOG", style="Panel.TLabelframe", padding=4)
        own_box.pack(fill="both", expand=True, padx=3, pady=3)
        self.country_log = self._log_widget(own_box)
        battle_box = ttk.LabelFrame(right, text="⚔ 即時戰鬥LOG", style="Panel.TLabelframe", padding=4)
        battle_box.pack(fill="both", expand=True, padx=3, pady=3)
        self.battle_log = self._log_widget(battle_box)

        self.status = ttk.Label(self.root, text="滾輪縮放｜左鍵拖曳｜點擊領土查詢", style="Dark.TLabel", padding=5)
        self.status.pack(fill="x")
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def _log_widget(self, parent):
        text = tk.Text(parent, bg="#171717", fg="#e9e9e9", insertbackground="white", wrap="word", relief="flat", font=("Microsoft JhengHei UI", 10))
        scroll = ttk.Scrollbar(parent, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y"); text.pack(fill="both", expand=True)
        return text

    def load_or_generate(self):
        try: self.set_world(load_world())
        except Exception: self.generate_clicked()

    def generate_clicked(self):
        if self.war_busy: return
        try:
            settings = MapSettings(cfg.MAP_WIDTH, cfg.MAP_HEIGHT, int(self.seed_var.get()), STYLE_CODES.get(self.style_var.get(), "BALANCED")).validated()
        except ValueError:
            messagebox.showerror("參數錯誤", "Seed必須是整數。"); return
        self.war_busy = True; self.status.configure(text="正在生成拓荒世界…")
        threading.Thread(target=self._generate_worker, args=(settings,), daemon=True).start()

    def _generate_worker(self, settings):
        try:
            world = generate_world(settings)
            save_world(world)
            self.root.after(0, self.set_world, world)
        except Exception as exc: self.root.after(0, messagebox.showerror, "生成失敗", str(exc))
        finally: self.root.after(0, setattr, self, "war_busy", False)

    def set_world(self, world):
        self.world = world; self.war = WarEngine(world, SAVES_DIR / "war_state")
        self.full_image = render_environment(world, self.layer_var.get())
        self.seed_var.set(str(world.settings.seed)); self.selected_country_id = 1
        self.fit_world(); self.refresh_panels()

    def toggle_run(self):
        self.running = not self.running
        self.run_button.configure(text="暫停" if self.running else "繼續")

    def _auto_tick(self):
        if self.running and self.war and not self.war_busy:
            self.advance_war(1)
        self.root.after(int(cfg.SECONDS_PER_YEAR * 1000), self._auto_tick)

    def advance_war(self, years):
        if not self.war or self.war_busy: return
        self.war_busy = True
        threading.Thread(target=self._advance_worker, args=(years,), daemon=True).start()

    def _advance_worker(self, years):
        try:
            summary = self.war.step(years)
            image = render_environment(self.world, self.layer_var.get())
            self.root.after(0, self._finish_advance, summary, image)
        except Exception as exc:
            self.root.after(0, messagebox.showerror, "推進失敗", str(exc)); self.root.after(0, setattr, self, "war_busy", False)

    def _finish_advance(self, summary, image):
        self.full_image = image; self.redraw(); self.refresh_panels(); self.war_busy = False

    def refresh_panels(self):
        if not self.war: return
        summary = self.war.summary()
        self.year_var.set(f"🌍 世界第 {summary['year']} 年｜存活 {summary['alive']} 國｜行軍 {summary['campaigns']} 支｜戰役 {summary['battles']} 場")
        names = [c["name"] for c in self.war.countries]
        self.country_combo.configure(values=names)
        cid = min(max(1, self.selected_country_id), len(names)); self.selected_country_id = cid
        self.country_var.set(names[cid - 1])
        for item in self.ranking.get_children(): self.ranking.delete(item)
        for c in sorted(self.war.countries, key=lambda x: x["territory_cells"], reverse=True):
            self.ranking.insert("", "end", iid=str(c["id"]), text=c["name"], values=(c["territory_cells"], f"{c['population']:,}", f"{c['soldiers']:,}"))
        c = self.war.country(cid)
        lines = [
            f"狀態　　{'存活' if c['alive'] else '滅亡'}", f"領土　　{c['territory_cells']:,} 格",
            f"人口　　{c['population']:,}", f"士兵　　{c['soldiers']:,}", f"艦隊　　{c['fleet']}",
            f"聯盟　　第 {c['alliance']} 聯盟", f"糧食　　{c['food']:,.0f}", f"木材　　{c['timber']:,.0f}",
            f"礦產　　{c['minerals']:,.0f}", f"城市　　{c['cities']}｜兵營 {c['barracks']}",
            f"拓荒站　{c['outposts']}｜港口 {c['ports']}", f"戰績　　勝 {c['wars_won']}｜敗 {c['wars_lost']}",
        ]
        self._set_text(self.detail, "\n".join(lines))
        self._set_text(self.country_log, "\n".join(self.war.country_events.get(cid, [])[-120:]) or "尚無國家事件。")
        self._set_text(self.battle_log, "\n".join(self.war.events[-150:]) or "目前尚無戰鬥。")

    def _set_text(self, widget, value):
        widget.configure(state="normal"); widget.delete("1.0", "end"); widget.insert("end", value); widget.see("end"); widget.configure(state="disabled")

    def _country_combo_changed(self, _event=None):
        try: self.selected_country_id = [c["name"] for c in self.war.countries].index(self.country_var.get()) + 1
        except ValueError: return
        self.refresh_panels()

    def _ranking_changed(self, _event=None):
        selected = self.ranking.selection()
        if selected: self.selected_country_id = int(selected[0]); self.refresh_panels()

    def save_war(self):
        try: self.war.save(SAVES_DIR / "war_state"); messagebox.showinfo("完成", "戰局已存入saves資料夾。")
        except Exception as exc: messagebox.showerror("儲存失敗", str(exc))

    def load_war(self):
        try:
            self.war = WarEngine.load(self.world, SAVES_DIR / "war_state")
            self.full_image = render_environment(self.world, self.layer_var.get()); self.redraw(); self.refresh_panels()
        except Exception as exc: messagebox.showerror("讀取失敗", str(exc))

    def fit_world(self):
        if not self.world: return
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        self.zoom = min(cw / self.world.settings.width, ch / self.world.settings.height)
        self.center_x = self.world.settings.width / 2; self.center_y = self.world.settings.height / 2; self.redraw()

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
            for campaign in self.war.campaigns:
                if campaign.status != "marching": continue
                y0,x0=campaign.origin; y1,x1=campaign.objective
                color="#59e6f2" if campaign.mode=="naval" else "#ff5c57"
                self.canvas.create_line(ox+(x0-left)*self.zoom, oy+(y0-top)*self.zoom, ox+(x1-left)*self.zoom, oy+(y1-top)*self.zoom, fill=color, width=2, arrow="last", dash=(5,3))
        font = ("Microsoft JhengHei UI", cfg.COUNTRY_NAME_FONT_SIZE, "bold" if cfg.COUNTRY_NAME_FONT_BOLD else "normal")
        for country in self.world.countries:
            cid=int(country["id"]); cx,cy=country["capital"]
            if self.world.territory[cy,cx] != cid: continue
            sx,sy=ox+(cx-left)*self.zoom,oy+(cy-top)*self.zoom
            if -100 <= sx <= cw+100 and -30 <= sy <= ch+30:
                self.canvas.create_text(sx,sy-12,text=country["name"],font=font,fill="white",stroke_width=cfg.COUNTRY_NAME_OUTLINE_WIDTH,stroke_fill="#111")

    def on_wheel(self, event): self.zoom=max(0.05,min(15,self.zoom*(1.25 if event.delta>0 else .8))); self.redraw()
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
        if cid>0: self.selected_country_id=cid; self.refresh_panels()
        self.status.configure(text=f"座標({x},{y})｜{terrain_name(self.world.terrain[y,x])}｜{biome_name(self.world.biome[y,x])}｜{'無主地' if cid==0 else self.war.country(cid)['name']}")


def main():
    root=tk.Tk(); MapViewer(root); root.mainloop()


if __name__=="__main__": main()
