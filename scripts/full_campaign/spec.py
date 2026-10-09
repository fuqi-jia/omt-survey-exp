#!/usr/bin/env python3
"""Write an ExperimentOS specification covering every frozen manifest row."""
import argparse,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
REMOTE='/pub/data/jiafq/omt-survey-exp'


def main():
 ap=argparse.ArgumentParser();ap.add_argument('suite',choices=['fp','bv','bv_lia','maxsmt']);args=ap.parse_args()
 manifests=ROOT/'benchmarks/full_public/manifests'
 path=manifests/(args.suite+'.jsonl');data=path.read_bytes();offset=0;rows=[]
 for line in data.splitlines(keepends=True):
  row=json.loads(line)
  rows.append(dict(path=f'{args.suite}@{offset}',meta=dict(case_id=row['id'],suite=args.suite,source_sha256=row['sha256'],input_bytes=row['bytes'])))
  offset+=len(line)
 # All rows are retained. Deterministic order spreads families across the queue.
 rows.sort(key=lambda r:hashlib.sha256(r['meta']['case_id'].encode()).hexdigest())
 # A deterministic smallest input opens the platform's canary gate promptly;
 # every remaining input is still submitted at the same full budget.
 invalid_file=manifests/(args.suite+'-invalid.json')
 invalid=json.loads(invalid_file.read_text()) if invalid_file.exists() else {}
 first=min((r for r in rows if r['meta']['case_id'] not in invalid),key=lambda r:(r['meta']['input_bytes'],r['meta']['case_id']))
 rows.remove(first);rows.insert(0,first)
 inputs=manifests/(args.suite+'-eos.jsonl')
 inputs.write_text(''.join(json.dumps(row)+'\n' for row in rows))
 raw_suite='bv' if args.suite=='bv_lia' else args.suite
 variants=4 if args.suite=='maxsmt' else 3 if args.suite=='fp' else 2
 spec=dict(experiment='jos-full-'+args.suite+'-20261009-r1',
  description=f'Full public {args.suite}: {len(rows)} inputs, no sampling; paired solvers, 600 s each. Manifest '+hashlib.sha256(data).hexdigest(),
  environment=dict(host={'tags':['cpu']},workdir=REMOTE,require={'python3':'>=3.9'},
   data=[REMOTE+'/scripts',REMOTE+'/tools/full-python',REMOTE+'/tools/optimathsat-1.7.4-linux-64-bit',
         REMOTE+'/benchmarks/full_public/manifests',REMOTE+'/benchmarks/full_public/extracted/'+raw_suite]),
  protocol=dict(inputs={'from_file':REMOTE+'/'+inputs.relative_to(ROOT).as_posix()},
                timeout=f'{variants*780+180}s',memory='16G',parallelism=192,retain='365d'),
  trials=[{'name':'paired-solvers','params':{'harness_sha256':hashlib.sha256((ROOT/'scripts/full_campaign/run_case.py').read_bytes()).hexdigest()}}],
  run=dict(cmd='python3 '+REMOTE+'/scripts/full_campaign/run_case.py --case {input} --metrics "$EOS_METRICS_FILE"'),
  measurements={'from':'metrics.json','primary':'wall_time_s','checks':['completed == true','pipeline_ok == true']},
  artifacts={'collect':['evidence/*.json','evidence/*.stdout','evidence/*.stderr']})
 out=ROOT/'runs/full20261009';out.mkdir(parents=True,exist_ok=True)
 # JSON is a YAML subset, accepted by ExperimentOS without a writer dependency.
 target=out/(args.suite+'.yaml');target.write_text(json.dumps(spec,indent=2)+'\n')
 print(target,len(rows),'inputs',variants*len(rows),'solver invocations')


if __name__=='__main__':main()
