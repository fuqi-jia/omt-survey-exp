#!/usr/bin/env python3
"""Finite exhaustive check of the FP ordinal key and Z3's unsigned BV objectives."""
import json
from pathlib import Path
import z3
from revision_public_fp import load_problem


def main():
    eb, sb = 3, 4
    width = eb + sb
    values = []
    for raw in range(1 << width):
        value = z3.simplify(z3.fpBVToFP(z3.BitVecVal(raw, width), z3.FPSort(eb, sb)))
        if z3.is_true(z3.simplify(z3.fpIsNaN(value))):
            continue
        key = (~raw & ((1 << width) - 1)) if raw >> (width - 1) else raw ^ (1 << (width - 1))
        values.append((raw, value, key))
    checked = 0
    for raw_a, a, ka in values:
        for raw_b, b, kb in values:
            both_zero = z3.is_true(z3.simplify(z3.And(z3.fpIsZero(a), z3.fpIsZero(b))))
            lt = z3.is_true(z3.simplify(z3.fpLT(a, b)))
            if both_zero:
                assert (ka < kb) == (raw_a > raw_b)
            else:
                assert (ka < kb) == lt
            checked += 1
    bv = z3.BitVec('unsigned_check', 4)
    for sense, expected in [('min', 1), ('max', 15)]:
        opt = z3.Optimize()
        opt.add(z3.Or(bv == 1, bv == 15))
        handle = opt.minimize(bv) if sense == 'min' else opt.maximize(bv)
        assert opt.check() == z3.sat
        assert opt.model().eval(bv).as_long() == expected
        assert str(handle.lower()) == str(handle.upper()) == str(expected)
    comparisons = []
    root = Path(__file__).resolve().parents[1] / 'runs/rx032_public'
    for index in range(20):
        folder = root / f'{index:02d}'
        verified = []
        _, _, _, x, key, _, _ = load_problem(index)
        for form in ['fp', 'bvfp', 'bv']:
            path = folder / (form + '.verify.json')
            if not path.exists():
                continue
            record = json.loads(path.read_text())
            if record.get('status') != 'verified':
                continue
            if form == 'fp':
                v = z3.FP('__cross_value', x.sort())
                equal = z3.parse_smt2_string('(assert (= __cross_value ' + record['value'] + '))',
                                            decls={'__cross_value': v})[0]
                value = equal.arg(1)
            else:
                ordinal = int(record['value'])
                nbits = key.size()
                raw = ordinal ^ (1 << (nbits - 1)) if ordinal >> (nbits - 1) else ~ordinal & ((1 << nbits) - 1)
                value = z3.simplify(z3.fpBVToFP(z3.BitVecVal(raw, nbits), x.sort()))
            if verified:
                assert z3.is_true(z3.simplify(z3.fpEQ(value, verified[0][1])))
            verified.append((form, value))
        if len(verified) > 1:
            comparisons.append(dict(index=index, forms=[f for f, _ in verified], numerically_equal=True))
    result = dict(z3=z3.get_version_string(), non_nan_values=len(values),
                  ordered_pairs_checked=checked,
                  cross_form_verified_comparisons=comparisons,
                  semantics='Key matches IEEE numerical order except the explicit refinement -0 < +0; Z3 BV optimization is unsigned.',
                  limitations='This exhaustive small-format check is a regression check, not a proof of solver correctness.')
    path = root / 'encoding-check.json'
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
