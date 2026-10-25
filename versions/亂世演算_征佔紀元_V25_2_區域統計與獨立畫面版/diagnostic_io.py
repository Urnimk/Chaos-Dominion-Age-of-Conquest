"""V25_2 compact diagnostic snapshots, isolated write failures and retry spacing.
Game state/RNG are never modified. Existing JSON/JSONL/CSV event schema remains.
"""
import csv,gzip,io,json,os,tempfile,time,zipfile
from collections import deque
from pathlib import Path
import numpy as np
import map_config as cfg

class DiagnosticJSONEncoder(json.JSONEncoder):
    def default(self,value):
        if isinstance(value,np.ndarray):return value.tolist()
        if isinstance(value,np.generic):return value.item()
        if isinstance(value,deque):return list(value)
        if isinstance(value,(set,frozenset)):return sorted(value)
        if isinstance(value,Path):return str(value)
        return super().default(value)

def encoded(value):
    return json.dumps(value,cls=DiagnosticJSONEncoder,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')

class FastDiagnosticWriter:
    def __init__(self,logger):self.logger=logger;self.published={}
    def atomic(self,name,data,directory=None):
        directory=Path(directory or self.logger.output);path=directory/name
        directory.mkdir(parents=True,exist_ok=True)
        temp=None
        try:
            fd,temp=tempfile.mkstemp(prefix='.'+name+'.',suffix='.tmp',dir=directory)
            with os.fdopen(fd,'wb') as f:f.write(data)
            os.replace(temp,path);temp=None
        except OSError as exc:
            exc.diagnostic_file=str(path);exc.diagnostic_stage='atomic_write';raise
        finally:
            if temp is not None:
                try:os.unlink(temp)
                except OSError:pass
    def write(self,name,value,jsonl=False,directory=None):
        # Deque records are frozen payloads. Identity of ends detects append/rotation.
        token=None
        if jsonl and directory is None:
            token=(len(value),value[0] if value else None,value[-1] if value else None)
            previous=self.published.get(name)
            if previous is not None and previous[0]==token[0] and previous[1] is token[1] and previous[2] is token[2] and (self.logger.output/name).exists():return
        if jsonl:data=b''.join(encoded(row)+b'\n' for row in value)
        elif isinstance(value,str):data=value.encode('utf-8')
        else:data=encoded(value)
        if name=='diagnostic_state.json':
            name='diagnostic_state.json.gz';data=gzip.compress(data,compresslevel=1,mtime=0)
        self.atomic(name,data,directory)
        if token is not None:self.published[name]=token
    def csv(self,directory=None):
        d=self.logger;rows=list(d.performance)
        phases=sorted({p for row in rows for p in row['phases_ms']})
        text=io.StringIO(newline='')
        names=['year','simulation_ms','diagnostic_flush_ms','simulation_with_diagnostics_ms','ui_ms','total_recorded_ms']+phases+['counts_json','events_json']
        writer=csv.DictWriter(text,fieldnames=names);writer.writeheader()
        for row in rows:
            sim=row['simulation_ms'];cost=row.get('diagnostic_flush_ms',0.);ui=row.get('ui_ms',0.)
            writer.writerow({'year':row['year'],'simulation_ms':sim,'diagnostic_flush_ms':cost,
                'simulation_with_diagnostics_ms':sim+cost,'ui_ms':ui,'total_recorded_ms':sim+cost+ui,
                **row['phases_ms'],'counts_json':json.dumps(row['counts'],ensure_ascii=False),
                'events_json':json.dumps(row['events'],ensure_ascii=False)})
        self.atomic('performance_recent_1000y.csv',text.getvalue().encode('utf-8'),directory)


def writer(d):
    if not hasattr(d,'_io_writer'):d._io_writer=FastDiagnosticWriter(d)
    return d._io_writer

def write(d,name,value,jsonl=False):return writer(d).write(name,value,jsonl)

def documents(d,include_state=True):
    for name,rows in d.records.items():yield name+'.jsonl',rows,True
    if include_state:yield 'diagnostic_state.json',d.state_payload(),False
    yield 'stagnation_summary.json',d.last_analysis,False
    yield 'stagnation_intervals.jsonl',d.summaries,True
    yield 'performance_intervals.jsonl',d.performance_summaries,True
    yield 'cache_summary.json',d.cache_summary(),False
    yield 'logistics_summary.json',d.logistics_summary(),False

def summary_text(d):
    text=f'# V25_2 診斷分析包\n\n目前年份：{d.engine.year}；觀察起點：{d.first_year}。\n\n'
    text+='完整決策最近 100 年；其他明細與效能最近 1000 年。無法觀察的數值為 null。\n\n'
    text+=f'決策紀錄：{len(d.records["ai_decisions"])}；戰役紀錄：{len(d.records["war_outcomes"])}；效能年份：{len(d.performance)}。\n\n'
    text+='停滯國家：'+', '.join(r['name'] for r in d.last_analysis.get('countries',[]) if r['stagnation_detected'])+'\n\n'
    text+='寫檔耗時請看 diagnostic_flush_ms 與 simulation_with_diagnostics_ms，UI 另列。\n'
    if d.active_write_errors:text+='\n目前公開檔案寫入失敗：'+json.dumps(d.active_write_errors,ensure_ascii=False)+'\n'
    if d.errors:text+='\n歷史錯誤（不阻擋已恢復的匯出）：'+json.dumps(list(d.errors),ensure_ascii=False)+'\n'
    if d.dropped:text+='\n容量截斷：'+repr(dict(d.dropped))+'\n'
    return text

def record_error(d,name,exc):
    row={'year':d.engine.year,'file':getattr(exc,'diagnostic_file',str(d.output/name)),
         'stage':getattr(exc,'diagnostic_stage','serialize_or_write'),'error':repr(exc)}
    d.errors.append(row);d.active_write_errors[name]=row;d.last_flush_errors.append(row)

def flush(d,force=True):
    if not d.enabled:return None
    if not force and d.engine.year<d.next_flush_year:return d.output
    start=time.perf_counter();d.last_flush_attempt=d.engine.year
    d.next_flush_year=d.engine.year+max(1,int(getattr(cfg,'DIAGNOSTIC_FLUSH_INTERVAL_YEARS',20)))
    d.last_flush_errors=[];d.rotate();w=writer(d)
    def publish(name,value=None,jsonl=False,csv_file=False):
        try:
            if csv_file:w.csv()
            else:w.write(name,value,jsonl)
            d.active_write_errors.pop(name,None)
        except (OSError,ValueError,TypeError) as exc:record_error(d,name,exc)
    try:
        for name,value,jsonl in documents(d):publish(name,value,jsonl)
        perf=d.performance_summary();publish('performance_summary.json',perf)
        publish('slow_years.json',perf['slow_years']);publish('performance_recent_1000y.csv',csv_file=True)
        publish('diagnostic_summary.md',summary_text(d))
        publish('game_metadata.json',d.metadata())
        if not d.last_flush_errors:d.last_flush=d.engine.year
    finally:
        elapsed=(time.perf_counter()-start)*1000;d.io_ms+=elapsed
        if d.performance and d.performance[-1]['year']==d.engine.year:
            row=d.performance[-1];row['diagnostic_flush_ms']=row.get('diagnostic_flush_ms',0.)+elapsed
        d.last_io_year=d.engine.year
    return d.output

def export(d,path=None):
    if not d.enabled:raise RuntimeError('診斷未開啟；請先啟用設定並重新啟動，無法補造歷史。')
    if d.flags['stagnation']:d.analyze_stagnation()
    target=Path(path or d.output.parent/'diagnostic_package.zip');target.parent.mkdir(parents=True,exist_ok=True)
    # Export from current in-memory data, independent of locked public CSV/JSON files.
    with tempfile.TemporaryDirectory(prefix='diagnostic_export_',dir=target.parent) as temp:
        folder=Path(temp);w=writer(d)
        for name,value,jsonl in documents(d,include_state=False):w.write(name,value,jsonl,folder)
        perf=d.performance_summary();w.write('performance_summary.json',perf,directory=folder)
        w.write('slow_years.json',perf['slow_years'],directory=folder);w.csv(folder)
        w.write('game_metadata.json',d.metadata(),directory=folder)
        w.write('diagnostic_summary.md',summary_text(d),directory=folder)
        fd,tempzip=tempfile.mkstemp(prefix='.'+target.name+'.',suffix='.tmp',dir=target.parent);os.close(fd)
        try:
            with zipfile.ZipFile(tempzip,'w',zipfile.ZIP_DEFLATED) as z:
                for f in sorted(folder.iterdir()):z.write(f,'diagnostics/'+f.name)
            os.replace(tempzip,target);tempzip=None
        finally:
            if tempzip is not None:
                try:os.unlink(tempzip)
                except OSError:pass
    return target

def install_metrics(cls):
    original_metadata=cls.metadata;original_performance=cls.performance_summary
    def metadata(d):
        value=original_metadata(d)
        value['diagnostic_io']={'state_file':'diagnostic_state.json.gz','legacy_json_read_supported':True,
            'next_automatic_flush_year':d.next_flush_year,'last_attempt_year':d.last_flush_attempt,
            'last_successful_flush_year':d.last_flush,'active_write_errors':d.active_write_errors,
            'io_timing_through_year':d.last_io_year,'snapshot_io_timing_note':'This snapshot includes completed previous flushes; its own write is charged after completion and appears in the next snapshot/export.',
            'legacy_rows_missing_flush_timing':sum('diagnostic_flush_ms' not in r for r in d.performance)}
        return value
    def performance(d):
        value=original_performance(d)
        io_total=sum(r.get('diagnostic_flush_ms',0.) for r in d.performance)
        value.update(diagnostic_flush_total_ms=io_total,
            simulation_with_diagnostics_total_ms=value['simulation_total_ms']+io_total,
            total_recorded_ms=value['simulation_total_ms']+io_total+value['ui_total_ms'],
            average_with_diagnostics_ms=(value['simulation_total_ms']+io_total)/max(1,len(d.performance)),
            io_timing_through_year=d.last_io_year,
            legacy_rows_missing_flush_timing=sum('diagnostic_flush_ms' not in r for r in d.performance))
        return value
    cls.metadata=metadata;cls.performance_summary=performance
