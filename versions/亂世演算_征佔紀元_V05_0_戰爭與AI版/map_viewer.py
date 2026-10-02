"""Tkinter 世界地圖檢視器：縮放、拖曳、點格查詢與重新生成。"""

from __future__ import annotations

import random
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

from PIL import ImageTk

import map_config as cfg
from map_generator import MapSettings, SAVES_DIR, generate_world, load_world, save_world
from map_renderer import render_environment
from terrain_rules import terrain_name
from climate_rules import biome_name, water_name
from war_engine import WarEngine


STYLE_LABELS = {
    "RANDOM": "隨機風格",
    "BALANCED": "均衡世界",
    "SUPERCONTINENT": "超級大陸",
    "ARCHIPELAGO": "群島世界",
    "FRACTURED": "破碎大陸",
    "INLAND_SEAS": "內海世界",
    "TWIN_CONTINENTS": "雙大陸世界",
}
STYLE_CODES = {label: code for code, label in STYLE_LABELS.items()}


class MapViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("亂世演算_征佔紀元 V5｜戰爭與AI版")
        self.root.geometry("1500x920")
        self.world = None
        self.full_image = None
        self.tk_image = None
        self.zoom = 0.65
        self.center_x = cfg.MAP_WIDTH / 2
        self.center_y = cfg.MAP_HEIGHT / 2
        self.drag_start = None
        self.war = None
        self.war_busy = False

        self._build_ui()
        self.root.after(120, self.load_or_generate)

    def _build_ui(self):
        controls = ttk.Frame(self.root, padding=8)
        controls.pack(fill="x")

        self.width_var = tk.StringVar(value=str(cfg.MAP_WIDTH))
        self.height_var = tk.StringVar(value=str(cfg.MAP_HEIGHT))
        self.seed_var = tk.StringVar(value=str(cfg.MAP_SEED))
        self.style_var = tk.StringVar(value=STYLE_LABELS.get(cfg.WORLD_STYLE, "隨機風格"))
        self.layer_var = tk.StringVar(value="國家與領土")

        for label, variable, width in (
            ("寬", self.width_var, 7),
            ("高", self.height_var, 7),
            ("Seed", self.seed_var, 13),
        ):
            ttk.Label(controls, text=label).pack(side="left", padx=(4, 2))
            ttk.Entry(controls, textvariable=variable, width=width).pack(side="left")

        ttk.Label(controls, text="世界風格").pack(side="left", padx=(10, 2))
        ttk.Combobox(
            controls,
            textvariable=self.style_var,
            values=list(STYLE_CODES),
            state="readonly",
            width=12,
        ).pack(side="left")

        ttk.Label(controls, text="顯示圖層").pack(side="left", padx=(10, 2))
        layer_box = ttk.Combobox(
            controls,
            textvariable=self.layer_var,
            values=(
                "國家與領土", "生態環境", "基礎地形", "溫度", "濕度", "降雨",
                "農業價值", "木材價值", "礦產價值", "淡水供應",
                "建城價值", "防禦價值", "移動成本",
            ),
            state="readonly",
            width=11,
        )
        layer_box.pack(side="left")
        layer_box.bind("<<ComboboxSelected>>", self.layer_changed)

        self.generate_button = ttk.Button(controls, text="生成世界", command=self.generate_clicked)
        self.generate_button.pack(side="left", padx=8)
        ttk.Button(controls, text="隨機Seed", command=self.random_seed).pack(side="left")
        ttk.Button(controls, text="讀取存檔", command=self.load_clicked).pack(side="left", padx=8)
        ttk.Button(controls, text="全圖", command=self.fit_world).pack(side="left")
        ttk.Button(controls, text="推進1年", command=lambda: self.advance_war(1)).pack(side="left", padx=(12, 2))
        ttk.Button(controls, text="推進10年", command=lambda: self.advance_war(10)).pack(side="left", padx=2)
        ttk.Button(controls, text="儲存戰局", command=self.save_war).pack(side="left", padx=2)
        ttk.Button(controls, text="讀取戰局", command=self.load_war).pack(side="left", padx=2)

        self.progress = ttk.Progressbar(controls, maximum=100, length=180)
        self.progress.pack(side="right", padx=8)

        self.canvas = tk.Canvas(self.root, bg="#0b1725", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.status = ttk.Label(self.root, text="滑鼠滾輪縮放｜左鍵拖曳｜點擊查詢格子", padding=6)
        self.status.pack(fill="x")
        self.war_log = tk.Text(self.root, height=7, bg="#141820", fg="#e6e6e6", insertbackground="white", wrap="word")
        self.war_log.pack(fill="x")
        self.war_log.insert("end", "V5：推進年份後，AI只會攻擊接壤國或具有港口、艦隊及航程能力的國家。\n")
        self.war_log.configure(state="disabled")

        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def random_seed(self):
        self.seed_var.set(str(random.SystemRandom().randint(1, 2**31 - 1)))

    def load_or_generate(self):
        try:
            self.set_world(load_world())
        except Exception:
            self.generate_clicked()

    def settings_from_ui(self):
        return MapSettings(
            width=int(self.width_var.get()),
            height=int(self.height_var.get()),
            seed=int(self.seed_var.get()),
            world_style=STYLE_CODES.get(self.style_var.get(), "RANDOM"),
        ).validated()

    def generate_clicked(self):
        try:
            settings = self.settings_from_ui()
        except ValueError:
            messagebox.showerror("參數錯誤", "寬、高與 Seed 必須是整數。")
            return
        self.generate_button.configure(state="disabled")
        self.status.configure(text="正在生成世界…")
        threading.Thread(target=self._generate_worker, args=(settings,), daemon=True).start()

    def _generate_worker(self, settings):
        try:
            world = generate_world(
                settings,
                lambda value, message: self.root.after(
                    0, self._show_progress, value, message
                ),
            )
            save_world(world)
            self.root.after(0, self.set_world, world)
        except Exception as exc:
            self.root.after(0, messagebox.showerror, "生成失敗", str(exc))
        finally:
            self.root.after(0, lambda: self.generate_button.configure(state="normal"))

    def _show_progress(self, value, message):
        self.progress["value"] = value * 100
        self.status.configure(text=message)

    def load_clicked(self):
        try:
            self.set_world(load_world())
        except Exception as exc:
            messagebox.showerror("讀取失敗", str(exc))

    def set_world(self, world):
        self.world = world
        self.war = WarEngine(world, SAVES_DIR / "war_state")
        self.full_image = render_environment(world, self.layer_var.get())
        self.width_var.set(str(world.settings.width))
        self.height_var.set(str(world.settings.height))
        self.seed_var.set(str(world.settings.seed))
        self.style_var.set(STYLE_LABELS.get(world.world_style, world.world_style))
        self.progress["value"] = 100
        self.fit_world()
        ocean = 100.0 * float((world.terrain <= 1).mean())
        self.status.configure(
            text=f"第{self.war.year}年｜完成｜{world.world_style}｜{world.settings.width}×{world.settings.height}｜海洋 {ocean:.1f}%｜{world.generation_seconds:.2f} 秒"
        )

    def advance_war(self, years):
        if not self.war or self.war_busy:
            return
        self.war_busy = True
        self.status.configure(text=f"正在推進{years}年…")
        threading.Thread(target=self._advance_war_worker, args=(years,), daemon=True).start()

    def _advance_war_worker(self, years):
        try:
            summary = self.war.step(years)
            self.root.after(0, self._finish_war_advance, summary)
        except Exception as exc:
            self.root.after(0, messagebox.showerror, "推進失敗", str(exc))
            self.root.after(0, setattr, self, "war_busy", False)

    def _finish_war_advance(self, summary):
        self.full_image = render_environment(self.world, self.layer_var.get())
        self.redraw()
        self.status.configure(
            text=f"第{summary['year']}年｜存活 {summary['alive']} 國｜行軍中 {summary['campaigns']} 支｜累計戰役 {summary['battles']} 場"
        )
        lines = (self.war.alerts + self.war.events[-10:])[-14:]
        self.war_log.configure(state="normal")
        self.war_log.delete("1.0", "end")
        self.war_log.insert("end", "\n".join(lines) if lines else "目前世界和平，但AI正在評估接壤、兵力、距離與資源。")
        self.war_log.configure(state="disabled")
        self.war_busy = False

    def save_war(self):
        if not self.war:
            return
        try:
            self.war.save(SAVES_DIR / "war_state")
            messagebox.showinfo("完成", "戰爭狀態已存入 saves/war_state.json 與 war_state.npz。")
        except Exception as exc:
            messagebox.showerror("儲存失敗", str(exc))

    def load_war(self):
        if not self.world:
            return
        try:
            self.war = WarEngine.load(self.world, SAVES_DIR / "war_state")
            self.full_image = render_environment(self.world, self.layer_var.get())
            self.redraw()
            summary = self.war.summary()
            self.status.configure(text=f"已讀取第{summary['year']}年｜存活 {summary['alive']} 國｜行軍中 {summary['campaigns']} 支")
        except Exception as exc:
            messagebox.showerror("讀取失敗", str(exc))

    def layer_changed(self, _event=None):
        if not self.world:
            return
        self.full_image = render_environment(self.world, self.layer_var.get())
        self.redraw()

    def fit_world(self):
        if not self.world:
            return
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        self.zoom = min(cw / self.world.settings.width, ch / self.world.settings.height)
        self.center_x = self.world.settings.width / 2
        self.center_y = self.world.settings.height / 2
        self.redraw()

    def redraw(self):
        if not self.world or self.full_image is None:
            return
        cw = max(2, self.canvas.winfo_width())
        ch = max(2, self.canvas.winfo_height())
        half_w = cw / (2 * self.zoom)
        half_h = ch / (2 * self.zoom)
        left = max(0, int(self.center_x - half_w))
        top = max(0, int(self.center_y - half_h))
        right = min(self.world.settings.width, int(self.center_x + half_w) + 1)
        bottom = min(self.world.settings.height, int(self.center_y + half_h) + 1)
        if right <= left or bottom <= top:
            return
        crop = self.full_image.crop((left, top, right, bottom))
        target = (max(1, int((right - left) * self.zoom)), max(1, int((bottom - top) * self.zoom)))
        resample = 0 if self.zoom >= 2.0 else 2
        crop = crop.resize(target, resample=resample)
        self.tk_image = ImageTk.PhotoImage(crop)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self.tk_image, anchor="center")
        self.view_box = (left, top, right, bottom, target[0], target[1])
        self._draw_campaigns(left, top, cw, ch, target[0], target[1])

    def _draw_campaigns(self, left, top, cw, ch, tw, th):
        if not self.war:
            return
        offset_x = (cw - tw) / 2
        offset_y = (ch - th) / 2
        for campaign in self.war.campaigns:
            if campaign.status != "marching":
                continue
            y0, x0 = campaign.origin
            y1, x1 = campaign.objective
            sx0, sy0 = offset_x + (x0 - left) * self.zoom, offset_y + (y0 - top) * self.zoom
            sx1, sy1 = offset_x + (x1 - left) * self.zoom, offset_y + (y1 - top) * self.zoom
            color = "#55dff0" if campaign.mode == "naval" else "#ff5f57"
            self.canvas.create_line(sx0, sy0, sx1, sy1, fill=color, width=2, arrow="last", dash=(5, 3))
            self.canvas.create_text((sx0 + sx1) / 2, (sy0 + sy1) / 2, text=f"{campaign.years_left}年", fill="white")

    def on_wheel(self, event):
        factor = 1.25 if event.delta > 0 else 0.8
        self.zoom = max(0.08, min(12.0, self.zoom * factor))
        self.redraw()

    def on_press(self, event):
        self.drag_start = (event.x, event.y, self.center_x, self.center_y)

    def on_drag(self, event):
        if not self.drag_start:
            return
        sx, sy, cx, cy = self.drag_start
        self.center_x = cx - (event.x - sx) / self.zoom
        self.center_y = cy - (event.y - sy) / self.zoom
        self.center_x = min(max(0, self.center_x), self.world.settings.width)
        self.center_y = min(max(0, self.center_y), self.world.settings.height)
        self.redraw()

    def on_release(self, event):
        if not self.drag_start or not self.world:
            return
        sx, sy, _cx, _cy = self.drag_start
        moved = abs(event.x - sx) + abs(event.y - sy)
        self.drag_start = None
        if moved > 5:
            return
        left, top, _right, _bottom, tw, th = self.view_box
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        px = event.x - (cw - tw) / 2
        py = event.y - (ch - th) / 2
        x = int(left + px / self.zoom)
        y = int(top + py / self.zoom)
        if not (0 <= x < self.world.settings.width and 0 <= y < self.world.settings.height):
            return
        code = int(self.world.terrain[y, x])
        biome = biome_name(self.world.biome[y, x])
        water = water_name(self.world.water[y, x])
        country_id = int(self.world.territory[y, x])
        country_name = "無主地"
        war_detail = ""
        if 0 < country_id <= len(self.world.countries):
            country_name = self.world.countries[country_id - 1]["name"]
            if self.war:
                c = self.war.country(country_id)
                war_detail = f"｜人口 {c['population']:,}｜士兵 {c['soldiers']:,}｜艦隊 {c['fleet']}｜聯盟 {c['alliance']}"
        place_names = {0: "", 1: "首都", 2: "城市", 3: "港口"}
        place = place_names.get(int(self.world.settlement[y, x]), "")
        self.status.configure(
            text=(
                f"座標 ({x}, {y})｜{country_name}{(' / ' + place) if place else ''}｜{terrain_name(code)} / {biome}｜水體 {water}｜"
                f"溫度 {float(self.world.temperature[y, x]):.1f}°C｜濕度 {float(self.world.humidity[y, x])*100:.0f}%｜"
                f"降雨 {float(self.world.rainfall[y, x]):.0f} mm{war_detail}｜"
                f"農 {int(self.world.agriculture[y, x])} 木 {int(self.world.timber[y, x])} 礦 {int(self.world.minerals[y, x])} "
                f"水 {int(self.world.freshwater[y, x])} 城 {int(self.world.city_value[y, x])} "
                f"防 {int(self.world.defense_value[y, x])} 移 {int(self.world.movement_cost[y, x]) if self.world.movement_cost[y, x] != 255 else '不可通行'}"
            )
        )


def main():
    root = tk.Tk()
    MapViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
