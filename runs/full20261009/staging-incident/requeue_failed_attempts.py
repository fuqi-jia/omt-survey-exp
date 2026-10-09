import datetime,json,shlex,subprocess,sys
from pathlib import Path
root=Path('/pub/data/jiafq/omt-survey-exp');out=root/'runs/full20261009';incident=out/'staging-incident'
sys.path[:0]=[str(root/'scripts/full_campaign'),'/pub/data/jiafq/experimentos/src','/pub/data/jiafq/experimentos/pylibs']
import archive_results as archive
from eos.config import load_config
from eos.api.app import _build_executors
from eos.db.conn import connect
from eos.store import Store
store=Store(connect(Path('/pub/data/jiafq/eos/eos.db')))
eid='bcac3b19f39f';exp=store.get_experiment(eid)
assert exp['name']=='jos-full-bv_lia-20261009-r1'
assert exp['status']=='broken' and exp['error'].startswith('Own-campaign staging incident:'),(exp['status'],exp['error'])
for host in ['panda3','panda6']:
 repaired=json.loads((incident/(host+'-full-hash-repair.json')).read_text())
 assert repaired['verified_inputs']==508
assert not (root/'benchmarks/full_public/extracted/bv/.eos-stage.json').exists()
exs=_build_executors(load_config('/pub/data/jiafq/experimentos/config.toml'))
receipts=json.loads((incident/'archived-failures.json').read_text())
done=[]
for receipt in receipts:
 rid=receipt['run'];row=store.get_run(rid)
 assert row['experiment_id']==eid and row['status']=='invalid' and row['infra_attempt']==receipt['infra_attempt'],rid
 expected={rid:json.loads(row['input_meta_json'])}
 verified=archive.verify(root/receipt['archive']['path'],expected)
 assert verified['sha256']==receipt['archive']['sha256']
 preserved=row['workdir']+'.infra'+str(row['infra_attempt'])+'-preserved'
 code='BASE='+repr(row['workdir'])+'\nSAVED='+repr(preserved)+'''\nfrom pathlib import Path\np=Path(BASE);q=Path(SAVED)\nassert p.parent==q.parent and p.parent.name=='jos-full-bv_lia-20261009-r1'\nif p.exists():\n assert not q.exists()\n assert (p/'exit_code').read_text().strip()=='0'\n p.rename(q)\nassert q.is_dir() and not p.exists()\nprint(str(q))\n'''
 result=exs[row['host']].run('python3 -c '+shlex.quote(code),timeout=60)
 assert result.exit_code==0,result.stderr
 reason='Input staging infrastructure failure before both solvers started; full input hashes repaired. Original attempt archived '+verified['sha256']+'; original directory preserved at '+preserved
 record=dict(observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),run=rid,case=receipt['case'],old_host=row['host'],preserved_workdir=preserved,archive=verified,reason=reason)
 (incident/(rid+'-retry-receipt.json')).write_text(json.dumps(record,indent=2)+'\n')
 store.release_to_pending(rid,reason)
 changed=store.get_run(rid);assert changed['status']=='pending' and changed['infra_attempt']==row['infra_attempt']+1
 done.append(rid);print('REQUEUED_SAME_RUN_ID',rid,flush=True)
result=subprocess.run(['/pub/data/jiafq/experimentos/eos','resume',eid,'--yes'],cwd='/pub/data/jiafq/experimentos',capture_output=True,text=True)
assert result.returncode==0,(result.stdout,result.stderr)
(incident/'resume.log').write_text(result.stdout+result.stderr)
record=dict(observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),experiment=eid,requeued=done,original_attempts_preserved=True,solver_protocol_changed=False)
(incident/'requeue-complete.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
