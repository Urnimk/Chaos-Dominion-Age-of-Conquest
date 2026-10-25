"""Persistent provincial operations subordinate to the existing island commitment."""
import numpy as np
import map_config as cfg
from combat_feasibility import province_assessment

TITLES={'CONQUER':'奪取省份','CONNECT':'打通走廊','SECURE_BASE':'鞏固登陸省','SECURE_PORT':'取得港口','PACIFY':'清理殘餘勢力','PREPARE_LANDING':'建立海外立足點','DEVELOP':'擴張本島領土'}

def finish(e,c,task,status,reason):
    task.update(status=status,end_year=int(e.year),end_reason=reason)
    c.setdefault('province_task_history',[]).append(dict(task));c['province_task_history']=c['province_task_history'][-100:]
    e._log(c['id'],f"省份任務{status}：{task.get('name','未定省份')}｜{reason}")
    c['province_task']=None


def progress(e,c,task):
    p=e.world_state_cache.provinces;pid=int(task['province_id']);idx=p.layout.indices[pid];owners=e.world.territory.ravel()[idx]
    owned=owners==c['id'];hostile=np.array([int(v)>0 and int(v)!=c['id'] and not (c['alliance']>0 and e.country(int(v))['alliance']==c['alliance']) for v in np.unique(owners)])
    enemies=[int(v) for v,yes in zip(np.unique(owners),hostile) if yes]
    soldiers=p.totals(pid,'soldiers');enemy=sum(soldiers.get(v,0) for v in enemies);own=soldiers.get(c['id'],0)
    support=sum(p.totals(n,'soldiers').get(c['id'],0) for n in p.layout.neighbors[pid])
    support=min(support,e._theatre_committable(max(0,e._home_soldiers(c['id'],p.layout.islands[pid])-int(e.world_state_cache.total('population',c['id'],p.layout.islands[pid])*cfg.MIN_GARRISON_RATIO))))
    important=np.isin(e.world.settlement.ravel()[idx],(1,3))&np.isin(owners,enemies)
    return dict(owned_cells=int(owned.sum()),control=float(owned.mean()),enemy_army=int(enemy),own_army=int(own),support_army=int(support),hostile_key_sites=int(important.sum()))


def update(e,c,g):
    lm=int(g['target_landmass']);parent=g.get('commitment_id');p=e.world_state_cache.provinces;task=c.get('province_task')
    cooldown=c.setdefault('province_task_cooldowns',{});c['province_task_cooldowns']={k:v for k,v in cooldown.items() if v>e.year};cooldown=c['province_task_cooldowns']
    if task and (task.get('landmass_id')!=lm or task.get('parent_commitment')!=parent):
        finish(e,c,task,'CANCELLED','島嶼戰略變更或本土危機');task=None
    if task:
        pid=int(task['province_id'])
        if pid<=0 or pid>=len(p.layout.indices) or task.get('province_key')!=e.province_labels[pid-1].key:
            finish(e,c,task,'CANCELLED','省界已重建');task=None
    if task:
        m=progress(e,c,task);task['progress']=m
        if m['owned_cells']>task['best_cells']:
            task['best_cells']=m['owned_cells'];task['last_progress_year']=int(e.year)
        complete=m['control']>=cfg.PROVINCE_TASK_CONTROL_REQUIRED and m['hostile_key_sites']==0 and m['enemy_army']<=max(0,(m['own_army']+m['support_army'])*cfg.PROVINCE_TASK_ENEMY_RATIO)
        options=[o for o in e.legal_targets(c['id']) if o['mode']=='land' and o['landmass_id']==lm]
        reachable=any(pid in p.frontier(c['id'],o['id'],lm) for o in options)
        assessment=province_assessment(e,c,task['target_country'],pid,lm) if reachable else {'feasible':False,'reason':'NO_FRONTIER'}
        task['combat_assessment']=assessment
        reason='取得戰略控制，關鍵據點無敵軍佔領' if complete else '前線已不可達' if not reachable else '省內無可行攻擊點，重新評估其他前線省份' if not assessment['feasible'] else '長期未取得土地進展' if e.year-task['last_progress_year']>=cfg.PROVINCE_TASK_STALL_YEARS else None
        if reason:
            cooldown[str(pid)]=int(e.year+cfg.PROVINCE_TASK_RETRY_YEARS)
            finish(e,c,task,'COMPLETED' if complete else 'REPLAN',reason);task=None
    if not task:
        choices={}
        for o in e.legal_targets(c['id']):
            if o['mode']!='land' or int(o['landmass_id'])!=lm:continue
            for pid,points in p.frontier(c['id'],o['id'],lm).items():
                if cooldown.get(str(pid),0)>e.year:continue
                assessment=province_assessment(e,c,o['id'],pid,lm)
                if not assessment['feasible']:continue
                check=progress(e,c,{'province_id':pid})
                if check['control']>=cfg.PROVINCE_TASK_CONTROL_REQUIRED and check['hostile_key_sites']==0 and check['enemy_army']<=(check['own_army']+check['support_army'])*cfg.PROVINCE_TASK_ENEMY_RATIO:continue
                idx=p.layout.indices[pid];owners=e.world.territory.ravel()[idx];control=float(np.mean(owners==c['id']))
                hostile_sites=int(np.count_nonzero(np.isin(e.world.settlement.ravel()[idx],(1,3))&(owners==o['id'])))
                army=p.totals(pid,'soldiers');pressure=army.get(o['id'],0)/max(200,sum(p.totals(n,'soldiers').get(c['id'],0) for n in (pid,)+p.layout.neighbors[pid]))
                friendly_neighbors=sum(np.any(e.world.territory.ravel()[p.layout.indices[n]]==c['id']) for n in p.layout.neighbors[pid])
                score=pressure-.4*hostile_sites-.2*control-.1*min(2,friendly_neighbors)
                candidate=(score,pid,o['id'],control,hostile_sites,friendly_neighbors)
                if pid not in choices or candidate<choices[pid]:choices[pid]=candidate
        if choices:
            _,pid,enemy,control,sites,neighbors=min(choices.values());label=e.province_labels[pid-1]
            kind='SECURE_PORT' if sites else 'CONNECT' if neighbors>=2 else 'PACIFY' if control>=.6 else 'CONQUER'
            task=dict(province_id=pid,province_key=label.key,name=label.name,kind=kind,target_country=enemy,landmass_id=lm,parent_commitment=parent,
                started_year=int(e.year),last_progress_year=int(e.year),best_cells=0,status='ACTIVE',reason='同一戰略島嶼上可達的前線省份；綜合兵力壓力、關鍵據點及友方接壤省區選擇')
            task['progress']=progress(e,c,task);task['best_cells']=task['progress']['owned_cells'];c['province_task']=task
            e._log(c['id'],f"中期省份任務：{TITLES[kind]}「{label.name}」｜長期目標：{e.landmass_place_name(lm,c)}｜{task['reason']}")
    if task:g['target_country']=task['target_country']
    c['long_term_goal']={'kind':'UNIFY_ISLAND','landmass_id':lm,'name':e.landmass_place_name(lm,c) if lm else '評估下一座可行島嶼'}
    return task


