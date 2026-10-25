"""One troop budget and defense estimate for task choice, preflight and launch."""
import numpy as np
import map_config as cfg

def defense(e,defender,point):
    c=e.country(defender);lm=int(e.world.continent[point]);army=e._home_soldiers(defender,lm)
    share=max(e._local_garrison_share(c,point),float(np.median(cfg.BATTLE_LEARNED_GARRISON_SHARES)))
    return min(army,max(200,int(army*share)))*c['morale']*e._terrain_defense(point)

def available(e,c,lm):
    return max(0,e._home_soldiers(c['id'],lm)-int(e.world_state_cache.total('population',c['id'],lm)*cfg.MIN_GARRISON_RATIO))

def legal_actions(e,c,defender,point,budget,mode='land'):
    required=defense(e,defender,point)*cfg.AI_OFFENSIVE_SAFETY_RATIO
    strength=max(.01,c['morale']*((1-cfg.AMPHIBIOUS_ATTACK_PENALTY) if mode=='naval' else 1.))
    return [f'ATTACK:{int(round(f*100))}' for f in cfg.TACTICAL_ATTACK_FRACTIONS
            if budget>=cfg.AI_MIN_ATTACK_SOLDIERS and min(budget,max(cfg.AI_MIN_ATTACK_SOLDIERS,int(budget*int(round(f*100))/100)))*strength>=required]

def province_assessment(e,c,enemy,pid,lm):
    points=e.world_state_cache.provinces.frontier(c['id'],enemy,lm).get(pid)
    if points is None or not len(points):return {'feasible':False,'reason':'NO_FRONTIER'}
    if len(points)>96:points=points[np.linspace(0,len(points)-1,96,dtype=int)]
    w=e.world.terrain.shape[1];budget=available(e,c,lm)
    required=min(defense(e,enemy,divmod(int(i),w))*cfg.AI_OFFENSIVE_SAFETY_RATIO for i in points)
    strength=e._theatre_committable(budget)*max(.01,c['morale'])
    return dict(feasible=bool(budget>=cfg.AI_MIN_ATTACK_SOLDIERS and strength>=required),
                reason='FEASIBLE' if strength>=required else 'INSUFFICIENT_COMMITTABLE_FORCE',attack=float(strength),required=float(required))
