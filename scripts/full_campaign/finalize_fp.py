#!/usr/bin/env python3
"""Audit every raw FP file, filling the original generator's missing defined objectives."""
import hashlib,json,re,bisect
from collections import defaultdict
from pathlib import Path
import prepare
import run_case
import z3

ROOT=prepare.ROOT;DATA=prepare.DATA;base=prepare.EXTRACTED/'fp'
supplement_path=DATA/'fp-supplement.json'
coverage=[];supplement=json.loads(supplement_path.read_text()) if supplement_path.exists() else [];missing=[]
for record in supplement:
 assert prepare.sha(ROOT/record['generated'])==record['sha256']
index=defaultdict(list)
for path in (base/'obench').rglob('*.smt2'):index[path.parent].append(path.name)
for names in index.values():names.sort()
for source in sorted((base/'bench').rglob('*.smt2')):
 relative=source.relative_to(base/'bench');directory=base/'obench'/relative.parent
 prefix=source.stem+'.'
 names=index[directory]
 outputs=[directory/name for name in names[bisect.bisect_left(names,prefix):bisect.bisect_left(names,prefix+'\uffff')]]
 if not outputs:
  # The published script scans only declare-fun for Schanda. Some source files
  # expose their FP values via zero-argument define-fun instead (e.g. rounding
  # mode diagnostics). Retain these sources as explicit additional tasks.
  commands=list(run_case.split_commands(source.read_text()))
  retained=[c for c in commands if not re.match(r'\((?:set-|get-|check-sat|exit)',c)]
  context='\n'.join(retained)
  candidates=[]
  for c in retained:
   m=re.match(r'\((?:declare|define)-fun\s+(\|[^|]*\||[^\s()]+)\s*\(\s*\)',c)
   if not m:continue
   name=m.group(1)
   parsed=z3.parse_smt2_string(context+f'\n(assert (= {name} {name}))')
   if z3.is_fp(parsed[-1].arg(0)):candidates.append(name)
  kind='all named nullary FP terms omitted by upstream objective scan'
  if not candidates:
   assertions=z3.parse_smt2_string(context)
   todo=list(assertions);seen=set()
   while todo:
    expr=todo.pop()
    if expr.get_id() in seen:continue
    seen.add(expr.get_id())
    if z3.is_fp(expr):
     candidates=[expr.sexpr()];break
    todo.extend(expr.children())
   kind='first deterministic FP subterm; no named nullary FP target in raw source'
  if not candidates:
   # One upstream Griggio file contains only metadata, check-sat and exit.
   # Keep this degenerate source in coverage as a constant-objective task;
   # it supplies no evidence about FP arithmetic performance.
   assert not list(z3.parse_smt2_string(context)),relative
   candidates=['(_ +zero 8 24)']
   kind='empty upstream formula; constant binary32 zero objective, degenerate feasibility check'
  for i,term in enumerate(candidates):
   for sense in ['minimize','maximize']:
    p=directory/(source.stem+f'.supplement_{i}.{sense}.smt2');p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('(set-option :produce-models true)\n'+context+f'\n({sense} {term})\n(check-sat)\n(get-objectives)\n')
    outputs.append(p)
    supplement.append(dict(source=source.relative_to(ROOT).as_posix(),source_sha256=prepare.sha(source),
                           generated=p.relative_to(ROOT).as_posix(),target=term,rule=kind,sha256=prepare.sha(p)))
 coverage.append(dict(source=source.relative_to(ROOT).as_posix(),sha256=prepare.sha(source),
                      outputs=[p.relative_to(ROOT).as_posix() for p in sorted(outputs)]))
(DATA/'fp-source-coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
supplement_path.write_text(json.dumps(supplement,indent=2)+'\n')
assert len(coverage)==17314,(len(coverage),missing)
assert not missing,missing
aliases=[];extra=[]
for p in sorted((base/'o300').rglob('*.smt2')):
 g=base/'obench'/p.relative_to(base/'o300')
 if g.exists() and prepare.sha(g)==prepare.sha(p):
  aliases.append(dict(published=p.relative_to(ROOT).as_posix(),generated=g.relative_to(ROOT).as_posix(),sha256=prepare.sha(p)))
 else:extra.append(p)
(DATA/'fp-published-aliases.json').write_text(json.dumps(aliases,indent=2)+'\n')
assert len(aliases)+len(extra)==1120
paths=sorted((base/'obench').rglob('*.smt2'))+extra
prepare.manifest('fp',paths,dict(raw_sources=17314,raw_sources_with_tasks=len(coverage),
                 published=1120,published_aliases=len(aliases),published_extra=len(extra),
                 supplemental_tasks=len(supplement),sampling=False,
                 degenerate_tasks=sum('empty upstream formula' in r['rule'] for r in supplement),
                 generator_sha256=prepare.sha(base/'bin/run_translation_all_statuses.sh')))
print('ALL_RAW_SOURCES_COVERED',len(coverage),'SUPPLEMENTAL_TASKS',len(supplement))