def describe(e,c,g,bindings):
    c['province_phase']={'UNIFY_HOMELAND':'本島拓荒／整理前線','COLONIZE_LANDMASS':'殖民目標島','ESTABLISH_OVERSEAS_BASE':'建立基地與港口','REINFORCE_THEATRE':'鞏固基地與補給','PACIFY_LANDMASS':'拓荒與平定島嶼','PREPARE_OVERSEAS_EXPANSION':'尋找可行島嶼','PREPARE_NEXT_EXPEDITION':'準備下一次遠征'}.get(g['goal_type'],'重新評估可達省份')
    task=c.get('province_task');c['province_support_status']='援軍航行中' if c.get('reinforcement_voyage') else '尚無在途援軍'
    attacks=any(k in bindings for k in ('ATTACK_FRONT','CUT_OFF','ENCIRCLE_CAPITAL','ATTACK_HOMELAND','ATTACK_OVERSEAS'))
    reason='可執行進攻' if attacks else '需先取得港口' if 'SECURE_SUPPLY' in bindings else '等待增援或運輸資源' if 'REINFORCE_ACTIVE_THEATRE' in bindings or 'WAIT_FOR_TRANSPORT' in bindings else '尚無可行進攻：檢查兵力、補給、休養或前線通路'
    if not attacks:
        lm=int(g['target_landmass']);pop=e.world_state_cache.total('population',c['id'],lm)
        available=max(0,e._home_soldiers(c['id'],lm)-int(pop*cfg.MIN_GARRISON_RATIO))
        details=[f"當地可用兵力{available}／最低{cfg.AI_MIN_ATTACK_SOLDIERS}"]
        if e.year<int(c.get('recovery_until_year',0)):details.append(f"休養至第{c['recovery_until_year']}年")
        details.append(f"疲乏{c.get('war_exhaustion',0):.0%}")
        reason+='；'+'，'.join(details)
    c['province_block_reason']=reason
    if task:task['block_reason']=reason
    return f"最終：統一世界｜長期：{c['long_term_goal']['name']}｜中期：{TITLES[task['kind']]} {task['name']}（{task['progress']['control']:.0%}）" if task else f"最終：統一世界｜長期：{c['long_term_goal']['name']}｜中期：{c['province_phase']}"
