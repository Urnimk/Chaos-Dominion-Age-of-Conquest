"""V13_4 Pygame 專用視窗：保留征佔紀元的戰爭核心與存檔格式。"""
from __future__ import annotations

import math
import queue
import random
import threading
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pygame
from scipy import ndimage

import map_config as cfg
from climate_rules import biome_name
from map_generator import MapSettings, SAVES_DIR, generate_world, load_world, save_world
from map_renderer import render_environment
from terrain_rules import terrain_name
from war_engine import WarEngine

WINDOW_SIZE = (1500, 920)
TOP_H = 58
STATUS_H = 26
RIGHT_W = 360
ZOOM_MIN, ZOOM_MAX = 0.1, 15.0
AUTO_LOAD_LAST_SAVE = True
AUTO_SAVE_ENABLED = True
AUTO_SAVE_EVERY_YEARS = 100
SIM_MAX_BATCH_YEARS = 1
LAYERS = ("國家與領土", "生態環境", "基礎地形", "農業價值", "木材價值", "礦產價值",
          "淡水供應", "建城價值", "防禦價值", "移動成本")
STYLE_LABELS = {
    "RANDOM": "隨機風格", "BALANCED": "均衡世界", "SUPERCONTINENT": "超級大陸",
    "ARCHIPELAGO": "群島世界", "FRACTURED": "破碎大陸", "INLAND_SEAS": "內海世界",
    "TWIN_CONTINENTS": "雙大陸世界",
}

BG = (20, 25, 32)
PANEL = (31, 38, 47)
PANEL_2 = (40, 49, 60)
TEXT = (232, 237, 243)
MUTED = (158, 172, 188)
ACCENT = (48, 156, 201)
GOLD = (244, 201, 93)


def capital_landmass_mask(territory, continent, country_id, capital):
    """與 Tk 版相同：只回傳首都所在陸塊，避免把殖民地算進定位範圍。"""
    owned = territory == int(country_id)
    cx, cy = map(int, capital)
    if not (0 <= cy < territory.shape[0] and 0 <= cx < territory.shape[1]):
        return owned
    land = owned & (continent == continent[cy, cx])
    labels, _ = ndimage.label(land, structure=np.ones((3, 3), dtype=np.uint8))
    label = int(labels[cy, cx])
    return (labels == label) if label > 0 else owned


