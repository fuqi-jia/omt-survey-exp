import concurrent.futures, datetime, json, shlex, sqlite3, sys
from pathlib import Path
sys.path[:0]=['/pub/data/jiafq/experimentos/src','/pub/data/jiafq/experimentos/pylibs']
from eos.config import load_config
from eos.api.app import _build_executors
exs=_build_executors(load_config('/pub/data/jiafq/experimentos/config.toml'))
root=Path('/pub/data/jiafq/omt-survey-exp');out=root/'runs/full20261009'
con=sqlite3.connect('file:/pub/data/jiafq/eos/eos.db?mode=ro',uri=True)
hosts=[r[0] for r in con.execute("select distinct host from run r join experiment e on r.experiment_id=e.id where e.name like 'jos-full-%-20261009-r1' and host!='' order by host")]
code='''from pathlib import Path
import json,hashlib
root=Path('/pub/data/jiafq/omt-survey-exp')
results={}
for suite in ['bv','bv_lia']:
 rows=[json.loads(l) for l in (root/'benchmarks/full_public/manifests'/(suite+'.jsonl')).read_text().splitlines()]
 missing=[];mismatched=[]
 for row in rows:
  p=root/row['path']
  if not p.exists():missing.append({'case':row['id'],'path':row['path']})
  elif p.stat().st_size!=row['bytes']:mismatched.append({'case':row['id'],'bytes':p.stat().st_size,'expected':row['bytes']})
 results[suite]={'expected':len(rows),'missing':missing,'size_mismatches':mismatched}
 if suite=='bv_lia':
  row=next(r for r in rows if r['id']=='337925e0aee91077116e')
  p=root/row['path']
  results[suite]['failed_case_now_sha256']=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
p=root/'benchmarks/full_public/extracted/bv/.eos-stage.json'
results['stage_marker']=p.read_text() if p.exists() else None
print(json.dumps(results))
'''
def check(host):
 r=exs[host].run('python3 -c '+shlex.quote(code),timeout=60)
 if r.exit_code:return host,{'error':r.stderr[-500:]}
 return host,json.loads(r.stdout)
records={}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for host,data in pool.map(check,hosts):
  records[host]=data
  print(host,json.dumps(data,ensure_ascii=False),flush=True)
report={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'All 508 expected BV/LIA file paths and sizes on every execution host; SHA256 of the infrastructure-failed input additionally checked. Each solver invocation separately verifies its full source hash.','hosts':records}
(out/'stage-presence-audit.json').write_text(json.dumps(report,indent=2)+'\n')
