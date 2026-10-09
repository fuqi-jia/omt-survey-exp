#!/usr/bin/env python3
"""Parse every manifested input before the performance campaign; no sampling."""
import argparse,json,time
from pathlib import Path
import run_case as runner

ap=argparse.ArgumentParser();ap.add_argument('suite');args=ap.parse_args()
path=runner.DATA/'manifests'/(args.suite+'.jsonl')
errors=[];count=0;start=time.monotonic()
for line in path.read_text().splitlines():
 row=json.loads(line);count+=1
 try:
  p=runner.load_problem(row)
  if args.suite=='fp':
   import z3
   assert z3.is_fp(p['target'])
  elif args.suite=='bv':
   import z3
   assert z3.is_bv(p['target'])
 except Exception as e:
  errors.append(dict(id=row['id'],path=row['path'],error=str(e)))
 if count%1000==0:print(count,'parsed',len(errors),'errors',flush=True)
record=dict(suite=args.suite,inputs=count,errors=errors,passed=not errors,
            manifest_sha256=runner.sha(path),elapsed_s=time.monotonic()-start)
out=runner.ROOT/'runs/full20261009'/('parse-'+args.suite+'.json')
out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(inputs=count,errors=len(errors),elapsed_s=record['elapsed_s'])),flush=True)
raise SystemExit(bool(errors))
