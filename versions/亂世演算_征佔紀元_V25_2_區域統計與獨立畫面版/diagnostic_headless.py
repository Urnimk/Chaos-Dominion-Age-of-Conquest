"""Read-only continuation: python diagnostic_headless.py --save saves --years 100 --level 2 --output diagnostics_run"""
import argparse, random, time
from pathlib import Path
import map_config as cfg
from map_generator import load_world
from war_engine import WarEngine

def configure(level,output):
    cfg.ENABLE_DIAGNOSTIC_LOG=level>0;cfg.DIAGNOSTIC_DETAIL_LEVEL=level
    for key in ('ENABLE_AI_DECISION_LOG','ENABLE_STAGNATION_LOG','ENABLE_PERFORMANCE_LOG','ENABLE_WAR_DIAGNOSTIC_LOG','ENABLE_LOGISTICS_DIAGNOSTIC_LOG','ENABLE_CACHE_DIAGNOSTIC_LOG'):
        setattr(cfg,key,level>0 and (key!='ENABLE_AI_DECISION_LOG' or level>=2))
    cfg.DIAGNOSTIC_OUTPUT_DIR=str(output)

def main():
    p=argparse.ArgumentParser();p.add_argument('--save',type=Path,required=True);p.add_argument('--years',type=int,default=100)
    p.add_argument('--level',type=int,choices=(0,1,2),default=1);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.years<0:p.error('years must be nonnegative')
    if a.output.resolve()==a.save.resolve() or a.save.resolve() in a.output.resolve().parents:p.error('output must be outside the source saves folder')
    configure(a.level,a.output)
    e=WarEngine.load(load_world(a.save),a.save/'war_state.npz');random.seed(e.world.settings.seed)
    start=time.perf_counter()
    for i in range(a.years):
        e.step(1)
        if (i+1)%25==0:print(f'{i+1} years / world year {e.year}',flush=True)
    print(f'{time.perf_counter()-start:.3f} seconds')
    if e.diagnostics:print(e.export_diagnostic_package(a.output.parent/(a.output.name+'_package.zip')))
if __name__=='__main__':main()
