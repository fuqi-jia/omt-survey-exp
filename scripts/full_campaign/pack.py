#!/usr/bin/env python3
"""Repack exact source bytes for transport, excluding historical solver binaries/logs."""
import argparse,hashlib,io,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'benchmarks/full_public'
ap=argparse.ArgumentParser();ap.add_argument('suite',choices=['fp','bv']);args=ap.parse_args()
if args.suite=='fp':
 archive=DATA/'downloads/fp-layer.tar.gz'
 if not archive.exists():archive=ROOT/'benchmarks/public_fp/upstream-layer.tar.gz'
else:archive=DATA/'downloads/tacas16.tar.gz'
rows=[];out=DATA/'downloads'/(args.suite+'-inputs.tar.xz')
with tarfile.open(archive) as t,tarfile.open(out,'w:xz',preset=6) as o:
 for m in t:
  if not m.isfile():continue
  if args.suite=='fp':
   parts=m.name.split('/')[2:]
   accept=parts[0]=='bench' or (parts[0]=='bin' and parts[1]=='run_translation.sh') or (parts[0]=='o300' and m.name.endswith('.smt2') and not m.name.endswith(('.fp_to_bv.smt2','.sat.smt2','.unsat.smt2')))
   if not accept:continue
   data=t.extractfile(m).read();info=tarfile.TarInfo('/'.join(parts));info.size=len(data)
   o.addfile(info,io.BytesIO(data));rows.append(dict(path=info.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
  elif m.name.endswith(('.smt2','/README.txt')):
   o.addfile(m,t.extractfile(m));rows.append(dict(path=m.name,bytes=m.size))
(DATA/(args.suite+'-source-members.json')).write_text(json.dumps(rows,indent=2)+'\n')
print(out,len(rows),out.stat().st_size)
