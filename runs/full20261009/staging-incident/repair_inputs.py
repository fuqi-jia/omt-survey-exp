import concurrent.futures, datetime, json, shlex, sys
from pathlib import Path
sys.path[:0]=['/pub/data/jiafq/experimentos/src','/pub/data/jiafq/experimentos/pylibs']
from eos.config import load_config
from eos.api.app import _build_executors
root=Path('/pub/data/jiafq/omt-survey-exp');out=root/'runs/full20261009'
incident=out/'staging-incident'
initial=incident/'initial-stage-presence-audit.json'
if not initial.exists():initial.write_bytes((out/'stage-presence-audit.json').read_bytes())
inventory=json.loads(initial.read_text())
hosts=[h for h,d in inventory['hosts'].items() if any(d.get(s,{}).get('missing') or d.get(s,{}).get('size_mismatches') for s in ['bv','bv_lia'])]
assert set(hosts)=={'panda3','panda6'}
src=root/'benchmarks/full_public/extracted/bv'
assert not (src/'.eos-stage.json').exists()
exs=_build_executors(load_config('/pub/data/jiafq/experimentos/config.toml'))
code='''from pathlib import Path
import hashlib,json,time
root=Path('/pub/data/jiafq/omt-survey-exp');start=time.monotonic();records=[]
for suite in ['bv','bv_lia']:
 manifest=root/'benchmarks/full_public/manifests'/(suite+'.jsonl')
 rows=[json.loads(l) for l in manifest.read_text().splitlines()]
 for row in rows:
  p=root/row['path'];digest=hashlib.sha256()
  with p.open('rb') as stream:
   while True:
    chunk=stream.read(4*1024*1024)
    if not chunk:break
    digest.update(chunk)
  assert p.stat().st_size==row['bytes'] and digest.hexdigest()==row['sha256'],row['id']
  records.append({'case':row['id'],'sha256':digest.hexdigest(),'bytes':row['bytes']})
print(json.dumps({'verified_inputs':len(records),'elapsed_s':time.monotonic()-start,'records':records}))
'''
def repair(host):
 ex=exs[host]
 result=ex.run("python3 -c 'import json,shutil;u=shutil.disk_usage(\"/pub/data/jiafq\");print(json.dumps({\"free\":u.free,\"total\":u.total}))'",timeout=60)
 assert result.exit_code==0
 space=json.loads(result.stdout);assert space['free']>15*1024**3,space
 print(host,'DISK',json.dumps(space),'starting incremental repair',flush=True)
 ex.put_tree(src,str(src),timeout=1800)
 result=ex.run('python3 -c '+shlex.quote(code),timeout=1800)
 assert result.exit_code==0,(host,result.stderr[-1000:])
 report=json.loads(result.stdout);assert report['verified_inputs']==508
 report.update(host=host,observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),disk_before=space)
 (incident/(host+'-full-hash-repair.json')).write_text(json.dumps(report,indent=2)+'\n')
 print(host,'VERIFIED',report['verified_inputs'],'inputs',flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 list(pool.map(repair,hosts))
print('REPAIR_COMPLETE: both hosts have every original BV/LIA input with the frozen content hash',flush=True)