class PygameViewer:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption("亂世演算_征佔紀元 V13_4｜Pygame 地圖視窗")
        self.clock = pygame.time.Clock()
        self.font = self._load_font(17)
        self.small = self._load_font(14)
        self.heading = self._load_font(21, bold=True)
        self.world = self.war = None
        self.map_surface = None
        self._scaled_map_cache = None
        self._scaled_map_cache_key = None
        self.map_image_pil = None
        self.map_overlays = {}
        self.selected_country_id = 1
        self.layer_index = 0
        self.world_style_index = list(STYLE_LABELS).index(cfg.WORLD_STYLE) if cfg.WORLD_STYLE in STYLE_LABELS else 1
        self.seed_text = str(cfg.MAP_SEED)
        self.seed_focused = False
        self.hide_region_names = False
        self.zoom = 0.5
        self.center_x = cfg.MAP_WIDTH / 2
        self.center_y = cfg.MAP_HEIGHT / 2
        self.drag_origin = None
        self.view_rect = pygame.Rect(0, TOP_H, 1000, 800)
        self.status = "正在載入世界…"
        self.running = bool(cfg.AUTO_RUN_ON_START)
        self.sim_credit = 0.0
        self.last_clock = time.perf_counter()
        self.war_busy = False
        self.loading_busy = True
        self.saving_busy = False
        self.resume_after_save = False
        self.exit_requested = False
        self.close_save_started = False
        self.should_close = False
        self.last_autosave_year = None
        self.last_visual_revision = -1
        self.last_map_refresh = 0.0
        self.last_panel_refresh = 0.0
        self.country_snapshot = []
        self.country_events = {}
        self.world_events = []
        self.history_events = []
        self.alliance_names = {}
        self.campaign_snapshot = []
        self.alive_count = 0
        self.year = 0
        self.map_generation = 0
        self.map_jobs = queue.Queue(maxsize=1)
        self.map_results = queue.Queue(maxsize=1)
        self.app_results = queue.Queue()
        self.buttons = []
        self.text_cache = OrderedDict()
        self.panel_tab = "國家"
        self.panel_scroll = 0
        self.row_hits = []
        self.colony_hits = []
        self.running = bool(cfg.AUTO_RUN_ON_START)
        threading.Thread(target=self._map_worker, daemon=True, name="pygame-map-render").start()
        threading.Thread(target=self._load_worker, daemon=True, name="pygame-world-load").start()

    def _load_font(self, size, bold=False):
        candidates = ("Microsoft YaHei UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "SimHei", "Noto Sans CJK TC")
        for name in candidates:
            found = pygame.font.match_font(name, bold=bold)
            if found:
                return pygame.font.Font(found, size)
        return pygame.font.SysFont(None, size, bold=bold)

    def _load_worker(self):
        try:
            try:
                world = load_world()
            except Exception:
                settings = MapSettings(cfg.MAP_WIDTH, cfg.MAP_HEIGHT, int(cfg.MAP_SEED), cfg.WORLD_STYLE).validated()
                world = generate_world(settings)
                save_world(world)
            war = WarEngine(world, SAVES_DIR / "war_state")
            if AUTO_LOAD_LAST_SAVE:
                try:
                    war = WarEngine.load(world, SAVES_DIR / "war_state")
                except Exception:
                    pass
            self.app_results.put(("world", world, war, None))
        except Exception as exc:
            self.app_results.put(("error", str(exc)))

    def _start_generation(self):
        if self.loading_busy or self.war_busy:
            return
        try:
            seed = int(self.seed_text)
            code = list(STYLE_LABELS)[self.world_style_index]
            settings = MapSettings(cfg.MAP_WIDTH, cfg.MAP_HEIGHT, seed, code).validated()
        except (ValueError, TypeError):
            self.status = "Seed 必須是整數。"
            return
        self.loading_busy = True
        self.running = False
        self.status = "正在生成新世界…"

        def worker():
            try:
                world = generate_world(settings)
                save_world(world)
                war = WarEngine(world, SAVES_DIR / "war_state")
                self.app_results.put(("world", world, war, None))
            except Exception as exc:
                self.app_results.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True, name="pygame-world-generation").start()

    def _map_worker(self):
        while True:
            generation, war, layer = self.map_jobs.get()
            if generation != self.map_generation:
                continue
            try:
                snapshot, overlays = war.map_render_snapshot()
                for country in overlays.get("countries", []):
                    cx, cy = map(int, country["capital"])
                    country["capital_owned"] = (
                        0 <= cy < snapshot.territory.shape[0]
                        and 0 <= cx < snapshot.territory.shape[1]
                        and int(snapshot.territory[cy, cx]) == int(country["id"])
                    )
                rendered = render_environment(snapshot, layer)
                result = (generation, war, rendered, overlays, None)
            except Exception as exc:
                result = (generation, war, None, None, str(exc))
            try:
                self.map_results.put_nowait(result)
            except queue.Full:
                try:
                    self.map_results.get_nowait()
                except queue.Empty:
                    pass
                self.map_results.put_nowait(result)

    def _request_map(self):
        if not self.war:
            return
        self.map_generation += 1
        item = (self.map_generation, self.war, LAYERS[self.layer_index])
        try:
            self.map_jobs.put_nowait(item)
        except queue.Full:
            try:
                self.map_jobs.get_nowait()
            except queue.Empty:
                pass
            self.map_jobs.put_nowait(item)

    def _step_worker(self, years):
        war = self.war
        try:
            summary = war.step(years)
            self.app_results.put(("step", war, summary, int(years), None))
        except Exception as exc:
            self.app_results.put(("step", war, None, int(years), str(exc)))

    def _save_worker(self, world, war, year, auto=False):
        try:
            save_world(world)
            war.save(SAVES_DIR / "war_state")
            self.app_results.put(("saved", int(year), bool(auto), None))
        except Exception as exc:
            self.app_results.put(("saved", int(year), bool(auto), str(exc)))

    def _begin_save(self, auto=False):
        if not self.world or not self.war or self.war_busy or self.saving_busy:
            return False
        self.saving_busy = True
        self.resume_after_save = bool(self.running and not auto)
        if auto:
            self.resume_after_save = bool(self.running)
        self.running = False
        threading.Thread(target=self._save_worker, args=(self.world, self.war, self.year, auto),
                         daemon=True, name="pygame-save").start()
        return True

    def _handle_background_results(self):
        while True:
            try:
                event = self.app_results.get_nowait()
            except queue.Empty:
                break
            if event[0] == "world":
                _, self.world, self.war, _ = event
                self.loading_busy = False
                self.map_surface = None
                self._scaled_map_cache = None
                self._scaled_map_cache_key = None
                self.map_overlays = {}
                self.last_visual_revision = -1
                self.last_autosave_year = None
                self.year = self.war.year
                self.seed_text = str(self.world.settings.seed)
                self.center_x = self.world.settings.width / 2
                self.center_y = self.world.settings.height / 2
                self._refresh_panels()
                self._request_map()
                self.fit_world()
                self.status = f"世界載入完成｜Seed {self.world.settings.seed}｜{STYLE_LABELS.get(self.world.settings.world_style, self.world.settings.world_style)}"
            elif event[0] == "error":
                self.loading_busy = False
                self.status = f"作業失敗：{event[1]}"
            elif event[0] == "step":
                _, war, summary, years, error = event
                if war is not self.war:
                    continue
                self.war_busy = False
                if error:
                    self.status = f"模擬推進失敗：{error}"
                else:
                    self.year = int(summary["year"])
                    self._refresh_panels()
                    revision = int(self.war.visual_revision)
                    now = time.perf_counter()
                    if revision != self.last_visual_revision and now - self.last_map_refresh >= 0.5:
                        self._request_map()
                        self.last_map_refresh = now
                    if AUTO_SAVE_ENABLED and (self.last_autosave_year is None or self.year-self.last_autosave_year >= AUTO_SAVE_EVERY_YEARS):
                        if self._begin_save(auto=True):
                            self.last_autosave_year = self.year
                    self.status = f"世界第 {self.year} 年｜存活 {summary['alive']} 國｜殖民航程 {summary['colonizing_voyages']}｜戰役 {summary['campaigns']}"
            elif event[0] == "saved":
                _, year, auto, error = event
                self.saving_busy = False
                if error:
                    self.status = f"存檔失敗：{error}"
                    self.running = bool(self.resume_after_save and not self.exit_requested)
                    if self.exit_requested:
                        self.should_close = True
                else:
                    self.last_autosave_year = year
                    self.status = f"已儲存｜世界第 {year} 年" if not auto else f"已自動儲存｜世界第 {year} 年"
                    self.running = bool(self.resume_after_save and not self.exit_requested)
                    if self.exit_requested:
                        self.should_close = True
        newest = None
        while True:
            try:
                newest = self.map_results.get_nowait()
            except queue.Empty:
                break
        if newest:
            generation, war, image, overlays, error = newest
            if generation == self.map_generation and war is self.war:
                if error:
                    self.status = f"地圖渲染失敗：{error}"
                else:
                    self.map_surface = pygame.image.fromstring(image.tobytes(), image.size, "RGB").convert()
                    self._scaled_map_cache = None
                    self._scaled_map_cache_key = None
                    self.map_overlays = overlays
                    self.last_visual_revision = int(overlays["revision"])

    def _refresh_panels(self):
        if not self.war:
            return
        with self.war._state_lock:
            self.year = int(self.war.year)
            self.alive_count = sum(bool(c.get("alive")) for c in self.war.countries)
            self.country_snapshot = []
            for c in self.war.countries:
                item = {key: c.get(key) for key in ("id", "name", "alive", "territory_cells", "population",
                         "soldiers", "fleet", "alliance", "wars_won", "wars_lost", "capital")}
                item["colonies"] = []
                for colony in c.get("colonies", []):
                    colony_copy = dict(colony)
                    ax, ay = map(int, colony_copy.get("anchor", (0, 0)))
                    colony_copy["region_name"] = self.war.geographic_name_at(ay, ax)
                    item["colonies"].append(colony_copy)
                voyage = c.get("colonization_voyage")
                item["colonization_voyage"] = dict(voyage) if voyage else None
                self.country_snapshot.append(item)
            self.country_events = {int(k): list(v[-30:]) for k, v in self.war.country_events.items()}
            self.world_events = list(self.war.events[-50:])
            self.history_events = list(self.war.history_events[-100:])
            self.alliance_names = dict(self.war.alliance_names)
            self.campaign_snapshot = [
                {"mode": c.mode, "status": c.status, "origin": c.origin,
                 "objective": c.objective, "attacker": c.attacker, "defender": c.defender}
                for c in self.war.campaigns
            ]

    def _layout(self):
        w, h = self.screen.get_size()
        right_w = min(RIGHT_W, max(300, w // 3))
        self.view_rect = pygame.Rect(0, TOP_H, w-right_w, h-TOP_H-STATUS_H)
        self.panel_rect = pygame.Rect(w-right_w, TOP_H, right_w, h-TOP_H-STATUS_H)

    def fit_world(self):
        if not self.world:
            return
        self._layout()
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX,
            min(self.view_rect.width/self.world.settings.width,
                self.view_rect.height/self.world.settings.height)*0.96))
        self.center_x = self.world.settings.width/2
        self.center_y = self.world.settings.height/2

    def focus_country(self, country_id):
        if not self.world or not self.war:
            return
        country = next((c for c in self.country_snapshot if int(c["id"]) == int(country_id)), None)
        if not country:
            return
        self.selected_country_id = int(country_id)
        cx, cy = country.get("capital", (self.world.settings.width//2, self.world.settings.height//2))
        with self.war._state_lock:
            mask = capital_landmass_mask(self.world.territory, self.world.continent, country_id, (cx, cy))
            ys, xs = np.where(mask)
        if len(xs):
            self.center_x = float(xs.mean())
            self.center_y = float(ys.mean())
            span_x = max(1, int(xs.max()-xs.min()+1))
            span_y = max(1, int(ys.max()-ys.min()+1))
            self._layout()
            self.zoom = max(0.35, min(8.0, min(self.view_rect.width/span_x, self.view_rect.height/span_y)*0.82))
        else:
            self.center_x, self.center_y = float(cx), float(cy)
        self.status = f"定位至 {country['name']} 首都主島"

    def _map_world_at(self, sx, sy):
        if not self.view_rect.collidepoint(sx, sy) or not self.world:
            return None
        x = self.center_x + (sx-self.view_rect.centerx)/self.zoom
        y = self.center_y + (sy-self.view_rect.centery)/self.zoom
        ix, iy = int(x), int(y)
        if 0 <= ix < self.world.settings.width and 0 <= iy < self.world.settings.height:
            return ix, iy
        return None

    def _zoom_at(self, factor, sx, sy):
        before = self._map_world_at(sx, sy)
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom*factor))
        if before:
            self.center_x = before[0] - (sx-self.view_rect.centerx)/self.zoom
            self.center_y = before[1] - (sy-self.view_rect.centery)/self.zoom

    def _draw_text(self, text, x, y, color=TEXT, font=None, max_width=None):
        font = font or self.font
        key = (id(font), str(text), tuple(color), int(max_width or 0))
        image = self.text_cache.get(key)
        if image is None:
            image = font.render(str(text), True, color)
            if max_width and image.get_width() > max_width:
                image = pygame.transform.smoothscale(image, (max_width, max(1, int(image.get_height()*max_width/image.get_width()))))
            self.text_cache[key] = image
            if len(self.text_cache) > 1024:
                self.text_cache.popitem(last=False)
        else:
            self.text_cache.move_to_end(key)
        self.screen.blit(image, (int(x), int(y)))
        return image.get_height()

    def _button(self, label, key, x, y, w, h=34, active=False):
        rect = pygame.Rect(x, y, w, h)
        self.buttons.append((rect, key))
        pygame.draw.rect(self.screen, ACCENT if active else PANEL_2, rect, border_radius=5)
        pygame.draw.rect(self.screen, (78, 96, 114), rect, 1, border_radius=5)
        surf = self.small.render(label, True, TEXT)
        self.screen.blit(surf, surf.get_rect(center=rect.center))
        return rect.right

    def _draw_top(self):
        w, _ = self.screen.get_size()
        pygame.draw.rect(self.screen, PANEL, (0, 0, w, TOP_H))
        x, y = 9, 11
        x = self._button("暫停" if self.running else "繼續", "run", x, y, 62, active=self.running)+5
        x = self._button("推進1年", "step1", x, y, 72)+5
        x = self._button("推進10年", "step10", x, y, 80)+5
        x = self._button("新世界", "new", x, y, 62)+5
        style_code = list(STYLE_LABELS)[self.world_style_index]
        x = self._button(STYLE_LABELS[style_code], "style", x, y, 94)+5
        seed_rect = pygame.Rect(x, y, 118, 34)
        self.buttons.append((seed_rect, "seed"))
        pygame.draw.rect(self.screen, (18, 23, 29) if self.seed_focused else PANEL_2, seed_rect, border_radius=4)
        self._draw_text(self.seed_text[-14:], seed_rect.x+7, seed_rect.y+8, TEXT, self.small)
        x = seed_rect.right+5
        x = self._button("隨機 Seed", "random_seed", x, y, 81)+5
        x = self._button("儲存", "save", x, y, 54)+5
        x = self._button("讀取", "load", x, y, 54)+5
        x = self._button("圖層 ‹", "layer", x, y, 86)+5
        x = self._button("全圖", "fit", x, y, 52)+5
        self._button("顯示地名" if self.hide_region_names else "隱藏地名", "names", x, y, 78)
        label = f"第 {self.year:,} 年｜{self.alive_count} 國｜{STYLE_LABELS.get(getattr(getattr(self.world, 'settings', None), 'world_style', ''), '')}"
        self._draw_text(label, max(9, w-330), 8, MUTED, self.small, 320)

    def _draw_map(self):
        pygame.draw.rect(self.screen, (10, 19, 29), self.view_rect)
        if not self.world or self.map_surface is None:
            self._draw_text("正在準備地圖…", self.view_rect.centerx-65, self.view_rect.centery, MUTED)
            return
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(self.view_rect)
        width, height = self.world.settings.width, self.world.settings.height
        half_w, half_h = self.view_rect.width/(2*self.zoom), self.view_rect.height/(2*self.zoom)
        left, right = max(0, int(self.center_x-half_w)), min(width, int(self.center_x+half_w)+1)
        top, bottom = max(0, int(self.center_y-half_h)), min(height, int(self.center_y+half_h)+1)
        if right <= left or bottom <= top:
            return
        src = pygame.Rect(left, top, right-left, bottom-top)
        cache_key = (id(self.map_surface), self.map_generation, src.x, src.y, src.width, src.height,
                     round(self.zoom, 6), round(self.center_x, 4), round(self.center_y, 4),
                     self.view_rect.width, self.view_rect.height)
        if cache_key != self._scaled_map_cache_key:
            crop = self.map_surface.subsurface(src)
            target_size = (max(1, int(src.width*self.zoom)), max(1, int(src.height*self.zoom)))
            self._scaled_map_cache = pygame.transform.smoothscale(crop, target_size) if target_size != crop.get_size() else crop
            self._scaled_map_cache_key = cache_key
        scaled = self._scaled_map_cache
        dest = scaled.get_rect(center=(self.view_rect.centerx + int((left+right-1)/2-self.center_x)*self.zoom,
                                       self.view_rect.centery + int((top+bottom-1)/2-self.center_y)*self.zoom))
        self.screen.blit(scaled, dest)
        self._draw_map_overlays()
        self.screen.set_clip(previous_clip)

    def _map_to_screen(self, x, y):
        return (self.view_rect.centerx+(float(x)-self.center_x)*self.zoom,
                self.view_rect.centery+(float(y)-self.center_y)*self.zoom)

    def _draw_map_overlays(self):
        overlays = self.map_overlays
        if not overlays:
            return
        clip = self.screen.get_clip()
        self.screen.set_clip(self.view_rect)
        if not self.hide_region_names:
            regions = sorted(overlays.get("regions", []), key=lambda r: r["size"], reverse=True)[:cfg.GEOGRAPHIC_MAX_VISIBLE_LABELS]
            for r in regions:
                if r["size"] < cfg.GEOGRAPHIC_LABEL_MIN_CELLS:
                    continue
                sx, sy = self._map_to_screen(*r["center"])
                if self.view_rect.inflate(120, 40).collidepoint(sx, sy):
                    self._draw_text(r["name"], sx, sy, (202, 211, 222), self.small)
        width = self.world.settings.width
        for c in overlays.get("campaigns", []):
            if c["status"] != "marching":
                continue
            y0, x0 = c["origin"]; y1, x1 = c["objective"]
            color = (88, 230, 242) if c["mode"] == "naval" else (255, 92, 87)
            pygame.draw.line(self.screen, color, self._map_to_screen(x0, y0), self._map_to_screen(x1, y1), 2)
        for voyage in overlays.get("voyages", []):
            route = voyage.get("route", [])
            points = []
            for x, y in route:
                if points and abs(float(x)-points[-1][0]) > width/2:
                    if len(points) > 1:
                        pygame.draw.lines(self.screen, GOLD, False, [self._map_to_screen(a,b) for a,b in points], 2)
                    points = []
                points.append((float(x), float(y)))
            if len(points)>1:
                pygame.draw.lines(self.screen, GOLD, False, [self._map_to_screen(a,b) for a,b in points], 2)
            if route:
                for point, color in ((route[0], (74,222,128)), (route[-1], (251,113,133))):
                    pygame.draw.circle(self.screen, color, tuple(map(int, self._map_to_screen(*point))), 4)
        for c in overlays.get("countries", []):
            x, y = c["capital"]
            if not c.get("capital_owned", False):
                continue
            sx, sy = self._map_to_screen(x, y)
            if self.view_rect.inflate(200, 60).collidepoint(sx, sy):
                label = self.small.render(c["name"], True, (255,255,255))
                outline = self.small.render(c["name"], True, (20,20,20))
                for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    self.screen.blit(outline, (int(sx-label.get_width()/2+dx), int(sy-17+dy)))
                self.screen.blit(label, (int(sx-label.get_width()/2), int(sy-17)))
        self.screen.set_clip(clip)

    def _draw_panel(self):
        r = self.panel_rect
        pygame.draw.rect(self.screen, PANEL, r)
        self.row_hits = []
        self.colony_hits = []
        tabs = ("國家", "聯盟", "戰史")
        x = r.x+8
        for tab in tabs:
            x = self._button(tab, "tab:"+tab, x, r.y+8, 70, 31, active=self.panel_tab==tab)+5
        y = r.y+48
        if self.panel_tab == "國家":
            country = next((c for c in self.country_snapshot if int(c["id"])==self.selected_country_id), None)
            if country:
                self._draw_text(country["name"], r.x+12, y, GOLD, self.heading, r.width-24); y += 31
                for label, value in (("首都", self._capital_name(country)), ("領土格", f"{country['territory_cells']:,}"),
                                     ("人口", f"{country['population']:,}"), ("士兵", f"{country['soldiers']:,}"),
                                     ("艦隊／殖民地", f"{country['fleet']:,}／{len(country.get('colonies') or [])}"),
                                     ("聯盟", self._alliance_name(country.get("alliance", 0))),
                                     ("戰績", f"{country['wars_won']} 勝／{country['wars_lost']} 敗")):
                    self._draw_text(f"{label}：{value}", r.x+14, y, TEXT, self.small, r.width-25); y += 21
                voyage = country.get("colonization_voyage")
                if voyage:
                    ax, ay = voyage.get("anchor", (0, 0))
                    arrival = voyage.get("estimated_arrival_year", self.year)
                    self._draw_text(f"航行中：({ax}, {ay}) 海岸｜預計第 {arrival} 年抵達",
                                    r.x+14, y, GOLD, self.small, r.width-25)
                    y += 21
                for colony in country.get("colonies", [])[:6]:
                    ax, ay = map(int, colony.get("anchor", (0, 0)))
                    name = colony.get("region_name", "殖民地")
                    rr = pygame.Rect(r.x+13, y, r.width-26, 19)
                    self.colony_hits.append((rr, ax, ay, name))
                    self._draw_text(f"殖民地：{name}｜第 {colony.get('founded_year', 0)} 年建立 ↗",
                                    rr.x, rr.y, (90, 196, 231), self.small, rr.width)
                    y += 20
                for entry in self.country_events.get(self.selected_country_id, [])[-2:]:
                    self._draw_text(f"紀錄：{entry}", r.x+14, y, MUTED, self.small, r.width-25)
                    y += 19
            y += 9
            self._draw_text("國家排名（點選定位首都主島）", r.x+12, y, MUTED, self.small); y += 23
            available = max(0, r.bottom-STATUS_H-y-5)
            row_h = 30
            ranked = sorted((c for c in self.country_snapshot if c.get("alive")), key=lambda c:c.get("territory_cells",0), reverse=True)
            visible = max(0, available//row_h)
            for i, c in enumerate(ranked[self.panel_scroll:self.panel_scroll+visible]):
                rr = pygame.Rect(r.x+7, y, r.width-14, row_h-2)
                if int(c["id"]) == self.selected_country_id:
                    pygame.draw.rect(self.screen, (54,74,91), rr, border_radius=3)
                self._draw_text(f"{i+self.panel_scroll+1:>2}. {c['name']}", rr.x+6, rr.y+6, TEXT, self.small, 170)
                self._draw_text(f"{c['territory_cells']:,} 格", rr.right-98, rr.y+6, MUTED, self.small)
                self.row_hits.append((rr, int(c["id"])))
                y += row_h
        elif self.panel_tab == "聯盟":
            groups = {}
            for c in self.country_snapshot:
                aid = int(c.get("alliance") or 0)
                if aid > 0:
                    g = groups.setdefault(aid, {"members": [], "land":0, "army":0})
                    g["members"].append(c["name"]); g["land"] += int(c.get("territory_cells",0)); g["army"] += int(c.get("soldiers",0))
            self._draw_text(f"現有聯盟：{len(groups)}", r.x+12, y, GOLD, self.heading); y += 35
            for aid, g in sorted(groups.items(), key=lambda item:item[1]["land"], reverse=True):
                self._draw_text(self.alliance_names.get(aid, f"第 {aid} 聯盟"), r.x+12, y, TEXT, self.font, r.width-20); y+=23
                self._draw_text(f"成員 {len(g['members'])}｜領土 {g['land']:,} 格｜兵力 {g['army']:,}", r.x+14, y, MUTED, self.small, r.width-22); y+=19
                self._draw_text("、".join(g["members"]), r.x+14, y, MUTED, self.small, r.width-22); y+=30
        else:
            self._draw_text("近期重大事件", r.x+12, y, GOLD, self.heading); y+=32
            events = list(reversed(self.history_events[-25:])) + list(reversed(self.world_events[-15:]))
            max_width = r.width-26
            for entry in events[:max(0,(r.bottom-STATUS_H-y)//43)]:
                line = str(entry).replace("\n", " ")
                self._draw_text(line, r.x+13, y, TEXT, self.small, max_width)
                y += 39

    def _capital_name(self, c):
        return f"({c['capital'][0]}, {c['capital'][1]})" if c.get("capital") else "—"

    def _alliance_name(self, aid):
        aid = int(aid or 0)
        return self.alliance_names.get(aid, "無" if aid <= 0 else f"第 {aid} 聯盟")

    def _draw_status(self):
        w, h = self.screen.get_size()
        pygame.draw.rect(self.screen, (13, 17, 22), (0,h-STATUS_H,w,STATUS_H))
        self._draw_text(self.status, 8, h-20, MUTED, self.small, w-20)

    def _draw(self):
        self._layout()
        self.buttons = []
        self.screen.fill(BG)
        self._draw_top()
        self._draw_map()
        self._draw_panel()
        self._draw_status()
        pygame.display.flip()

    def _activate(self, key):
        if key == "run":
            self.running = not self.running
            if not self.running:
                self.sim_credit = 0.0
        elif key in ("step1", "step10"):
            years = 1 if key=="step1" else 10
            if self.war and not self.war_busy and not self.loading_busy and not self.saving_busy:
                self.war_busy = True
                threading.Thread(target=self._step_worker, args=(years,), daemon=True, name="pygame-simulation-step").start()
        elif key == "new":
            self._start_generation()
        elif key == "style":
            self.world_style_index = (self.world_style_index+1)%len(STYLE_LABELS)
        elif key == "random_seed":
            self.seed_text = str(random.SystemRandom().randint(1,2**31-1))
        elif key == "save":
            if self._begin_save():
                self.status = "正在儲存戰局…"
        elif key == "load":
            if self.world and not self.war_busy and not self.saving_busy:
                self.running = False
                self.loading_busy = True
                world = self.world
                def worker():
                    try:
                        war = WarEngine.load(world, SAVES_DIR/"war_state")
                        self.app_results.put(("world", world, war, None))
                    except Exception as exc:
                        self.app_results.put(("error", str(exc)))
                threading.Thread(target=worker, daemon=True, name="pygame-load-save").start()
                self.status = "正在讀取戰局…"
        elif key == "layer":
            self.layer_index = (self.layer_index+1)%len(LAYERS)
            self._request_map()
        elif key == "fit":
            self.fit_world()
        elif key == "names":
            self.hide_region_names = not self.hide_region_names
        elif key.startswith("tab:"):
            self.panel_tab = key.split(":",1)[1]
            self.panel_scroll = 0
        elif key == "seed":
            self.seed_focused = True

    def _start_step_if_due(self, elapsed):
        if not self.running or not self.war or self.war_busy or self.loading_busy or self.saving_busy:
            return
        self.sim_credit = min(self.sim_credit+elapsed/max(0.001,float(cfg.SECONDS_PER_YEAR)), float(cfg.SIM_MAX_BACKLOG_YEARS))
        if self.sim_credit >= 1:
            years = min(int(self.sim_credit), int(SIM_MAX_BATCH_YEARS))
            self.sim_credit -= years
            self.war_busy = True
            threading.Thread(target=self._step_worker, args=(years,), daemon=True, name="pygame-simulation-step").start()

    def _handle_event(self, event):
        if event.type == pygame.QUIT:
            self.exit_requested = True
            self.running = False
            if not self.war:
                self.should_close = True
            return
        if event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
        if event.type == pygame.KEYDOWN and self.seed_focused:
            if event.key == pygame.K_RETURN:
                self.seed_focused = False
                self._start_generation()
            elif event.key == pygame.K_BACKSPACE:
                self.seed_text = self.seed_text[:-1]
            elif event.unicode.isdigit() or (event.unicode == "-" and not self.seed_text):
                self.seed_text += event.unicode
            return
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if self.view_rect.collidepoint(mx,my):
                self._zoom_at(1.25 if event.y>0 else 0.8, mx, my)
            elif self.panel_rect.collidepoint(mx,my):
                self.panel_scroll=max(0,self.panel_scroll-event.y)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.seed_focused = False
            for rect, key in reversed(self.buttons):
                if rect.collidepoint(event.pos):
                    self._activate(key)
                    return
            for rect, cid in self.row_hits:
                if rect.collidepoint(event.pos):
                    self.focus_country(cid)
                    return
            for rect, x, y, name in self.colony_hits:
                if rect.collidepoint(event.pos):
                    self.center_x, self.center_y = float(x), float(y)
                    self.zoom = max(self.zoom, 1.5)
                    self.status = f"定位殖民地：{name}"
                    return
            if self.view_rect.collidepoint(event.pos):
                self.drag_origin=(event.pos, self.center_x, self.center_y, False)
        if event.type == pygame.MOUSEMOTION and self.drag_origin:
            start, cx, cy, moved = self.drag_origin
            dx,dy=event.pos[0]-start[0],event.pos[1]-start[1]
            self.center_x=cx-dx/self.zoom; self.center_y=cy-dy/self.zoom
            self.drag_origin=(start,cx,cy,moved or abs(dx)+abs(dy)>5)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag_origin:
            start, cx, cy, moved = self.drag_origin
            if not moved and self.world:
                point=self._map_world_at(*event.pos)
                if point:
                    x,y=point
                    with self.war._state_lock:
                        cid=int(self.world.territory[y,x])
                        tile=int(self.world.terrain[y,x])
                        biome=int(self.world.biome[y,x])
                    if cid>0:
                        self.selected_country_id=cid
                        country=next((c for c in self.country_snapshot if int(c["id"])==cid),None)
                        name=country["name"] if country else f"國家 {cid}"
                    else:
                        name="無主地"
                    self.status=f"座標 ({x},{y})｜{terrain_name(tile)}｜{biome_name(biome)}｜{name}"
            self.drag_origin=None

    def run(self):
        while True:
            now=time.perf_counter()
            elapsed=max(0.0,now-self.last_clock)
            self.last_clock=now
            for event in pygame.event.get():
                self._handle_event(event)
            self._handle_background_results()
            self._start_step_if_due(elapsed)
            if self.exit_requested and not self.saving_busy and not self.war_busy and not self.close_save_started:
                self.close_save_started = True
                if not self._begin_save(auto=True):
                    self.should_close = True
            if self.should_close:
                pygame.quit()
                return
            self._draw()
            self.clock.tick(30)


def main():
    PygameViewer().run()


if __name__ == "__main__":
    main()
