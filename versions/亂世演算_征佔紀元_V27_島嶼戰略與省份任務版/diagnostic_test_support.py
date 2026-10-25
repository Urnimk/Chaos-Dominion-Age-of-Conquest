import copy,random,tempfile
from contextlib import contextmanager
import numpy as np
import map_config as cfg
from map_generator import generate_world,MapSettings
from war_engine import WarEngine
from diagnostic_headless import configure

@contextmanager
def settings(level=2):
    keys=['ENABLE_DIAGNOSTIC_LOG','DIAGNOSTIC_DETAIL_LEVEL','DIAGNOSTIC_OUTPUT_DIR','COUNTRY_COUNT',
          'ENABLE_AI_DECISION_LOG','ENABLE_STAGNATION_LOG','ENABLE_PERFORMANCE_LOG','ENABLE_WAR_DIAGNOSTIC_LOG',
          'ENABLE_LOGISTICS_DIAGNOSTIC_LOG','ENABLE_CACHE_DIAGNOSTIC_LOG','DIAGNOSTIC_FLUSH_INTERVAL_YEARS']
    previous={k:getattr(cfg,k) for k in keys}
    with tempfile.TemporaryDirectory() as directory:
        configure(level,directory);cfg.COUNTRY_COUNT=4;cfg.DIAGNOSTIC_FLUSH_INTERVAL_YEARS=20
        try:yield directory
        finally:
            for k,v in previous.items():setattr(cfg,k,v)

def world():
    random.seed(2026)
    return generate_world(MapSettings(128,128,2026,'ISLANDS',.7))

def state(e):
    return {'territory':e.world.territory.copy(),'population':e.local_population.copy(),'soldiers':e.local_soldiers.copy(),
            'countries':copy.deepcopy(e.countries),'campaigns':copy.deepcopy(e.campaigns),
            'brains':{k:b.to_dict() for k,b in e.rl_brains.items()},'rng':copy.deepcopy(e.rng.bit_generator.state),
            'python_rng':random.getstate(),'events':copy.deepcopy(e.events),'disconnected_since':copy.deepcopy(e.disconnected_since)}
