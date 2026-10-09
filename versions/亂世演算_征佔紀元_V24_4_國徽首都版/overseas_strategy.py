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
        cid=int(cid);lm=None if landmass is None else int(landmass)
        key=(cid,lm)
        fallback=getattr(self,'_spatial_cache_fallback_epoch',0)
        if lm is None:
            local=getattr(self,'_territory_epoch_by_country',{}).get(cid,0)
        else:
            local=getattr(self,'_territory_epoch_by_country_landmass',{}).get((cid,lm),0)
        version=(fallback,local)
        cached=getattr(self,'_indices_cache',{}).get(key)
        if cached is None or cached[0]!=version:
            mask=self.world.territory==int(cid)
            if lm is not None: mask &= self.world.continent==lm
            self._indices_cache[key]=(version,np.flatnonzero(mask))
        return self._indices_cache[key][1]

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
        snapshot=self._strategic_snapshot_for(c['id'])
        if snapshot is not None:
            return snapshot.get_or_compute(
                ('theatre',int(site['continent_id'])),lambda:self._theatre_uncached(c,site))
        return self._theatre_uncached(c,site)

    def _theatre_uncached(self,c,site):
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

    def _retreat_reason(self,c,site,t=None):
        """Only recent local defensive collapse can authorize abandonment."""
        t=t or self._theatre(c,site)
        if not t['enemies'] or c.get('reinforcement_voyage') or not t['port']:
            return None
        if t['army'] >= t['enemy_army'] * cfg.OVERSEAS_RETREAT_ARMY_RATIO:
            return None
        last=int(site.get('last_defensive_defeat_year',-1000000))
        if not 0 <= self.year-last <= cfg.OVERSEAS_RETREAT_DEFEAT_WINDOW:
            return None
        before=int(site.get('defensive_crisis_start_cells',0))
        now=len(self._spatial_indices(c['id'],t['lm']))
        lost=max(0.0,1.0-now/max(1,before))
        if before<=0 or lost < cfg.OVERSEAS_RETREAT_LAND_LOSS_RATIO:
            return None
        return f"近期同島防守戰敗、領土流失{lost:.0%}，駐軍{t['army']:,}／敵軍{t['enemy_army']:,}"

    def _viable_theatre_targets(self,c,lm,kind='ATTACK_FRONT'):
        """Read-only offensive preflight against one actual objective, not all rivals."""
        if self.year < int(c.get('recovery_until_year',0)):
            return []
        if sum(x.attacker==c['id'] and x.status=='marching' for x in self.campaigns)>=cfg.AI_MAX_ACTIVE_CAMPAIGNS:
            return []
        idx=self._spatial_indices(c['id'],lm)
        available=max(0,self._home_soldiers(c['id'],lm)-int(self.local_population.ravel()[idx].sum()*cfg.MIN_GARRISON_RATIO))
        if available<cfg.AI_MIN_ATTACK_SOLDIERS:return []
        committed=max(min(available,max(cfg.AI_MIN_ATTACK_SOLDIERS,int(available*f))) for f in cfg.TACTICAL_ATTACK_FRACTIONS)
        result=[];previous=getattr(self,'_selected_theatre',None)
        try:
            self._selected_theatre=(c['id'],lm,kind)
            for option in self.legal_targets(c['id']):
                if option['mode']!='land' or option.get('landmass_id')!=lm:continue
                objective=self._objective(c['id'],option['id'],'land',lm)
                if objective is None:continue
                target=self.country(option['id']);army=self._home_soldiers(target['id'],lm)
                share=max(self._local_garrison_share(target,objective),float(np.median(cfg.BATTLE_LEARNED_GARRISON_SHARES)))
                defense=min(army,max(200,int(army*share)))*target['morale']*self._terrain_defense(objective)
                if committed*max(.01,c['morale'])>=defense*cfg.AI_OFFENSIVE_SAFETY_RATIO:
                    result.append((defense,option))
        finally:self._selected_theatre=previous
        return [option for _,option in sorted(result,key=lambda item:item[0])]

    def _can_expand_theatre(self,c,lm):
        owned=(self.world.territory==c['id'])&(self.world.continent==lm)
        free=int(np.maximum(0,self.local_population[owned]-self.local_soldiers[owned]-1).sum())
        army=int(self.local_soldiers[owned].sum());pop=int(self.local_population[owned].sum())
        free+=max(0,army-int(math.ceil(pop*cfg.MIN_GARRISON_RATIO)))
        if free<cfg.SETTLER_POPULATION_PER_CELL or c['food']<cfg.EXPANSION_FOOD_COST_PER_CELL or c['timber']<cfg.EXPANSION_TIMBER_COST_PER_CELL:return False
        neutral=(self.world.territory==0)&(self.world.continent==lm)&(self.world.terrain>=2)&(self.world.movement_cost<255)
        return bool(np.any(neutral&self._adjacent_land_mask(owned)))

    def _strategic_state_actions(self,cid,colony_available=False):
        """Compatibility entry point; V23 policy has no Q-floor attack biases."""
        return self._macro_state_actions(cid,colony_available)

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

    def _reinforcement_manifest(self,c,t):
        if not t or not t['port'] or c.get('reinforcement_voyage') or c['fleet']<1:return None
        if t['gap']<cfg.AI_MIN_ATTACK_SOLDIERS and t['supply_need']<=0:return None
        cid=c['id'];home=self._home_continent_id(c);hi=self._spatial_indices(cid,home)
        hp=int(self.local_population.ravel()[hi].sum());ha=self._home_soldiers(cid,home)
        available=max(0,ha-int(hp*cfg.MIN_GARRISON_RATIO));dest=t['port']
        ports=np.argwhere((self.world.territory==cid)&(self.world.continent==home)&(self.world.settlement==PORT))
        if not len(ports):return None
        route=None
        for py,px in sorted(ports.tolist(),key=lambda p:self._wrapped_distance_cells((p[1],p[0]),dest,self.world.settings.width)):
            route=self._sea_route((px,py),dest)
            if route:break
        if not route:return None
        distance=self._route_distance_km(route);years=max(1,math.ceil(distance/cfg.SEA_MARCH_CELLS_PER_YEAR))
        budget=self._overseas_population_budget(c,t['lm'])
        max_people=min(budget['people'],int(hp*(1.-cfg.OVERSEAS_REINFORCEMENT_HOME_MIN_POP_RATIO)),
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
        if amount<=0 and supply<=1e-6:return None
        if people>hp-ha+amount:return None
        return dict(px=px,py=py,route=route,distance=distance,years=years,budget=budget,amount=amount,people=people,supply=supply,hp=hp,home=home,dest=dest)

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
            focus=c.get('macro_goal',{}).get('target_landmass')
            if focus:ts=[t for t in ts if t['lm']==focus]
            if not ts:continue
            t=max(ts,key=lambda t:(bool(t['enemies']),t['supply_need']>0,t['gap']/max(1,t['target'])));dest=t['port']
            manifest=self._reinforcement_manifest(c,t)
            if not manifest:continue
            px,py,route,distance,years,budget,amount,people,supply,hp,home,dest=(manifest[k] for k in ('px','py','route','distance','years','budget','amount','people','supply','hp','home','dest'))
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
                 'launched_year':self.year,'supply_food':supply,'embarked_population':True,
                 'departure_population_budget':budget}
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
                self._record_overseas_failure(c,lm)
                v['return_reason']='port_lost';v['returning']=True;v['years_left']=max(1,self.year-int(v.get('launched_year',self.year)))
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
            if v.get('returning') and v.get('return_reason') in ('strategic_evacuation','port_lost'):
                self._record_overseas_failure(c,lm)
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
                    self._telemetry(c,'reinforcements_returned')
                    returned_food=max(0.0,float(v.get('supply_food',0)))
                    c['food']+=returned_food
                    reason=v.get('return_reason','legacy_unknown')
                    label={'strategic_evacuation':'海外戰區主動撤離','port_lost':'海外指定補給港失效'}.get(reason,'舊存檔返航（未記錄原因）')
                    self._log(c['id'],f"{label}：{int(v.get('transported_population',0)):,}人（含{int(v['soldiers']):,}名士兵）完成返航，餘糧{returned_food:,.1f}入本島倉。")
                    if reason=='port_lost':self._apply_delayed_rl_credit(c,v,-.2,'補給航線中斷')
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
            targets=self._viable_theatre_targets(c,lm,kind)
            if not targets:return False
            wanted=c.get('macro_goal',{}).get('target_country')
            target=next((o for o in targets if o['id']==wanted),targets[0])
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
        free=int(np.maximum(0,self.local_population[owned]-self.local_soldiers[owned]-1).sum())
        # Peaceful local soldiers may become settlers; no births or overseas transfers.
        if free<len(cells)*cfg.SETTLER_POPULATION_PER_CELL and not self._theatre(c,self._site(c,lm))['enemies']:
            army=int(self.local_soldiers[owned].sum());pop=int(self.local_population[owned].sum())
            demobilize=min(max(0,army-int(math.ceil(pop*cfg.MIN_GARRISON_RATIO))),max(0,len(cells)*cfg.SETTLER_POPULATION_PER_CELL-free))
            released=self._take_local_soldiers(c['id'],lm,demobilize)
            if released:
                self._sync_army_totals(c['id'])
                self._telemetry(c,'settler_demobilizations',released)
                self._log(c['id'],f'和平外島{lm}：{released}名士兵解甲參與拓荒，保留最低駐軍。')
            free=int(np.maximum(0,self.local_population[owned]-self.local_soldiers[owned]-1).sum())
        cells=cells[:free//max(1,int(cfg.SETTLER_POPULATION_PER_CELL))]
        moved=self._move_settlers(c['id'],cells)
        if not moved:return False
        cells=cells[:moved];self.world.territory[cells[:,0],cells[:,1]]=c['id']
        c['food']-=moved*cfg.EXPANSION_FOOD_COST_PER_CELL;c['timber']-=moved*cfg.EXPANSION_TIMBER_COST_PER_CELL
        self._mark_world_changed(c['id'],landmass_ids=(lm,));self._build_geography();
        from war_engine import _border_mask
        self.world.border=_border_mask(self.world.territory)
        self._telemetry(c,'theatre_expansion_cells',moved)
        self._log(c['id'],f'戰略拓荒：島{lm}新增{moved}格領土，推進海外平定。')
        return True

    def _evacuate_theatre(self,c,site):
        """Preflight the entire evacuation before debiting people or releasing land."""
        reason=self._retreat_reason(c,site)
        if not reason:return False
        lm=int(site['continent_id']);port=self._logistics_port(c,site)
        home=self._home_continent_id(c)
        ports=np.argwhere((self.world.territory==c['id'])&(self.world.continent==home)&(self.world.settlement==PORT))
        if lm==home or not len(ports):return False
        route=None
        for py,px in ports:
            route=self._sea_route(port,(int(px),int(py)))
            if route:break
        if not route:return False
        idx=self._spatial_indices(c['id'],lm)
        people=int(self.local_population.ravel()[idx].sum())
        army=self._home_soldiers(c['id'],lm)
        distance=self._route_distance_km(route)
        years=max(1,math.ceil(distance/cfg.SEA_MARCH_CELLS_PER_YEAR))
        transit=people*cfg.FOOD_CONSUMPTION_PER_PERSON*years
        stock=max(0.0,float(site.get('supply_food',0)))
        home_food=max(0.0,transit-stock)
        if (people<=0 or people>self._transport_population_capacity(c['fleet'])
                or army>self._transport_soldier_capacity(c['fleet'])
                or transit>c['fleet']*cfg.OVERSEAS_FOOD_PER_SHIP or home_food>c['food']):
            self._log(c['id'],f"島{lm}撤離暫緩：無法一次安全運送全體{people:,}人及航程糧食，保留居民與領土。")
            return False
        food=min(stock+home_food,c['fleet']*cfg.OVERSEAS_FOOD_PER_SHIP)
        ships=max(1,math.ceil(people/cfg.OVERSEAS_POPULATION_PER_SHIP),
                  math.ceil(army/cfg.OVERSEAS_SOLDIERS_PER_SHIP),math.ceil(food/cfg.OVERSEAS_FOOD_PER_SHIP))
        self._record_overseas_failure(c,lm)
        c['food']-=home_food;c['fleet']-=ships
        c['reinforcement_voyage']={'continent_id':lm,'anchor':list(port),'origin_port':[int(px),int(py)],'origin_landmass':home,
            'returning':True,'return_reason':'strategic_evacuation','embarked_population':True,
            'transported_population':people,'soldiers':army,'fleet':ships,
            'years_left':years,'total_years':years,'launched_year':self.year,
            'route':list(reversed(route)),'supply_food':food}
        # returning voyages store the original outward route; renderer reverses it.
        mask=(self.world.territory==c['id'])&(self.world.continent==lm)
        cells=int(mask.sum())
        self.world.territory[mask]=0;self.world.settlement[mask]=0;self.building_owner[mask]=0
        self.local_population[mask]=0;self.local_soldiers[mask]=0
        c['overseas_capitals']=[s for s in c['overseas_capitals'] if int(s['continent_id'])!=lm]
        c['overseas_capital']=c['overseas_capitals'][0] if c['overseas_capitals'] else None
        c['colonies']=[s for s in c['colonies'] if int(s.get('continent_id',-1))!=lm]
        self._mark_world_changed(c['id'],landmass_ids=(lm,));self._build_geography();self._telemetry(c,'evacuations')
        self._log(c['id'],f"島{lm}主動撤離：{reason}；全體{people:,}人（含{army:,}名士兵）登船，釋出{cells:,}格，返航{years}年；攜糧{food:,.1f}，未能運走糧食{max(0.0,stock+home_food-food):,.1f}。")
        return True

    def _strategic_reward(self,before,after,action):
        if not after.get('alive'):return -4.
        # Bounded stocks eliminate the old infinite reward from accumulating food forever.
        land_gain=after['world_control_share']-before.get('world_control_share',0)
        pop_change=math.log1p(after['population'])-math.log1p(before['population'])
        reward=20*min(0.,land_gain)+.05*pop_change
        reward+=after.get('macro_credit',0)-before.get('macro_credit',0)
        reward-=.25*(after['wars_lost']-before['wars_lost'])
        reward+=.2*(before.get('war_exhaustion',0)-after.get('war_exhaustion',0))
        # No repeatable port/boat rewards; milestone ledger supplies bounded credit.
        if action.endswith(('DEFEND_CAPITAL','DEFEND_PORT','WAIT_REINFORCEMENTS')) and land_gain<=0 and after['wars_won']==before['wars_won']:
            reward-=cfg.AI_IDLE_DEFENSE_PENALTY
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
