#!/usr/bin/env python3
"""Parse every manifested input before the performance campaign; no sampling."""
import argparse,fcntl,json,time
from pathlib import Path
import run_case as runner
import z3

ap=argparse.ArgumentParser();ap.add_argument('suite');args=ap.parse_args()
path=runner.DATA/'manifests'/(args.suite+'.jsonl')
out=runner.ROOT/'runs/full20261009'/('parse-'+args.suite+'.json')
lock=out.with_suffix('.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX)
rows=[json.loads(line) for line in path.read_text().splitlines()]
adapter=Path(runner.__file__) if args.suite!='bv_lia' else Path(__file__).with_name('run_lia_diagnostic.py')
fingerprint=dict(manifest_sha256=runner.sha(path),adapter_sha256=runner.sha(adapter),
                common_source_sha256=runner.sha(Path(runner.__file__)),
                parser_sha256=runner.sha(runner.ROOT/'scripts/revision_public_fp.py'),
                solver_library_sha256=runner.sha(Path(z3.__file__).parent/'lib/libz3.so'))
if out.exists():
 cached=json.loads(out.read_text())
 if cached.get('passed') and cached.get('inputs')==len(rows) and all(cached.get(k)==v for k,v in fingerprint.items()):
  assert all(runner.sha(runner.ROOT/r['path'])==r['sha256'] for r in rows)
  print('Reused complete parse audit after rechecking every source hash:',args.suite,len(rows),flush=True)
  raise SystemExit(0)
errors=[];count=0;start=time.monotonic()
interval=min(1000,max(10,len(rows)//20))
for row in rows:
 count+=1
 try:
  if args.suite=='bv_lia':
   import run_lia_diagnostic as diagnostic
   source=runner.ROOT/row['path'];assert runner.sha(source)==row['sha256']
   p=diagnostic.parse_input(source)
  else:p=runner.load_problem(row)
  if args.suite=='fp':
   import z3
   assert z3.is_fp(p['target'])
  elif args.suite=='bv':
   import z3
   assert z3.is_bv(p['target'])
 except Exception as e:
  errors.append(dict(id=row['id'],path=row['path'],error=str(e)))
 if count%interval==0:print(count,'parsed',len(errors),'errors',flush=True)
record=dict(suite=args.suite,inputs=count,errors=errors,passed=not errors,
            **fingerprint,elapsed_s=time.monotonic()-start)
out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(inputs=count,errors=len(errors),elapsed_s=record['elapsed_s'])),flush=True)
raise SystemExit(bool(errors))
