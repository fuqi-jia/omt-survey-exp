#!/usr/bin/env python3
"""Read only this campaign's ExperimentOS state on its control node."""
import datetime,json,sqlite3
from pathlib import Path

ROOT=Path('/pub/data/jiafq/omt-survey-exp')
con=sqlite3.connect('file:/pub/data/jiafq/eos/eos.db?mode=ro',uri=True)
con.row_factory=sqlite3.Row
result={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'experiments':[]}
for e in con.execute("select id,name,status,canary_state,error from experiment where name like 'jos-full-%-20261009-%' order by name"):
 exp=dict(e)
 exp['counts']={r['status']:r['n'] for r in con.execute('select status,count(*) n from run where experiment_id=? group by status',(e['id'],))}
 exp['hosts']=[dict(r) for r in con.execute("select host,status,count(*) n from run where experiment_id=? and status!='pending' group by host,status",(e['id'],))]
 exp['failures']=[dict(r) for r in con.execute("select id,input,host,status,error,log_tail from run where experiment_id=? and status in ('failed','invalid','oom') limit 8",(e['id'],))]
 result['experiments'].append(exp)
out=ROOT/'runs/full20261009/control-status.json'
out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
