"""V23 persistent world strategy. Targets are selected outside Expected SARSA.
The commitment survives tactical phase changes, travel and save/load.
No resources, combat outcomes or map cells are created by this controller.
"""
from __future__ import annotations
import math
import numpy as np
import map_config as cfg
from country_generator import PORT

GOALS = ('UNIFY_HOMELAND', 'PREPARE_OVERSEAS_EXPANSION', 'COLONIZE_LANDMASS',
         'ESTABLISH_OVERSEAS_BASE', 'CONQUER_LANDMASS', 'REINFORCE_THEATRE',
         'PACIFY_LANDMASS', 'DESTROY_RIVAL', 'PREPARE_NEXT_EXPEDITION')

class HierarchicalStrategyMixin:
    def _macro_measure(self,c,lm):
        idx=self._spatial_indices(c['id'],lm) if lm else np.array([],dtype=int)
        owners=set(int(x) for x in np.unique(self.world.territory[self.world.continent==lm]) if x>0) if lm else set()
        rivals=sorted(x for x in owners if x!=c['id'] and self.country(x)['alive'])
        site=self._site(c,lm) if lm else None
        total=max(1,int(self._landmass_sizes[lm])) if 0<lm<len(self._landmass_sizes) else 1
        return {'cells':len(idx),'control':len(idx)/total,'army':int(self.local_soldiers.ravel()[idx].sum()),
                'rivals':rivals,'base':bool(site),'port':bool(site and self._logistics_port(c,site)),
                'pacified':len(idx)/total>=cfg.OVERSEAS_REGION_CONTROL_SHARE_REQUIRED and not rivals}

    def _macro_event(self,c,event,**kw):
        entry={'year':int(self.year),'event':event,**kw}
        c.setdefault('macro_history',[]).append(entry)
        c['macro_history']=c['macro_history'][-500:]
        self._telemetry(c,'macro_'+event.lower())

    def _macro_new_commitment(self,c,lm,kind,target=None):
        n=int(c.get('macro_sequence',0))+1;c['macro_sequence']=n
        m=self._macro_measure(c,lm)
        commit={'id':n,'target_landmass':int(lm),'target_country':target,'kind':kind,
                'started_year':int(self.year),'last_progress_year':int(self.year),
                'best_control':m['control'],'best_army':m['army'],'fewest_rivals':len(m['rivals']),
                'had_base':m['base'],'had_port':m['port'],'status':'ACTIVE'}
        c['strategic_commitment']=commit
        self._macro_event(c,'COMMIT',commitment=n,landmass=lm,kind=kind,target=target)
        return commit

    def _macro_candidates(self,c):
        """Read-only selector score: local force, distance, island size/yield, supply burden."""
        home=self._home_continent_id(c);choices=[];cool=c.get('macro_target_cooldowns',{})
        for lm in sorted(self._overseas_landmass_ids(c)):
            m=self._macro_measure(c,lm)
            if m['pacified'] or int(cool.get(str(lm),0))>self.year:continue
            enemy=sum(self._home_soldiers(x,lm) for x in m['rivals'])
            score=5+m['control']+math.log1p(self._landmass_sizes[lm])/10-math.log1p(enemy/max(1,m['army']))
            choices.append((score,lm,'CONQUER',m['rivals'][0] if m['rivals'] else None))
        # Finish established islands first; preserves progression/expedition-slot rules.
        if choices:return sorted(choices,reverse=True)
        legal=self.legal_targets(c['id']);force=self._home_soldiers(c['id'],home)
        for o in legal:
            lm=int(o['landmass_id'])
            if o['mode']!='naval' or int(cool.get(str(lm),0))>self.year:continue
            budget=self._overseas_population_budget(c,lm)
            if budget['people']<cfg.AI_MIN_ATTACK_SOLDIERS:continue
            local=self._home_soldiers(o['id'],lm);distance=float(o['distance'])
            value=math.log1p(int(self._landmass_sizes[lm]))/4
            relative=math.log1p(force/max(200,local));supply=distance*cfg.SUPPLY_PER_SOLDIER_CELL
            choices.append((value+relative-distance/1000-supply,lm,'CONQUER',o['id']))
        context=self._colony_context();coords=self._colony_candidates(c,context)
        for lm in sorted(set(int(x) for x in self.world.continent[coords[:,0],coords[:,1]])) if len(coords) else []:
            if int(cool.get(str(lm),0))>self.year:continue
            group=coords[self.world.continent[coords[:,0],coords[:,1]]==lm]
            y,x=group[np.argmax(self.world.city_value[group[:,0],group[:,1]])]
            distance=self._wrapped_distance_cells(c['capital'],(int(x),int(y)),self.world.settings.width)
            budget=self._overseas_population_budget(c,lm)
            if budget['people']<=0:continue
            value=math.log1p(budget['capacity'])/5
            choices.append((value-distance/1000,lm,'COLONIZE',None))
        return sorted(choices,reverse=True)

    def _macro_update(self,c):
        c['world_goal']='WORLD_UNIFICATION';home=self._home_continent_id(c)
        unified=self._homeland_is_unified(c);commit=c.get('strategic_commitment')
        # A homeland emergency suspends the overseas commitment, never discards it.
        critical=self._homeland_is_critical(c)
        if commit and commit['target_landmass']!=home and critical:
            if commit['status']!='SUSPENDED':
                commit['status']='SUSPENDED';self._macro_event(c,'SUSPEND',landmass=commit['target_landmass'],reason='HOME_FATAL_THREAT')
            return self._macro_stage(c,'UNIFY_HOMELAND',home,None,'HOME_FATAL_THREAT')
        if commit and commit['status']=='SUSPENDED':
            commit['status']='ACTIVE';commit['last_progress_year']=self.year
            self._macro_event(c,'RESUME',landmass=commit['target_landmass'])
        if not commit:
            # A travelling expedition already is a commitment; migration adopts it.
            voyage=c.get('colonization_voyage')
            naval=next((x for x in self.campaigns if x.attacker==c['id'] and x.mode=='naval' and x.status=='marching'),None)
            if voyage:
                lm=int(voyage.get('continent_id',self.world.continent[voyage['anchor'][1],voyage['anchor'][0]]))
                commit=self._macro_new_commitment(c,lm,'COLONIZE')
            elif naval:
                lm=int(self.world.continent[naval.objective]);commit=self._macro_new_commitment(c,lm,'CONQUER',naval.defender)
            elif not unified:
                commit=self._macro_new_commitment(c,home,'HOME')
            else:
                choices=self._macro_candidates(c)
                if choices:
                    _,lm,kind,target=choices[0];commit=self._macro_new_commitment(c,lm,kind,target)
                else:return self._macro_stage(c,'PREPARE_OVERSEAS_EXPANSION',0,None,'NO_FEASIBLE_TARGET')
        lm=commit['target_landmass'];m=self._macro_measure(c,lm)
        progress=(m['control']>commit['best_control']+1e-6 or len(m['rivals'])<commit['fewest_rivals']
                  or (m['base'] and not commit['had_base']) or (m['port'] and not commit['had_port'])
                  or m['army']>commit['best_army']+cfg.AI_MIN_ATTACK_SOLDIERS)
        if progress:commit['last_progress_year']=self.year
        commit['best_control']=max(commit['best_control'],m['control']);commit['best_army']=max(commit['best_army'],m['army'])
        commit['fewest_rivals']=min(commit['fewest_rivals'],len(m['rivals']))
        travelling=bool(c.get('colonization_voyage') or any(x.attacker==c['id'] and x.status=='marching' and int(self.world.continent[x.objective])==lm for x in self.campaigns))
        reason=None
        if m['pacified']:reason='PACIFIED'
        elif commit['had_base'] and not m['base'] and not m['cells'] and not travelling:reason='BASE_DESTROYED'
        elif lm<=0 or lm>=len(self._landmass_sizes) or self._landmass_sizes[lm]<=0:reason='TARGET_UNREACHABLE'
        elif self.year-commit['last_progress_year']>=cfg.MACRO_STALL_YEARS and not travelling and not c.get('reinforcement_voyage'):reason='LONG_NO_PROGRESS'
        commit['had_base']|=m['base'];commit['had_port']|=m['port']
        if reason:
            if reason=='PACIFIED' and lm not in c.setdefault('macro_completed_islands',[]):
                c['macro_completed_islands'].append(lm)
                c['macro_credit_total']=float(c.get('macro_credit_total',0))+.6
            self._macro_event(c,'COMPLETE' if reason=='PACIFIED' else 'ABORT',commitment=commit['id'],landmass=lm,reason=reason,duration=self.year-commit['started_year'])
            if reason!='PACIFIED':c.setdefault('macro_target_cooldowns',{})[str(lm)]=self.year+cfg.MACRO_RETRY_COOLDOWN_YEARS
            c['strategic_commitment']=None
            return self._macro_stage(c,'PREPARE_NEXT_EXPEDITION',lm,None,reason,m)
        target=commit.get('target_country')
        if target not in m['rivals'] and m['rivals']:
            # Rival changes only within the committed island, after it leaves that island.
            target=min(m['rivals'],key=lambda x:self._home_soldiers(x,lm));commit['target_country']=target
        if lm==home:stage='UNIFY_HOMELAND'
        elif not m['base']:stage='COLONIZE_LANDMASS' if commit['kind']=='COLONIZE' or not m['rivals'] else 'ESTABLISH_OVERSEAS_BASE'
        elif not m['port']:stage='ESTABLISH_OVERSEAS_BASE'
        elif not m['rivals']:stage='PACIFY_LANDMASS'
        else:
            t=self._theatre(c,self._site(c,lm))
            stage='REINFORCE_THEATRE' if t['gap']>=cfg.AI_MIN_ATTACK_SOLDIERS or t['supply_need']>0 else ('DESTROY_RIVAL' if len(m['rivals'])==1 else 'CONQUER_LANDMASS')
        return self._macro_stage(c,stage,lm,target,'PHASE_PROGRESS',m)

    def _macro_stage(self,c,stage,lm,target,reason,m=None):
        previous=c.get('macro_goal',{});commit=c.get('strategic_commitment') or {}
        goal={'goal_type':stage,'target_country':target,'target_landmass':int(lm),
              'started_year':previous.get('started_year',self.year) if previous.get('goal_type')==stage and previous.get('target_landmass')==lm else int(self.year),
              'last_progress_year':commit.get('last_progress_year',self.year),'progress':m or self._macro_measure(c,lm),
              'success_condition':self._macro_success_condition(stage),
              'failure_condition':['BASE_DESTROYED','HOME_FATAL_THREAT','TARGET_UNREACHABLE','LONG_NO_PROGRESS'],
              'switch_reason':reason,'commitment_id':commit.get('id')}
        if previous.get('goal_type')!=stage or previous.get('target_landmass')!=lm:
            self._macro_event(c,'PHASE',goal=stage,landmass=lm,reason=reason)
        c['macro_goal']=goal;c['strategic_focus_island']=int(lm);c['strategic_phase']=stage
        return goal

    @staticmethod
    def _macro_success_condition(stage):
        return {
            'UNIFY_HOMELAND':{'home_control_at_least':.8,'other_home_regimes':0},
            'PREPARE_OVERSEAS_EXPANSION':{'feasible_target_selected':True},
            'COLONIZE_LANDMASS':{'colony_arrived_on_committed_island':True},
            'ESTABLISH_OVERSEAS_BASE':{'overseas_capital':True,'fixed_port':True},
            'CONQUER_LANDMASS':{'other_island_regimes':0},
            'REINFORCE_THEATRE':{'local_force_gap_below_minimum':True,'supply_deficit':0},
            'PACIFY_LANDMASS':{'control_at_least':.8,'other_island_regimes':0},
            'DESTROY_RIVAL':{'target_leaves_committed_island':True},
            'PREPARE_NEXT_EXPEDITION':{'next_commitment_selected':True},
        }[stage]

    def _macro_state_actions(self,cid,colony_available=False):
        c=self.country(cid);g=self._macro_update(c);lm=g['target_landmass'];home=self._home_continent_id(c)
        m=self._macro_measure(c,lm);site=self._site(c,lm);t=self._theatre(c,site) if site else None
        hp=int(self.local_population.ravel()[self._spatial_indices(cid,home)].sum());food_years=c['food']/max(1,hp*cfg.FOOD_CONSUMPTION_PER_PERSON)
        resting=self.year<int(c.get('recovery_until_year',0));bindings={}
        # No Q floor / ATTACK_BIAS. Q chooses only executable tasks inside the commitment.
        if site and not m['port'] and self._can_pay(c,cfg.PORT_COST):bindings['SECURE_SUPPLY']=f'BUILD_OVERSEAS_PORT:{lm}'
        manifest=self._reinforcement_manifest(c,t) if t and t['port'] and not c.get('reinforcement_voyage') else None
        if manifest:bindings['REINFORCE_ACTIVE_THEATRE']='REINFORCE_OVERSEAS'
        if lm and not resting:
            if m['cells']:
                for kind in ('ATTACK_FRONT','CUT_OFF','ENCIRCLE_CAPITAL'):
                    targets=self._viable_theatre_targets(c,lm,kind)
                    if targets:
                        target=next((o for o in targets if o['id']==g.get('target_country')),targets[0])
                        if site:bindings[kind]=f'THEATRE:{lm}:{kind}'
                        else:bindings['ATTACK_HOMELAND']=f"ATTACK:{target['id']}:land"
                if site and self._can_expand_theatre(c,lm):bindings['EXPAND_BEACHHEAD']=f'THEATRE:{lm}:EXPAND_BEACHHEAD'
            elif g['goal_type']=='COLONIZE_LANDMASS' and not c.get('colonization_voyage'):
                coords=self._colony_candidates(c,self._colony_context())
                if len(coords) and np.any(self.world.continent[coords[:,0],coords[:,1]]==lm):bindings['COLONIZE']='COLONIZE'
            else:
                options=[o for o in self.legal_targets(cid) if o['mode']=='naval' and o['landmass_id']==lm]
                options.sort(key=lambda o:(o['id']!=g.get('target_country'),self._home_soldiers(o['id'],lm)))
                for o in options:
                    if self._macro_landing_feasible(c,o):bindings['ATTACK_OVERSEAS']=f"ATTACK:{o['id']}:naval";break
        incoming=any(x.defender==cid and x.status=='marching' and int(self.world.continent[x.objective])==lm for x in self.campaigns)
        if site and incoming:
            bindings['DEFEND_CAPITAL']=f'THEATRE:{lm}:DEFEND_CAPITAL'
            if m['port']:bindings['DEFEND_PORT']=f'THEATRE:{lm}:DEFEND_PORT'
        if site and not bindings and c.get('reinforcement_voyage'):
            bindings['WAIT_FOR_TRANSPORT']=f'THEATRE:{lm}:WAIT_REINFORCEMENTS'
        # Building the first port and funding troop transport are prerequisites.
        if 'SECURE_SUPPLY' in bindings:bindings={'SECURE_SUPPLY':bindings['SECURE_SUPPLY']}
        elif manifest and t and t['supply_need']>0:bindings={'REINFORCE_ACTIVE_THEATRE':'REINFORCE_OVERSEAS'}
        if not bindings or food_years<1 or c.get('war_exhaustion',0)>.5:
            bindings['REST_AND_REPRODUCE']='REST_AND_REPRODUCE'
        # If nothing can execute, REST rebuilds food under the existing 3x rule.
        c['macro_action_bindings']=bindings
        labels=dict(zip(GOALS,('統一本島','準備海外擴張','殖民目標地區','建立海外基地','征服目標地區','增援目前戰區','平定目標地區','清除目標政權據點','準備下一次遠征')))
        place=self.landmass_place_name(lm,c)
        c['strategic_block_reason']=f"中期目標：{labels[g['goal_type']]}｜目標地區：{place}｜已持續{self.year-(c.get('strategic_commitment') or {}).get('started_year',self.year)}年"
        enemy=sum(self._home_soldiers(x,lm) for x in m['rivals'])
        state=(min(4,int(len(self._spatial_indices(cid,home))/max(1,self._landmass_sizes[home])*5)),
               min(4,int(self._home_soldiers(cid,home)/max(1,hp)*20)),min(4,int(c.get('war_exhaustion',0)*5)),
               min(3,sum(x.attacker==cid and x.status=='marching' for x in self.campaigns)),GOALS.index(g['goal_type']),
               min(4,int(m['control']*5)),min(4,int(enemy/max(1,m['army']))),int(m['base'])+int(m['port']),
               min(3,int(food_years)),int(bool(c.get('reinforcement_voyage')))+2*int(bool(c.get('colonization_voyage'))),
               min(3,len(m['rivals'])),min(10,int(c['territory_cells']/max(1,self._landmass_sizes.sum())*10)))
        return state,list(bindings),{}

    def _macro_landing_feasible(self,c,o):
        lm=o['landmass_id'];home=self._home_continent_id(c)
        budget=self._overseas_population_budget(c,lm);people=budget['people']
        if people<=0 or self._transport_population_capacity(c['fleet'])<people:return False
        idx=self._spatial_indices(c['id'],home);pop=int(self.local_population.ravel()[idx].sum())
        available=min(max(0,self._home_soldiers(c['id'],home)-int(pop*cfg.MIN_GARRISON_RATIO)),people,self._transport_soldier_capacity(c['fleet']))
        if available<cfg.AI_MIN_ATTACK_SOLDIERS:return False
        objective=self._objective(c['id'],o['id'],'naval',lm)
        if objective is None:return False
        target=self.country(o['id']);army=self._home_soldiers(target['id'],lm)
        share=max(self._local_garrison_share(target,objective),float(np.median(cfg.BATTLE_LEARNED_GARRISON_SHARES)))
        defense=min(army,max(200,int(army*share)))*target['morale']*self._terrain_defense(objective)
        return available*max(cfg.TACTICAL_ATTACK_FRACTIONS)*c['morale']*(1-cfg.AMPHIBIOUS_ATTACK_PENALTY)>=defense

    def _macro_metrics(self,c,metrics):
        g=c.get('macro_goal',{});lm=g.get('target_landmass',0);m=self._macro_measure(c,lm)
        # Per-island high-water credit, persisted for the life of this country.
        ledger=c.setdefault('macro_credit',{});key=str(lm);old=ledger.setdefault(key,{'control':0.,'base':False,'port':False,'supply':False})
        if not c.get('macro_credit_initialized'):
            for island in self._overseas_landmass_ids(c)|{self._home_continent_id(c)}:
                p=self._macro_measure(c,island);ledger[str(island)]={'control':p['control'],'base':p['base'],'port':p['port'],'supply':False}
            c['macro_credit_initialized']=True;old=ledger.setdefault(key,{'control':0.,'base':False,'port':False,'supply':False})
        gain=2*max(0,m['control']-old['control'])+.25*int(m['base'] and not old['base'])+.25*int(m['port'] and not old['port'])
        # One arrival milestone per island; no points for endlessly circulating boats.
        if self._site(c,lm) and self._site(c,lm).get('last_supply_year',0)>c.get('macro_credit_start_year',self.year) and not old['supply']:
            gain+=.15;old['supply']=True
        c.setdefault('macro_credit_start_year',self.year)
        old['control']=max(old['control'],m['control']);old['base']|=m['base'];old['port']|=m['port']
        c['macro_credit_total']=float(c.get('macro_credit_total',0))+gain
        live={int(o['id']) for o in self.countries if o['alive'] and o['id']!=c['id']}
        seen=set(c.get('macro_seen_rivals',live));paid=set(c.get('macro_elimination_credit',[]))
        newly_dead=seen-live-paid
        c['macro_credit_total']+=.5*len(newly_dead)
        c['macro_seen_rivals']=sorted(seen|live);c['macro_elimination_credit']=sorted(paid|newly_dead)
        metrics.update(macro_credit=c['macro_credit_total'],macro_landmass=lm,macro_control=m['control'],
                       macro_pacified=m['pacified'],macro_remaining=len(m['rivals']))
        return metrics
