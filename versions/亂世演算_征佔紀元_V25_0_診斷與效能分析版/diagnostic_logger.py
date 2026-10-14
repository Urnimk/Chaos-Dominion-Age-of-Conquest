"""V25 observational diagnostics. No engine RNG, AI query or cache mutation.

All records live outside game/save state. Disabled hooks do not allocate payloads.
Timers use exclusive nesting; UI is separate from simulation. JSON null means
unmeasured/unsupported, never a fabricated win probability or causal estimate.
"""
from __future__ import annotations
import copy, csv, functools, hashlib, inspect, json, math, os, time, uuid, zipfile
from collections import Counter, defaultdict, deque
from pathlib import Path
import numpy as np
import map_config as cfg

GAME_VERSION='V25'
SCHEMA_VERSION=1
ACTIONS=('ATTACK_HOMELAND','ATTACK_OVERSEAS','ATTACK_FRONT','CUT_OFF','ENCIRCLE_CAPITAL',
         'EXPAND_BEACHHEAD','COLONIZE','REINFORCE_ACTIVE_THEATRE','SECURE_SUPPLY',
         'DEFEND_CAPITAL','DEFEND_PORT','WAIT_FOR_TRANSPORT','REST_AND_REPRODUCE')
BLOCKERS=set('NO_LEGAL_TARGET NO_VIABLE_TARGET TARGET_TOO_STRONG NO_FLEET NO_PORT NO_TRANSPORT_CAPACITY NO_AVAILABLE_ARMY HOME_GARRISON_LOCK FOOD_SHORTAGE SUPPLY_BLOCKED REINFORCEMENT_BLOCKED PORT_LOST EXPEDITION_COOLDOWN RECOVERY_LOCK ALLIANCE_LOCK MACRO_GOAL_STALLED MACRO_GOAL_LOOP TARGET_SWITCHING Q_PREFERS_IDLE Q_PREFERS_DEFENSE REPEATED_FAILED_ATTACK TERRITORY_GAIN_NOT_DURABLE EXCLAVE_LOSS CORRIDOR_CUT NO_PROGRESS_ACTION COLONY_NOT_MATURE FRONT_FORCE_INSUFFICIENT UNKNOWN'.split())
CATEGORIES={'ai':'ENABLE_AI_DECISION_LOG','stagnation':'ENABLE_STAGNATION_LOG','performance':'ENABLE_PERFORMANCE_LOG',
            'war':'ENABLE_WAR_DIAGNOSTIC_LOG','logistics':'ENABLE_LOGISTICS_DIAGNOSTIC_LOG','cache':'ENABLE_CACHE_DIAGNOSTIC_LOG'}
STREAMS={'ai':'ai_decisions','stagnation':'stagnation_events','war':'war_outcomes','logistics':'logistics_events','macro':'macro_events','territory':'territory_events','major':'major_events'}

def plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {str(k):plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,deque)):return [plain(v) for v in value]
    if isinstance(value,(set,frozenset)):return sorted(plain(v) for v in value)
    if isinstance(value,Path):return str(value)
    if isinstance(value,float) and not math.isfinite(value):return None
    if value is None or isinstance(value,(str,int,float,bool)):return value
    return str(value)

