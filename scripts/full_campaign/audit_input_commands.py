#!/usr/bin/env python3
"""Audit objective directions and option directives in every original BV/LIA file.

This supplements the completed full SMT parser audits. It checks the lexical
source directives without solving, rewriting, or selecting performance inputs.
"""
import collections
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'benchmarks/full_public'
OUT = ROOT / 'runs/full20261009'


def main():
    report = {}
    for suite in ['bv', 'bv_lia']:
        manifest = DATA / 'manifests' / (suite + '.jsonl')
        rows = [json.loads(line) for line in manifest.read_text().splitlines()]
        counts, options, records = collections.Counter(), collections.Counter(), []
        for row in rows:
            source = (ROOT / row['path']).read_bytes()
            assert hashlib.sha256(source).hexdigest() == row['sha256']
            # Remove line comments before matching generated top-level commands.
            # These generated benchmark files do not use semicolons in strings.
            clean = re.sub(rb';[^\r\n]*', b'', source)
            goals = collections.Counter(m.group(1).decode() for m in
                re.finditer(rb'\(\s*(minimize|maximize)\b', clean))
            directives = [m.group(0).decode() for m in
                re.finditer(rb'\(\s*set-option\s+[^()]*\)', clean)]
            # A nested or multiline value must not silently evade this audit.
            assert len(directives) == len(re.findall(rb'\(\s*set-option\b', clean))
            assert sum(goals.values()) > 0
            if suite == 'bv':
                assert sum(goals.values()) == 1
            counts.update(goals)
            options.update(directives)
            records.append(dict(case=row['id'], source_sha256=row['sha256'],
                                objectives=dict(goals), options=directives))
        report[suite] = dict(inputs=len(rows),
            manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            objective_directions=dict(counts), option_directives=dict(options), records=records)
        print(suite, len(rows), 'inputs', dict(counts), 'options', dict(options), flush=True)
    (OUT / 'input-commands-audit.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
