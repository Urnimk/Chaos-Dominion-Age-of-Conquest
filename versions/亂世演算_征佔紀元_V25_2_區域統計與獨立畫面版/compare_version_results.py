"""Compare two locally generated verification .pickle files, field by field."""
import argparse,pickle,json
from pathlib import Path
import numpy as np
import war_engine  # Campaign class required when reading active campaign records.
p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);a=p.parse_args()
before=pickle.loads(a.before.read_bytes());after=pickle.loads(a.after.read_bytes())
result={key:bool(np.array_equal(before[key],after[key]) if isinstance(before[key],np.ndarray) else before[key]==after[key]) for key in before}
print(json.dumps(result,ensure_ascii=False,indent=2))
if not all(result.values()):raise SystemExit(1)
print('PASS: authoritative state, Q tables and RNG are exactly equal')