class DiagnosticLogger:
    def __init__(self,engine,output=None,level=None):
        self.engine=engine
        self.level=int(getattr(cfg,'DIAGNOSTIC_DETAIL_LEVEL',1) if level is None else level)
        self.flags={k:bool(getattr(cfg,v,False)) for k,v in CATEGORIES.items()}
        self.enabled=self.level>0 and bool(getattr(cfg,'ENABLE_DIAGNOSTIC_LOG',False))
        self.output=Path(output or getattr(cfg,'DIAGNOSTIC_OUTPUT_DIR','diagnostics'))
        self.session=uuid.uuid4().hex
        self.sequence=0;self.current=None;self.last_decision={};self.pending_rewards={}
        self.records={s:deque() for s in STREAMS.values()}
        self.performance=deque();self.history=defaultdict(deque);self.summaries=deque()
        self.global_history=deque();self.major=deque();self.stack=[]
        self.counts=Counter();self.year_counts=Counter();self.cache=defaultdict(Counter)
        self.changed_country_ids=set()
        self.phases=Counter();self.ui_phases=Counter();self.errors=deque(maxlen=30)
        self.buffer_bytes=Counter();self.dropped=Counter();self.campaign_data={};self.voyage_ids={};self.durable=[]
        self.island_stats=defaultdict(Counter)
        self.gains=Counter();self.losses=Counter();self.country_stats=defaultdict(Counter)
        self.observed_gains=defaultdict(dict);self.territory_baseline=None
        self.last_flush=None;self.first_year=None;self.current_year=engine.year;self.last_year=None
        self.health_history=deque(maxlen=20);self.performance_summaries=deque(maxlen=2000)
        self.last_analysis={};self.topology=[];self.year_events=Counter();self.started=0
        self.io_ms=0.;self.seen_world_pacified=set();self.target_runs=defaultdict(list)
        self.captured=set();self.pending_baseline={};self.restored=False;self.in_year=False
        self.arrivals={};self.voyage_decisions={}

    def enabled_for(self,category):
        return self.enabled and self.flags.get(category,category in ('macro','major')) and (category!='ai' or self.level>=2)

    def count(self,name,n=1):
        self.counts[name]+=n;self.year_counts[name]+=n

    def emit(self,stream,event,cid=None,**payload):
        row={'schema_version':SCHEMA_VERSION,'session_id':self.session,'year':int(self.engine.year),'event':event,
             'country_id':cid,**plain(payload)}
        if event=='ARRIVAL_SETTLEMENT':self.arrivals[(cid,'reinforcement_voyage')]=row
        row['_record_bytes']=len(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        q=self.records[stream];q.append(row);self.buffer_bytes[stream]+=row['_record_bytes']
        byte_limit=int(getattr(cfg,'DIAGNOSTIC_MAX_STREAM_MIB',64))*1024*1024
        while q and self.buffer_bytes[stream]>byte_limit:
            removed=q.popleft();self.buffer_bytes[stream]-=removed.get('_record_bytes',0);self.dropped[stream+'_bytes']+=1
        limit=int(getattr(cfg,'DIAGNOSTIC_MAX_RECORDS_PER_STREAM',100000))
        if len(q)>limit:
            removed=q.popleft();self.buffer_bytes[stream]-=removed.get('_record_bytes',0);self.dropped[stream]+=1
        return row

    def observe(self,kind,values,condition=None):
        """Receives existing function locals only; never calls a game query."""
        if not self.enabled:return
        self.count('target_evaluations' if kind in ('landing','defenses','candidate','legal_filter') else 'observations')
        c=values.get('c') or values.get('country') or {}
        fields=('lm','home','local','distance','value','relative','supply','score','enemy','force','available','pop','hp','ha',
                'army','share','defense','objective','max_people','military_room','military_cap','source_food','source_reserve',
                'limit_food','amount','people','years','required','committed','resting','food_years','incoming','budget')
        data={k:plain(values[k]) for k in fields if k in values}
        if 'o' in values:data['option']=plain(values['o'])
        if 'option' in values:data['option']=plain(values['option'])
        if 'target' in values and isinstance(values['target'],dict):data['target_id']=values['target']['id']
        if 'tid' in values:
            data['target_id']=values['tid']
            target=values.get('target') or {}
            data['target_alive']=target.get('alive');data['target_alliance']=target.get('alliance');data['attacker_alliance']=c.get('alliance')
        if kind=='rule_candidate':
            data['candidate']=plain(values.get('scored',[])[-1]) if values.get('scored') else None
            data['components']={k:plain(values[k]) for k in ('ratio','resource_value','naval_bonus','score','target_share') if k in values}
            data['random_component_separately_measured']=False
        if kind=='defenses':data['ranked_defenses']=plain(values.get('_diagnostic_result'))
        if kind=='viable':
            data['viable_options']=plain(values.get('_diagnostic_result'));data['kind']=values.get('kind')
            if not values.get('_diagnostic_result'):
                data['blocker']='RECOVERY_LOCK' if self.engine.year<int(c.get('recovery_until_year',0)) else 'NO_AVAILABLE_ARMY' if values.get('available',cfg.AI_MIN_ATTACK_SOLDIERS)<cfg.AI_MIN_ATTACK_SOLDIERS else 'NO_VIABLE_TARGET'
        if condition:data['rejected_condition']=condition
        if 'lm' in values and c.get('overseas_attack_bans'):
            deadline=int(c['overseas_attack_bans'].get(str(values['lm']),0))
            if self.engine.year<deadline:data['rejection_code']='EXPEDITION_COOLDOWN';data['ban_until']=deadline
        if 'diagnostic_rejection' in values:data['rejection_code']=values['diagnostic_rejection']
        result=values.get('_diagnostic_result')
        if kind=='landing':
            data['feasible']=bool(result);data['estimated_win_probability']=None
            if not result:
                reason='UNKNOWN'
                if 'available' in values and values['available']<cfg.AI_MIN_ATTACK_SOLDIERS:reason='NO_AVAILABLE_ARMY'
                elif values.get('objective','unset') is None:reason='NO_VIABLE_TARGET'
                elif 'defense' in values:reason='TARGET_TOO_STRONG'
                elif c.get('fleet',0)*min(cfg.OVERSEAS_SOLDIERS_PER_SHIP,cfg.OVERSEAS_POPULATION_PER_SHIP)<cfg.AI_MIN_ATTACK_SOLDIERS:reason='NO_TRANSPORT_CAPACITY'
                data['blocker']=reason
        elif kind=='manifest':
            t=values.get('t') or {};data['theatre']=plain({k:t.get(k) for k in ('lm','army','population','target','gap','supply_need','port','reinforcement_block_reason')})
            data['manpower_waterfall']={'country_population':c.get('population'),'country_soldiers':c.get('soldiers'),'source_soldiers':values.get('ha'),'source_population':values.get('hp'),'garrison_reserve':max(0,values.get('ha',0)-values.get('available',0)) if 'ha' in values else None,'available_army':values.get('available'),'ship_troop_capacity':c.get('fleet',0)*cfg.OVERSEAS_SOLDIERS_PER_SHIP,'ship_population_capacity':c.get('fleet',0)*cfg.OVERSEAS_POPULATION_PER_SHIP,'food_budget':values.get('limit_food'),'food_funded_soldiers':values.get('amount'),'actual_embarked':None,'destination_army':t.get('army'),'enemy_island_army':t.get('enemy_army'),'destination_target':t.get('target')}
            data['manifest']=plain({k:result.get(k) for k in ('amount','people','supply','years','distance','home','dest','budget')} if result else None)
            if self.enabled_for('logistics'):self.emit('logistics_events','MANIFEST_EVALUATED',c.get('id'),**data)
        elif kind=='actions':
            data.update(legal_actions=list(values.get('bindings',{})),bindings=plain(values.get('bindings',{})),
                        theatre=plain(values.get('t')),progress=plain(values.get('m')),manifest_available=bool(values.get('manifest')))
            if self.current is not None:self.current['action_filter']=data
        elif kind=='candidate':
            choices=values.get('choices',[]);data['candidate']=plain(choices[-1]) if choices else None
            if '_diagnostic_result' in values:data['ranked_results']=plain(result)
            data['selection_rule']='descending tuple(score, island_id, kind, target_id); established theatres first'
        if self.current is not None and self.enabled_for('ai'):
            if kind not in ('manifest','actions'):self.current['evaluations'].append({'type':kind,**data})
            elif kind=='manifest':self.current['logistics_evaluations'].append(data)
        if kind=='landing' and not result:self.country_stats[c.get('id')]['landing_rejected_'+data['blocker']]+=1

    def begin_decision(self,country):
        self.count('AI_decisions');self.sequence+=1
        cid=country['id'];did=f'{self.session}:{self.sequence}'
        self.last_decision[cid]=did
        self.current={'decision_id':did,'country_id':cid,'country_name':country['name'],'year':self.engine.year,
                      'evaluations':[],'logistics_evaluations':[],'country_before':plain({k:country.get(k) for k in
                      ('population','soldiers','fleet','food','war_exhaustion','territory_cells','ports','alliance','recovery_until_year')}),
                      'start_world_goal':country.get('world_goal'),'macro_before':copy.deepcopy(country.get('macro_goal'))}
        # Capture snapshot only after the game's original call produces it.

    def snapshot(self,snapshot):
        self.count('strategic_snapshots')
        if self.current is not None and self.enabled_for('ai'):self.current['resource_snapshot']=plain(snapshot.values)

    def rl_selection(self,state,actions,values,biases,preferences,epsilon,explore,index,best):
        if self.current is None:return
        self.current['selection']={'state':plain(state),'legal_actions':list(actions),'q_values':dict(zip(actions,plain(values))),
          'biases':{a:float(biases.get(a,0.)) for a in actions},'epsilon':float(epsilon),
          'effective_scores':dict(zip(actions,plain(preferences))),'tie_indices':plain(best),
          'selection_source':'MACRO_COMMITMENT' if len(actions)==1 else 'RL_EXPLORE' if explore else 'RL_EXPLOIT','sampling_source':'RL_EXPLORE' if explore else 'RL_EXPLOIT','chosen_action':actions[index],
          'macro_constraint_source':'MACRO_COMMITMENT','estimated_win_probability':None}

    def complete_decision(self,c,state,actions,biases,policy,action,success,reward):
        row=self.current
        if row is None:return
        cid=c['id'];stats=self.country_stats[cid];stats['decisions']+=1;stats['action:'+policy]+=1;stats['success:'+policy]+=int(success)
        previous=self.pending_rewards.get(cid)
        if previous:
            self.emit('ai_decisions','DELAYED_REWARD',cid,decision_id=previous.rsplit('|',1)[0],raw_reward=reward,credited_action='previous decision') if self.enabled_for('ai') else None
            stats['reward_sum:'+previous.split('|')[-1]]+=reward
            stats['reward_count:'+previous.split('|')[-1]]+=1
        self.pending_rewards[cid]=row['decision_id']+'|'+policy
        # IDs used in causal edges omit the auxiliary action suffix.
        if self.enabled_for('ai'):
            commit=c.get('strategic_commitment') or {};g=c.get('macro_goal') or {};before=row['country_before']
            row.update(world_goal=c.get('world_goal'),macro_goal=plain(g),macro_target=g.get('target_country'),strategic_phase=c.get('strategic_phase'),
              strategic_commitment=plain(commit),commitment_age=self.engine.year-commit.get('started_year',self.engine.year),
              overseas_bases=plain(c.get('overseas_capitals',[])),world_control=before['territory_cells']/max(1,int(self.engine._landmass_sizes.sum())),
              selection_source=row.get('selection',{}).get('selection_source'),current_RL_state=plain(state),legal_actions=list(actions),executed_action=action,chosen_action=policy,success=bool(success),
              next_decision_year=c.get('next_ai_decision_year'),bindings=plain(c.get('macro_action_bindings',{})),
              progress=plain(g.get('progress')),blockers=self.decision_blockers(row,c))
            row['filtered_actions']=[{'action':a,'rejected_reason':('SUPPLY_BLOCKED' if r'SECURE_SUPPLY' not in actions else 'FIRST_PORT_PREREQUISITE') if a in row.get('pre_prerequisite_bindings',{}) else 'MACRO_BINDING_FILTER','evidence':row.get('action_filter'),
              'note':'Not executable in this commitment; exact condition/candidate rejection is in evaluations. No fabricated cause.'}
              for a in ACTIONS if a not in actions]
            self.emit('ai_decisions','STRATEGIC_DECISION',cid,**{k:v for k,v in row.items() if k not in ('year','country_id')})
        if self.enabled_for('war'):self.pending_baseline[row['decision_id']]={'cid':cid,'year':self.engine.year,'action':policy,
                'indices':None,'start_cells':int(c['territory_cells']),'checked':[]}
        self.current=None

    def decision_blockers(self,row,c):
        evidence=[];f=row.get('action_filter',{});snap=row.get('resource_snapshot',{});sel=row.get('selection',{});before=row.get('country_before',{})
        def add(code,**e):evidence.append({'blocker':code,'evidence':plain(e)})
        if before.get('fleet',1)<cfg.OVERSEAS_MIN_FLEET:add('NO_FLEET',fleet=before.get('fleet'),required=cfg.OVERSEAS_MIN_FLEET,scope='naval expedition')
        if before.get('ports')==0:add('NO_PORT',ports=0)
        if before.get('recovery_until_year',0)>self.engine.year:add('RECOVERY_LOCK',until=before['recovery_until_year'])
        if snap.get('available_home_soldiers',cfg.AI_MIN_ATTACK_SOLDIERS)<cfg.AI_MIN_ATTACK_SOLDIERS:
            add('HOME_GARRISON_LOCK' if snap.get('home_soldiers',0)>=cfg.AI_MIN_ATTACK_SOLDIERS else 'NO_AVAILABLE_ARMY',**snap)
        if f.get('food_years',1)<1:add('FOOD_SHORTAGE',food_years=f['food_years'])
        t=f.get('theatre') or {}
        if t.get('gap',0)>0:add('FRONT_FORCE_INSUFFICIENT',army=t.get('army'),target=t.get('target'),gap=t['gap'])
        if t.get('reinforcement_block_reason'):add('REINFORCEMENT_BLOCKED',reason=t['reinforcement_block_reason'])
        if t.get('phase')=='SUPPLY_INTERRUPTED':add('PORT_LOST',phase=t['phase'],port=t.get('port'),site=t.get('site'))
        if t.get('phase')=='ESTABLISH_PORT':add('COLONY_NOT_MATURE',phase=t['phase'],port=t.get('port'))
        for manifest in row.get('logistics_evaluations',[]):
            mt=manifest.get('theatre') or {};reason=mt.get('reinforcement_block_reason')
            codes={'補給港不可用':'NO_PORT','來源基地沒有可用港口':'NO_PORT','沒有可用艦艇':'NO_FLEET','本島可出兵不足':'NO_AVAILABLE_ARMY','人口／運輸容量不足':'NO_TRANSPORT_CAPACITY','糧食或可用運輸資源不足':'FOOD_SHORTAGE' if manifest.get('limit_food',1)>-1 and manifest.get('limit_food',1)<=1e-6 else 'REINFORCEMENT_BLOCKED','本島至戰區沒有有效航線':'SUPPLY_BLOCKED','已有運輸船隊在途':'REINFORCEMENT_BLOCKED'}
            if reason in codes:add(codes[reason],manifest=manifest,scope='observed manifest rejection')
        if t.get('supply_need',0)>0 and f.get('manifest_available') and f.get('legal_actions')==['REINFORCE_ACTIVE_THEATRE']:
            add('SUPPLY_BLOCKED',supply_need=t['supply_need'],exclusive_binding=f['legal_actions'])
        if any(q['attacker']==c['id'] and not q['targets'] for q in row.get('legal_target_queries',[])):add('NO_LEGAL_TARGET',queries=row['legal_target_queries'])
        if any(i.get('ranked_results')==[] for i in row.get('evaluations',[]) if i['type']=='candidate'):add('NO_VIABLE_TARGET',selector='macro_candidates',ranked_results=[])
        if sel.get('legal_actions') and not set(sel['legal_actions']) & {'ATTACK_HOMELAND','ATTACK_OVERSEAS','ATTACK_FRONT','CUT_OFF','ENCIRCLE_CAPITAL','EXPAND_BEACHHEAD','COLONIZE','REINFORCE_ACTIVE_THEATRE','SECURE_SUPPLY'}:
            add('NO_PROGRESS_ACTION',legal_actions=sel.get('legal_actions'),note='No claim that no legal enemy exists; selector may not have been called.')
        if sel.get('selection_source')=='RL_EXPLOIT' and sel.get('chosen_action') in ('REST_AND_REPRODUCE','DEFEND_CAPITAL','DEFEND_PORT'):
            attacks=[a for a in sel.get('legal_actions',[]) if a.startswith('ATTACK') or a in ('CUT_OFF','ENCIRCLE_CAPITAL')]
            if attacks and sel['effective_scores'][sel['chosen_action']]>max(sel['effective_scores'][a] for a in attacks)+1e-12:add('Q_PREFERS_IDLE' if sel['chosen_action']=='REST_AND_REPRODUCE' else 'Q_PREFERS_DEFENSE',selection=sel)
        for item in row.get('evaluations',[]):
            if item.get('blocker'):add(item['blocker'],evaluation=item)
            condition=item.get('rejected_condition','')
            if 'alliance' in condition and item.get('target_id')!=c['id'] and item.get('attacker_alliance',0)>0 and item.get('attacker_alliance')==item.get('target_alliance') and item.get('target_alive'):add('ALLIANCE_LOCK',condition=condition,target=item.get('target_id'))
            if item.get('rejection_code')=='EXPEDITION_COOLDOWN':add('EXPEDITION_COOLDOWN',condition=condition,island=item.get('lm'),until=item.get('ban_until'))
        return evidence or [{'blocker':'UNKNOWN','evidence':{'note':'No observed restriction; do not infer a blocker from territory alone.'}}]

    def macro(self,c,event,payload):
        if not self.flags['stagnation'] and not self.enabled_for('ai'):return
        self.emit('macro_events',event,c['id'],decision_id=self.last_decision.get(c['id']),payload=payload,
                  commitment=copy.deepcopy(c.get('strategic_commitment')),goal=copy.deepcopy(c.get('macro_goal')))
        if event in ('COMMIT','PHASE','COMPLETE','ABORT'):self.country_stats[c['id']]['macro_'+event]+=1
        if event=='COMPLETE':self.emit('major_events','MACRO_COMPLETED',c['id'],payload=payload)

    def push_timer(self,phase):
        self.stack.append([phase,time.perf_counter(),0.])
    def pop_timer(self):
        phase,start,children=self.stack.pop();duration=time.perf_counter()-start
        if self.stack:self.stack[-1][2]+=duration
        ms=max(0.,duration-children)*1000
        if phase.startswith('ui:'):
            if not self.in_year and self.performance and self.performance[-1]['year']==self.engine.year:
                row=self.performance[-1];p=phase[3:];row['ui_phases_ms'][p]=row['ui_phases_ms'].get(p,0.)+ms;row['ui_ms']+=ms
            else:self.ui_phases[phase[3:]]+=ms
        else:self.phases[phase]+=ms

    def begin_year(self):
        self.in_year=True
        if not self.restored:self.restore_history();self.restored=True
        self.current_year=self.engine.year
        if self.first_year is None:self.first_year=self.engine.year
        self.started=time.perf_counter();self.phases=Counter();self.year_counts=Counter();self.year_events=Counter();self.changed_country_ids=set()
        if self.flags['stagnation'] or self.enabled_for('war'):
            if self.territory_baseline is None:self.territory_baseline=self.engine.world.territory.copy()
        if self.flags['stagnation'] and not self.global_history:self.sample_world()
        for x in self.engine.campaigns:
            if x.id not in self.campaign_data and self.enabled_for('war'):self.campaign_started(x,None,adopted=True)

    def campaign_started(self,x,before,adopted=False):
        self.count('campaigns_created' if not adopted else 'campaigns_adopted');self.year_events['campaigns_created']+=int(not adopted)
        self.country_stats[x.attacker]['active_attacks']+=int(not adopted);self.country_stats[x.defender]['passive_attacks']+=int(not adopted)
        if not self.enabled_for('war'):return
        parent=self.campaign_data.get(getattr(x,'reinforcement_for',0),{})
        causal_decision=self.current['decision_id'] if self.current is not None and self.current['country_id']==x.attacker else parent.get('decision_id')
        record={'campaign_id':x.id,'decision_id':causal_decision,'parent_campaign_id':getattr(x,'reinforcement_for',0) or None,'start_year':self.engine.year,'attacker':x.attacker,'defender':x.defender,
                'start_soldiers':x.soldiers,'start_fleet':x.fleet,'start_supply':x.supply,'start_population':before.get('population') if before else None,
                'start_territory':before.get('territory_cells') if before else None,'mode':x.mode,'source_landmass':x.origin_landmass,
                'objective':plain(x.objective),'distance':x.distance,'years':x.years_left,'food_consumed':0.,'captured_indices':set(),
                'own_loss_counter_start':self.country_stats[x.attacker]['gross_lost'],
                'adopted_existing_campaign':adopted,'food_consumed_before_observation':None if adopted else 0}
        self.campaign_data[x.id]=record
        self.emit('war_outcomes','CAMPAIGN_STARTED',x.attacker,**{k:v for k,v in record.items() if k!='captured_indices'})

    def battle_finished(self,attackers,before,locals_result=None):
        if not self.enabled_for('war'):return
        for x in attackers:
            r=self.campaign_data.get(x.id)
            if not r:continue
            row={k:v for k,v in r.items() if k!='captured_indices'}
            loc=locals_result or {};country=self.engine.country(x.attacker)
            row.update(end_year=self.engine.year,status=x.status,own_deaths=x.casualties,enemy_deaths=loc.get('defense_losses'),
                 fleet_loss=max(0,r['start_fleet']-x.fleet),gross_territory_captured=len(r['captured_indices']),
                 end_territory=country['territory_cells'],net_territory_gain=country['territory_cells']-r['start_territory'] if r['start_territory'] is not None else None,
                 territory_lost=self.country_stats[x.attacker]['gross_lost']-r.get('own_loss_counter_start',self.country_stats[x.attacker]['gross_lost']),durable_gain_after_20_years=None,durable_gain_after_50_years=None,
                 shared_battle=len(attackers)>1,attribution='capture attributed to owning victor; battle costs per campaign, defender losses shared')
            self.emit('war_outcomes','CAMPAIGN_FINISHED',x.attacker,**row)
            self.country_stats[x.attacker]['war_'+x.status]+=1
            cap=int(getattr(cfg,'DIAGNOSTIC_MAX_DURABLE_CELL_REFERENCES',1000000))
            tracked=sum(len(item['indices']) for item in self.durable if item['indices'] is not None)
            indices=sorted(r['captured_indices']) if tracked+len(r['captured_indices'])<=cap else None
            if indices is None:self.dropped['durable_cell_reference_limit']+=1
            self.durable.append({'year':self.engine.year,'cid':x.attacker,'campaign_id':x.id,'decision_id':r['decision_id'],
                'indices':indices,'gross_captured':len(r['captured_indices']),'checked':[],'own_deaths':x.casualties,'food_consumed':r['food_consumed']})
            self.campaign_data.pop(x.id,None)

    def mutation(self,name,before,context):
        after=self.engine.world.territory
        idx=np.flatnonzero(before.ravel()!=after.ravel())
        if not len(idx):return
        old=before.ravel()[idx];new=after.ravel()[idx]
        self.year_events['territory_changed_cells']+=len(idx)
        for cid in np.unique(np.concatenate((old,new))):
            if cid<=0:continue
            self.changed_country_ids.add(int(cid));self.year_events['countries_with_territory_changes']=len(self.changed_country_ids)
            gain=idx[new==cid];loss=idx[old==cid]
            self.gains[int(cid)]+=len(gain);self.losses[int(cid)]+=len(loss)
            for field,indices in (('gross_gained',gain),('gross_lost',loss)):
                ids,amounts=np.unique(self.engine.world.continent.ravel()[indices],return_counts=True)
                for island,amount in zip(ids,amounts):
                    if island>0:self.island_stats[(int(cid),int(island))][field]+=int(amount)
            self.country_stats[int(cid)]['gross_gained']+=len(gain);self.country_stats[int(cid)]['gross_lost']+=len(loss)
            if len(loss) and self.level>=2 and self.enabled_for('war') and name in ('_capture_area','_capture_nearest_loser_cell'):
                self.corridor_evidence(int(cid),before,after,loss)
            for i in gain:self.observed_gains[int(cid)][int(i)]=self.engine.year
            for i in loss:self.observed_gains[int(cid)].pop(int(i),None)
            if name in ('_cleanup_overseas_exclaves_uncached','_discard_split_fragment'):
                self.country_stats[int(cid)]['exclave_loss']+=len(loss)
            if self.enabled_for('war'):
                self.emit('territory_events','OWNERSHIP_CHANGE',int(cid),cause=name,gross_gained=len(gain),gross_lost=len(loss),
                          decision_id=self.last_decision.get(int(cid)),note='Exact function scope; corridor intent is not inferred.')
        if self.enabled_for('war') and context:
            attackers=context or []
            for x in attackers:
                if x.id in self.campaign_data:self.campaign_data[x.id]['captured_indices'].update(int(i) for i in idx[new==x.attacker])
        # Incremental hook covers this mutation; annual reconciliation catches any others.
        if self.territory_baseline is not None:self.territory_baseline.ravel()[idx]=after.ravel()[idx]

    def country_sample(self,c,territory_counts,land_counts,owner_sets):
        cid=c['id'];home=int(self.engine.world.continent[c['capital'][1],c['capital'][0]])
        # Read immutable arrays only. No _home_continent_id migration side effects.
        ctrl={str(lm):int(counts.get(cid,0))/max(1,int(self.engine._landmass_sizes[lm])) for lm,counts in land_counts.items() if counts.get(cid,0)>0}
        enemies=len(set().union(*(owner_sets.get(int(lm),set()) for lm in ctrl))- {cid}) if ctrl else 0
        stats=self.country_stats[cid];commit=c.get('strategic_commitment') or {};g=c.get('macro_goal') or {}
        row={'year':self.engine.year,'territory':int(territory_counts[cid]) if cid<len(territory_counts) else 0,
             'population':c.get('population',0),'soldiers':c.get('soldiers',0),'fleet':c.get('fleet',0),
             'world_control':c.get('territory_cells',0)/max(1,int(self.engine._landmass_sizes.sum())),
             'home_control':ctrl.get(str(home),0),'island_control':ctrl,
             'island_cells':{str(island):counts.get(cid,0) for island,counts in land_counts.items() if counts.get(cid,0)},
             'island_stats':{str(island):dict(stats) for (owner,island),stats in self.island_stats.items() if owner==cid},'enemies_on_owned_islands':enemies,
             'alive':c['alive'],'stats':dict(stats),'macro_goal':plain(g),'commitment':plain(commit),
             'macro_age':self.engine.year-commit.get('started_year',self.engine.year),'last_real_progress_year':commit.get('last_progress_year'),
             'durable_cells_20':sum(self.engine.year-y>=20 for y in self.observed_gains[cid].values())}
        self.history[cid].append(row)
        for cell,y in list(self.observed_gains[cid].items()):
            if self.engine.year-y>int(getattr(cfg,'DIAGNOSTIC_LOG_RETENTION_YEARS',1000)):self.observed_gains[cid].pop(cell,None)
        return row

    def sample_world(self):
        e=self.engine;t=e.world.territory.ravel();lm=e.world.continent.ravel();n=len(e.countries)+1
        counts=np.bincount(t.astype(np.int32,copy=False),minlength=n)
        # One combined scan, no per-country full map scan for annual histories.
        encoded=lm.astype(np.int64)*n+t
        codes,amounts=np.unique(encoded,return_counts=True)
        pairs=(np.column_stack((codes//n,codes%n)),amounts)
        self.count('diagnostic_full_world_scans')
        land_counts=defaultdict(dict);owners=defaultdict(set)
        for (island,cid),amount in zip(*pairs):
            if island>0 and cid>0:land_counts[int(island)][int(cid)]=int(amount);owners[int(island)].add(int(cid))
        for c in e.countries:self.country_sample(c,counts,land_counts,owners)
        alive=sum(c['alive'] for c in e.countries);largest=max((c['territory_cells'] for c in e.countries if c['alive']),default=0)/max(1,int(e._landmass_sizes.sum()))
        pacified={island for island,o in owners.items() if len(o)==1 and max(land_counts[island].values())/max(1,e._landmass_sizes[island])>=cfg.OVERSEAS_REGION_CONTROL_SHARE_REQUIRED}
        new=pacified-self.seen_world_pacified
        if self.last_year is not None:
            for island in sorted(new):self.emit('major_events','ISLAND_PACIFIED',next(iter(owners[island])),island_id=island)
        self.seen_world_pacified|=pacified
        self.global_history.append({'year':e.year,'alive':alive,'largest_control':largest,'pacified_count':len(self.seen_world_pacified)})
        if alive==1 and (not self.last_year or self.global_history[-2]['alive']!=1):self.emit('major_events','WORLD_SINGLE_SURVIVOR',None,world_control=largest)

    def analyze_stagnation(self):
        e=self.engine;rows=[]
        for c in e.countries:
            h=self.history[c['id']]
            if not h:continue
            now=h[-1];old=next((r for r in reversed(h) if r['year']<=e.year-100),h[0]);long=next((r for r in reversed(h) if r['year']<=e.year-200),None)
            delta={k:now['stats'].get(k,0)-old['stats'].get(k,0) for k in set(now['stats'])|set(old['stats'])}
            decisions=[r for r in self.records['ai_decisions'] if r['event']=='STRATEGIC_DECISION' and r['country_id']==c['id'] and r['year']>old['year']]
            act=Counter({k[7:]:v for k,v in delta.items() if k.startswith('action:') and v})
            total=sum(act.values());entropy=-sum((v/total)*math.log2(v/total) for v in act.values()) if total else None
            blockers=[b for r in decisions for b in r.get('blockers',[])];signals=[]
            net=now['territory']-old['territory'];gross=delta.get('gross_gained',0);loss=delta.get('gross_lost',0)
            if total>=5 and len(act)>0 and max(act.values())/total>=.8:signals.append({'signal':'LOW_DECISION_ENTROPY','evidence':{'counts':dict(act),'entropy_bits':entropy}})
            if gross>=100 and max(0,net)/gross<.1:signals.append({'signal':'LOW_DURABLE_CONQUEST_EFFICIENCY','evidence':{'gross':gross,'net':net}})
            if delta.get('exclave_loss',0)>0:blockers.append({'blocker':'EXCLAVE_LOSS','evidence':{'cells_lost':delta['exclave_loss']}})
            if gross and net<=0:blockers.append({'blocker':'TERRITORY_GAIN_NOT_DURABLE','evidence':{'gross':gross,'net':net}})
            macro=[r for r in self.records['macro_events'] if r['country_id']==c['id'] and r['event']=='COMMIT' and r['year']>e.year-100]
            targets=[r['payload'].get('landmass') for r in macro]
            if len(targets)>=4 and any(targets[i:i+4]==[targets[i],targets[i+1],targets[i],targets[i+1]] and targets[i]!=targets[i+1] for i in range(len(targets)-3)):
                blockers.append({'blocker':'MACRO_GOAL_LOOP','evidence':{'commitments':macro}})
            commit=now['commitment']
            if commit and e.year-commit.get('last_progress_year',e.year)>=500:blockers.append({'blocker':'MACRO_GOAL_STALLED','evidence':commit})
            if len(targets)>=3:blockers.append({'blocker':'TARGET_SWITCHING','evidence':{'targets':targets,'count':len(targets)}})
            failures=[r for r in self.records['war_outcomes'] if r['event']=='CAMPAIGN_FINISHED' and r['country_id']==c['id'] and r.get('status')=='lost' and r['year']>old['year']]
            repeated=Counter(r.get('defender') for r in failures)
            for rival,count in repeated.items():
                if count>=3:blockers.append({'blocker':'REPEATED_FAILED_ATTACK','evidence':{'target':rival,'failures':count}})
            stagnant=bool(c['alive'] and long and now['territory']-long['territory']<=max(2,long['territory']*.005)
                 and now['enemies_on_owned_islands']>=long['enemies_on_owned_islands']
                 and not any(v>long['island_control'].get(k,0)+.01 for k,v in now['island_control'].items()))
            if stagnant:self.emit('stagnation_events','STAGNATION DETECTED',c['id'],baseline_year=long['year'],current=now,baseline=long,blockers=blockers or [{'blocker':'UNKNOWN','evidence':{'history_years':e.year-long['year']}}])
            if len(h) and e.year-h[0]['year']>=300:
                older=next((r for r in reversed(h) if r['year']<=e.year-300),None)
                ranks={k:1+sum(x.get(k,0)>c.get(k,0) for x in e.countries if x['alive']) for k in ('population','soldiers','fleet')}
                if older and max(ranks.values())<=3 and now['world_control']-older['world_control']<=.001:
                    signals.append({'signal':'UNDERPERFORMING_MAJOR_POWER','evidence':{'ranks':ranks,'control_delta':now['world_control']-older['world_control'],'years':300}})
            row={'country_id':c['id'],'name':c['name'],'baseline_year':old['year'],'year':e.year,'observed_years':e.year-old['year'],
                 'territory_before':old['territory'],'territory_now':now['territory'],'gross_territory_gained':gross,'gross_territory_lost':loss,'net_territory_change':net,
                 'durable_territory_gain_20':now['durable_cells_20'],'world_control_change':now['world_control']-old['world_control'],
                 'home_control_change':now['home_control']-old['home_control'],'island_control_before':old['island_control'],'island_control_now':now['island_control'],
                 'enemy_count_change':now['enemies_on_owned_islands']-old['enemies_on_owned_islands'],'events':delta,
                 'macro_goal':now['macro_goal'],'macro_goal_age':now['macro_age'],'last_real_progress_year':now['last_real_progress_year'],
                 'stagnation_detected':stagnant,'blockers':blockers,'signals':signals,'decision_distribution':dict(act),'entropy_bits':entropy,
                 'target_persistence':self.target_persistence(c['id']), 'action_effectiveness':self.action_effectiveness(c['id'])}
            rows.append(row)
        global_stall=None
        older=next((r for r in reversed(self.global_history) if r['year']<=e.year-500),None)
        if older and self.global_history:
            now=self.global_history[-1]
            if now['alive']==older['alive'] and abs(now['largest_control']-older['largest_control'])<=.005 and now['pacified_count']==older['pacified_count']:
                global_stall={'signal':'GLOBAL_STALEMATE','baseline':older,'current':now,'top_5':sorted(rows,key=lambda r:r['territory_now'],reverse=True)[:5]}
                self.emit('major_events','GLOBAL_STALEMATE',None,**global_stall)
        self.last_analysis={'year':e.year,'countries':rows,'global_stalemate':global_stall,'coverage_start_year':self.first_year,
                           'blocker_vocabulary':sorted(BLOCKERS),'note':'Only observed evidence is causal; UNKNOWN remains when unavailable.'}
        self.summaries.append(self.last_analysis)
        if len(self.summaries)>2000:self.summaries.popleft();self.dropped['summary_intervals']+=1

    def target_persistence(self,cid):
        commits=[r for r in self.records['macro_events'] if r['country_id']==cid and r['event']=='COMMIT']
        ends=[r for r in self.records['macro_events'] if r['country_id']==cid and r['event'] in ('ABORT','COMPLETE')]
        return {'completed_or_failed_count':len(ends),'mean_years':float(np.mean([r['payload'].get('duration',0) for r in ends])) if ends else None,
                'unfinished_switch_ratio':sum(r['event']=='ABORT' for r in ends)/len(ends) if ends else None,'observed_commitments':len(commits)}

    def action_effectiveness(self,cid):
        stats=self.country_stats[cid];out={}
        for key,n in stats.items():
            if not key.startswith('action:') or not n:continue
            action=key[7:];dur=[r for r in self.records['war_outcomes'] if r['event']=='ACTION_DURABILITY' and r['country_id']==cid and r.get('action')==action]
            out[action]={'uses':n,'success_rate':stats['success:'+action]/n,'average_delayed_reward':stats['reward_sum:'+action]/max(1,stats['reward_count:'+action]) if stats['reward_count:'+action] else None,
              'mean_20_year_net_territory_gain':float(np.mean([r['net_territory_gain'] for r in dur if r['horizon']==20])) if any(r['horizon']==20 for r in dur) else None,
              'mean_50_year_net_territory_gain':float(np.mean([r['net_territory_gain'] for r in dur if r['horizon']==50])) if any(r['horizon']==50 for r in dur) else None}
        return out

    def durability(self):
        now=self.engine.year;t=self.engine.world.territory.ravel()
        for r in self.durable:
            for horizon in (20,50):
                if horizon not in r['checked'] and now>=r['year']+horizon:
                    cells=sum(t[i]==r['cid'] for i in r['indices']) if r['indices'] is not None else None;r['checked'].append(horizon)
                    self.emit('war_outcomes','DURABLE_GAIN',r['cid'],decision_id=r['decision_id'],campaign_id=r['campaign_id'],horizon=horizon,
                        **{f'durable_gain_after_{horizon}_years':cells},gross_captured=r.get('gross_captured',len(r['indices']) if r['indices'] is not None else None),tracking_truncated=r['indices'] is None,
                        territory_per_1000_deaths=1000*cells/r['own_deaths'] if r['own_deaths'] and cells is not None else None,
                        territory_per_1000_food=1000*cells/r['food_consumed'] if r['food_consumed'] and cells is not None else None,
                        retention_definition='ownership at anniversary; intermediate loss/recapture is visible in territory events')
        self.durable=[r for r in self.durable if len(r['checked'])<2]
        for did,r in list(self.pending_baseline.items()):
            for horizon in (20,50):
                if horizon not in r['checked'] and now>=r['year']+horizon:
                    r['checked'].append(horizon)
                    self.emit('war_outcomes','ACTION_DURABILITY',r['cid'],decision_id=did,action=r['action'],horizon=horizon,
                        net_territory_gain=self.engine.country(r['cid'])['territory_cells']-r['start_cells'],
                        attribution='country change after action; correlation, not exclusive causal credit')
            if len(r['checked'])==2:self.pending_baseline.pop(did,None)

    def topology_sample(self):
        from scipy import ndimage
        e=self.engine;rows=[]
        # Wrap horizontal adjacency explicitly using component union; no game cache is touched.
        for c in e.countries:
            if not c['alive']:continue
            islands={int(e.world.continent[x.objective]) for x in e.campaigns if x.attacker==c['id'] or x.defender==c['id']}
            islands|={int(s['continent_id']) for s in c.get('overseas_capitals',[])}
            for island in sorted(islands):
                coords=np.argwhere(e.world.continent==island)
                if not len(coords):continue
                y0,x0=coords.min(axis=0);y1,x1=coords.max(axis=0)+1
                mask=(e.world.territory[y0:y1,x0:x1]==c['id'])&(e.world.continent[y0:y1,x0:x1]==island)
                labels,num=ndimage.label(mask,structure=np.array([[0,1,0],[1,1,1],[0,1,0]],dtype=int));self.count('diagnostic_ndimage_label_calls')
                parent=list(range(num+1))
                def find(i):
                    while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
                    return i
                if False:  # source simulation uses non-wrapping 4-neighbour components
                    for y in range(mask.shape[0]):
                        if not labels[y,0]:continue
                        for dy in (-1,0,1):
                            if 0<=y+dy<mask.shape[0] and labels[y+dy,-1]:parent[find(int(labels[y,0]))]=find(int(labels[y+dy,-1]))
                sizes=Counter()
                for label,count in enumerate(np.bincount(labels.ravel())):
                    if label:sizes[find(label)]+=int(count)
                cells=int(mask.sum());largest=max(sizes.values(),default=0)
                def connected(point):
                    if point is None:return None
                    x,y=point
                    if not(y0<=y<y1 and x0<=x<x1):return 0
                    label=int(labels[y-y0,x-x0]);return sizes[find(label)] if label else 0
                site=next((s for s in c.get('overseas_capitals',[]) if int(s['continent_id'])==island),None)
                port=(site or {}).get('logistics_port');anchor=(site or {}).get('anchor',c['capital'])
                front=(mask&ndimage.binary_dilation((e.world.territory[y0:y1,x0:x1]>0)&(e.world.territory[y0:y1,x0:x1]!=c['id']),structure=np.ones((3,3)) ))
                front_idx=np.argwhere(front)
                local_army=int(e.local_soldiers[y0:y1,x0:x1][mask].sum());effective=int(e.local_soldiers[y0:y1,x0:x1][front].sum())
                enemy_mask=(e.world.continent==island)&(e.world.territory>0)&(e.world.territory!=c['id'])
                enemy_army=int(e.local_soldiers[enemy_mask].sum())
                historical=next((r for r in reversed(self.history[c['id']]) if r['year']<=e.year-100),self.history[c['id']][0] if self.history[c['id']] else {})
                before_stats=historical.get('island_stats',{}).get(str(island),{})
                current_stats=self.island_stats[(c['id'],island)]
                gross=current_stats['gross_gained']-before_stats.get('gross_gained',0)
                lost=current_stats['gross_lost']-before_stats.get('gross_lost',0)
                durable=sum(e.world.continent.ravel()[cell]==island and e.year-year>=20 for cell,year in self.observed_gains[c['id']].items())
                rows.append({'year':e.year,'country_id':c['id'],'island_id':island,'cells':cells,'gross_cells_gained':gross,'gross_cells_lost':lost,'net_cells_gained':cells-historical.get('island_cells',{}).get(str(island),cells),'durable_cells':durable,'window_start':historical.get('year'),'connected_components':len(sizes),
                  'largest_component_cells':largest,'largest_component_ratio':largest/max(1,cells),'disconnected_cells':cells-largest,
                  'cells_connected_to_capital':connected(anchor),'cells_connected_to_logistics_port':connected(port),
                  'exclave_cells_lost':self.country_stats[c['id']]['exclave_loss'],'corridor_cut_count':self.country_stats[c['id']]['corridor_cuts'],
                  'corridor_note':'Counted only when exact capture deletion increases 4-neighbour components; no inferred intent.',
                  'front_width':len(front_idx),'overseas_total_army':local_army,'effective_front_cell_army':effective,
                  'enemy_island_army':enemy_army,'local_force_ratio':local_army/max(1,enemy_army),
                  'supply_food':(site or {}).get('supply_food'),'last_supply_year':(site or {}).get('last_supply_year'),
                  'effective_front_definition':'soldiers located on owned cells adjacent to enemy; excludes inland/mobile campaign soldiers'})
        self.topology=rows

    def end_year(self):
        self.push_timer('diagnostics')
        if self.territory_baseline is not None:
            self.mutation('annual_unattributed_reconciliation',self.territory_baseline,None)
            np.copyto(self.territory_baseline,self.engine.world.territory)
        if self.flags['stagnation']:self.sample_world()
        if self.enabled_for('war'):self.durability()
        interval=max(1,int(getattr(cfg,'STAGNATION_ANALYSIS_INTERVAL_YEARS',100)))
        if self.flags['stagnation'] and (self.engine.year%interval==0):
            self.analyze_stagnation()
            if self.level>=2:self.topology_sample()
        for c in self.engine.countries:
            if c['alive']:
                self.country_stats[c['id']]['port_observed_years']+=int(bool(c.get('ports')))
                self.country_stats[c['id']]['port_idle_years']+=int(bool(c.get('ports')) and not c.get('reinforcement_voyage') and not c.get('colonization_voyage'))
        self.rotate()
        self.pop_timer()
        total=(time.perf_counter()-self.started)*1000
        accounted=sum(self.phases.values());self.phases['other']+=max(0.,total-accounted)
        if self.enabled_for('performance'):
            self.performance.append({'year':self.engine.year,'simulation_ms':total,'phases_ms':dict(self.phases),'counts':dict(self.year_counts),
                'events':dict(self.year_events),'ui_ms':sum(self.ui_phases.values()),'ui_phases_ms':dict(self.ui_phases)})
            self.ui_phases=Counter()
            if self.engine.year%max(1,int(getattr(cfg,'PERFORMANCE_SUMMARY_INTERVAL_YEARS',1000)))==0:
                self.performance_summaries.append(self.performance_summary());self.health_history.append(self.health())
        self.last_year=self.engine.year;self.in_year=False
        if self.last_flush is None or self.engine.year-self.last_flush>=int(getattr(cfg,'DIAGNOSTIC_FLUSH_INTERVAL_YEARS',20)):self.flush()

    def rotate(self):
        year=self.engine.year;ret=int(getattr(cfg,'DIAGNOSTIC_LOG_RETENTION_YEARS',1000));ai=int(getattr(cfg,'AI_DECISION_LOG_RETENTION_YEARS',100))
        for name,q in self.records.items():
            keep=ai if name=='ai_decisions' else ret
            if name=='major_events':
                limit=int(getattr(cfg,'DIAGNOSTIC_MAX_MAJOR_EVENTS',10000))
                while len(q)>limit:
                    removed=q.popleft();self.buffer_bytes[name]-=removed.get('_record_bytes',0);self.dropped[name]+=1
                continue
            while q and q[0]['year']<=year-keep:
                removed=q.popleft();self.buffer_bytes[name]-=removed.get('_record_bytes',0)
        for q in self.history.values():
            while q and q[0]['year']<year-ret:q.popleft()
        while self.global_history and self.global_history[0]['year']<year-ret:self.global_history.popleft()
        while self.performance and self.performance[0]['year']<=year-ret:self.performance.popleft()

    def performance_summary(self):
        rows=list(self.performance);vals=np.asarray([r['simulation_ms'] for r in rows])
        phases=Counter();counts=Counter();ui=Counter()
        for r in rows:phases.update(r['phases_ms']);counts.update(r['counts']);ui.update(r.get('ui_phases_ms',{}))
        total=float(vals.sum());uitotal=sum(ui.values())
        return {'window_start':rows[0]['year'] if rows else None,'window_end':rows[-1]['year'] if rows else None,'years_observed':len(rows),
          'simulation_total_ms':total,'average_ms':float(vals.mean()) if len(vals) else None,'median_ms':float(np.median(vals)) if len(vals) else None,
          'p95_ms':float(np.percentile(vals,95)) if len(vals) else None,'maximum_ms':float(vals.max()) if len(vals) else None,
          'simulation_phases':{p:{'ms':ms,'percent':100*ms/max(.0001,total)} for p,ms in phases.items()},
          'ui_total_ms':uitotal,'ui_phases':{p:{'ms':ms,'percent_of_ui':100*ms/max(.0001,uitotal)} for p,ms in ui.items()},
          'counts':dict(counts),'write_io_ms_since_session_start':self.io_ms,'timing_definition':'exclusive nested phases; UI excluded from simulation; periodic flush separately timed',
          'health':self.health(),'slow_years':sorted(rows,key=lambda r:r['simulation_ms'],reverse=True)[:int(getattr(cfg,'PERFORMANCE_TOP_SLOW_YEARS',30))]}

    def health(self):
        e=self.engine;cache=getattr(e,'world_state_cache',None)
        rss=None
        try:
            import psutil
            rss=psutil.Process().memory_info().rss
        except ImportError:
            if Path('/proc/self/statm').exists():rss=int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
        sizes={'RSS_bytes':rss,'sea_route_cache':len(getattr(e,'_sea_route_cache',{})),
          'WorldStateCache_entries':len(cache._landmass_owners)+len(cache._country_landmasses) if cache else 0,
          'spatial_index_cache_entries':len(getattr(e,'_indices_cache',{})), 'strategic_snapshot_live_count':int(getattr(e,'_active_strategic_snapshot',None) is not None),
          'strategic_snapshot_count_total':self.counts['strategic_snapshots'],'log_buffer_records':sum(map(len,self.records.values())),'log_serialized_buffer_bytes':sum(self.buffer_bytes.values()),
          'active_campaigns':len(e.campaigns),'voyages':sum(bool(c.get(k)) for c in e.countries for k in ('colonization_voyage','reinforcement_voyage')),
          'event_history_size':len(e.events)+len(e.history_events)+sum(map(len,e.country_events.values())),
          'Q_table_entries':sum(len(b.q_values)+len(b.tactical_q_values) for b in e.rl_brains.values()),
          'retention_dropped':dict(self.dropped)}
        sizes['growth_signals']=[{'structure':k,'previous':self.health_history[-1][k],'current':v,'signal':'GROWING_REVIEW_REQUIRED',
          'unused_history_confirmed':False} for k,v in sizes.items() if k!='growth_signals' and isinstance(v,int) and self.health_history and isinstance(self.health_history[-1].get(k),int) and v>self.health_history[-1][k]*1.25+100]
        return sizes

    def metadata(self):
        e=self.engine
        params={k:plain(v) for k,v in vars(cfg).items() if k.isupper() and isinstance(v,(str,int,float,bool,tuple,list,Path))}
        return {'game_version':GAME_VERSION,'diagnostic_schema_version':SCHEMA_VERSION,'session_id':self.session,'current_year':e.year,
          'seed':e.world.settings.seed,'map_size':[e.world.settings.width,e.world.settings.height],'country_count':len(e.countries),
          'alive_country_count':sum(c['alive'] for c in e.countries),'relevant_map_config_parameters':params,
          'Q_schema_version':'hierarchical_expected_SARSA_12D','save_version':'unchanged V24 save schema',
          'LOG_settings':{'enabled':self.enabled,'detail_level':self.level,'categories':self.flags},'coverage_start_year':self.first_year,
          'limitations':['No computed win probability in original algorithm.','Unobserved pre-session history and old voyage decision IDs are null.',
            'Corridor-cut causality and ship-loss metrics unsupported by source model remain null.','Retention caps and write errors are reported.'],
          'errors':list(self.errors),'dropped_records':dict(self.dropped)}

    def cache_summary(self):
        return {name:{**dict(c),'hit_rate':c['hit']/max(1,c['hit']+c['miss'])} for name,c in self.cache.items()}

    def logistics_summary(self):
        rows=list(self.records['logistics_events']);arr=[r for r in rows if r['event']=='VOYAGE_FINISHED'];sent=[r for r in rows if r['event']=='VOYAGE_STARTED']
        return {'window_years':getattr(cfg,'DIAGNOSTIC_LOG_RETENTION_YEARS',1000),'dispatches':len(sent),'resolved':len(arr),
          'arrival_success_rate':sum(bool(r.get('delivered')) for r in arr)/len(arr) if arr else None,
          'fleet_capacity_utilization_mean':float(np.mean([r['soldier_capacity_utilization'] for r in sent if r.get('soldier_capacity_utilization') is not None])) if any(r.get('soldier_capacity_utilization') is not None for r in sent) else None,
          'countries':{str(cid):{'ports_idle_fraction':s['port_idle_years']/s['port_observed_years'] if s['port_observed_years'] else None,
             'definition':'fraction of observed port-country years with no civilian or reinforcement voyage; land/naval combat use excluded'} for cid,s in self.country_stats.items()},
          'waterfalls':'see logistics_events.jsonl MANIFEST_EVALUATED and VOYAGE_STARTED/FINISHED', 'front_health':self.topology}

    def _write(self,name,value,jsonl=False):
        path=self.output/name;tmp=path.with_suffix(path.suffix+'.tmp')
        with tmp.open('w',encoding='utf-8',newline='') as f:
            if jsonl:
                for row in value:f.write(json.dumps(plain(row),ensure_ascii=False,allow_nan=False)+'\n')
            elif isinstance(value,str):f.write(value)
            else:json.dump(plain(value),f,ensure_ascii=False,indent=2,allow_nan=False)
        os.replace(tmp,path)

    def flush(self):
        if not self.enabled:return None
        start=time.perf_counter()
        try:
            self.output.mkdir(parents=True,exist_ok=True)
            self.rotate()
            for name,rows in self.records.items():self._write(name+'.jsonl',rows,True)
            self._write('diagnostic_state.json',self.state_payload());self._write('game_metadata.json',self.metadata());self._write('stagnation_summary.json',self.last_analysis)
            self._write('stagnation_intervals.jsonl',self.summaries,True)
            perf=self.performance_summary();self._write('performance_summary.json',perf)
            self._write('performance_intervals.jsonl',self.performance_summaries,True)
            self._write('slow_years.json',perf['slow_years']);self._write('cache_summary.json',self.cache_summary())
            self._write('logistics_summary.json',self.logistics_summary())
            rows=list(self.performance);phases=sorted({p for r in rows for p in r['phases_ms']})
            path=self.output/'performance_recent_1000y.csv';tmp=path.with_suffix('.csv.tmp')
            with tmp.open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['year','simulation_ms','ui_ms']+phases+['counts_json','events_json']);w.writeheader()
                for r in rows:w.writerow({'year':r['year'],'simulation_ms':r['simulation_ms'],'ui_ms':r.get('ui_ms',0),**r['phases_ms'],
                  'counts_json':json.dumps(r['counts'],ensure_ascii=False),'events_json':json.dumps(r['events'],ensure_ascii=False)})
            os.replace(tmp,path)
            text=f'# {GAME_VERSION} 診斷分析包\n\n目前年份：{self.engine.year}；觀察起點：{self.first_year}。\n\n'
            text+='完整決策保留最近 100 年；其他明細保留最近 1000 年。未實測／模型未提供欄位為 null。\n\n'
            text+=f'決策紀錄：{len(self.records["ai_decisions"])}；戰役紀錄：{len(self.records["war_outcomes"])}；效能年份：{len(self.performance)}。\n\n'
            text+='停滯國家：'+', '.join(r['name'] for r in self.last_analysis.get('countries',[]) if r['stagnation_detected'])+'\n\n'
            text+='請一併提供同年份 saves、遊戲 ZIP、重現步驟；未滿 200／500 年不會臆測國家／世界停滯。\n'
            if self.errors:text+='\n寫檔錯誤：'+repr(list(self.errors))+'\n'
            if self.dropped:text+='\n容量上限造成截斷：'+repr(dict(self.dropped))+'\n'
            self._write('diagnostic_summary.md',text)
            self.last_flush=self.engine.year
        except (OSError,ValueError,TypeError) as exc:self.errors.append({'year':self.engine.year,'error':repr(exc)})
        self.io_ms+=(time.perf_counter()-start)*1000
        return self.output

    def export(self,path=None):
        if not self.enabled:raise RuntimeError('診斷未開啟；請先啟用參數並重新啟動。無法補造過去決策。')
        if self.flags['stagnation']:self.analyze_stagnation()
        self.flush()
        if any('error' in x for x in self.errors):raise RuntimeError('診斷寫檔失敗：'+str(self.errors[-1]))
        target=Path(path or self.output.parent/'diagnostic_package.zip');target.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(self.output.iterdir()):
                if p.suffix in ('.json','.jsonl','.csv','.md') and p.name!='diagnostic_state.json':z.write(p,'diagnostics/'+p.name)
        return target

# Per-method wrappers keep all additional derived observations outside game state.
PHASES={'_economic_year':'population_economy','_construct_building':'buildings','_expand_all_countries':'territory_expansion',
 '_ai_decisions':'AI_decisions','_advance_campaigns':'war_campaigns','_battle':'battle','_theatre_year':'overseas_theatres',
 '_advance_colony_voyages':'colony_voyages','_advance_overseas_reinforcements':'reinforcement_voyages',
 '_reinforce_v22':'reinforcement_dispatch','_cleanup_overseas_exclaves':'territory_connectivity',
 '_check_territorial_splits':'territory_splits','_check_power_splits':'power_splits','_check_colony_independence':'colony_independence',
 '_refresh_survival':'survival','_build_geography':'geography','_refresh_land_totals':'world_totals',
 '_sea_route':'pathfinding','_sea_route_uncached':'sea_route_A_star','_territory_components':'connectivity_components',
 '_ensure_all_country_brains':'brains','_finalize_extinct_rl_brains':'RL_terminal','_update_monarchs':'monarchs','save':'autosave_or_manual_save'}
MUTATIONS={'_capture_area','_capture_nearest_loser_cell','_cleanup_overseas_exclaves_uncached','_discard_split_fragment','_split_country','_complete_colony_voyage','_expand_theatre','_expand_all_countries','_extinguish_country'}
COUNTS={'_sea_route':'sea_route_calls','_sea_route_uncached':'sea_route_uncached_calls','_build_geography':'build_geography_calls',
 '_reinforcement_manifest':'reinforcement_checks','_construct_building':'building_checks','save':'saves','_refresh_land_totals':'full_world_scans',
 '_territory_components':'connectivity_component_calls','_colony_context_uncached':'full_world_scans'}

def install_engine(cls):
    original_init=cls.__init__
    @functools.wraps(original_init)
    def init(self,*a,**kw):
        original_init(self,*a,**kw)
        self.diagnostics=DiagnosticLogger(self) if getattr(cfg,'ENABLE_DIAGNOSTIC_LOG',False) and getattr(cfg,'DIAGNOSTIC_DETAIL_LEVEL',0)>0 else None
    cls.__init__=init
    methods=set(PHASES)|MUTATIONS|set(COUNTS)|{'launch_campaign','_advance_campaigns','_battle','_macro_event','_macro_stage','_make_strategic_snapshot','_mark_world_changed','_reinforce_v22','_found_overseas_colonies','_arrive_reinforcements_v22','_return_peacetime_surplus','_evacuate_theatre','_macro_measure','_theatre','_colony_context','_spatial_indices','_sea_route','legal_targets','_objective','_cancel_colony_voyage','_complete_colony_voyage'}
    for name in methods:
        original=getattr(cls,name)
        def build(name,original):
            required={'launch_campaign':2,'_battle':1,'_macro_event':2,'_macro_stage':1,'_make_strategic_snapshot':1,'_sea_route':2,'_spatial_indices':1,'legal_targets':1,'_objective':3,'_macro_measure':2,'_theatre':2,'_cancel_colony_voyage':2,'_complete_colony_voyage':2,'_construct_building':1,'_extinguish_country':1}.get(name,0)
            @functools.wraps(original)
            def wrapped(self,*a,**kw):
                d=getattr(self,'diagnostics',None)
                if d is None or not d.enabled:return original(self,*a,**kw)
                original_args=a
                if kw and len(a)<required:
                    bound=inspect.signature(original).bind(self,*a,**kw);bound.apply_defaults()
                    a=tuple(v for k,v in bound.arguments.items() if k!='self')
                timer=d.enabled_for('performance') and name in PHASES
                if timer:d.push_timer(('ui:' if any(x[0].startswith('ui:') for x in d.stack) or not d.in_year else '')+PHASES[name])
                if name in COUNTS:d.count(COUNTS[name])
                observe=(d.flags['stagnation'] or d.enabled_for('war'))
                if name in MUTATIONS and observe and d.territory_baseline is not None:
                    d.mutation('pre_hook_unattributed_reconciliation',d.territory_baseline,None)
                before=self.world.territory.copy() if name in MUTATIONS and observe else None
                old_country=None;old_voyages=None;campaign_before=None
                old_ports=int(a[0].get('ports',0)) if name=='_construct_building' else None
                old_goal=copy.deepcopy(a[0].get('macro_goal')) if name=='_macro_stage' and (d.flags['stagnation'] or d.enabled_for('ai')) else None
                if name=='launch_campaign':old_country=dict(self.country(a[0]))
                if name=='_advance_campaigns' and d.enabled_for('war'):
                    campaign_before={x.id:(x.supply,x.soldiers,x.casualties) for x in self.campaigns}
                if name in ('_reinforce_v22','_found_overseas_colonies','_arrive_reinforcements_v22','_return_peacetime_surplus','_evacuate_theatre','_advance_colony_voyages') and d.enabled_for('logistics'):
                    old_voyages={c['id']:{k:copy.deepcopy(c.get(k)) for k in ('reinforcement_voyage','colonization_voyage')} for c in self.countries}
                if name=='_battle':
                    self._diagnostic_battle_context=a[0];self._diagnostic_battle_locals=None
                if d.enabled_for('cache') and name in ('legal_targets','_macro_measure','_theatre'):
                    snap=getattr(self,'_active_strategic_snapshot',None)
                    cid=a[0] if name=='legal_targets' else a[0]['id']
                    if snap is not None and snap.country_id==cid and snap.year==self.year and snap.territory_epoch==getattr(self,'_territory_epoch',0):
                        key=('legal_targets',int(cid)) if name=='legal_targets' else ('macro_measure',int(a[1])) if name=='_macro_measure' else ('theatre',int(a[1]['continent_id']))
                        hit=key in snap.memo;d.cache['StrategicSnapshot']['hit' if hit else 'miss']+=1;d.cache['StrategicSnapshot']['rebuild']+=int(not hit)
                        d.cache['StrategicSnapshot']['entries']=len(snap.memo)
                if name=='_colony_context' and d.enabled_for('cache'):
                    hit=getattr(self,'_colony_epoch',-1)==getattr(self,'_territory_epoch',0)
                    d.cache['colony_context']['hit' if hit else 'miss']+=1;d.cache['colony_context']['rebuild']+=int(not hit)
                if name=='_sea_route' and d.enabled_for('cache'):
                    key=(tuple(a[0]),tuple(a[1]),int(getattr(self,'_navigation_epoch',0)))
                    hit=key in getattr(self,'_sea_route_cache',{})
                    d.cache['sea_route']['hit' if hit else 'miss']+=1
                    d.count('sea_route_cache_hits' if hit else 'sea_route_cache_misses')
                spatial_hits=None
                if name=='_spatial_indices' and d.enabled_for('cache'):spatial_hits=len(getattr(self,'_indices_cache',{}))
                try:
                    result=original(self,*original_args,**kw)
                    if before is not None:d.mutation(name,d.territory_baseline if d.territory_baseline is not None else before,getattr(self,'_diagnostic_battle_context',None))
                    if old_ports is not None:d.year_events['ports_created']+=max(0,int(a[0].get('ports',0))-old_ports)
                    if name=='launch_campaign' and result:d.campaign_started(result,old_country)
                    if name=='_extinguish_country':d.emit('major_events','COUNTRY_EXTINCT',a[0]['id'],reason=a[2] if len(a)>2 else kw.get('reason'))
                    if name=='_advance_campaigns' and d.enabled_for('war'):
                        active_ids={x.id for x in self.campaigns}
                        for ident,record in list(d.campaign_data.items()):
                            if ident not in active_ids:
                                d.emit('war_outcomes','CAMPAIGN_CANCELLED_OUTSIDE_BATTLE',record['attacker'],campaign_id=ident,decision_id=record['decision_id'],reason='observed campaign removed without battle; inspect survival events')
                                d.campaign_data.pop(ident,None)
                    if name=='_battle':
                        d.battle_finished(a[0],None,getattr(self,'_diagnostic_battle_locals',None));self._diagnostic_battle_context=None
                    if name=='_macro_event':d.macro(a[0],a[1],kw)
                    if name=='_make_strategic_snapshot':d.snapshot(result)
                    if name=='legal_targets' and d.current is not None and d.enabled_for('ai'):
                        d.current.setdefault('legal_target_queries',[]).append({'attacker':a[0],'targets':plain(result)})
                    if name=='_objective' and d.current is not None and d.enabled_for('ai'):
                        d.current.setdefault('objective_queries',[]).append({'attacker':a[0],'defender':a[1],'mode':a[2],'island':a[3] if len(a)>3 else None,'objective':plain(result),'available':result is not None})
                    if name in ('_cancel_colony_voyage','_complete_colony_voyage') and d.enabled_for('logistics'):
                        key=(a[0]['id'],'colonization_voyage')
                        if name=='_cancel_colony_voyage':d.arrivals[key]={'delivered':False,'return_reason':a[2] if len(a)>2 else None}
                        elif key not in d.arrivals:d.arrivals[key]={'delivered':True}
                        d.emit('logistics_events','COLONY_CANCELLED' if name=='_cancel_colony_voyage' else 'COLONY_COMPLETION_EVALUATED',a[0]['id'],voyage_id=d.voyage_ids.get((a[0]['id'],'colonization_voyage')),reason=a[2] if len(a)>2 else None,decision_id=d.last_decision.get(a[0]['id']))
                    if name=='_macro_stage' and d.flags['stagnation']:
                        c=a[0];commit=c.get('strategic_commitment') or {}
                        event='PROGRESSED' if commit.get('last_progress_year')==self.year else 'STALLED' if self.year-commit.get('last_progress_year',self.year)>=cfg.MACRO_STALL_YEARS else 'CONTINUED'
                        d.emit('macro_events',event,c['id'],goal=plain(result),commitment=plain(commit))
                        if old_goal and (old_goal.get('goal_type')!=result['goal_type'] or old_goal.get('target_landmass')!=result['target_landmass']):
                            d.emit('macro_events','SWITCHED',c['id'],old_goal=old_goal,new_goal=plain(result),switch_reason=result.get('switch_reason'),years_committed=self.year-commit.get('started_year',self.year),progress_before_switch=old_goal.get('progress'))
                    if name=='_mark_world_changed' and d.enabled_for('cache'):
                        d.cache['territory_revision']['invalidate']+=1
                        d.cache['territory_revision']['global_invalidate' if kw.get('landmass_ids') is None else 'targeted_invalidate']+=1
                    if name=='_spatial_indices' and spatial_hits is not None:
                        d.cache['spatial_indices']['calls']+=1
                        d.cache['spatial_indices']['entries']=len(self._indices_cache)
                    if old_voyages is not None:
                        _observe_voyages(d,old_voyages)
                    return result
                finally:
                    if timer:d.pop_timer()
            return wrapped
        setattr(cls,name,build(name,original))
    original_step=cls.step
    @functools.wraps(original_step)
    def step(self,years=1):
        d=getattr(self,'diagnostics',None)
        if d is None or not d.enabled:return original_step(self,years)
        for _ in range(max(1,int(years))):
            # begin is before the original increment, so don't modify its year semantics.
            d.begin_year();original_step(self,1);d.end_year()
        return self.summary()
    cls.step=step
    def export(self,path=None):
        if not getattr(self,'diagnostics',None):raise RuntimeError('診斷未啟用；請開啟設定後重新啟動。')
        return self.diagnostics.export(path)
    cls.export_diagnostic_package=export


def _observe_voyages(d,old):
    for c in d.engine.countries:
        for key in ('reinforcement_voyage','colonization_voyage'):
            previous=old.get(c['id'],{}).get(key);now=c.get(key)
            if not previous and now and (c['id'],key) not in d.voyage_ids:
                d.sequence+=1;vid=f'{d.session}:voyage:{d.sequence}';d.voyage_ids[(c['id'],key)]=vid
                d.voyage_decisions[vid]=d.current['decision_id'] if d.current is not None and d.current['country_id']==c['id'] else None
                record=plain({k:v for k,v in now.items() if k not in ('route','rl_state')})
                soldiers=now.get('soldiers',now.get('transported_soldiers',0));fleet=now.get('fleet',now.get('transport_fleet',0))
                cap=fleet*cfg.OVERSEAS_SOLDIERS_PER_SHIP
                d.emit('logistics_events','VOYAGE_STARTED',c['id'],voyage_id=vid,kind=key,decision_id=d.voyage_decisions[vid],dispatch_source='STRATEGIC_DECISION' if d.voyage_decisions[vid] else 'AUTOMATIC_OR_MANUAL_LOGISTICS',
                    soldier_capacity_utilization=soldiers/cap if cap else None,record=record)
                d.country_stats[c['id']]['reinforcement_dispatch' if key=='reinforcement_voyage' else 'colonization_dispatch']+=1
            elif previous and not now:
                settlement=d.arrivals.pop((c['id'],key),{})
                vid=d.voyage_ids.pop((c['id'],key),None)
                d.emit('logistics_events','VOYAGE_FINISHED',c['id'],voyage_id=vid,kind=key,
                    decision_id=d.voyage_decisions.pop(vid,None),returning=previous.get('returning',False),delivered=settlement.get('delivered'),settlement=settlement,
                    # End-of-function locals arrival hook gives exact last-year attrition/cargo.
                    record=plain({k:v for k,v in previous.items() if k not in ('route','rl_state')}),
                    note='delivery detail and actual arrival quantities are in ARRIVAL_SETTLEMENT event')


def install_cache(cls):
    for name in ('landmass_ownership','country_landmasses','invalidate'):
        original=getattr(cls,name)
        def build(name,original):
            @functools.wraps(original)
            def wrapped(self,*a,**kw):
                d=getattr(self.engine,'diagnostics',None)
                if d is None or not d.enabled_for('cache'):return original(self,*a,**kw)
                hits=self.hits;misses=self.misses
                result=original(self,*a,**kw)
                c=d.cache['WorldStateCache'];c['hit']+=self.hits-hits;c['miss']+=self.misses-misses;c['rebuild']+=self.misses-misses
                if name=='invalidate':c['invalidate']+=1;c['unknown_global_reason' if (kw.get('landmass_ids',a[1] if len(a)>1 else None)) is None else 'territory_changed_reason']+=1
                c['entries']=len(self._landmass_owners)+len(self._country_landmasses)
                return result
            return wrapped
        setattr(cls,name,build(name,original))


def install_ui(cls):
    for name,phase in {'refresh_panels':'ranking_log_panels','redraw':'map_canvas_render','_maybe_auto_save':'autosave','_maybe_save_map_snapshot':'map_snapshot'}.items():
        if not hasattr(cls,name):continue
        original=getattr(cls,name)
        def build(original,phase):
            @functools.wraps(original)
            def wrapped(self,*a,**kw):
                d=getattr(getattr(self,'war',None),'diagnostics',None)
                if not d or not d.enabled_for('performance'):return original(self,*a,**kw)
                d.count('map_renders' if phase=='map_canvas_render' else 'UI_refreshes' if phase=='ranking_log_panels' else phase+'_calls')
                d.push_timer('ui:'+phase)
                try:return original(self,*a,**kw)
                finally:d.pop_timer()
            return wrapped
        setattr(cls,name,build(original,phase))


def diagnostic_label(engine,*args,**kwargs):
    from scipy import ndimage
    d=getattr(engine,'diagnostics',None)
    if d is not None and d.enabled_for('performance'):d.count('ndimage_label_calls')
    return ndimage.label(*args,**kwargs)


def _corridor_evidence(self,cid,before,after,loss):
    from scipy import ndimage
    islands=np.unique(self.engine.world.continent.ravel()[loss])
    structure=np.array([[0,1,0],[1,1,1],[0,1,0]],dtype=np.uint8)
    for island in islands:
        if island<=0:continue
        coords=np.argwhere((before==cid)&(self.engine.world.continent==island))
        if not len(coords):continue
        y0,x0=coords.min(axis=0);y1,x1=coords.max(axis=0)+1
        b=(before[y0:y1,x0:x1]==cid)&(self.engine.world.continent[y0:y1,x0:x1]==island)
        a=(after[y0:y1,x0:x1]==cid)&(self.engine.world.continent[y0:y1,x0:x1]==island)
        _,nb=ndimage.label(b,structure=structure);_,na=ndimage.label(a,structure=structure)
        self.count('diagnostic_ndimage_label_calls',2)
        if na>nb:
            self.country_stats[cid]['corridor_cuts']+=1
            self.emit('territory_events','CORRIDOR_CUT',cid,island_id=int(island),components_before=int(nb),components_after=int(na),
                removed_cells=int((b&~a).sum()),evidence='captured cells split remaining same-island territory using original 4-neighbour topology')
DiagnosticLogger.corridor_evidence=_corridor_evidence


def _state_payload(self):
    return {'seed':self.engine.world.settings.seed,'map_size':[self.engine.world.settings.width,self.engine.world.settings.height],
       'year':self.engine.year,'records':plain(self.records),'history':plain(self.history),'performance':plain(self.performance),
       'global_history':plain(self.global_history),'summaries':plain(self.summaries),'country_stats':plain(self.country_stats),'island_stats':[[cid,lm,dict(counts)] for (cid,lm),counts in self.island_stats.items()],
       'durable':plain(self.durable),'pending_baseline':plain(self.pending_baseline),'voyage_decisions':plain(self.voyage_decisions),'observed_gains':plain(self.observed_gains),
       'campaign_data':plain(self.campaign_data),'last_decision':plain(self.last_decision),'pending_rewards':plain(self.pending_rewards),
       'voyage_ids':[[cid,key,vid] for (cid,key),vid in self.voyage_ids.items()],
       'performance_summaries':plain(self.performance_summaries),'cache':plain(self.cache),'counts':plain(self.counts),
       'health_history':plain(self.health_history),'first_year':self.first_year,'last_analysis':plain(self.last_analysis),
       'seen_world_pacified':plain(self.seen_world_pacified),'dropped':plain(self.dropped)}
DiagnosticLogger.state_payload=_state_payload


def _restore_history(self):
    path=self.output/'diagnostic_state.json'
    if not path.exists():return
    try:
        state=json.loads(path.read_text(encoding='utf-8'))
        if state['seed']!=self.engine.world.settings.seed or state['map_size']!=[self.engine.world.settings.width,self.engine.world.settings.height] or state['year']!=self.engine.year:
            self.errors.append({'year':self.engine.year,'warning':'existing diagnostic history does not match loaded save year/seed/map; started new session'})
            return
        self.records={k:deque(v) for k,v in state['records'].items()}
        self.buffer_bytes=Counter({k:sum(r.get('_record_bytes',0) for r in v) for k,v in self.records.items()})
        self.history=defaultdict(deque,{int(k):deque(v) for k,v in state['history'].items()})
        self.performance=deque(state['performance']);self.global_history=deque(state['global_history']);self.summaries=deque(state['summaries'])
        self.country_stats=defaultdict(Counter,{int(k):Counter(v) for k,v in state['country_stats'].items()})
        self.island_stats=defaultdict(Counter,{(cid,lm):Counter(counts) for cid,lm,counts in state.get('island_stats',[])})
        self.voyage_decisions=state.get('voyage_decisions',{})
        self.durable=state['durable'];self.pending_baseline=state['pending_baseline']
        self.observed_gains=defaultdict(dict,{int(k):{int(i):y for i,y in v.items()} for k,v in state['observed_gains'].items()})
        self.campaign_data={int(k):dict(v,captured_indices=set(v['captured_indices'])) for k,v in state['campaign_data'].items()}
        self.last_decision={int(k):v for k,v in state['last_decision'].items()};self.pending_rewards={int(k):v for k,v in state['pending_rewards'].items()}
        self.voyage_ids={(cid,key):vid for cid,key,vid in state['voyage_ids']}
        self.performance_summaries=deque(state['performance_summaries'],maxlen=2000);self.cache=defaultdict(Counter,{k:Counter(v) for k,v in state['cache'].items()})
        self.counts=Counter(state['counts']);self.health_history=deque(state['health_history'],maxlen=20)
        self.first_year=state['first_year'];self.last_analysis=state['last_analysis'];self.seen_world_pacified=set(state['seen_world_pacified']);self.dropped=Counter(state['dropped'])
        self.last_year=state['year'];self.last_flush=state['year'];self.rotate()
    except (OSError,ValueError,KeyError,TypeError) as exc:self.errors.append({'year':self.engine.year,'history_restore_error':repr(exc)})
DiagnosticLogger.restore_history=_restore_history

# Attribute instrumentation CPU time to diagnostics, including hooks inside AI/war.
for _method_name in ('emit','observe','begin_decision','complete_decision','mutation','macro','snapshot','rl_selection'):
    _original=getattr(DiagnosticLogger,_method_name)
    def _timed_diagnostic(original):
        @functools.wraps(original)
        def wrapped(self,*args,**kw):
            if not self.in_year or not self.enabled_for('performance'):return original(self,*args,**kw)
            self.push_timer('diagnostics')
            try:return original(self,*args,**kw)
            finally:self.pop_timer()
        return wrapped
    setattr(DiagnosticLogger,_method_name,_timed_diagnostic(_original))


def _rule_decision(self,c,values,condition):
    if self.current is None:return
    overseas=values.get('overseas_action');choice=values.get('choice');campaign=values.get('campaign')
    if 'recovery_until_year' in condition:action='RECOVERY_LOCK'
    elif overseas and 'overseas_action' in condition:action=overseas
    elif 'rest_chance' in condition:action='REST_AND_REPRODUCE'
    elif 'AI_BASE_WAR_CHANCE' in condition:action='RULE_RANDOM_WAR_GATE'
    elif condition=='RULE_LOOP_COMPLETED' and values.get('scored'):
        action='ATTACK:'+str(choice['id'])+':'+choice['mode']
    else:action='RULE_CONTINUE'
    cid=c['id'];stats=self.country_stats[cid];stats['decisions']+=1;stats['action:'+action]+=1
    if self.enabled_for('ai'):
        row=self.current
        self.emit('ai_decisions','STRATEGIC_DECISION',cid,decision_id=row['decision_id'],selection_source='RULE',chosen_action=action,
          selection_reason=condition,country_name=c['name'],country_before=row['country_before'],evaluations=row['evaluations'],
          chosen_target=plain(choice) if condition=='RULE_LOOP_COMPLETED' else None,
          final_scored_candidates=plain(values.get('scored')) if condition=='RULE_LOOP_COMPLETED' else None,
          legal_actions=None,q_values=None,estimated_win_probability=None,
          success=bool(campaign) if action.startswith('ATTACK:') else None,
          note='Original rule branch; random gate outcomes are observed without resampling.')
    self.current=None
DiagnosticLogger.rule_decision=_rule_decision
