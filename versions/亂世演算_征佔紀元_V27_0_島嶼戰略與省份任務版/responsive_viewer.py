"""Main-thread Tk adapter for the V25_2 snapshot-based simulation runtime."""
import time
from types import SimpleNamespace
from tkinter import messagebox
from simulation_runtime import SimulationRuntime,RasterRuntime


class ResponsiveViewerMixin:
    def _init_runtime(self,options):
        self._runtime_options=options;self._runtime_pending={};self._runtime_completed={}
        self._snapshot_hold=False;self._closing=False;self._save_pending=False;self._save_retry_after=0.;self._redraw_pending=False
        self._raster_token=0;self._requested_raster_key=None;self._displayed_raster_key=None
        self._panel_year=None;self._world_generation=0
        def prepare(view):
            # Compute missing sea routes on a detached view, never in a drag callback.
            view._presentation_voyages=type(self)._compute_sea_voyages(SimpleNamespace(war=view))
        self._runtime=SimulationRuntime(prepare_view=prepare)
        def render(world,selection):
            if isinstance(selection,tuple):
                layer,style=selection
                return options['render_environment'](world,layer,visual_style=style)
            return options['render_environment'](world,selection)
        self._raster=RasterRuntime(render,metrics=self._runtime.metrics)
        self.root.after(16,self._poll_runtime)
    def _runtime_submit(self,kind,**data):
        if kind in ('load','export'):
            existing=next((token for token,value in self._runtime_pending.items() if value==kind),None)
            if existing is not None:return existing
        token=self._runtime.submit(kind,**data);self._runtime_pending[token]=kind
        self.war_busy=True;return token
    def _runtime_settings(self):
        o=self._runtime_options
        return o['MapSettings'](int(self.width_var.get()),int(self.height_var.get()),
            int(self.seed_var.get()),o['STYLE_CODES'].get(self.style_var.get(),'BALANCED')).validated()
    def load_or_generate(self):
        self._runtime_submit('initialize',settings=self._runtime_settings(),
            path=self._runtime_options['SAVES_DIR']/'war_state',load_last=self._runtime_options['AUTO_LOAD_LAST_SAVE'])
    def generate_clicked(self):
        if self.war_busy or self._closing:return
        try:settings=self._runtime_settings()
        except ValueError:messagebox.showerror('參數錯誤','Seed、地圖寬度與高度必須是整數。');return
        self.status.configure(text='正在背景生成世界…')
        self._runtime_submit('initialize',settings=settings,generate=True,load_last=False,
                             path=self._runtime_options['SAVES_DIR']/'war_state')
    def set_world(self,world):
        if self.war_busy:return
        self._runtime_submit('initialize',world=world,load_last=self._runtime_options['AUTO_LOAD_LAST_SAVE'],
                             path=self._runtime_options['SAVES_DIR']/'war_state')
    def advance_war(self,years):
        if not self.war or self.war_busy or self._snapshot_hold or self._closing:return
        self._runtime_submit('advance',years=max(1,int(years)))
    def _poll_runtime(self):
        for packet in self._runtime.poll():
            kind=packet['kind'];token=packet['token']
            if packet['done']:self._runtime_pending.pop(token,None)
            if packet.get('view') is not None:
                view=packet['view'];self.war=view;self.world=view.world
                if kind in ('initialize','load'):
                    self._world_generation+=1;self._requested_raster_key=None
                    self.full_image=None;self._panel_year=None;self._last_auto_save_year=None
                    self.seed_var.set(str(self.world.settings.seed))
                    self.width_var.set(str(self.world.settings.width));self.height_var.set(str(self.world.settings.height))
                    self.style_var.set(self._runtime_options['STYLE_LABELS'].get(self.world.world_style,'均衡世界'))
                    if kind=='initialize':self.selected_country_id=1;self._map_has_been_fitted=False
                if kind=='advance':
                    completed=packet.get('completed',packet.get('result',0));previous=self._runtime_completed.get(token,0)
                    self._sim_years_completed_window+=max(0,int(completed or 0)-previous)
                    self._runtime_completed[token]=int(completed or 0)
                now=time.perf_counter()
                if kind!='advance' or now-self._last_ui_refresh>=.25 or not self.running:
                    self.refresh_panels();self._last_ui_refresh=now;self._panel_year=self.war.year
                year=self.war.year
                self._snapshot_hold=bool(self._runtime_options['MAP_SNAPSHOT_ENABLED'] and year!=self._last_map_snapshot_year and (year==500 or year>=1000 and year%max(1,self._runtime_options['MAP_SNAPSHOT_INTERVAL_YEARS'])==0))
                self.redraw()
                self._request_raster(force=kind in ('initialize','load'))
                if packet['done'] and kind=='advance':self._maybe_auto_save()
            if packet['done']:
                self._runtime_completed.pop(token,None)
                if kind=='save':
                    self._save_pending=False
                    if not packet.get('error'):
                        self._last_auto_save_year=packet['result'];self.status.configure(text=f'已背景存檔｜世界第 {packet["result"]} 年')
                if kind=='export' and not packet.get('error'):messagebox.showinfo('診斷分析包',f'已匯出：{packet["result"]}')
                if packet.get('error'):
                    if kind=='save':
                        self._save_retry_after=time.perf_counter()+5.
                        self.status.configure(text='背景存檔失敗（稍後重試）：'+packet['error'])
                    else:
                        if kind in ('initialize','advance','load'):
                            self.running=False
                            if hasattr(self,'run_button'):self.run_button.configure(text='繼續')
                        messagebox.showerror('背景作業失敗',packet['error'])
                if kind=='close':self._raster.stop();self.root.destroy();return
        self.war_busy=bool(self._runtime_pending)
        if self.war and self._panel_year!=self.war.year and time.perf_counter()-self._last_ui_refresh>=.25:
            self.refresh_panels();self._panel_year=self.war.year;self._last_ui_refresh=time.perf_counter()
        self._request_raster()
        raster=self._raster.poll()
        if raster and raster[0]==self._raster_token:
            _,layer,image,error=raster
            if error:self.status.configure(text='地圖繪製失敗：'+error)
            else:
                self.full_image=image;self._displayed_raster_key=self._requested_raster_key
                self.redraw()
                if not self._map_has_been_fitted:self.root.after_idle(self.fit_world)
                # Screenshots must match the year used for the raster and overlays.
                # Capture only after the queued Tk redraw has completed.
        self.root.after(16,self._poll_runtime)
    def _request_raster(self,force=False):
        if not self.war or self._closing:return
        style=self._selected_visual_style()
        key=(self._world_generation,self.layer_var.get(),style,self.war.visual_revision,self.war.year)
        if self._snapshot_hold and (self._requested_raster_key is None or self._requested_raster_key[-1]!=self.war.year):force=True
        # Base pixels depend on visual_revision, not the year/army movement.
        if not force and self._requested_raster_key and key[:4]==self._requested_raster_key[:4]:return
        now=time.perf_counter()
        if not force and now-self._last_map_refresh<self._runtime_options['MAP_REFRESH_SECONDS']:return
        self._requested_raster_key=key;self._last_map_refresh=now
        self._raster_token=self._raster.request(self.world,(self.layer_var.get(),style) if style is not None else self.layer_var.get(),year=self.war.year)
    def _selected_visual_style(self):
        var=getattr(self,'visual_style_var',None)
        if var is None:return None
        return self._runtime_options['VISUAL_STYLE_CODES'].get(var.get(),'CLASSIC')
    def _visual_style_changed(self,*_args):
        self._request_raster(force=True);self.redraw()
    def _layer_changed(self,*_args):self._request_raster(force=True)
    def redraw(self):
        if self._redraw_pending or self._closing:return
        self._redraw_pending=True;self.root.after(16,self._flush_redraw)
    def _flush_redraw(self):
        self._redraw_pending=False
        if not self._closing:
            self._redraw_now()
            if self._snapshot_hold and self._displayed_raster_key and self._displayed_raster_key[-1]==self.war.year:
                try:self._maybe_save_map_snapshot(force_refresh=False)
                finally:self._snapshot_hold=False
    def _maybe_auto_save(self,force=False):
        o=self._runtime_options
        if not o['AUTO_SAVE_ENABLED'] or not self.war or self._save_pending or self._closing:return
        if not force and time.perf_counter()<self._save_retry_after:return
        year=self.war.year
        if force or self._last_auto_save_year is None or year-self._last_auto_save_year>=max(1,int(o['AUTO_SAVE_EVERY_YEARS'])):
            self._save_pending=True;self._runtime_submit('save',path=o['SAVES_DIR']/'war_state',world=True)
    def save_war(self):
        if not self.war or self._save_pending or self._closing:return
        self._save_pending=True;self._runtime_submit('save',path=self._runtime_options['SAVES_DIR']/'war_state',world=True)
        self.status.configure(text='已排程背景存檔；目前模擬年度完成後執行。')
    def load_war(self):
        if self.war and not self._closing:self._runtime_submit('load',path=self._runtime_options['SAVES_DIR']/'war_state')
    def export_diagnostics(self):
        if self.war and not self._closing:self._runtime_submit('export')
    def _on_close(self):
        if self._closing:return
        self._closing=True;self.running=False
        self.status.configure(text='等待目前作業完成並安全存檔…')
        self._runtime_submit('close',save=self._runtime_options['AUTO_SAVE_ENABLED'],path=self._runtime_options['SAVES_DIR']/'war_state')
