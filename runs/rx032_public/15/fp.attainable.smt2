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
 (let ((?x35 (fp (_ bv0 1) (_ bv0 8) (_ bv0 23))))
(= a ?x35)))
(check-sat)
