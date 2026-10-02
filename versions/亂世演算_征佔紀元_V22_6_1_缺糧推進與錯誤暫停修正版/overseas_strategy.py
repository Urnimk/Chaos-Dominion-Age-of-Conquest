"""V22: explicit theatre options, paid ports, physical supply voyages and local development.

No country-specific bonuses. All options obey the same resource and transport budgets.
The strategic state schema is versioned independently of the world save schema.
"""
from __future__ import annotations
import math
import numpy as np
from scipy import ndimage
import map_config as cfg
from country_generator import PORT

THEATRE_ACTIONS = ('EXPAND_BEACHHEAD','ATTACK_FRONT','DEFEND_CAPITAL','DEFEND_PORT',
                   'CUT_OFF','REQUEST_REINFORCEMENTS','WAIT_REINFORCEMENTS',
                   'BUILD_SECOND_PORT','ENCIRCLE_CAPITAL','RECOVER_PORT','RETREAT','REDEPLOY')
PHASES = ('HOME_CONTEST','HOME_DEVELOPMENT','EXPLORE','ESTABLISH_PORT',
          'SUPPLY_INTERRUPTED','REINFORCE','CONSOLIDATE','ISLAND_CAMPAIGN','PACIFIED')

class OverseasStrategyMixin:
    def _spatial_indices(self, cid, landmass=None):
        epoch=getattr(self,'_territory_epoch',0)
        if getattr(self,'_indices_epoch',-1)!=epoch:
            self._indices_cache={};self._indices_epoch=epoch
        key=(int(cid),landmass)
        if key not in self._indices_cache:
            mask=self.world.territory==int(cid)
            if landmass is not None: mask &= self.world.continent==int(landmass)
            self._indices_cache[key]=np.flatnonzero(mask)
        return self._indices_cache[key]

    def _telemetry(self,c,event,amount=1):
        counters=c.setdefault('strategy_counters',{})
        counters[event]=int(counters.get(event,0))+int(amount)

    def _site(self,c,lm):
        return next((s for s in c.get('overseas_capitals',[]) if int(s.get('continent_id',-1))==int(lm)),None)

    def _port_valid(self,c,point,lm=None):
        if not point or len(point)!=2:return False
        x,y=map(int,point);h,w=self.world.territory.shape
        return (0<=y<h and 0<=x<w and int(self.world.territory[y,x])==int(c['id'])
                and int(self.world.settlement[y,x])==PORT
                and (lm is None or int(self.world.continent[y,x])==int(lm)))

    def _logistics_port(self,c,site,build=False,second=False):
        """Reading a route NEVER builds or silently changes a lost designated port."""
        lm=int(site.get('continent_id',0));old=site.get('logistics_port')
        if not second and self._port_valid(c,old,lm): return tuple(old)
        if not build:return None
        if not self._can_pay(c,cfg.PORT_COST):return None
        ax,ay=map(int,site['anchor'])
        if not hasattr(self,'_coastal_mask'):
            sea=self.world.terrain<=1
            self._coastal_mask=self._adjacent_land_mask(sea)&~sea
        mask=(self.world.territory==c['id'])&(self.world.continent==lm)&self._coastal_mask
        existing=[p for p in site.get('supply_ports',[]) if self._port_valid(c,p,lm)]
        if old and self._port_valid(c,old,lm) and list(old) not in existing:existing.append(list(old))
        cells=np.argwhere(mask & ((self.world.settlement==0)|(self.world.settlement==PORT)))
        if not len(cells):return None
        dx=np.minimum(abs(cells[:,1]-ax),self.world.settings.width-abs(cells[:,1]-ax))
        distance=np.hypot(cells[:,0]-ay,dx)
        allowed=distance<=cfg.OVERSEAS_PORT_MAX_DISTANCE
        if not old and np.any(allowed & ((cells[:,0]!=ay)|(cells[:,1]!=ax))):
            allowed &= (cells[:,0]!=ay)|(cells[:,1]!=ax)
        if second:
            for px,py in existing:
                dd=np.minimum(abs(cells[:,1]-px),self.world.settings.width-abs(cells[:,1]-px))
                allowed &= np.hypot(cells[:,0]-py,dd)>=cfg.OVERSEAS_SECOND_PORT_MIN_DISTANCE
        cells=cells[allowed];distance=distance[allowed]
        if not len(cells):return None
        py,px=map(int,cells[int(np.argmin(distance))])
        if self.world.settlement[py,px]!=PORT:
            self._pay(c,cfg.PORT_COST);self.world.settlement[py,px]=PORT
            self.building_owner[py,px]=int(c['id'])
            self.world.countries[c['id']-1].setdefault('ports',[]).append([px,py])
            self._telemetry(c,'ports_built')
        if [px,py] not in existing:existing.append([px,py])
        site['supply_ports']=existing
        if not second or not self._port_valid(c,old,lm):site['logistics_port']=[px,py]
        c['ports']=int(np.count_nonzero((self.world.territory==c['id'])&(self.world.settlement==PORT)))
        self.visual_revision+=1;self._build_geography()
        self._log(c['id'],f"海外補給港建設／指定完成：島{lm}，港口({px},{py})；後续增援沿指定航線。")
        return px,py

    def _theatre(self,c,site):
        cid=int(c['id']);lm=int(site['continent_id']);idx=self._spatial_indices(cid,lm)
        pop=int(self.local_population.ravel()[idx].sum());army=int(self.local_soldiers.ravel()[idx].sum())
        owners=np.unique(self.world.territory[self.world.continent==lm])
        enemies=[int(x) for x in owners if x>0 and x!=cid and self.country(int(x))['alive']
                 and not (c['alliance']>0 and self.country(int(x))['alliance']==c['alliance'])]
        enemy_army=sum(self._landmass_soldiers(x,lm) for x in enemies)
        port=self._logistics_port(c,site)
        # Leave a real home reserve; overseas target includes offensive capability and enemy pressure.
        # Reinforcement immigrants enlarge the resident population on arrival.
        # Do not cap the requested force by the tiny pre-arrival beachhead population.
        target=max(int(pop*cfg.OVERSEAS_PEACE_GARRISON_RATIO),
                   int(enemy_army*cfg.OVERSEAS_ENEMY_GARRISON_RATIO) if enemies else 0)
        productivity_bonus=min(cfg.MAX_CITY_FOOD_PRODUCTIVITY_BONUS,int(c.get('cities',0))*cfg.CITY_FOOD_PRODUCTIVITY_BONUS)
        production=float(self.food_yield.ravel()[idx].sum())*cfg.FOOD_PRODUCTION_MULTIPLIER*(1.0+productivity_bonus)
        supply_need=max(0.0,(pop*cfg.FOOD_CONSUMPTION_PER_PERSON-production)*cfg.OVERSEAS_SUPPLY_BUFFER_YEARS-float(site.get('supply_food',0))) if production<pop*cfg.FOOD_CONSUMPTION_PER_PERSON else 0.0
        pacified=self._overseas_landmass_is_pacified(c,lm)
        phase=('ESTABLISH_PORT' if not port and not site.get('logistics_port') else
               'SUPPLY_INTERRUPTED' if not port else
               'REINFORCE' if army<target else
               'ISLAND_CAMPAIGN' if enemies else 'PACIFIED' if pacified else 'CONSOLIDATE')
        return dict(lm=lm,population=pop,army=army,enemies=enemies,enemy_army=enemy_army,
                    target=target,gap=max(0,target-army),supply_need=supply_need,port=port,phase=phase,site=site)

    def _strategic_state_actions(self,cid,colony_available=False):
        c=self.country(cid);pop=max(1,c['population']);ratio=c['soldiers']/pop
        theatres=[self._theatre(c,s) for s in c.get('overseas_capitals',[])]
        priority={'SUPPLY_INTERRUPTED':0,'ESTABLISH_PORT':1,'REINFORCE':2,'ISLAND_CAMPAIGN':3,'CONSOLIDATE':4,'PACIFIED':5}
        focus=min(theatres,key=lambda t:(not bool(t['enemies']), priority[t['phase']], -t['gap'], t['lm'])) if theatres else None
        unified=self._homeland_is_unified(c)
        phase=focus['phase'] if focus else ('EXPLORE' if unified else 'HOME_CONTEST')
        legal=self.legal_targets(cid)
        readiness=min(4,int(ratio/.045));threat=min(4,int((focus['enemy_army']/max(1,focus['army'])) if focus else 0))
        home=self._home_continent_id(c);hi=self._spatial_indices(cid,home)
        control=len(hi)/max(1,int(self._landmass_sizes[home]));exhaustion=c.get('war_exhaustion',0)
        state=(readiness,threat,min(4,int(control*5)),int(bool(colony_available))+2*int(bool(theatres)),
               min(4,sum(x.attacker==cid and x.status=='marching' for x in self.campaigns)),
               min(4,int(exhaustion*5)),PHASES.index(phase),
               (0 if not focus else 1 if not focus['port'] else 2 if c.get('reinforcement_voyage') else 3),
               min(10,int(c.get('territory_cells',0)/max(1,int(self._landmass_sizes.sum()))*10)))
        actions=['REST_AND_REPRODUCE'];biases={}
        resting=self.year<int(c.get('recovery_until_year',0))
        # Defensive/logistics actions remain legal while recovering from combat.
        for t in theatres:
            lm=t['lm'];site=t['site']
            if not t['port']:
                if self._can_pay(c,cfg.PORT_COST):actions.append(f'BUILD_OVERSEAS_PORT:{lm}');biases[f'BUILD_OVERSEAS_PORT:{lm}']=.30
                if site.get('logistics_port') and t['enemies']:actions.append(f'THEATRE:{lm}:RECOVER_PORT')
            else:
                if (t['gap']>=cfg.AI_MIN_ATTACK_SOLDIERS or t['supply_need']>0) and not c.get('reinforcement_voyage'):
                    actions.append('REINFORCE_OVERSEAS');biases['REINFORCE_OVERSEAS']=.25
                if c.get('reinforcement_voyage'):actions.append(f'THEATRE:{lm}:WAIT_REINFORCEMENTS')
                if t['enemies'] and t['army'] < t['enemy_army'] * .3 and not c.get('reinforcement_voyage'):actions.append(f'THEATRE:{lm}:RETREAT')
                if t['enemies']:
                    actions.extend([f'THEATRE:{lm}:DEFEND_CAPITAL',f'THEATRE:{lm}:DEFEND_PORT'])
                    if len([p for p in site.get('supply_ports',[]) if self._port_valid(c,p,lm)])<2:
                        actions.append(f'THEATRE:{lm}:BUILD_SECOND_PORT')
                # 拓荒每年依既有週期被動執行，不把已滿島嶼的空操作放入 AI 動作。
            if t['enemies'] and not resting and t['gap']<cfg.AI_MIN_ATTACK_SOLDIERS and t['army']>t['population']*cfg.MIN_GARRISON_RATIO+cfg.AI_MIN_ATTACK_SOLDIERS:
                actions.extend(f'THEATRE:{lm}:{kind}' for kind in ('ATTACK_FRONT','CUT_OFF','ENCIRCLE_CAPITAL'))
            if t['phase']=='PACIFIED' and colony_available and not resting:actions.append(f'THEATRE:{lm}:REDEPLOY')
        if not resting:
            if colony_available:actions.append('COLONIZE')
            for option in legal:
                lm=option.get('landmass_id');mode=option['mode']
                if mode=='naval' and lm in self._overseas_landmass_ids(c):continue
                if mode=='land' and lm!=home and any(t['lm']==lm and t['gap']>=cfg.AI_MIN_ATTACK_SOLDIERS for t in theatres):continue
                actions.append(f"ATTACK:{option['id']}:{mode}")
        if focus and focus['gap']>=cfg.AI_MIN_ATTACK_SOLDIERS:actions.append(f"THEATRE:{focus['lm']}:REQUEST_REINFORCEMENTS")
        actions=list(dict.fromkeys(actions))
        c['strategic_phase']=phase;c['strategic_focus_island']=focus['lm'] if focus else 0
        # Periodic information-seeking changes policy, never Q values or country resources.
        stalled=self.year-int(c.get('last_strategic_progress_year',self.year))
        if stalled>=cfg.AI_STRATEGIC_REVIEW_YEARS:
            counts=c.get('action_visits',{});probes=[x for x in actions if x!='REST_AND_REPRODUCE' and not x.endswith(('WAIT_REINFORCEMENTS','REQUEST_REINFORCEMENTS'))]
            if probes:
                least=min(int(counts.get(x,0)) for x in probes)
                for x in probes:
                    if int(counts.get(x,0))==least:biases[x]=biases.get(x,0)+cfg.AI_INFORMATION_REVIEW_BIAS
        # Focus the active front before spending decisions rearranging peaceful garrisons.
        preferred=[]
        if focus and focus['enemies']:
            lm=focus['lm']
            if not focus['port']:
                preferred=[f'BUILD_OVERSEAS_PORT:{lm}']
            elif focus['gap']>=cfg.AI_MIN_ATTACK_SOLDIERS or focus['supply_need']>0:
                preferred=['REINFORCE_OVERSEAS'] if not c.get('reinforcement_voyage') else []
            elif not resting:
                preferred=[f'THEATRE:{lm}:{k}' for k in ('ATTACK_FRONT','CUT_OFF','ENCIRCLE_CAPITAL')]
        if not preferred and unified and not resting and self._overseas_expansion_ready(c):
            preferred=[a for a in actions if (a.startswith('ATTACK:') and a.endswith(':naval')) or a=='COLONIZE']
        brain=self.rl_brains[cid]
        idle=[a for a in actions if a=='REST_AND_REPRODUCE' or a.endswith(('DEFEND_CAPITAL','DEFEND_PORT','WAIT_REINFORCEMENTS','EXPAND_BEACHHEAD'))]
        floor=max((brain.value(state,a) for a in idle),default=0.0)+cfg.AI_THEATRE_COMMITMENT_BIAS
        for a in preferred:
            if a in actions:biases[a]=max(biases.get(a,0.0),floor-brain.value(state,a))
        return state,actions,biases

    def _local_growth(self,c,growth):
        """Each valid island receives the same national bonus; food caps still apply."""
        cid=c['id'];home=self._home_continent_id(c)
        sites=[{'anchor':c['capital'],'continent_id':home}]+c.get('overseas_capitals',[])
        fractions=c.setdefault('island_growth_fractions',{})
        if 'growth_fraction' in c:
            fractions.setdefault(str(home),float(c.pop('growth_fraction')))
        productivity_bonus=min(cfg.MAX_CITY_FOOD_PRODUCTIVITY_BONUS,int(c.get('cities',0))*cfg.CITY_FOOD_PRODUCTIVITY_BONUS)
        capacity_factor=cfg.FOOD_PRODUCTION_MULTIPLIER*(1.0+productivity_bonus)/cfg.FOOD_CONSUMPTION_PER_PERSON*cfg.FOOD_GROWTH_RESERVE_RATIO
        all_idx=self._spatial_indices(cid)
        stock_factor=cfg.FOOD_GROWTH_RESERVE_RATIO/(max(1.0,float(cfg.POPULATION_STOCK_SUPPORT_YEARS))*cfg.FOOD_CONSUMPTION_PER_PERSON)
        national_stock=0.0
        valid=[];seen=set()
        for site in sites:
            x,y=map(int,site['anchor']);lm=int(site['continent_id'])
            if lm in seen:continue
            seen.add(lm);idx=self._spatial_indices(cid,lm)
            if not len(idx) or self.world.territory[y,x]!=cid:continue
            pop=int(self.local_population.ravel()[idx].sum())
            # Only food already held at this location supports births; cargo at sea is excluded.
            stock=max(0.0,float(c.get('food',0) if lm==home else site.get('supply_food',0)))
            national_stock+=stock
            room=max(0,int(float(self.food_yield.ravel()[idx].sum())*capacity_factor+stock*stock_factor-pop))
            if lm == home:
                # 本土仍使用國家級成長量；海外則每個陸塊各自獲得發展人口。
                total=max(0.0,float(growth))+float(fractions.get(str(lm),0.0))
            else:
                island_capacity=float(self.food_yield.ravel()[idx].sum()) * cfg.FOOD_PRODUCTION_MULTIPLIER * (1.0+productivity_bonus) / max(0.0001,cfg.FOOD_CONSUMPTION_PER_PERSON)
                bonus=min(float(getattr(cfg,'OVERSEAS_POPULATION_BONUS_CAP',3.0)),
                           max(0.0,island_capacity)/max(1.0,float(cfg.FOOD_CAPACITY_BONUS_PER_PERSON)))
                total=float(getattr(cfg,'OVERSEAS_ANNUAL_POPULATION_GROWTH',10))*(1.0+bonus)+float(fractions.get(str(lm),0.0))
            births=int(total);fractions[str(lm)]=total-births
            if room and births:valid.append((x,y,min(room,births)))
        desired=sum(n for _,_,n in valid)
        if not desired:return 0
        amounts=np.array([n for _,_,n in valid],dtype=np.int64)
        actual=0
        for (x,y,_),n in zip(valid,amounts):
            self.local_population[y,x]+=int(n);actual+=int(n)
        self._telemetry(c,'births',actual);return actual

    def _local_recruits(self,c,annual_rate):
        """Each island drafts its own civilians, with fractional annual carry.

        Soldiers remain part of the population. Land armies still marching on this
        island count toward its ceiling; embarking at sea physically removes residents.
        """
        cid=c['id'];home=self._home_continent_id(c)
        fractions=c.setdefault('island_recruit_fractions',{})
        for lm in sorted({home}|self._overseas_landmass_ids(c)):
            idx=self._spatial_indices(cid,lm)
            pop=int(self.local_population.ravel()[idx].sum())
            army=int(self.local_soldiers.ravel()[idx].sum())
            marching=sum(int(x.soldiers) for x in self.campaigns if x.attacker==cid
                         and x.status=='marching' and x.mode=='land' and int(x.origin_landmass)==lm)
            gap=max(0,int(pop*cfg.LOCAL_RECRUIT_TARGET_RATIO)-army-marching)
            if not gap:
                fractions[str(lm)]=0.0;continue
            amount=max(0.,pop*float(annual_rate))+float(fractions.get(str(lm),0.))
            recruits=min(gap,int(amount));fractions[str(lm)]=amount-int(amount)
            self._add_local_soldiers(cid,lm,recruits)
            actual=int(self.local_soldiers.ravel()[idx].sum())-army
            self._telemetry(c,'local_recruits',actual)
            if lm!=home:self._telemetry(c,'overseas_local_recruits',actual)

    def _reinforce_v22(self,selected_country_ids=None,force=False):
        if not force and self.year%cfg.OVERSEAS_REINFORCEMENT_CHECK_YEARS:return set()
        launched=set()
        for c in self.countries:
            cid=c['id']
            if selected_country_ids is not None and cid not in selected_country_ids:continue
            if not c['alive'] or c.get('reinforcement_voyage') or c['fleet']<1:continue
            home=self._home_continent_id(c);hi=self._spatial_indices(cid,home)
            hp=int(self.local_population.ravel()[hi].sum());ha=self._home_soldiers(cid,home)
            available=max(0,ha-int(hp*cfg.MIN_GARRISON_RATIO))
            ts=[self._theatre(c,s) for s in c.get('overseas_capitals',[])]
            ts=[t for t in ts if t['port'] and (t['gap']>=cfg.AI_MIN_ATTACK_SOLDIERS or t['supply_need']>0)]
            if not ts:continue
            t=max(ts,key=lambda t:(bool(t['enemies']),t['supply_need']>0,t['gap']/max(1,t['target'])));dest=t['port']
            ports=np.argwhere((self.world.territory==cid)&(self.world.continent==home)&(self.world.settlement==PORT))
            if not len(ports):continue
            route=None
            for py,px in sorted(ports.tolist(),key=lambda p:self._wrapped_distance_cells((p[1],p[0]),dest,self.world.settings.width)):
                route=self._sea_route((px,py),dest)
                if route:break
            if not route:continue
            distance=self._route_distance_km(route);years=max(1,math.ceil(distance/cfg.SEA_MARCH_CELLS_PER_YEAR))
            max_people=min(int(hp*(1.-cfg.OVERSEAS_REINFORCEMENT_HOME_MIN_POP_RATIO)),
                           self._transport_population_capacity(c['fleet']))
            ratio=cfg.OVERSEAS_REINFORCEMENT_MAX_ISLAND_POP_RATIO
            amount=min(t['gap'],available,int(ha*.5),self._transport_soldier_capacity(c['fleet']),
                       max(0,int((t['population']+max_people)*ratio)-t['army']))
            def cargo(n):
                people=max(n,math.ceil((t['army']+n)/ratio-t['population'])) if n else 0
                # All passengers eat; include existing island deficit and arriving residents.
                food=t['supply_need']+people*cfg.FOOD_CONSUMPTION_PER_PERSON*(years+cfg.OVERSEAS_SUPPLY_BUFFER_YEARS)
                return people,food
            # Find a fully funded manifest BEFORE taking people, troops, food or ships.
            limit_food=min(c['food'],c['fleet']*cfg.OVERSEAS_FOOD_PER_SHIP)
            low,high=0,max(0,int(amount))
            while low<high:
                mid=(low+high+1)//2;people,food=cargo(mid)
                if people<=max_people and food<=limit_food:low=mid
                else:high=mid-1
            amount=low if low>=cfg.AI_MIN_ATTACK_SOLDIERS else 0
            people,supply=cargo(amount)
            if not amount:supply=min(t['supply_need'],limit_food)
            if amount<=0 and supply<=1e-6:continue
            soldiers=self._take_local_soldiers(cid,home,amount)
            source=(self.world.territory==cid)&(self.world.continent==home)
            # Do not take residents who still serve in the home garrison or land campaigns.
            if soldiers!=amount or people>hp-self._home_soldiers(cid,home):
                self._add_local_soldiers(cid,home,soldiers);continue
            removed=self._remove_population_in_mask(source,people)
            if removed!=people:
                x,y=c['capital'];self.local_population[y,x]+=removed;self._add_local_soldiers(cid,home,soldiers);continue
            ships=max(1,math.ceil(soldiers/cfg.OVERSEAS_SOLDIERS_PER_SHIP),
                      math.ceil(people/cfg.OVERSEAS_POPULATION_PER_SHIP),math.ceil(supply/cfg.OVERSEAS_FOOD_PER_SHIP))
            c['fleet']-=ships;c['food']-=supply
            c['reinforcement_voyage']={'continent_id':t['lm'],'anchor':list(dest),'origin_port':[px,py],
                 'origin_landmass':home,'soldiers':soldiers,'transported_population':people,'fleet':ships,
                 'years_left':years,'total_years':years,'route':route,'route_distance_km':distance,
                 'launched_year':self.year,'supply_food':supply,'embarked_population':True}
            self._telemetry(c,'reinforcements_launched');self._sync_army_totals(cid)
            cargo = f"{soldiers}名士兵、{people-soldiers}名居民、糧食{supply:,.1f}" if soldiers else f"糧食{supply:,.1f}（純補給）"
            self._log(cid,f"{'增援' if soldiers else '補給'}船隊自本島港({px},{py})向指定海外港{dest}運送{cargo}、{ships}艘艦艇，航程{years}年。")
            launched.add(cid)
        return launched

    def _arrive_reinforcements_v22(self):
        for c in self.countries:
            v=c.get('reinforcement_voyage')
            if not v:continue
            if not c['alive']:c['reinforcement_voyage']=None;continue
            lm=int(v['continent_id']);site=self._site(c,lm)
            valid=bool(site and self._port_valid(c,v['anchor'],lm))
            if not valid and not v.get('returning'):
                v['returning']=True;v['years_left']=max(1,self.year-int(v.get('launched_year',self.year)))
                self._telemetry(c,'route_interruptions');self._log(c['id'],'海外港失守或被毀，增援航線中斷，船隊實際返航。')
            v['years_left']=int(v.get('years_left',1))-1
            cost=int(v.get('transported_population',v.get('soldiers',0)))*cfg.FOOD_CONSUMPTION_PER_PERSON
            if float(v.get('supply_food',cost))>=cost:v['supply_food']=float(v.get('supply_food',cost))-cost
            else:
                loss=min(int(v.get('soldiers',0)),max(1,int(int(v.get('soldiers',0))*cfg.SUPPLY_SHORTAGE_ATTRITION)))
                v['soldiers']-=loss
                if v.get('embarked_population'):v['transported_population']=max(0,int(v.get('transported_population',0))-loss)
                self._telemetry(c,'transport_attrition',loss)
            if v['years_left']>0:continue
            target_lm=int(v['origin_landmass']) if v.get('returning') else lm
            point=v.get('origin_port',c['capital']) if v.get('returning') else v['anchor']
            idx=self._spatial_indices(c['id'],target_lm)
            if len(idx):
                x,y=map(int,point)
                if self.world.territory[y,x]!=c['id']:y,x=np.unravel_index(int(idx[0]),self.world.territory.shape)
                if v.get('embarked_population'):self.local_population[y,x]+=int(v.get('transported_population',0))
                self._add_local_soldiers(c['id'],target_lm,int(v['soldiers']),near=(y,x));c['fleet']+=int(v.get('fleet',0))
                if not v.get('returning'):
                    site['supply_food']=float(site.get('supply_food',0))+float(v.get('supply_food',0))
                    site['last_supply_year']=self.year;self._telemetry(c,'reinforcements_arrived');self._telemetry(c,'troop_reinforcements_arrived' if int(v['soldiers'])>0 else 'supply_only_arrivals')
                    troops = int(v['soldiers']); delivered_food = float(v.get('supply_food',0))
                    cargo = f"{troops}名士兵、糧食{delivered_food:,.1f}" if troops else f"糧食{delivered_food:,.1f}（純補給）"
                    self._log(c['id'],f"海外{'增援' if troops else '補給'}抵達指定港{point}，{cargo}送達島{lm}基地。")
                    # Food deliveries earn bounded value proportional to useful net-deficit coverage.
                    deficit = max(0.0, self._theatre(c,site)['supply_need'] + delivered_food)
                    credit = .25 if troops > 0 else .08 * min(1.0, delivered_food / max(1.0, deficit))
                    if credit > 0:self._apply_delayed_rl_credit(c,v,credit,'運兵抵達' if troops else '糧食補給抵達')
                else:
                    self._telemetry(c,'reinforcements_returned');self._log(c['id'],'海外增援目的地失守，部隊完成返航。')
                    self._apply_delayed_rl_credit(c,v,-.2,'補給航線中斷')
            c['reinforcement_voyage']=None;self._sync_army_totals(c['id'])

    def _theatre_action(self,c,action):
        cid=c['id']
        if action.startswith('BUILD_OVERSEAS_PORT:'):
            site=self._site(c,int(action.split(':')[1]));return bool(site and self._logistics_port(c,site,build=True))
        _,lm,kind=action.split(':');lm=int(lm);site=self._site(c,lm)
        if not site:return False
        self._telemetry(c,'tactic_'+kind)
        if kind=='BUILD_SECOND_PORT':return bool(self._logistics_port(c,site,build=True,second=True))
        if kind=='REQUEST_REINFORCEMENTS':
            site['reinforcement_requested_year']=self.year
            return cid in self._reinforce_v22({cid},True)
        if kind=='WAIT_REINFORCEMENTS':return bool(c.get('reinforcement_voyage'))
        if kind=='REDEPLOY':return cid in self._found_overseas_colonies({cid},True)
        if kind=='RETREAT':return self._evacuate_theatre(c,site)
        if kind in ('DEFEND_CAPITAL','DEFEND_PORT'):
            point=site['anchor'] if kind=='DEFEND_CAPITAL' else site.get('logistics_port')
            if not point:return False
            # Reposition a limited garrison inside the SAME island; no extra soldiers.
            amount=min(self._home_soldiers(cid,lm),max(20,int(self._home_soldiers(cid,lm)*.25)))
            moved=self._take_local_soldiers(cid,lm,amount);x,y=map(int,point)
            if self.world.territory[y,x]!=cid:self._add_local_soldiers(cid,lm,moved);return False
            # Local residents cap troop concentration. Remaining soldiers stay on the island.
            room=max(0,int(self.local_population[y,x]-self.local_soldiers[y,x]));placed=min(room,moved)
            self.local_soldiers[y,x]+=placed;self._add_local_soldiers(cid,lm,moved-placed)
            site['defensive_focus']=kind;site['defensive_until']=self.year+cfg.OVERSEAS_DEFENSE_DURATION
            return moved>0
        if kind=='EXPAND_BEACHHEAD':
            return self._expand_theatre(c,lm)
        if kind in ('ATTACK_FRONT','CUT_OFF','ENCIRCLE_CAPITAL','RECOVER_PORT'):
            targets=[x for x in self.legal_targets(cid) if x['mode']=='land' and x.get('landmass_id')==lm]
            if not targets:return False
            target=min(targets,key=lambda x:self._home_soldiers(x['id'],lm))
            self._selected_theatre=(cid,lm,kind)
            try:return self.launch_campaign(cid,target['id'],'land') is not None
            finally:self._selected_theatre=None
        return False

    def _expand_theatre(self,c,lm):
        owned=(self.world.territory==c['id'])&(self.world.continent==lm)
        neutral=(self.world.territory==0)&(self.world.continent==lm)&(self.world.terrain>=2)&(self.world.movement_cost<255)
        cells=np.argwhere(neutral&self._adjacent_land_mask(owned))
        amount=min(len(cells),cfg.BASE_EXPANSION_CELLS+int(c.get('frontier_level',0)),
                   int(c['food']/cfg.EXPANSION_FOOD_COST_PER_CELL),int(c['timber']/cfg.EXPANSION_TIMBER_COST_PER_CELL))
        if amount<=0:return False
        score=self.world.city_value[cells[:,0],cells[:,1]];cells=cells[np.argsort(score)[-amount:]]
        moved=self._move_settlers(c['id'],cells)
        if not moved:return False
        cells=cells[:moved];self.world.territory[cells[:,0],cells[:,1]]=c['id']
        c['food']-=moved*cfg.EXPANSION_FOOD_COST_PER_CELL;c['timber']-=moved*cfg.EXPANSION_TIMBER_COST_PER_CELL
        self._mark_world_changed(c['id']);self._build_geography();
        from war_engine import _border_mask
        self.world.border=_border_mask(self.world.territory)
        self._telemetry(c,'theatre_expansion_cells',moved)
        return True

    def _evacuate_theatre(self,c,site):
        """Evacuation uses a controlled port and a timed voyage, never teleportation."""
        lm=int(site['continent_id']);port=self._logistics_port(c,site)
        if not port:
            # An isolated army must recover/build a port before it can be evacuated.
            return False
        if c.get('reinforcement_voyage'):return False
        home=self._home_continent_id(c);ports=np.argwhere((self.world.territory==c['id'])&(self.world.continent==home)&(self.world.settlement==PORT))
        if not len(ports):return False
        py,px=map(int,ports[0]);route=self._sea_route(port,(px,py))
        if not route:return False
        idx=self._spatial_indices(c['id'],lm);people=min(int(self.local_population.ravel()[idx].sum()),self._transport_population_capacity(c['fleet']))
        if people<=0:return False
        army=self._take_local_soldiers(c['id'],lm,min(people,self._home_soldiers(c['id'],lm)))
        mask=(self.world.territory==c['id'])&(self.world.continent==lm);people=self._remove_population_in_mask(mask,people)
        ships=max(1,math.ceil(people/cfg.OVERSEAS_POPULATION_PER_SHIP));distance=self._route_distance_km(route);years=max(1,math.ceil(distance/cfg.SEA_MARCH_CELLS_PER_YEAR))
        food=people*cfg.FOOD_CONSUMPTION_PER_PERSON*years
        # Full cost checked before execution by rollback if insufficient.
        if c['food']<food:
            x,y=site['anchor'];self.local_population[y,x]+=people;self._add_local_soldiers(c['id'],lm,army);return False
        c['food']-=food;c['fleet']-=ships
        c['reinforcement_voyage']={'continent_id':lm,'anchor':list(port),'origin_port':[px,py],'origin_landmass':home,
            'returning':True,'embarked_population':True,'transported_population':people,'soldiers':army,'fleet':ships,
            'years_left':years,'total_years':years,'launched_year':self.year,'route':route,'supply_food':food}
        self.world.territory[mask]=0;self.world.settlement[mask]=0;self.building_owner[mask]=0;self.local_population[mask]=0;self.local_soldiers[mask]=0
        c['overseas_capitals']=[s for s in c['overseas_capitals'] if int(s['continent_id'])!=lm]
        c['colonies']=[s for s in c['colonies'] if int(s.get('continent_id',-1))!=lm]
        self._mark_world_changed(c['id']);self._build_geography();self._telemetry(c,'evacuations');return True

    def _strategic_reward(self,before,after,action):
        if not after.get('alive'):return -4.
        # Bounded stocks eliminate the old infinite reward from accumulating food forever.
        land_gain=after['world_control_share']-before.get('world_control_share',0)
        pop_change=math.log1p(after['population'])-math.log1p(before['population'])
        reward=40*land_gain+.15*pop_change
        reward+=.15*(after['wars_won']-before['wars_won'])-.25*(after['wars_lost']-before['wars_lost'])
        reward+=.2*(before.get('war_exhaustion',0)-after.get('war_exhaustion',0))
        reward+=cfg.AI_RL_GAMMA*after.get('strategic_potential',0)-before.get('strategic_potential',0)
        if after.get('world_control_share',0)>=.999 and before.get('world_control_share',0)<.999:reward+=4
        return float(np.clip(reward,-4,4))

    def _theatre_year(self):
        for c in self.countries:
            if not c['alive']:continue
            area=c.get('territory_cells',0)
            if area>int(c.get('strategic_high_water',area)):
                c['last_strategic_progress_year']=self.year
            c.setdefault('last_strategic_progress_year',self.year)
            c['strategic_high_water']=max(area,int(c.get('strategic_high_water',area)))
            for site in c.get('overseas_capitals',[]):
                lm=int(site['continent_id']);idx=self._spatial_indices(c['id'],lm)
                if not len(idx):continue
                pop=int(self.local_population.ravel()[idx].sum());army=int(self.local_soldiers.ravel()[idx].sum())
                # Economic production/consumption was already posted exactly once by _economic_year.
                if float(site.get('food_shortfall_this_year',0))>0:
                    site['unsupplied_years']=int(site.get('unsupplied_years',0))+1
                    # Residents stay in theatre while awaiting a real supply/evacuation voyage.
                    # No instantaneous transfer of people or garrison back across the ocean.
                    if site['unsupplied_years']>cfg.OVERSEAS_SUPPLY_GRACE_YEARS:
                        loss=min(army,max(1,int(army*cfg.OVERSEAS_ISOLATION_ATTRITION)))
                        taken=self._take_local_soldiers(c['id'],lm,loss)
                        mask=(self.world.territory==c['id'])&(self.world.continent==lm);removed=self._remove_population_in_mask(mask,taken)
                        self._telemetry(c,'isolated_casualties',removed)
                else:site['unsupplied_years']=0
            # Alliances have a strategic exit; they do not permanently disable the world goal.
            if self.year%cfg.ALLIANCE_STRATEGIC_REVIEW_YEARS==0 and c.get('alliance',0)>0 and self._homeland_is_unified(c):
                rivals=[o for o in self.countries if o['alive'] and o['id']!=c['id']]
                if rivals and all(o['alliance']==c['alliance'] for o in rivals):
                    c['alliance']=0;self._log(c['id'],'全球只剩同盟政權，戰略評估後退出同盟；重新開放外交競爭。')
