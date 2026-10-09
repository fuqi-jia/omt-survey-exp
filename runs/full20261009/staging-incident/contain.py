from pathlib import Path
import datetime, json, sys
sys.path[:0]=['/pub/data/jiafq/experimentos/src','/pub/data/jiafq/experimentos/pylibs']
from eos.store import Store
from eos.db.conn import connect
root=Path('/pub/data/jiafq/omt-survey-exp')
out=root/'runs/full20261009/staging-incident'
out.mkdir(exist_ok=True)
store=Store(connect(Path('/pub/data/jiafq/eos/eos.db')))
eid='bcac3b19f39f'
exp=store.get_experiment(eid)
assert exp['name']=='jos-full-bv_lia-20261009-r1'
before=out/'experiment-before-containment.json'
if not before.exists():before.write_text(json.dumps(exp,ensure_ascii=False,indent=2)+'\n')
reason='Own-campaign staging incident: copied source .eos-stage.json preceded complete LIA inputs on Panda3/6; hold new dispatch until full file-presence audit passes. Existing runs continue; failed pre-solver attempts will be archived and retried.'
assert exp['status'] not in ['completed','cancelled']
store.mark_experiment_broken(eid,reason)
marker=root/'benchmarks/full_public/extracted/bv/.eos-stage.json'
saved=out/'control-marker-before.json'
if marker.exists():
 data=json.loads(marker.read_text())
 assert data['src']==str(marker.parent)
 if saved.exists():assert marker.read_bytes()==saved.read_bytes()
 else:marker.rename(saved)
receipt={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'experiment':eid,'action':'Hold this experiment via Store.mark_experiment_broken; move own control-side derived staging marker to incident evidence so later rsync cannot advertise completeness before inputs arrive. No solver, input, manifest, spec, or global scheduler changes.','reason':reason,'source_marker_present':marker.exists()}
(out/'containment.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt),flush=True)
