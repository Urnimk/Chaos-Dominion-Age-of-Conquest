"""V26 royal registry. No map scans, combat bonuses, or main-engine RNG use.
A person has one identity; titles have separate reign records and ambitions.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from collections import Counter
import hashlib
import random
import math
import map_config as cfg

PERSONALITIES = ('CONQUEROR','CONSERVATOR','SEA_KING','PIONEER','AVENGER','GAMBLER','CAUTIOUS','DIPLOMAT','AMBITIOUS')
ABILITIES = ('military','administration','naval','diplomacy','willpower')
TRADITIONS = ('MILITARY','NAVAL','COLONIAL','ADMINISTRATIVE','DIPLOMATIC')
NAMES = ('阿洛斯','伊蓮娜','路德維希','瑪蒂爾達','卡爾','索菲亞','腓特烈','艾德里安','奧古斯特','克莉絲汀')
LABELS = dict(zip(PERSONALITIES,('征服型','守成型','海權型','拓荒型','復仇型','冒險型','謹慎型','外交型','野心型')))

def clamp(x, low=0., high=1.): return max(low,min(high,float(x)))
def tuples(x): return tuple(tuples(v) if isinstance(v,list) else v for v in x)

@dataclass
class ReignAmbition:
    kind: str = 'UNIFY_HOMELAND'
    target_country: int | None = None
    target_landmass: int = 0
    start_year: int = 0
    commitment: float = .5
    progress: float = 0.
    last_progress_year: int = 0
    stagnation_years: int = 0
    baseline: float = 0.
    completed: bool = False
    baseline_metrics: dict = field(default_factory=dict)

@dataclass
class KingMemory:
    grudges: dict = field(default_factory=dict)
    personal_relations: dict = field(default_factory=dict)
    last_decay_year: int = 0

@dataclass
class RegencyState:
    active: bool = False
    until_year: int = 0
    council: str = '王室議會'

@dataclass
class RoyalPerson:
    person_id: int
    name: str
    dynasty_id: int
    country_of_origin: int
    birth_year: int
    death_year: int | None = None
    father_id: int | None = None
    mother_id: int | None = None
    spouse_id: int | None = None
    children_ids: list = field(default_factory=list)
    gender: str = 'F'
    succession_eligible: bool = True
    claims: list = field(default_factory=list)
    current_titles: list = field(default_factory=list)

@dataclass
class KingProfile(RoyalPerson):
    personality: str = 'CAUTIOUS'
    secondary_traits: list = field(default_factory=list)
    abilities: dict = field(default_factory=dict)
    legitimacy: float = .85
    memory: KingMemory = field(default_factory=KingMemory)
    regency: RegencyState = field(default_factory=RegencyState)
    personally_commanding: bool = False
    death_due_year: int = 0
    reigns: dict = field(default_factory=dict)
    posthumous_title: str = ''
    @property
    def king_id(self): return self.person_id

@dataclass
class DynastyProfile:
    dynasty_id: int
    name: str
    founded_year: int
    founder_id: int
    tradition: str
    prestige: float = .5
    reign_count: int = 0
    relations: dict = field(default_factory=dict)
    history: list = field(default_factory=list)

@dataclass
class Claim:
    claim_id: int
    claimant_person_id: int
    target_country_id: int
    claim_strength: float
    claim_source: str
    created_year: int
    expiry_year: int
    inheritable: bool = True

@dataclass
class RoyalMarriage:
    marriage_id: int
    person_a: int
    person_b: int
    created_year: int
    countries: list
    political: bool = True
    ended_year: int | None = None
    children: list = field(default_factory=list)

@dataclass
class PersonalUnion:
    union_id: int
    monarch_id: int
    member_countries: list
    senior_partner: int
    junior_partners: list
    created_year: int
    union_loyalty: dict = field(default_factory=dict)
    union_legitimacy: float = .85
    integration_progress: float = 0.
    succession_rule: str = 'LOCAL_COGNATIC_PRIMOGENITURE'
    shared_wars: list = field(default_factory=list)
    diplomatic_policy: dict = field(default_factory=dict)
    stage: str = 'PERSONAL_UNION'
    last_check_year: int = 0
    low_loyalty_since: dict = field(default_factory=dict)

@dataclass
class SuccessionWar:
    war_id: int
    attacker: int
    defender: int
    claimant_id: int
    created_year: int
    war_goal: str = 'WAR_GOAL_SUCCESSION'
    status: str = 'PENDING'
    campaigns: list = field(default_factory=list)
    resolved_year: int | None = None

class KingSystem:
    def __init__(self, engine, migrate=True):
        self.engine=engine; self.seed=int(engine.world.settings.seed)
        self.persons={}; self.dynasties={}; self.claims={}; self.marriages={}; self.unions={}; self.wars={}
        self.streams={}; self.sequences={}; self.next_ids={k:1 for k in ('person','dynasty','claim','marriage','union','war')}
        self.history=[]; self.country_history={}; self.metrics=Counter(); self.last_tick=engine.year
        self._index={}; self._claim_index={}
        if migrate:
            for c in engine.countries:
                if c.get('alive'): self.ensure_country(c)
    @property
    def year(self): return self.engine.year
    def rng(self, kind, cid=0):
        key=f'{kind}:{cid}'
        if key not in self.streams:
            seed=int.from_bytes(hashlib.sha256(f'{self.seed}:V26:{key}'.encode()).digest()[:8],'big')
            self.streams[key]=random.Random(seed)
        return self.streams[key]
    def ident(self, kind):
        n=self.next_ids[kind];self.next_ids[kind]=n+1;return n
    def emit(self,event,cid=None,**data):
        row=dict(year=self.year,event=event,country_id=cid,**data)
        self.history.append(row);self.history=self.history[-cfg.KING_HISTORY_LIMIT:]
        self.metrics[event]+=1
        if cid:
            h=self.country_history.setdefault(str(cid),[]);h.append(row);del h[:-cfg.KING_COUNTRY_HISTORY_LIMIT]
        dynasty_ids={self.persons[p].dynasty_id for p in (data.get('monarch_id'),data.get('person_a'),data.get('claimant_id')) if p in self.persons}
        for did in dynasty_ids:
            h=self.dynasties[did].history;h.append(row);del h[:-cfg.KING_COUNTRY_HISTORY_LIMIT]
        d=getattr(self.engine,'diagnostics',None)
        if d is not None and d.enabled_for('major'): d.emit('major_events',event,cid,**data)
    def new_dynasty(self,cid,name=None):
        i=self.ident('dynasty');r=self.rng('king',cid)
        d=DynastyProfile(i,name or f'{self.engine.country(cid).get("royal_surname","新王")}王朝',self.year,0,r.choice(TRADITIONS))
        self.dynasties[i]=d;return d
    def new_person(self,cid,dynasty_id=None,birth_year=None,name=None,father=None,mother=None):
        r=self.rng('king',cid);did=dynasty_id or self.new_dynasty(cid).dynasty_id
        i=self.ident('person');birth=self.year-r.randint(22,42) if birth_year is None else birth_year
        p=KingProfile(i,name or r.choice(NAMES)+'．'+self.dynasties[did].name.removesuffix('王朝'),did,cid,birth,
            father_id=father,mother_id=mother,gender=r.choice(('F','M')),personality=r.choice(PERSONALITIES),
            secondary_traits=r.sample(('堅毅','多疑','務實','仁厚','好勝','耐心'),2),
            abilities={k:r.randint(20,95) for k in ABILITIES},death_due_year=birth+r.randint(cfg.KING_LIFESPAN_MIN,cfg.KING_LIFESPAN_MAX))
        # Tradition biases abilities slightly without determining the personality.
        a=dict(MILITARY='military',NAVAL='naval',COLONIAL='naval',ADMINISTRATIVE='administration',DIPLOMATIC='diplomacy')[self.dynasties[did].tradition]
        if cfg.ENABLE_DYNASTY_SYSTEM:p.abilities[a]=min(100,p.abilities[a]+5)
        self.persons[i]=p
        p.memory.last_decay_year=self.year
        if not self.dynasties[did].founder_id:self.dynasties[did].founder_id=i
        for parent in (father,mother):
            if parent in self.persons:self.persons[parent].children_ids.append(i)
        self.metrics['ROYAL_BIRTH']+=1;return p
    def ensure_country(self,c):
        p=self.persons.get(c.get('monarch_id'))
        if p:return p
        d=self.new_dynasty(c['id'],str(c.get('royal_surname','新王'))+'王朝')
        p=self.new_person(c['id'],d.dynasty_id,name=c.get('king_name'))
        # Migration preserves the old reign, name, and scheduled change.
        p.death_due_year=max(self.year+1,int(c.get('king_next_year',p.death_due_year)))
        p.birth_year=min(p.birth_year,int(c.get('king_since_year',self.year))-18)
        since=int(c.get('king_since_year',self.year))
        self.accession(c,p,'MIGRATION',number=int(c.get('king_number',1)))
        c['king_since_year']=since;p.reigns[str(c['id'])]['accession_year']=since
        p.reigns[str(c['id'])]['migrated_partial_reign']=True
        return p
    def profile(self,c):return self.persons.get(c.get('monarch_id'))
    def reign(self,c):
        p=self.profile(c)
        return p.reigns.get(str(c['id'])) if p else None
    def rank(self,c):
        strength=lambda v:v.get('soldiers',0)+v.get('fleet',0)*18+v.get('population',0)*.05
        power=strength(c)
        return 1+sum(x['alive'] and (strength(x)>power or (strength(x)==power and x['id']<c['id'])) for x in self.engine.countries)
    def record_action(self,c,policy,success):
        r=self.reign(c)
        if r:
            counts=r['statistics'].setdefault('actions',{});counts[policy]=counts.get(policy,0)+1
            if success:r['statistics']['successful_actions']=r['statistics'].get('successful_actions',0)+1
    def rival_score(self,c,cid,lm):
        p=self.profile(c);base=-math.log1p(self.engine._home_soldiers(cid,lm))/5
        if not p or not cfg.ENABLE_KING_STRATEGY_SYSTEM:return base
        a=self.reign(c)['ambition'];grudge=p.memory.grudges.get(str(cid),0)
        politics=any(w.attacker==c['id'] and w.defender==cid and w.status in ('PENDING','ACTIVE') for w in self.wars.values())
        return base+min(.6,grudge*(.6 if p.personality=='AVENGER' else .2))+.3*(a.get('target_country')==cid)+.3*politics
    def operational_commitment(self,c):
        p=self.profile(c)
        if not p or not cfg.ENABLE_KING_STRATEGY_SYSTEM:return 1.
        return 1.+(.06 if p.personality in ('CONQUEROR','AMBITIOUS','GAMBLER') else 0.)+(.02 if p.personally_commanding else 0.)
    def state_measure(self,c):
        return {k:int(c.get(k,0)) for k in ('population','territory_cells','wars_won','wars_lost','fleet')}
    def accession(self,c,p,reason,number=None):
        old=self.profile(c);old_reign=self.reign(c)
        if old and old.person_id!=p.person_id:
            self.finish_reign(c,old,reason)
            if c['id'] in old.current_titles:old.current_titles.remove(c['id'])
            if old.death_year is None:self.claim(old.person_id,c['id'],.6,'FORMER_MONARCH')
        inherited='CONTINUE'
        if old:
            for k,v in old.memory.grudges.items():
                c.setdefault('national_rivalry',{})[k]=clamp(c.get('national_rivalry',{}).get(k,0)+v*.15)
            if old.personality!=p.personality:inherited='MODIFY'
        p.regency=RegencyState(cfg.ENABLE_REGENCY and self.year-p.birth_year<18,max(self.year,p.birth_year+18))
        n=number if number is not None else int(c.get('king_number',0))+1
        c.update(monarch_id=p.person_id,king_id=p.person_id,king_name=p.name,king_number=n,
                 royal_surname=self.dynasties[p.dynasty_id].name.removesuffix('王朝'),king_since_year=self.year,
                 king_next_year=p.death_due_year,world_goal='WORLD_UNIFICATION')
        if c['id'] not in p.current_titles:p.current_titles.append(c['id'])
        ambition=self.choose_ambition(c,p)
        if old_reign:
            previous=old_reign.get('ambition',{})
            inherited=('ABANDON' if not self.ambition_valid(c,previous) or self.year-previous.get('last_progress_year',self.year)>=cfg.KING_AMBITION_STALL_YEARS else 'CONTINUE' if previous.get('kind')==ambition.kind else 'MODIFY')
        if old_reign and inherited=='CONTINUE':
            prev=old_reign.get('ambition',{})
            if prev and self.ambition_valid(c,prev) and self.year-prev.get('last_progress_year',self.year)<cfg.KING_AMBITION_STALL_YEARS:ambition=ReignAmbition(**dict(prev,start_year=self.year))
        p.reigns[str(c['id'])]=dict(accession_year=self.year,reign_number=n,ambition=asdict(ambition),
            start=self.state_measure(c),start_rank=self.rank(c),start_bases=len(c.get('overseas_capitals',[])),start_colonies=len(c.get('colonies',[])),start_islands=len(c.get('macro_completed_islands',[])),statistics={'wars_won':0,'wars_lost':0,'colonies':0,'bases':0,'islands_pacified':0,'eliminations':0,'ambitions_completed':0,'lost_capital':0,'gross_gains':0,'losses':0},
            inherited_policy=inherited,last_measure=self.state_measure(c),commanding=False)
        self.dynasties[p.dynasty_id].reign_count+=1
        self.emit('KING_ACCESSION',c['id'],monarch_id=p.person_id,name=p.name,dynasty=p.dynasty_id,personality=p.personality,
            abilities=p.abilities,legitimacy=p.legitimacy,ambition=asdict(ambition),commitment=ambition.commitment,
            inherited_policy=inherited,strategic_change=f'{getattr(old,"personality",None)} → {p.personality}',reason=reason)
        if reason!='MIGRATION':self.engine._log(c['id'],f'{reason}：第{n}任{p.name}登基，{LABELS[p.personality]}，治世志向 {ambition.kind}。')
        self._index.clear()
    def critical(self,c):
        e=self.engine;home=e._home_continent_id(c)
        if home<=0:return False
        _,counts,_=e.world_state_cache.landmass_ownership(home)
        cells=int(counts[c['id']]) if c['id']<len(counts) else 0
        x,y=map(int,c['capital'])
        initial=c.setdefault('king_initial_home_cells',max(1,cells))
        threshold=min(cfg.OVERSEAS_RETREAT_HOME_MAX_CELLS,max(1,int(initial*cfg.OVERSEAS_RETREAT_INITIAL_HOME_SHARE)))
        return cells<=threshold or int(e.world.territory[y,x])!=c['id'] or c.get('war_exhaustion',0)>.9
    def choose_ambition(self,c,p,exclude=None):
        e=self.engine;home=e._home_continent_id(c);current=c.get('strategic_commitment') or {}
        lm=int(current.get('target_landmass') or home);target=current.get('target_country')
        # Small scalar/cached state only; no target search or per-country world scan.
        choices=[('BECOME_MILITARY_HEGEMON',2.,0,None)]
        if not e._homeland_is_unified(c):choices.append(('UNIFY_HOMELAND',8.,home,None))
        if c.get('war_exhaustion',0)>.65 or self.critical(c):choices.append(('RESTORE_NATIONAL_POWER',12.,home,None))
        if lm and lm!=home:choices.extend([('CONQUER_LANDMASS',4.,lm,target),('BUILD_OVERSEAS_NETWORK',3.,lm,None)])
        if c.get('ports',0) and c.get('fleet',0)>=cfg.OVERSEAS_MIN_FLEET:
            choices.extend([('ESTABLISH_NAVAL_HEGEMONY',3.,0,None),('COLONIAL_EXPANSION',3.,0,None)])
        rivals=[(float(v),int(k)) for k,v in p.memory.grudges.items() if int(k)!=c['id'] and int(k)<=len(e.countries) and e.country(int(k)).get('alive')]
        if rivals:
            _,rival=max(rivals)
            # Only focus an existing reachable rival, not a random remote ruler.
            if rival==target or tuple(sorted((c['id'],rival))) in e.land_contacts:
                choices.extend([('DESTROY_RIVAL',4.,lm,rival),('CAPTURE_ENEMY_CAPITAL',3.,lm,rival),('RECOVER_LOST_TERRITORY',3.,home,rival)])
        preference={'CONQUEROR':'CONQUER_LANDMASS','CONSERVATOR':'RESTORE_NATIONAL_POWER','SEA_KING':'ESTABLISH_NAVAL_HEGEMONY',
            'PIONEER':'COLONIAL_EXPANSION','AVENGER':'DESTROY_RIVAL','GAMBLER':'CAPTURE_ENEMY_CAPITAL','CAUTIOUS':'BUILD_OVERSEAS_NETWORK','DIPLOMAT':'BECOME_MILITARY_HEGEMON','AMBITIOUS':'CONQUER_LANDMASS'}[p.personality]
        scored=[(score+(2. if kind==preference else 0.)+p.abilities['willpower']/200,kind,l,t) for kind,score,l,t in choices if kind!=exclude]
        if not scored:scored=[(1.,'UNIFY_HOMELAND',home,None)]
        _,kind,lm,target=max(scored)
        commitment=clamp(.3+p.abilities['willpower']/200+( .1 if p.personality in ('AVENGER','CONQUEROR') else 0),cfg.KING_AMBITION_MIN_COMMITMENT,cfg.KING_AMBITION_MAX_COMMITMENT)
        baseline=float(c.get('territory_cells',0) if kind not in ('RESTORE_NATIONAL_POWER','BECOME_MILITARY_HEGEMON') else c.get('population',0))
        a=ReignAmbition(kind,target,lm,self.year,commitment,0.,self.year,0,baseline)
        a.baseline_metrics=dict(fleet=c.get('fleet',0),bases=len(c.get('overseas_capitals',[])),colonies=len(c.get('colonies',[])),exhaustion=c.get('war_exhaustion',0),army=c.get('soldiers',0),rank=self.rank(c),territory=c.get('territory_cells',0))
        if target and target<=len(e.countries):a.baseline_metrics['enemy_capital']=list(e.country(target)['capital'])
        if lm>0:
            total,counts,_=e.world_state_cache.landmass_ownership(lm);a.baseline_metrics['island_control']=(int(counts[c['id']]) if c['id']<len(counts) else 0)/max(1,total)
        return a
    def ambition_valid(self,c,a):
        t=a.get('target_country')
        if t and (t>len(self.engine.countries) or not self.engine.country(t).get('alive') or self.same_union(c['id'],t)):return False
        return not (self.critical(c) and a['kind'] not in ('UNIFY_HOMELAND','RESTORE_NATIONAL_POWER'))
    def change_ambition(self,c,reason):
        r=self.reign(c);p=self.profile(c)
        if not r:return
        old=r['ambition'];new=asdict(self.choose_ambition(c,p,old['kind'] if reason in ('STALLED','COMPLETED') else None))
        r['ambition']=new
        self.emit('KING_AMBITION_CHANGE',c['id'],monarch_id=p.person_id,old=old,new=new,reason=reason,progress=old['progress'],years=self.year-old['start_year'])
        # Preserve sailing/ongoing campaigns and bases. Only release a stalled macro when safe.
        commit=c.get('strategic_commitment')
        travelling=c.get('colonization_voyage') or any(x.attacker==c['id'] and x.status=='marching' for x in self.engine.campaigns)
        if reason=='STALLED' and commit and not travelling and self.year-commit.get('last_progress_year',self.year)>=cfg.KING_AMBITION_STALL_YEARS:
            c.setdefault('macro_target_cooldowns',{})[str(commit['target_landmass'])]=self.year+cfg.MACRO_RETRY_COOLDOWN_YEARS
            c['strategic_commitment']=None
    def update_ambition(self,c):
        p=self.profile(c);r=self.reign(c);a=r['ambition'];now=self.state_measure(c);last=r['last_measure'];s=r['statistics']
        s['gross_gains']+=max(0,now['territory_cells']-last['territory_cells']);s['losses']+=max(0,last['territory_cells']-now['territory_cells'])
        for k in ('wars_won','wars_lost'):s[k]=max(s[k],now[k]-r['start'][k])
        s['bases']=max(s['bases'],len(c.get('overseas_capitals',[]))-r.get('start_bases',0));s['colonies']=max(s['colonies'],len(c.get('colonies',[]))-r.get('start_colonies',0))
        s['islands_pacified']=max(0,len(c.get('macro_completed_islands',[]))-r.get('start_islands',0));r['last_measure']=now
        commit=c.get('strategic_commitment') or {}
        baseline=a.get('baseline_metrics',{});kind=a['kind'];complete=False
        progress=max(0.,(now['territory_cells']-baseline.get('territory',a['baseline']))/max(1,baseline.get('territory',a['baseline'])))
        if kind=='UNIFY_HOMELAND':
            complete=self.engine._homeland_is_unified(c)
            total,counts,_=self.engine.world_state_cache.landmass_ownership(self.engine._home_continent_id(c))
            progress=max(0.,(int(counts[c['id']]) if c['id']<len(counts) else 0)/max(1,total)-baseline.get('island_control',0))
        elif kind in ('CONQUER_LANDMASS','RECOVER_LOST_TERRITORY'):
            lm=a['target_landmass']
            if lm:
                total,counts,owners=self.engine.world_state_cache.landmass_ownership(lm)
                control=(int(counts[c['id']]) if c['id']<len(counts) else 0)/max(1,total)
                progress=max(0.,control-baseline.get('island_control',0));complete=control>=.8 and not (owners-{c['id']})
        elif kind in ('BUILD_OVERSEAS_NETWORK','COLONIAL_EXPANSION'):
            progress=max(0,len(c.get('overseas_capitals',[]))-baseline.get('bases',len(c.get('overseas_capitals',[]))))
            if kind=='COLONIAL_EXPANSION':progress=max(progress,len(c.get('colonies',[]))-baseline.get('colonies',0))
            complete=progress>=1
        elif kind=='ESTABLISH_NAVAL_HEGEMONY':
            progress=max(0.,(c.get('fleet',0)-baseline.get('fleet',0))/max(10,baseline.get('fleet',0)))
            complete=progress>=.25 and len(c.get('overseas_capitals',[]))>baseline.get('bases',0)
        elif kind=='RESTORE_NATIONAL_POWER':
            progress=max(0.,baseline.get('exhaustion',0)-c.get('war_exhaustion',0),(now['population']-a['baseline'])/max(1,a['baseline']))
            complete=c.get('war_exhaustion',0)<.25 and progress>=.10
        elif kind=='BECOME_MILITARY_HEGEMON':
            progress=max(0.,(now['population']-a['baseline'])/max(1,a['baseline']), (c.get('soldiers',0)-baseline.get('army',0))/max(200,baseline.get('army',0)))
            complete=self.rank(c)==1 and progress>=.25
        elif kind in ('DESTROY_RIVAL','CAPTURE_ENEMY_CAPITAL'):
            target=a['target_country'];complete=bool(target and not self.engine.country(target)['alive'])
            if kind=='CAPTURE_ENEMY_CAPITAL' and baseline.get('enemy_capital'):
                x,y=baseline['enemy_capital'];complete|=int(self.engine.world.territory[y,x])==c['id']
            progress=1. if complete else progress
        if progress>a['progress']+.01:a['last_progress_year']=self.year
        a['progress']=max(a['progress'],progress);a['stagnation_years']=self.year-a['last_progress_year']
        if complete:a['completed']=True;s['ambitions_completed']+=1;self.change_ambition(c,'COMPLETED')
        elif not self.ambition_valid(c,a):self.change_ambition(c,'SAFETY_OR_INVALID_TARGET')
        elif a['stagnation_years']>=cfg.KING_AMBITION_STALL_YEARS:
            self.emit('KING_AMBITION_STALLED',c['id'],monarch_id=p.person_id,ambition=a.copy());self.change_ambition(c,'STALLED')
    def score_breakdown(self,c,score,lm,kind,target):
        p=self.profile(c);r=self.reign(c)
        if not p or not r or not cfg.ENABLE_KING_STRATEGY_SYSTEM:return dict(base=score,personality=0.,grudge=0.,ambition=0.,dynasty=0.,ability=0.,final=score)
        naval=lm!=self.engine._home_continent_id(c)
        biases={'CONQUEROR':(.7,-.3),'CONSERVATOR':(-.25,.1),'SEA_KING':(.55,.45),'PIONEER':(-.2,.9),'AVENGER':(.25,-.1),'GAMBLER':(.5,.1),'CAUTIOUS':(-.2,.35),'DIPLOMAT':(-.15,.1),'AMBITIOUS':(.55,.1)}
        personality=biases[p.personality][int(kind=='COLONIZE')]*(1 if naval else .5)
        a=r['ambition'];ambition=(.8*a['commitment'] if (a['target_landmass'] and lm==a['target_landmass']) or (a['kind']=='COLONIAL_EXPANSION' and kind=='COLONIZE') or (a['kind']=='ESTABLISH_NAVAL_HEGEMONY' and naval) else 0.)
        grudge=min(.6,p.memory.grudges.get(str(target),0)*(.6 if p.personality=='AVENGER' else .25)) if cfg.ENABLE_KING_GRUDGES else 0.
        tradition=self.dynasties[p.dynasty_id].tradition
        dynasty=.12 if cfg.ENABLE_DYNASTY_SYSTEM and ((tradition=='COLONIAL' and kind=='COLONIZE') or (tradition=='NAVAL' and naval) or (tradition=='MILITARY' and kind!='COLONIZE')) else 0.
        # Stable evaluation error (never consumes tactical/main RNG or varies on repeated UI reads).
        raw=int.from_bytes(hashlib.blake2s(f'{p.person_id}:{lm}:{target}:{self.year//20}'.encode(),digest_size=2).digest(),'big')/65535-.5
        skill=(p.abilities['naval' if naval else 'military']*.8+p.abilities['administration']*.2);ability=raw*(100-skill)/150
        scale=.65 if p.regency.active else 1.
        ambition+=min(.4,sum(.4 for w in self.wars.values() if w.attacker==c['id'] and w.defender==target and w.status in ('PENDING','ACTIVE')))
        final=score+clamp((personality+ambition+grudge+dynasty+ability)*scale,-cfg.KING_SCORE_MODIFIER_LIMIT,cfg.KING_SCORE_MODIFIER_LIMIT)
        return dict(base=score,personality=personality,grudge=grudge,ambition=ambition,dynasty=dynasty,ability=ability,final=final)
    def rank_targets(self,c,choices):
        out=[];d=getattr(self.engine,'diagnostics',None)
        for score,lm,kind,target in choices:
            b=self.score_breakdown(c,score,lm,kind,target);out.append((b['final'],lm,kind,target))
            if d is not None and d.enabled_for('ai'):d.emit('ai_decisions','KING_TARGET_SCORE',c['id'],landmass=lm,target=target,kind=kind,**b)
        return sorted(out,key=lambda x:(x[0],x[1],x[2],x[3] or 0),reverse=True)
    def action_biases(self,c,bindings):
        p=self.profile(c)
        if not p or not cfg.ENABLE_KING_STRATEGY_SYSTEM:return {}
        result={}
        for action in bindings:
            value=0.
            if 'ATTACK' in action or action in ('CUT_OFF','ENCIRCLE_CAPITAL'):
                value={'CONQUEROR':.12,'GAMBLER':.1,'AVENGER':.08,'CAUTIOUS':-.06,'CONSERVATOR':-.05}.get(p.personality,0.)
            elif action=='COLONIZE':value=.12 if p.personality in ('PIONEER','SEA_KING') else 0.
            elif action=='REST_AND_REPRODUCE':value=.04 if p.personality=='CONSERVATOR' else 0.
            elif action=='SECURE_SUPPLY':value=p.abilities['administration']/1000
            if p.personally_commanding and action=='REINFORCE_ACTIVE_THEATRE':value+=.08
            result[action]=value
        return result
    def risk_ratio(self,c):
        p=self.profile(c)
        if not p or not cfg.ENABLE_KING_STRATEGY_SYSTEM:return 1.
        base={'CAUTIOUS':1.08,'CONSERVATOR':1.05,'GAMBLER':.96,'CONQUEROR':.98}.get(p.personality,1.)
        return max(.95,base+(50-p.abilities['military'])/1500)
    def add_grudge(self,cid,enemy,amount):
        if not cfg.ENABLE_KING_GRUDGES:return
        p=self.profile(self.engine.country(cid))
        if p:p.memory.grudges[str(enemy)]=clamp(p.memory.grudges.get(str(enemy),0)+amount)
    def posthumous(self,stats):
        if stats.get('world_unified'):return '一統大帝'
        if stats.get('lost_capital',0):return '失土王' if stats.get('losses',0)>stats.get('gross_gains',0) else '多難王'
        if stats.get('ambitions_completed',0)>=2 and stats.get('wars_won',0)>stats.get('wars_lost',0):return '雄略王'
        if stats.get('bases',0)>=2:return '航海王'
        if stats.get('gross_gains',0)>stats.get('losses',0)*2+100:return '開疆王'
        if stats.get('wars_lost',0)>stats.get('wars_won',0)+2:return '失策王'
        if stats.get('population_growth',0)>.2:return '中興王'
        return '守成王'
    def finish_reign(self,c,p,reason):
        r=p.reigns.get(str(c['id']))
        if not r or r.get('end_year') is not None:return
        r['end_year']=self.year;r['end']=self.state_measure(c);s=r['statistics']
        s['population_growth']=(r['end']['population']-r['start']['population'])/max(1,r['start']['population'])
        s['durable_gains']=r['end']['territory_cells']-r['start']['territory_cells']
        for key in ('wars_won','wars_lost'):s[key]=r['end'][key]-r['start'][key]
        s['wars']=s['wars_won']+s['wars_lost'];s['years_reigned']=self.year-r['accession_year'];s['rank_change']=r.get('start_rank',self.rank(c))-self.rank(c)
        s['largest_nemesis']=max(p.memory.grudges,key=p.memory.grudges.get,default=None);s['homeland_unified']=self.engine._homeland_is_unified(c)
        self.dynasties[p.dynasty_id].prestige=clamp(self.dynasties[p.dynasty_id].prestige+.03*s['ambitions_completed']+.01*(s['wars_won']-s['wars_lost']))
        s['world_unified']=sum(bool(x['alive']) for x in self.engine.countries)==1
        r['posthumous_title']=self.posthumous(s);p.posthumous_title=r['posthumous_title']
        self.emit('KING_REIGN_ENDED',c['id'],monarch_id=p.person_id,name=p.name,personality=p.personality,title=p.posthumous_title,
                  start_year=r['accession_year'],end_year=self.year,statistics=dict(s),reason=reason)
    def claim(self,pid,cid,strength,source,years=None):
        if pid not in self.persons:return None
        for i in self._claim_index.get(cid,[]):
            old=self.claims[i]
            if old.claimant_person_id==pid and old.expiry_year>=self.year:
                if strength>old.claim_strength:old.claim_strength=strength;old.claim_source=source
                return old
        i=self.ident('claim');cl=Claim(i,pid,cid,clamp(strength),source,self.year,self.year+(years or cfg.CLAIM_LIFETIME_YEARS))
        self.claims[i]=cl;self._claim_index.setdefault(cid,[]).append(i);self.persons[pid].claims.append(i)
        self.emit('CLAIM_CREATED',cid,claimant_id=pid,claim_id=i,strength=cl.claim_strength,source=source,expiry=cl.expiry_year);return cl
    def related(self,a,b):
        if a.person_id==b.person_id:return True
        parents_a={x for x in (a.father_id,a.mother_id) if x};parents_b={x for x in (b.father_id,b.mother_id) if x}
        def ancestors(p):
            out=set()
            for parent in (p.father_id,p.mother_id):
                if parent in self.persons:
                    out.add(parent);v=self.persons[parent];out.update(x for x in (v.father_id,v.mother_id) if x)
            return out
        return bool(parents_a&parents_b or a.person_id in ancestors(b) or b.person_id in ancestors(a) or ancestors(a)&ancestors(b))
    def can_marry(self,a,b):
        return (a.death_year is None and b.death_year is None and not a.spouse_id and not b.spouse_id
            and 18<=self.year-a.birth_year<=55 and 18<=self.year-b.birth_year<=55 and a.gender!=b.gender and not self.related(a,b))
    def court(self,p):
        return self.senior(p.current_titles) if p.current_titles else p.country_of_origin
    def marriage_score(self,a,b):
        ca=self.engine.country(self.court(a));cb=self.engine.country(self.court(b))
        if not ca['alive'] or not cb['alive']:return -100.
        powera=max(1,ca.get('soldiers',0));powerb=max(1,cb.get('soldiers',0))
        relation=ca.get('national_relations',{}).get(str(cb['id']),0)
        relation=float(relation) if isinstance(relation,(float,int)) else 0.
        dr=self.dynasties[a.dynasty_id].relations.get(str(b.dynasty_id),0.)
        distance=self.engine._wrapped_distance_cells(ca['capital'],cb['capital'],self.engine.world.settings.width)
        threat=any(x.status=='marching' and {x.attacker,x.defender}=={ca['id'],cb['id']} for x in self.engine.campaigns)
        common=len(set(ca.get('national_rivalry',{}))&set(cb.get('national_rivalry',{})))
        heir_value=.7 if not self.main_heir(cb) else .1
        personality={'DIPLOMAT':.6,'AMBITIOUS':.4,'CONQUEROR':-.3,'CAUTIOUS':.2,'SEA_KING':.25 if cb.get('fleet',0)>0 else 0.,'AVENGER':-.4*a.memory.grudges.get(str(cb['id']),0)}.get(a.personality,0.)
        return 1.+clamp(relation/100,-.5,.5)+dr*.4+min(.4,math.log1p(powerb/powera)/5)+common*.1+heir_value+a.abilities['diplomacy']/200+personality-min(.5,distance/3000)-(2 if threat else 0)
    def marry(self,a,b,political=True):
        if not self.can_marry(a,b):return None
        a.spouse_id=b.person_id;b.spouse_id=a.person_id
        i=self.ident('marriage');m=RoyalMarriage(i,a.person_id,b.person_id,self.year,sorted({self.court(a),self.court(b)}),political)
        self.marriages[i]=m
        if political:
            self.dynasties[a.dynasty_id].relations[str(b.dynasty_id)]=clamp(self.dynasties[a.dynasty_id].relations.get(str(b.dynasty_id),0)+.15,-1,1)
            self.dynasties[b.dynasty_id].relations[str(a.dynasty_id)]=self.dynasties[a.dynasty_id].relations[str(b.dynasty_id)]
            for p,other in ((a,b),(b,a)):
                for title in other.current_titles:self.claim(p.person_id,title,.25,'ROYAL_MARRIAGE')
            self.emit('ROYAL_MARRIAGE_ACCEPTED',a.country_of_origin,person_a=a.person_id,person_b=b.person_id,marriage_id=i,countries=m.countries)
        return m
    def birth(self,m):
        a=self.persons[m.person_a];b=self.persons[m.person_b]
        # Children inherit both bloodlines. Origin alternates by court rather than all belonging to one parent.
        origin=(self.court(a),self.court(b))[len(m.children)%2]
        mother=a if a.gender=='F' else b;father=b if a.gender=='F' else a
        p=self.new_person(origin,father.dynasty_id,self.year,father=father.person_id,mother=mother.person_id)
        m.children.append(p.person_id)
        for parent in (a,b):
            for cid in parent.current_titles:self.claim(p.person_id,cid,.95,'MATERNAL_LINE' if parent==mother else 'PATERNAL_LINE')
        for parent in (a,b):
            for clid in parent.claims:
                cl=self.claims.get(clid)
                if cl and cl.inheritable and cl.expiry_year>=self.year and cl.claim_strength>=.5:
                    self.claim(p.person_id,cl.target_country_id,cl.claim_strength*.65,'DYNASTIC_RELATION')
        self.emit('ROYAL_HEIR_BORN',origin,marriage_id=m.marriage_id,monarch_id=p.person_id,parents=[a.person_id,b.person_id],claims=list(p.claims))
        return p
    def main_heir(self,c):
        p=self.profile(c)
        if not p:return None
        children=[self.persons[i] for i in p.children_ids if i in self.persons and self.persons[i].death_year is None and self.persons[i].succession_eligible]
        return min(children,key=lambda x:(x.country_of_origin!=c['id'],x.birth_year,x.person_id),default=None)
    def succession_candidates(self,c,old):
        candidates={}
        for pid in old.children_ids:
            if pid in self.persons:candidates[pid]=('DIRECT_HEIR',.95)
        for i in self._claim_index.get(c['id'],[]):
            cl=self.claims[i]
            if cl.expiry_year>=self.year and cl.claimant_person_id!=old.person_id:
                if cl.claimant_person_id not in candidates or cl.claim_strength>candidates[cl.claimant_person_id][1]:candidates[cl.claimant_person_id]=(cl.claim_source,cl.claim_strength)
        result=[]
        for pid,(source,strength) in candidates.items():
            p=self.persons.get(pid)
            if not p or p.death_year is not None or not p.succession_eligible:continue
            # Spousal weak claims alone cannot bypass legitimate children.
            support=.08*(p.country_of_origin==c['id'])+.04*(p.dynasty_id==old.dynasty_id)+p.legitimacy*.05
            age=self.year-p.birth_year;score=strength+support+min(.05,max(0,age)/1000)
            result.append(dict(person_id=pid,source=source,strength=strength,support=support,legitimacy=p.legitimacy,score=score,age=age))
        return sorted(result,key=lambda r:(-r['score'],self.persons[r['person_id']].birth_year,r['person_id']))
    def succeed(self,c,old,reason='君主駕崩'):
        candidates=self.succession_candidates(c,old);self.emit('SUCCESSION_STARTED',c['id'],monarch_id=old.person_id,candidates=candidates[:cfg.SUCCESSION_MAX_CANDIDATES])
        if candidates:
            p=self.persons[candidates[0]['person_id']];source=candidates[0]['source']
        else:
            # A collateral local branch is the normal fallback, not foreign random annexation.
            p=self.new_person(c['id'],old.dynasty_id,birth_year=self.year-self.rng('succession',c['id']).randint(18,45));source='COLLATERAL_BRANCH'
            p.legitimacy=.7
        r=self.rng('succession',c['id'])
        previous=old.reigns.get(str(c['id']),{}).get('statistics',{})
        p.legitimacy=clamp(p.legitimacy*.8+self.dynasties[p.dynasty_id].prestige*.2+.015*previous.get('ambitions_completed',0)-.04*previous.get('lost_capital',0)-.08*c.get('war_exhaustion',0),.3,1.)
        crisis=cfg.ENABLE_SUCCESSION_CRISIS and p.legitimacy<cfg.SUCCESSION_CRISIS_LEGITIMACY_THRESHOLD and r.random()<cfg.SUCCESSION_CRISIS_BASE_RATE*(1.5-p.legitimacy)
        if crisis:
            event=r.choice(('PALACE_COUP','USURPATION','SUCCESSION_STRUGGLE','SECESSION_PRESSURE'))
            p.legitimacy=clamp(p.legitimacy-.2,.3,1.);self.emit(event,c['id'],monarch_id=p.person_id)
            if event=='SECESSION_PRESSURE':c['royal_secession_until']=self.year+cfg.SUCCESSION_SECESSION_WINDOW
            if event=='USURPATION':
                p=self.new_person(c['id']);p.legitimacy=.55;source='USURPATION'
        self.accession(c,p,reason)
        self.emit('SUCCESSION_RESOLVED',c['id'],monarch_id=p.person_id,previous=old.person_id,source=source,
            candidates=candidates[:cfg.SUCCESSION_MAX_CANDIDATES],reason='合法宣稱、地方支持與長幼順位',cross_country=bool([t for t in p.current_titles if t!=c['id']]))
        if len(candidates)>1:
            other=candidates[1]
            if other['strength']>=.65 and candidates[0]['score']-other['score']<cfg.SUCCESSION_DISPUTE_SCORE_MARGIN:
                claimant=self.persons[other['person_id']];sponsors=[x for x in claimant.current_titles if x!=c['id']]
                if not sponsors and claimant.country_of_origin!=c['id']:sponsors=[claimant.country_of_origin]
                if sponsors:
                    self.emit('SUCCESSION_DISPUTED',c['id'],monarch_id=p.person_id,claimant_id=claimant.person_id,candidates=candidates[:3])
                    self.create_war(sponsors[0],c['id'],claimant.person_id)
        return p
    def death(self,p,reason='君主駕崩'):
        if p.death_year is not None:return
        titles=[x for x in p.current_titles if self.engine.country(x)['alive']]
        p.death_year=self.year
        if p.spouse_id in self.persons:self.persons[p.spouse_id].spouse_id=None
        for m in self.marriages.values():
            if p.person_id in (m.person_a,m.person_b) and m.ended_year is None:m.ended_year=self.year
        for cid in titles:self.succeed(self.engine.country(cid),p,reason)
        self.reconcile_unions()
    def realm(self,cid):
        u=self.union_for(cid)
        return set(u.member_countries) if u else {cid}
    def same_union(self,a,b):
        if a==b:return True
        ca=self.engine.country(a);cb=self.engine.country(b)
        return bool(ca.get('monarch_id') and ca.get('monarch_id')==cb.get('monarch_id'))
    def union_for(self,cid):
        uid=self._index.get(cid)
        if uid in self.unions:return self.unions[uid]
        for u in self.unions.values():
            if cid in u.member_countries:self._index[cid]=u.union_id;return u
        return None
    def senior(self,members):
        def score(cid):
            c=self.engine.country(cid);p=self.profile(c)
            return math.log1p(c.get('population',0))*.4+math.log1p(c.get('soldiers',0))*.4+math.log1p(c.get('territory_cells',0))*.2+(p.legitimacy if p else .5)*.1+( .1 if p and p.country_of_origin==cid else 0)
        return max(members,key=lambda cid:(score(cid),-cid))
    def reconcile_unions(self):
        groups={}
        for c in self.engine.countries:
            if c['alive'] and c.get('monarch_id'):groups.setdefault(c['monarch_id'],[]).append(c['id'])
        existing=list(self.unions.values());new={};self._index={}
        for pid,members in groups.items():
            if len(members)<2:continue
            old=max((u for u in existing if len(set(u.member_countries)&set(members))>=2),key=lambda u:len(set(u.member_countries)&set(members)),default=None)
            if old:
                u=old;previous=list(u.member_countries);changed=u.monarch_id!=pid or previous!=members
                u.monarch_id=pid;u.member_countries=members
                if changed:self.emit('PERSONAL_UNION_CONTINUED',members[0],monarch_id=pid,union_id=u.union_id,members=members)
            else:
                senior=self.senior(members);i=self.ident('union');u=PersonalUnion(i,pid,members,senior,[x for x in members if x!=senior],self.year,{str(x):.75 for x in members},last_check_year=self.year)
                self.emit('PERSONAL_UNION_CREATED',senior,monarch_id=pid,union_id=i,members=members,senior=senior)
            senior=self.senior(members)
            if senior!=u.senior_partner:self.emit('COURT_RELOCATION',senior,union_id=u.union_id,old=u.senior_partner,new=senior)
            u.senior_partner=senior;u.junior_partners=[x for x in members if x!=senior];new[u.union_id]=u
            for cid in members:self._index[cid]=u.union_id
        for u in existing:
            if u.union_id not in new:
                self.emit('PERSONAL_UNION_BROKEN',u.senior_partner,union_id=u.union_id,reason='DIFFERENT_SUCCESSORS_OR_MEMBER_LOSS',duration=self.year-u.created_year,members=u.member_countries)
            else:
                lost=set(u.union_loyalty)-{str(x) for x in new[u.union_id].member_countries}
                for cid in lost:
                    self.emit('PERSONAL_UNION_MEMBER_LEFT',int(cid),union_id=u.union_id,reason='DIFFERENT_SUCCESSOR');u.union_loyalty.pop(cid,None)
        self.unions=new
        # Cancel old orders coherently through the ordinary battle cancellation/return path.
        for campaign in self.engine.campaigns:
            if campaign.status=='marching' and self.same_union(campaign.attacker,campaign.defender):campaign.years_left=min(campaign.years_left,1)
    def create_war(self,attacker,defender,claimant,goal='WAR_GOAL_SUCCESSION'):
        if attacker==defender or not self.engine.country(attacker)['alive'] or not self.engine.country(defender)['alive']:return None
        if self.same_union(attacker,defender) and goal!='WAR_GOAL_INDEPENDENCE_FROM_UNION':return None
        if any(w.status in ('PENDING','ACTIVE') and (w.attacker,w.defender)==(attacker,defender) for w in self.wars.values()):return None
        i=self.ident('war');w=SuccessionWar(i,attacker,defender,claimant,self.year,goal);self.wars[i]=w
        self.emit('SUCCESSION_WAR_PROPOSED',attacker,war_id=i,target=defender,claimant_id=claimant,war_goal=goal);return w
    def attach_war(self,campaign):
        if not cfg.ENABLE_DYNASTIC_DIPLOMACY:return
        for w in self.wars.values():
            if w.status in ('PENDING','ACTIVE') and (w.attacker,w.defender)==(campaign.attacker,campaign.defender):
                p=self.persons.get(w.claimant_id)
                if not p or p.death_year is not None:continue
                campaign.war_goal=w.war_goal;campaign.claimant_id=w.claimant_id;campaign.dynastic_war_id=w.war_id
                w.status='ACTIVE';w.campaigns.append(campaign.id)
                self.emit('SUCCESSION_WAR_STARTED',campaign.attacker,war_id=w.war_id,campaign_id=campaign.id,claimant_id=w.claimant_id,war_goal=w.war_goal)
                break
        p=self.profile(self.engine.country(campaign.attacker))
        if p and cfg.ENABLE_PERSONAL_COMMAND:
            r=self.reign(self.engine.country(campaign.attacker));a=r['ambition']
            important=campaign.defender==a['target_country'] or tuple(reversed(self.engine.country(campaign.defender)['capital']))==campaign.objective
            r['commanding']=bool(important and self.year-p.birth_year>=18 and p.personality in ('CONQUEROR','AVENGER','GAMBLER','AMBITIOUS'))
            p.personally_commanding=any(x.get('commanding') for x in p.reigns.values() if x.get('end_year') is None)
    def resolve_war(self,campaign,attacker_wins):
        w=self.wars.get(campaign.dynastic_war_id)
        if not w or w.status!='ACTIVE':return
        if attacker_wins:
            p=self.persons.get(w.claimant_id);c=self.engine.country(w.defender)
            if w.war_goal=='WAR_GOAL_INDEPENDENCE_FROM_UNION':
                self.independence(w.attacker,'WAR_VICTORY')
                self.emit('UNION_INDEPENDENCE_CONFIRMED',w.attacker,war_id=w.war_id)
            elif p and p.death_year is None and c['alive']:
                self.accession(c,p,'王位戰爭勝利');self.reconcile_unions()
        if not attacker_wins and w.war_goal=='WAR_GOAL_INDEPENDENCE_FROM_UNION':
            senior=self.engine.country(w.defender);junior=self.engine.country(w.attacker);p=self.profile(senior)
            if senior['alive'] and junior['alive'] and p:
                self.accession(junior,p,'獨立戰爭失敗後恢復共主');self.reconcile_unions()
        w.status='WON' if attacker_wins else 'LOST';w.resolved_year=self.year
        self.emit('SUCCESSION_WAR_RESOLVED',w.attacker,war_id=w.war_id,result=w.status,war_goal=w.war_goal,claimant_id=w.claimant_id)
    def battle_event(self,attackers,attacker_wins,losses,defense_losses,captured):
        lead=attackers[0];winner=lead.attacker if attacker_wins else lead.defender;loser=lead.defender if attacker_wins else lead.attacker
        self.add_grudge(loser,winner,.12+min(.25,(losses+defense_losses)/max(1,self.engine.country(loser)['population'])))
        loser_country=self.engine.country(loser);winner_country=self.engine.country(winner)
        relations=loser_country.setdefault('national_relations',{});relations[str(winner)]=max(-100,relations.get(str(winner),0)-5)
        a=self.profile(winner_country);b=self.profile(loser_country)
        if a and b and a.dynasty_id!=b.dynasty_id:
            d=self.dynasties[a.dynasty_id];d.relations[str(b.dynasty_id)]=clamp(d.relations.get(str(b.dynasty_id),0)-.04,-1,1)
        # Allied assistance affects private relations, without alliance/army teleportation.
        for campaign in attackers[1:]:
            ally=self.profile(self.engine.country(campaign.attacker));leader=self.profile(self.engine.country(lead.attacker))
            if ally and leader:leader.memory.personal_relations[str(ally.person_id)]=clamp(leader.memory.personal_relations.get(str(ally.person_id),0)+.08,-1,1)
        for campaign in attackers:self.resolve_war(campaign,attacker_wins)
        if cfg.ENABLE_PERSONAL_COMMAND and b and b.personally_commanding and losses/max(1,self.engine.country(loser)['population'])>.02:
            r=self.rng('succession',loser)
            if r.random()<cfg.KING_BATTLE_DEATH_CHANCE:
                event=r.choice(('KING_KILLED_IN_BATTLE','KING_CAPTURED','KING_MISSING'))
                self.emit(event,loser,monarch_id=b.person_id);self.death(b,event)
        for campaign in attackers:
            p=self.profile(self.engine.country(campaign.attacker))
            if p:
                r=self.reign(self.engine.country(campaign.attacker))
                if r:r['commanding']=False
                p.personally_commanding=any(v.get('commanding') for v in p.reigns.values() if v.get('end_year') is None)
    def independence(self,cid,reason):
        u=self.union_for(cid)
        if not u or cid==u.senior_partner:return False
        senior=u.senior_partner;c=self.engine.country(cid);old=self.profile(c);p=self.new_person(cid,old.dynasty_id)
        self.accession(c,p,'共主獨立');self.emit('UNION_INDEPENDENCE',cid,union_id=u.union_id,reason=reason)
        self.reconcile_unions()
        if reason=='PROLONGED_LOW_LOYALTY' and c.get('soldiers',0)>=self.engine.country(senior).get('soldiers',0)*cfg.UNION_INDEPENDENCE_WAR_FORCE_RATIO and c.get('war_exhaustion',0)<.5:
            self.create_war(cid,senior,p.person_id,'WAR_GOAL_INDEPENDENCE_FROM_UNION')
        return True
    def integrate(self,u):
        e=self.engine;senior=e.country(u.senior_partner)
        if any(e.country(cid).get(k) for cid in u.member_countries for k in ('colonization_voyage','reinforcement_voyage')):return False
        for cid in list(u.junior_partners):
            c=e.country(cid)
            if not c['alive']:continue
            mask=e.world.territory==cid;landmasses=e.world_state_cache.country_landmasses(cid)
            e.world.territory[mask]=senior['id'];e.building_owner[e.building_owner==cid]=senior['id']
            for k in ('population','soldiers','fleet','food','timber','minerals'):senior[k]=senior.get(k,0)+c.get(k,0)
            for site in c.get('overseas_capitals',[]):
                if not any(s['continent_id']==site['continent_id'] for s in senior.get('overseas_capitals',[])):senior.setdefault('overseas_capitals',[]).append(site)
            home=e._home_continent_id(c);x,y=c['capital']
            if home!=e._home_continent_id(senior) and not any(s['continent_id']==home for s in senior.get('overseas_capitals',[])):
                senior.setdefault('overseas_capitals',[]).append(dict(anchor=[x,y],continent_id=home,founded_year=self.year,type='王朝整合首都'))
            for campaign in e.campaigns:
                if campaign.attacker==cid:campaign.attacker=senior['id']
                if campaign.defender==cid:campaign.defender=senior['id']
            self.finish_reign(c,self.profile(c),'POLITICAL_INTEGRATION');self.profile(c).current_titles.remove(cid)
            c.update(alive=False,ever_extinct=True,extinction_year=self.year,integrated_into=senior['id'],territory_cells=0,population=0,soldiers=0,fleet=0,food=0,timber=0,minerals=0,overseas_capitals=[],overseas_capital=None,colonies=[],cities=0,barracks=0,ports=0,colonization_voyage=None,reinforcement_voyage=None)
            e._mark_world_changed(cid,senior['id'],landmass_ids=landmasses)
        senior['overseas_capital']=next(iter(senior.get('overseas_capitals',[])),None)
        from war_engine import _border_mask
        e.world.border=_border_mask(e.world.territory);e._sync_army_totals();e._build_geography();e._land_totals_dirty=True
        u.stage='INTEGRATED_STATE';self.emit('UNION_INTEGRATED',senior['id'],union_id=u.union_id,members=u.member_countries,duration=self.year-u.created_year)
        self.reconcile_unions()
    def union_tick(self):
        for u in list(self.unions.values()):
            dt=self.year-u.last_check_year
            if dt<cfg.UNION_CHECK_INTERVAL:continue
            u.last_check_year=self.year;u.union_legitimacy=self.persons[u.monarch_id].legitimacy
            oldsenior=u.senior_partner;u.senior_partner=self.senior(u.member_countries);u.junior_partners=[x for x in u.member_countries if x!=u.senior_partner]
            if oldsenior!=u.senior_partner:self.emit('COURT_RELOCATION',u.senior_partner,union_id=u.union_id,old=oldsenior,new=u.senior_partner)
            senior=self.engine.country(u.senior_partner)
            # Shared enemy requires every participating court to be able to attack it legally.
            common=None
            for cid in u.member_countries:
                c=self.engine.country(cid);ally=c.get('alliance',0)
                eligible={x['id'] for x in self.engine.countries if x['alive'] and x['id'] not in u.member_countries and not (ally and x.get('alliance')==ally)}
                common=eligible if common is None else common&eligible
            u.diplomatic_policy={'shared_enemies':sorted(common or []),'leader':u.senior_partner}
            u.shared_wars=[w.war_id for w in self.wars.values() if w.status=='ACTIVE' and w.attacker in u.member_countries]
            for cid in list(u.junior_partners):
                c=self.engine.country(cid);key=str(cid);loyalty=u.union_loyalty.get(key,.75)
                pressure=c.get('war_exhaustion',0)*.007+max(0,math.log(max(1,c['population'])/max(1,senior['population'])))*.002
                gain=.0015*u.union_legitimacy+(.001 if c.get('wars_won',0)>0 and u.shared_wars else 0)
                loyalty=clamp(loyalty+dt*(gain-pressure));u.union_loyalty[key]=loyalty
                if loyalty<cfg.UNION_REFUSE_SUPPORT_THRESHOLD:
                    if key not in u.low_loyalty_since:
                        u.low_loyalty_since[key]=self.year;self.emit('REFUSE_SUPPORT',cid,union_id=u.union_id,loyalty=loyalty)
                    if self.year-u.low_loyalty_since[key]>=cfg.UNION_INDEPENDENCE_DELAY:
                        if loyalty<cfg.UNION_INDEPENDENCE_THRESHOLD:self.independence(cid,'PROLONGED_LOW_LOYALTY')
                        else:self.emit('INDEPENDENCE_MOVEMENT',cid,union_id=u.union_id,loyalty=loyalty)
                else:u.low_loyalty_since.pop(key,None)
            if u.union_id not in self.unions:continue
            stable=(min(u.union_loyalty.get(str(c),.75) for c in u.member_countries)>=cfg.UNION_INTEGRATION_LOYALTY and u.union_legitimacy>=cfg.UNION_INTEGRATION_LEGITIMACY
                    and not any(x.status=='marching' and (x.attacker in u.member_countries or x.defender in u.member_countries) for x in self.engine.campaigns)
                    and not u.low_loyalty_since and not any(self.engine.country(cid).get(k) for cid in u.member_countries for k in ('colonization_voyage','reinforcement_voyage')))
            if stable:
                p=self.persons[u.monarch_id];u.integration_progress=clamp(u.integration_progress+dt/cfg.UNION_INTEGRATION_YEARS*(.8+p.abilities['diplomacy']/250))
            else:u.integration_progress=max(0,u.integration_progress-dt/2000)
            age=self.year-u.created_year
            if u.integration_progress>=.33 and age>=75 and u.stage=='PERSONAL_UNION':u.stage='DYNASTIC_UNION';self.emit('DYNASTIC_UNION',u.senior_partner,union_id=u.union_id)
            if u.integration_progress>=.66 and age>=150 and u.stage=='DYNASTIC_UNION':u.stage='POLITICAL_INTEGRATION';self.emit('UNION_INTEGRATION_STARTED',u.senior_partner,union_id=u.union_id)
            if u.integration_progress>=1 and age>=cfg.UNION_INTEGRATION_MIN_YEARS and stable:self.integrate(u)
    def diplomacy_tick(self):
        if not cfg.ENABLE_DYNASTIC_DIPLOMACY:return
        r=self.rng('marriage');alive=[c for c in self.engine.countries if c['alive']]
        eligible={}
        for c in alive:
            p=self.profile(c)
            if not p:continue
            family=[p]+[self.persons[i] for i in p.children_ids if i in self.persons]
            eligible[c['id']]=[x for x in family if x.death_year is None and not x.spouse_id and 18<=self.year-x.birth_year<=55][:cfg.MARRIAGE_FAMILY_CANDIDATES]
        # A bounded rotation of nearby/powerful courts, not all-persons squared.
        ranked=sorted(alive,key=lambda c:(-c.get('population',0),c['id']))
        for ca in alive:
            for a in eligible.get(ca['id'],[]):
                if a.spouse_id:continue
                courts=[c for c in ranked if c['id']!=ca['id']]
                if len(courts)>cfg.MARRIAGE_COURT_CANDIDATES:
                    offset=(self.year//cfg.ROYAL_CHECK_INTERVAL+ca['id'])%len(courts);courts=(courts[offset:]+courts[:offset])[:cfg.MARRIAGE_COURT_CANDIDATES]
                candidates=[b for cb in courts for b in eligible.get(cb['id'],[]) if self.can_marry(a,b)]
                b=max(candidates,key=lambda b:self.marriage_score(a,b),default=None)
                if b and r.random()<cfg.ROYAL_MARRIAGE_CHANCE:
                    score=self.marriage_score(a,b);self.emit('ROYAL_MARRIAGE_PROPOSED',ca['id'],person_a=a.person_id,person_b=b.person_id,score=score)
                    if score>=cfg.ROYAL_MARRIAGE_MIN_SCORE and self.marriage_score(b,a)>=cfg.ROYAL_MARRIAGE_MIN_SCORE:self.marry(a,b)
                    else:self.emit('ROYAL_MARRIAGE_REJECTED',ca['id'],person_a=a.person_id,person_b=b.person_id,score=score)
                # Local spouses preserve normal succession; foreign marriage remains a minority.
                if not a.spouse_id and self.year-a.birth_year>=cfg.ROYAL_LOCAL_MARRIAGE_AGE:
                    spouse=self.new_person(ca['id'],birth_year=self.year-r.randint(20,32));spouse.gender='M' if a.gender=='F' else 'F';self.marry(a,spouse,False)
        for c in alive:
            p=self.profile(c)
            if not p or p.personality not in ('CONQUEROR','AMBITIOUS','DIPLOMAT'):continue
            for clid in p.claims:
                cl=self.claims.get(clid)
                if not cl or cl.claim_strength<cfg.CLAIM_THRONE_MIN_STRENGTH or cl.expiry_year<self.year:continue
                target=self.engine.country(cl.target_country_id);other=self.profile(target)
                if target['alive'] and target['id']!=c['id'] and other and other.legitimacy<cfg.CLAIM_THRONE_MAX_TARGET_LEGITIMACY and not self.same_union(c['id'],target['id']):
                    self.create_war(c['id'],target['id'],p.person_id,'WAR_GOAL_CLAIM_THRONE')
                    break
        for m in list(self.marriages.values()):
            if m.ended_year is not None or len(m.children)>=cfg.ROYAL_MAX_CHILDREN:continue
            a=self.persons[m.person_a];b=self.persons[m.person_b]
            if a.death_year is not None or b.death_year is not None:continue
            mother=a if a.gender=='F' else b
            if 18<=self.year-mother.birth_year<=cfg.ROYAL_FERTILITY_MAX_AGE and r.random()<cfg.ROYAL_BIRTH_CHANCE:self.birth(m)
    def tick(self):
        if not cfg.ENABLE_KING_STRATEGY_SYSTEM and not self.persons:return
        for c in self.engine.countries:
            if c['alive']:self.ensure_country(c)
        # Death resolution is identity-based; a shared monarch dies exactly once.
        for p in list(self.persons.values()):
            if p.death_year is None and self.year>=p.death_due_year:self.death(p)
        for c in self.engine.countries:
            if not c['alive']:
                p=self.profile(c)
                if p and c['id'] in p.current_titles:self.finish_reign(c,p,'COUNTRY_EXTINCT');p.current_titles.remove(c['id'])
                continue
            p=self.profile(c);c['world_goal']='WORLD_UNIFICATION'
            if p.regency.active and self.year>=p.regency.until_year:
                p.regency.active=False;self.emit('REGENCY_ENDED',c['id'],monarch_id=p.person_id)
            if self.year%cfg.KING_STRATEGY_INTERVAL==0:
                dt=max(0,self.year-p.memory.last_decay_year)
                if cfg.ENABLE_KING_GRUDGES:
                    p.memory.grudges={k:v*math.exp(-cfg.GRUDGE_DECAY_RATE*dt) for k,v in p.memory.grudges.items() if v*math.exp(-cfg.GRUDGE_DECAY_RATE*dt)>.01}
                p.memory.last_decay_year=self.year;self.update_ambition(c)
        if self.year%cfg.ROYAL_CHECK_INTERVAL==0:self.diplomacy_tick();self.reconcile_unions();self.union_tick();self.prune()
        for w in self.wars.values():
            if w.status in ('PENDING','ACTIVE') and (self.year-w.created_year>cfg.SUCCESSION_WAR_EXPIRY_YEARS or not self.engine.country(w.attacker)['alive'] or not self.engine.country(w.defender)['alive']):
                w.status='EXPIRED';w.resolved_year=self.year;self.emit('SUCCESSION_WAR_RESOLVED',w.attacker,war_id=w.war_id,result='EXPIRED_NO_VIABLE_CAMPAIGN')
        self.last_tick=self.year
    def prune(self):
        # Retain living royals, two ancestry generations, live claims and compact history.
        keep={p.person_id for p in self.persons.values() if p.death_year is None or p.current_titles}
        for _ in range(2):
            for pid in list(keep):
                p=self.persons.get(pid)
                if p:keep.update(x for x in (p.father_id,p.mother_id,p.spouse_id) if x in self.persons)
        self.claims={i:c for i,c in self.claims.items() if c.expiry_year>=self.year and c.claimant_person_id in keep and self.persons[c.claimant_person_id].death_year is None}
        self._claim_index={}
        for i,c in self.claims.items():self._claim_index.setdefault(c.target_country_id,[]).append(i)
        for p in self.persons.values():p.claims=[i for i in p.claims if i in self.claims];p.children_ids=[i for i in p.children_ids if i in keep]
        self.persons={i:p for i,p in self.persons.items() if i in keep}
        self.marriages={i:m for i,m in self.marriages.items() if m.ended_year is None or self.year-m.ended_year<cfg.ROYAL_ARCHIVE_YEARS}
        self.wars={i:w for i,w in self.wars.items() if w.resolved_year is None or self.year-w.resolved_year<cfg.ROYAL_ARCHIVE_YEARS}
        active={p.dynasty_id for p in self.persons.values()}
        self.dynasties={i:d for i,d in self.dynasties.items() if i in active}
    def to_dict(self):
        return dict(schema_version=1,seed=self.seed,next_ids=self.next_ids,sequences=self.sequences,
                    **{name:{str(i):asdict(v) for i,v in getattr(self,name).items()} for name in ('persons','dynasties','claims','marriages','unions','wars')},
                    rng_states={k:r.getstate() for k,r in self.streams.items()},history=self.history,country_history=self.country_history,metrics=dict(self.metrics),last_tick=self.last_tick)
    @classmethod
    def from_dict(cls,engine,data):
        s=cls(engine,False)
        if int(data.get('schema_version',0))!=1:raise ValueError('不支援的 V26 王室存檔版本')
        for name,typ in (('persons',KingProfile),('dynasties',DynastyProfile),('claims',Claim),('marriages',RoyalMarriage),('unions',PersonalUnion),('wars',SuccessionWar)):
            for key,raw in data.get(name,{}).items():
                raw=dict(raw)
                if name=='persons':raw['memory']=KingMemory(**raw.get('memory',{}));raw['regency']=RegencyState(**raw.get('regency',{}))
                getattr(s,name)[int(key)]=typ(**raw)
        s.next_ids=data['next_ids'];s.sequences=data.get('sequences',{});s.history=data.get('history',[]);s.country_history=data.get('country_history',{});s.metrics=Counter(data.get('metrics',{}));s.last_tick=data.get('last_tick',engine.year)
        for key,state in data.get('rng_states',{}).items():s.streams[key]=random.Random();s.streams[key].setstate(tuples(state))
        for i,c in s.claims.items():s._claim_index.setdefault(c.target_country_id,[]).append(i)
        for u in s.unions.values():
            for cid in u.member_countries:s._index[cid]=u.union_id
        for c in engine.countries:
            if c['alive'] and c.get('monarch_id') not in s.persons:raise ValueError(f'王室身分缺失：國家 {c["id"]}')
        return s
    def ui_rows(self,c):
        p=self.profile(c)
        if not p:return ()
        r=self.reign(c);a=r['ambition'];u=self.union_for(c['id']);heir=self.main_heir(c)
        spouse=self.persons.get(p.spouse_id);grudge=max(p.memory.grudges,key=p.memory.grudges.get,default=None)
        rows=[('王朝／年齡',f'{self.dynasties[p.dynasty_id].name}｜{self.year-p.birth_year}歲｜在位{self.year-r["accession_year"]}年'),
              ('君主人格',LABELS[p.personality]+'｜'+'、'.join(p.secondary_traits)),
            #   ('君主能力','／'.join(f'{dict(military="軍事",administration="行政",naval="海軍",diplomacy="外交",willpower="意志")[k]}:{v}' for k,v in p.abilities.items())),
            #   ('治世志向',f'{a["kind"]}｜承諾{a["commitment"]:.0%}｜進展{a["progress"]:.0%}'),('合法性／攝政',f'{p.legitimacy:.0%}｜'+(f'攝政至{p.regency.until_year}' if p.regency.active else '親政')+('｜親征中' if p.personally_commanding else '')),
              ('配偶／繼承人',f'{spouse.name if spouse else "無"}／{heir.name if heir else "旁系待議"}'),
              ('持有王位','、'.join(self.engine.country(i)['name'] for i in p.current_titles)),
              ('私人宿敵',self.engine.country(int(grudge))['name'] if grudge and int(grudge)<=len(self.engine.countries) else '無')]
        if u:rows.append(('共主邦聯',f'{u.stage}｜'+('Senior' if c['id']==u.senior_partner else 'Junior')+f'｜忠誠{u.union_loyalty.get(str(c["id"]),.75):.0%}｜整合{u.integration_progress:.0%}'))
        claims=[self.claims[i] for i in p.claims if i in self.claims]
        rows.append(('王位宣稱','、'.join(f'{self.engine.country(cl.target_country_id)["name"]} {cl.claim_strength:.0%}' for cl in claims[:4]) or '無'))
        history=[x for x in self.country_history.get(str(c['id']),[]) if x['event']=='KING_REIGN_ENDED'][-5:]
        for h in history:
            rows.append((f'歷代 {h["start_year"]}–{h["end_year"]}',f'{h["name"]}｜{h["title"]}'))
        return tuple(rows)
