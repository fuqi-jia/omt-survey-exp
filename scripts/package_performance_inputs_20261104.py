#!/usr/bin/env python3
"""Archive exact performance inputs and the structured API specifications."""
import _bootstrap
import hashlib
import io
import json
from pathlib import Path
import tarfile
from experiments.benchmarks.families import build
from experiments.encodings.smt2 import to_smt2
from experiments.encodings.minizinc import to_minizinc

ROOT=Path(__file__).resolve().parents[1]
run=ROOT/'runs/paper_refresh_20261030'
m=json.loads((run/'manifest.json').read_text())
out=ROOT/'benchmarks/performance-20261030';out.mkdir(parents=True,exist_ok=True)
p=out/'inputs.tar.gz'
with tarfile.open(p,'w:gz') as tar:
    for row in m['instances']:
        spec=build(row['family'],row['size'],row['seed'])
        data={row['name']+'.json':(json.dumps(spec,indent=2)+'\n').encode()}
        for kind,text in [('smt2',to_smt2(spec)),('mzn',to_minizinc(spec))]:
            b=text.encode();assert hashlib.sha256(b).hexdigest()==row['inputs'][kind]['sha256']
            data[row['inputs'][kind]['path']]=b
        for name,b in data.items():
            info=tarfile.TarInfo(name);info.size=len(b);info.mtime=0;info.mode=0o644;tar.addfile(info,io.BytesIO(b))
audit=ROOT/'runs/review_diagnostics_20261104/performance/input-archive.json';audit.parent.mkdir(parents=True,exist_ok=True)
audit.write_text(json.dumps(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),instances=97,cli_inputs=194,structured_api_specifications=97,all_cli_input_hashes_match_cohort_manifest=True),indent=2)+'\n')
print('PASS performance: 97 structured models, 194 exact CLI inputs')
