"""觀看者呈現；不修改原始診斷與模擬決策。"""
import re
import numpy as np
WORDS={'ATTACK_FRONT':'進攻敵方前線','DEFEND_CAPITAL':'保衛首都','DEFEND_PORT':'保衛港口','RECOVER_PORT':'收復港口','BUILD_PORT':'興建港口','BUILD_BASE':'建設海外基地','REINFORCE_OVERSEAS':'增援海外據點','THEATRE':'戰區','REST':'休養整備','REST_AND_REPRODUCE':'休養並恢復人口','EXPAND_BEACHHEAD':'擴大登陸據點','CUT_OFF':'切斷敵軍連接','ENCIRCLE_CAPITAL':'包圍敵方首都','CONQUER':'奪取省份','CONNECT':'連接己方領土','SECURE_PORT':'控制港口','PACIFY':'清除省內殘敵','REPLAN':'重新評估目標','ATTACK':'發動進攻','DEFEND':'鞏固防守','COLONIZE':'建立殖民據點','REINFORCE':'派遣增援','UNIFY_WORLD':'統一世界'}
def readable(text):
    text=str(text).replace('AI自行整理出戰術：','AI調整作戰順序，計畫依序：').replace('AI決策：','目前行動：').replace('；已執行；','；已開始執行。').replace('；未能執行；','；目前無法執行，原因：')
    return re.sub(r"[A-Z][A-Z_]+",lambda m:WORDS.get(m[0],m[0]),text)
def change(view,c,key):
    year=view.war.year; generation=getattr(view,'_world_generation',0)
    if getattr(view,'_trend_generation',None)!=generation:
        view._trend_generation=generation;view._trend_samples={}
    samples=view._trend_samples.setdefault(c['id'],[])
    if samples and year<samples[-1][0]:samples.clear()
    if not samples or samples[-1][0]!=year:
        samples.append((year,{k:int(c[k]) for k in ('population','soldiers','territory_cells')}))
    while len(samples)>1 and samples[1][0]<=year-100:samples.pop(0)
    age=year-samples[0][0]
    return '｜建立比較基準' if age==0 else f"｜近{age}年 {int(c[key])-samples[0][1][key]:+,}"
def overlay(view,left,top,cw,ch,tw,th):
    notebook=getattr(view,'left_notebook',None)
    if notebook is not None and notebook.select()==str(view.tab_country_overview):return
    e=view.war;cid=getattr(view,'selected_country_id',None)
    if not cid:return
    c=e.country(cid)
    ox,oy=(cw-tw)/2,(ch-th)/2
    def point(x,y):return ox+(x-left)*view.zoom,oy+(y-top)*view.zoom
    task=c.get('province_task') or {};pid=task.get('province_id',0)
    cachekey=(getattr(view,'_world_generation',0),e.year,cid,pid)
    if getattr(view,'_spectator_key',None)!=cachekey:
        own=e.world.territory==cid
        ids=e.world_state_cache.provinces.layout.ids
        masks=[(own,'#fff399',False)]
        if pid:masks.append((ids==pid,'#ff3535',True))
        lines=[]
        for mask,color,target in masks:
            # Extract only boundary edges, never draw interior grid.
            for axis in (0,1):
                diff=np.diff(np.pad(mask,((1,1),(1,1))),axis=axis)
                # Merge contiguous edges into segments to bound Canvas item count.
                rows=diff if axis==0 else diff.T
                for fixed,row in enumerate(rows):
                    points=np.flatnonzero(row)
                    if not len(points):continue
                    breaks=np.flatnonzero(np.diff(points)>1)+1
                    for run in np.split(points,breaks):
                        start,end=int(run[0])-1,int(run[-1])
                        if axis==0:lines.append((start,fixed,end,fixed,color,target))
                        else:lines.append((fixed,start,fixed,end,color,target))
        view._spectator_lines=lines;view._spectator_key=cachekey
    for x,y,x2,y2,color,target in view._spectator_lines:
        a,b=point(x,y);d,f=point(x2,y2)
        if max(a,d)<0 or min(a,d)>cw or max(b,f)<0 or min(b,f)>ch:continue
        view.canvas.create_line(a,b,d,f,fill=color,width=2 if target else 1,tags='spectator')
    for battle in e.campaigns:
        if battle.status!='marching' or battle.attacker!=cid:continue
        a,b=point(*battle.origin);d,f=point(*battle.objective)
        view.canvas.create_line(a,b,d,f,fill='#ff3535',width=2,arrow='last',tags='spectator')
    # view.canvas.create_text(12,12,anchor='nw',text='淡黃：選中國領土｜紅框：目標省（不代表已開戰）｜紅箭頭：進行中軍事行動',fill='#ffbd80',tags='spectator')
