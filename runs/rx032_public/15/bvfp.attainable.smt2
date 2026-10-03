; benchmark generated from python API
(set-info :status unknown)
(declare-fun a () (_ FloatingPoint 8 24))
(assert
 (or (fp.isNormal a) (fp.isZero a) (fp.isSubnormal a)))
(assert
 (fp.isPositive a))
(assert
 (not (fp.lt (fp.mul roundNearestTiesToEven a ((_ to_fp 8 24) (_ bv1061158912 32))) a)))
(assert
 (let ((?x23 (fp.to_ieee_bv a)))
(let ((?x27 (bvnot ?x23)))
(let ((?x24 ((_ extract 31 31) ?x23)))
(let (($x26 (= ?x24 (_ bv1 1))))
(let ((?x30 (ite $x26 ?x27 (bvxor ?x23 (_ bv2147483648 32)))))
(let (($x33 (not (fp.isNaN a))))
(and $x33 (= (_ bv2147483648 32) ?x30)))))))))
(check-sat)
