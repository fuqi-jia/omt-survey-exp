import datetime,json,shlex,sqlite3,sys,tarfile
from pathlib import Path
root=Path('/pub/data/jiafq/omt-survey-exp');out=root/'runs/full20261009';incident=out/'staging-incident'
sys.path[:0]=[str(root/'scripts/full_campaign'),'/pub/data/jiafq/experimentos/src','/pub/data/jiafq/experimentos/pylibs']
import archive_results as archive
from eos.config import load_config
from eos.api.app import _build_executors
exs=_build_executors(load_config('/pub/data/jiafq/experimentos/config.toml'))
con=sqlite3.connect('file:/pub/data/jiafq/eos/eos.db?mode=ro',uri=True);con.row_factory=sqlite3.Row
exp=dict(con.execute('select * from experiment where id=?',('bcac3b19f39f',)).fetchone())
assert exp['name']=='jos-full-bv_lia-20261009-r1'
assert exp['error'].startswith('Own-campaign staging incident:'), (exp['status'],exp['error'])
rows=[dict(r) for r in con.execute("select * from run where experiment_id=? and status='invalid'",(exp['id'],))]
records=[];raw=out/'raw/staging-incident';raw.mkdir(parents=True,exist_ok=True)
for row in rows:
 rid=row['id'];ex=exs[row['host']];expected={rid:json.loads(row['input_meta_json'])}
 metrics=json.loads(row['metrics_json'])
 if not all(r['status']=='worker_error' for r in metrics['results'].values()):
  print('SEPARATE_INVESTIGATION_REQUIRED',rid,flush=True);continue
 stderr={v:ex.read_text(row['workdir']+'/evidence/'+v+'.solve.stderr') for v in ['oms_lia','z3_lia']}
 if not all('FileNotFoundError:' in s and '/benchmarks/full_public/extracted/bv/' in s for s in stderr.values()):
  print('SEPARATE_INVESTIGATION_REQUIRED',rid,stderr,flush=True);continue
 record_path=incident/(rid+'-failed-attempt.json')
 if not record_path.exists():
  record_path.write_text(json.dumps({'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'run':row,'stderr':stderr,'classification':'infrastructure_missing_input_before_solver_invocation'},indent=2)+'\n')
 target=raw/(rid+'.tar.gz')
 if not target.exists():
  source=raw/'staged'/target.name
  config=dict(target=str(source),experiment_name=exp['name'],host=row['host'],runs=[dict(id=rid,workdir=row['workdir'])])
  config_path=incident/(rid+'-archive-request.json');config_path.write_text(json.dumps(config,indent=2)+'\n')
  remote_config='/tmp/jos-staging-'+rid+'.json';ex.put(config_path,remote_config)
  code='CONFIG_PATH='+repr(remote_config)+'\n'+archive.PACKER
  result=ex.run('python3 -c '+shlex.quote(code),timeout=120)
  assert result.exit_code==0,result.stderr
  partial=target.with_suffix('.download');ex.get(str(source),partial)
  archive.verify(partial,expected);partial.rename(target)
 verification=archive.verify(target,expected)
 with tarfile.open(target) as tar:
  for variant in ['oms_lia','z3_lia']:
   assert tar.extractfile(rid+'/evidence/'+variant+'.solve.stderr').read().decode()==stderr[variant]
 receipt=dict(host=row['host'],run=rid,case=expected[rid]['case_id'],original_workdir=row['workdir'],infra_attempt=row['infra_attempt'],archive=verification)
 (incident/(rid+'-archive-verification.json')).write_text(json.dumps(receipt,indent=2)+'\n')
 records.append(receipt)
 print('ARCHIVED_BEFORE_RETRY',rid,row['host'],verification['files'],verification['sha256'],flush=True)
(incident/'archived-failures.json').write_text(json.dumps(records,indent=2)+'\n')
