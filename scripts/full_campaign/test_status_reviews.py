"""Ensure postprocessing cannot turn arbitrary failures into accepted outcomes."""
import hashlib
import unittest
from status_reviews import POLICY, OOM_OUTPUT, check_evidence, digest_json


class AllocationReviewTests(unittest.TestCase):
    def setUp(self):
        self.metrics = dict(suite='bv_lia', case='case', results={'oms_lia': dict(
            status='solver_error', returncode=0, solver_returncode=1,
            budget_s=600, priority='lex')})
        self.provenance = dict(input=dict(id='case', sha256='source', suite='bv_lia'),
                               budget_s=600, memory_bytes=8 * 1024**3)
        self.review = dict(policy=POLICY, variant='oms_lia', case='case', source_sha256='source',
            reported_status='solver_error', effective_status='oom',
            metrics_sha256=digest_json(self.metrics), provenance_sha256=digest_json(self.provenance),
            native_stdout_sha256=hashlib.sha256(OOM_OUTPUT).hexdigest())

    def check(self, output=OOM_OUTPUT):
        check_evidence(self.review, self.metrics, self.provenance, output, b'', b'')

    def test_exact_native_response(self):
        self.check()

    def test_other_error_is_not_allocation_evidence(self):
        with self.assertRaises(AssertionError):
            self.check(b'(error "parser failed")\n')

    def test_stale_metrics_rejected(self):
        self.metrics['results']['oms_lia']['wall_s'] = 99
        with self.assertRaises(AssertionError):
            self.check()

    def test_changed_resource_budget_rejected(self):
        self.provenance['memory_bytes'] *= 2
        self.review['provenance_sha256'] = digest_json(self.provenance)
        with self.assertRaises(AssertionError):
            self.check()

    def test_wrong_source_rejected(self):
        self.review['source_sha256'] = 'different'
        with self.assertRaises(AssertionError):
            self.check()

    def test_signal_exit_not_inferred_as_oom(self):
        self.metrics['results']['oms_lia']['solver_returncode'] = -9
        self.review['metrics_sha256'] = digest_json(self.metrics)
        with self.assertRaises(AssertionError):
            self.check()


if __name__ == '__main__':
    unittest.main()
