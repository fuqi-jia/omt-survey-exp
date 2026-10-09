"""Evidence-bound postprocessing of native allocation failures.

The frozen runner and platform metrics are never changed. Only the exact
OptiMathSAT allocation-error response observed in this campaign is recognized;
other solver/worker errors remain unresolved. Every review is checked again
against the complete raw archive before publication.
"""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import sys

OOM_OUTPUT = b'(error "std::bad_alloc")\n'
POLICY = 'oms-lia-exact-bad-alloc-v1'


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def check_evidence(review, metrics, provenance, stdout, stderr, worker_stderr):
    """Fail closed if a review does not match the retained native evidence."""
    assert review['policy'] == POLICY
    assert review['variant'] == 'oms_lia'
    assert review['reported_status'] == 'solver_error'
    assert review['effective_status'] == 'oom'
    assert review['metrics_sha256'] == digest_json(metrics)
    assert metrics['suite'] == 'bv_lia' and metrics['case'] == review['case']
    result = metrics['results']['oms_lia']
    assert result['status'] == 'solver_error'
    assert result['returncode'] == 0 and result['solver_returncode'] == 1
    assert result['budget_s'] == 600 and result['priority'] == 'lex'
    assert provenance['input']['id'] == review['case']
    assert provenance['input']['sha256'] == review['source_sha256']
    assert provenance['input']['suite'] == 'bv_lia'
    assert provenance['memory_bytes'] == 8 * 1024**3
    assert provenance['budget_s'] == 600
    assert review['provenance_sha256'] == digest_json(provenance)
    assert stdout == OOM_OUTPUT and stderr == worker_stderr == b''
    assert review['native_stdout_sha256'] == hashlib.sha256(stdout).hexdigest()


class StatusReviews:
    def __init__(self, out):
        self.path = Path(out) / 'status-reviews.json'
        self.records = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.executors = None

    def classify(self, run, variant, metrics, expected):
        result = metrics['results'][variant]
        original = result.get('status', 'missing_status')
        if not (expected['suite'] == 'bv_lia' and variant == 'oms_lia'
                and original == 'solver_error' and result.get('returncode') == 0
                and result.get('solver_returncode') == 1):
            return original, None
        key = run['id'] + ':' + variant
        signature = dict(metrics_sha256=digest_json(metrics),
                         started_at=run['started_at'], infra_attempt=run['infra_attempt'])
        old = self.records.get(key)
        if old and all(old[k] == v for k, v in signature.items()):
            assert old['case'] == expected['id'] and old['source_sha256'] == expected['sha256']
            assert old['policy'] == POLICY and old['effective_status'] == 'oom'
            return old['effective_status'], key

        # Read only tiny response files; unexpected large output is not silently
        # classified. All I/O concerns remain unresolved errors in the snapshot.
        try:
            if self.executors is None:
                sys.path[:0] = ['/pub/data/jiafq/experimentos/src',
                                '/pub/data/jiafq/experimentos/pylibs']
                from eos.config import load_config
                from eos.api.app import _build_executors
                self.executors = _build_executors(load_config('/pub/data/jiafq/experimentos/config.toml'))
            from eos.models import InfraError
            code = 'BASE=' + repr(run['workdir']) + '''
import json
from pathlib import Path
p=Path(BASE)/'evidence'
files={}
for name in ['oms_lia.native.stdout','oms_lia.native.stderr','oms_lia.solve.stderr']:
 q=p/name
 assert q.stat().st_size<=256
 files[name]=q.read_bytes().decode('utf-8')
print(json.dumps({'files':files,'provenance':json.loads((p/'provenance.json').read_text())}))
'''
            try:
                probe = self.executors[run['host']].run('python3 -c ' + shlex.quote(code), timeout=60)
            except InfraError:
                return original, None
            if probe.exit_code:
                return original, None
            data = json.loads(probe.stdout)
            stdout = data['files']['oms_lia.native.stdout'].encode()
            record = dict(policy=POLICY, run=run['id'], variant=variant,
                case=expected['id'], source_sha256=expected['sha256'], host=run['host'],
                workdir=run['workdir'], observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                reported_status=original, effective_status='oom', **signature,
                provenance_sha256=digest_json(data['provenance']),
                native_stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                native_stdout=data['files']['oms_lia.native.stdout'],
                memory_bytes=8 * 1024**3,
                interpretation='Native allocation failure under the unchanged address-space limit; unsolved outcome, no retry or optimality claim.')
            check_evidence(record, metrics, data['provenance'], stdout,
                           data['files']['oms_lia.native.stderr'].encode(),
                           data['files']['oms_lia.solve.stderr'].encode())
        except (AssertionError, OSError, KeyError, ValueError):
            return original, None
        self.records[key] = record
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.records, indent=2) + '\n')
        temporary.replace(self.path)
        return 'oom', key
